"""Scraper App Store iOS (RSS JSON officiel Apple)."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from voc.config import APP_STORE_MAX_PAGES, MAX_REVIEWS_PER_SOURCE, scrape_start_date
from voc.ingestion._http import http_get, join_title_body, parse_dt_utc, to_paris_date

LOG = logging.getLogger(__name__)


def fetch(app_id: str, brand_code: str, *, since: date | None = None) -> pd.DataFrame:
    """Pagine le RSS Apple (max ~50 avis/page)."""
    since = since or scrape_start_date()
    rows: list[dict] = []

    for page in range(1, APP_STORE_MAX_PAGES + 1):
        if MAX_REVIEWS_PER_SOURCE and len(rows) >= MAX_REVIEWS_PER_SOURCE:
            break
        url = (
            f"https://itunes.apple.com/fr/rss/customerreviews"
            f"/page={page}/id={app_id}/sortBy=mostRecent/json"
        )
        payload = http_get(url, parse_json=True, attempts=3)
        if payload is None:
            continue

        entries = payload.get("feed", {}).get("entry", []) or []
        if not entries:
            break

        for entry in entries:
            rating = entry.get("im:rating", {}).get("label")
            if rating is None:
                continue
            dt = parse_dt_utc(entry.get("updated", {}).get("label", ""))
            if dt is None:
                continue
            day = to_paris_date(dt)
            if day < since:
                continue
            rid = entry.get("id", {}).get("label") or f"as_{dt.isoformat()}"
            rows.append(
                {
                    "source_review_id": rid,
                    "brand_code": brand_code,
                    "source_code": "app_store",
                    "review_date": dt.isoformat(),
                    "rating": int(rating),
                    "text": join_title_body(
                        entry.get("title", {}).get("label", ""),
                        entry.get("content", {}).get("label", ""),
                    ),
                    "author_handle": entry.get("author", {}).get("name", {}).get("label"),
                    "app_version": entry.get("im:version", {}).get("label"),
                    "vendor_response": None,
                    "vendor_response_at": None,
                }
            )

    if MAX_REVIEWS_PER_SOURCE:
        rows = rows[:MAX_REVIEWS_PER_SOURCE]
    LOG.info("app_store[%s] : %d avis collectés", brand_code, len(rows))
    return pd.DataFrame(rows)
