"""Scraper Trustpilot via le payload `__NEXT_DATA__`.

Trustpilot bloque les requêtes HTTP non-navigateur via AWS WAF (403). On utilise
**Playwright** (Chromium headless) pour rendre la page, attendre `networkidle` et
récupérer le HTML — le payload `__NEXT_DATA__` est extrait classiquement.

Fallback `requests` conservé pour les environnements sans Playwright (CI tests
mockés ou dev local sans browser installé). Sur la stack Docker, Chromium est
installé dans l'image Airflow (cf. `airflow/Dockerfile`) et Playwright est utilisé
par défaut.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import date

import pandas as pd
from bs4 import BeautifulSoup

from voc.config import MAX_REVIEWS_PER_SOURCE, TRUSTPILOT_MAX_PAGES_PER_STAR, scrape_start_date
from voc.ingestion._http import http_get, join_title_body, parse_dt_utc, to_paris_date

LOG = logging.getLogger(__name__)


def _playwright_available() -> bool:
    """True si Playwright + Chromium sont installés et lancables."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _fetch_html_pw(pw_page, url: str) -> str | None:
    """Charge une page Trustpilot via Playwright (contourne AWS WAF)."""
    try:
        pw_page.goto(url, wait_until="networkidle", timeout=30_000)
        return pw_page.content()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Playwright — échec %s: %s", url, exc)
        return None


def _parse_reviews(html: str, since: date, brand_code: str) -> tuple[list[dict], bool]:
    """Parse le HTML d'une page Trustpilot. Retourne (rows, all_out_of_window)."""
    rows: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return rows, True
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return rows, True

    avis_list = data.get("props", {}).get("pageProps", {}).get("reviews", []) or []
    if not avis_list:
        return rows, True

    all_out = True
    for a in avis_list:
        dt = parse_dt_utc(a.get("dates", {}).get("publishedDate", ""))
        if dt is None:
            continue
        day = to_paris_date(dt)
        if day >= since:
            all_out = False
        if day < since:
            continue
        rid = a.get("id") or f"tp_{dt.isoformat()}"
        rows.append(
            {
                "source_review_id": str(rid),
                "brand_code": brand_code,
                "source_code": "trustpilot",
                "review_date": dt.isoformat(),
                "rating": a.get("rating", 0),
                "text": join_title_body(a.get("title", ""), a.get("text", "")),
                "author_handle": (a.get("consumer") or {}).get("displayName"),
                "app_version": None,
                "vendor_response": (a.get("reply") or {}).get("message"),
                "vendor_response_at": (a.get("reply") or {}).get("publishedDate"),
            }
        )
    return rows, all_out


def _fetch_filter_pw(
    pw_page, base_url: str, params: str, since: date, brand_code: str
) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, TRUSTPILOT_MAX_PAGES_PER_STAR + 1):
        sep = "&" if params else "?"
        url = f"{base_url}?{params}{sep}page={page}" if params else f"{base_url}?page={page}"
        html = _fetch_html_pw(pw_page, url)
        if html is None:
            break
        batch, all_out = _parse_reviews(html, since, brand_code)
        rows.extend(batch)
        if all_out:
            break
        time.sleep(0.5 + random.uniform(0, 0.3))
    return rows


def _fetch_filter_requests(base_url: str, params: str, since: date, brand_code: str) -> list[dict]:
    """Fallback HTTP — souvent bloqué par AWS WAF, mais utile en CI/dev local."""
    rows: list[dict] = []
    for page in range(1, TRUSTPILOT_MAX_PAGES_PER_STAR + 1):
        sep = "&" if params else "?"
        url = f"{base_url}?{params}{sep}page={page}" if params else f"{base_url}?page={page}"
        html = http_get(url, attempts=2, timeout_s=15)
        if html is None:
            break
        batch, all_out = _parse_reviews(html, since, brand_code)
        rows.extend(batch)
        if all_out:
            break
        time.sleep(0.5 + random.uniform(0, 0.3))
    return rows


def fetch(trustpilot_url: str, brand_code: str, *, since: date | None = None) -> pd.DataFrame:
    """Pagine Trustpilot par filtre étoiles (1→5)."""
    since = since or scrape_start_date()
    rows: list[dict] = []
    use_pw = _playwright_available()

    if use_pw:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="fr-FR",
                )
                pw_page = context.new_page()
                for stars in range(1, 6):
                    if MAX_REVIEWS_PER_SOURCE and len(rows) >= MAX_REVIEWS_PER_SOURCE:
                        break
                    if stars > 1:
                        time.sleep(1.5 + random.uniform(0, 0.8))
                    batch = _fetch_filter_pw(
                        pw_page, trustpilot_url, f"stars={stars}", since, brand_code
                    )
                    rows.extend(batch)
            finally:
                browser.close()
    else:
        LOG.info("Playwright indisponible — fallback HTTP requests (peut être bloqué par WAF)")
        for stars in range(1, 6):
            if MAX_REVIEWS_PER_SOURCE and len(rows) >= MAX_REVIEWS_PER_SOURCE:
                break
            if stars > 1:
                time.sleep(1 + random.uniform(0, 0.5))
            rows.extend(_fetch_filter_requests(trustpilot_url, f"stars={stars}", since, brand_code))

    if MAX_REVIEWS_PER_SOURCE:
        rows = rows[:MAX_REVIEWS_PER_SOURCE]
    LOG.info("trustpilot[%s] : %d avis collectés (playwright=%s)", brand_code, len(rows), use_pw)
    return pd.DataFrame(rows)
