"""Helpers HTTP partagés (session, retries, backoff)."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

LOG = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = random.choice(_USER_AGENTS)
    return s


def _backoff(attempt: int, err: requests.RequestException) -> float:
    resp = getattr(err, "response", None)
    if resp is not None and resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 120)
            except ValueError:
                pass
    return min(2**attempt + random.uniform(0, 0.5), 10)


def http_get(
    url: str,
    *,
    session: requests.Session | None = None,
    parse_json: bool = False,
    timeout_s: int = 15,
    attempts: int = 4,
):
    """GET avec retries + backoff. Retourne dict (json) / str (text) / None."""
    s = session or make_session()
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            headers = {"User-Agent": random.choice(_USER_AGENTS)}
            r = s.get(url, timeout=timeout_s, headers=headers)
            r.raise_for_status()
            return r.json() if parse_json else r.text
        except requests.RequestException as e:
            last_err = e
            time.sleep(_backoff(i, e))
    LOG.warning("HTTP — échec après %s tentatives: %s", attempts, last_err)
    return None


def parse_dt_utc(value: str) -> datetime | None:
    if not value:
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def to_paris_date(dt: datetime) -> pd.Timestamp:
    ts = pd.Timestamp(dt)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(ZoneInfo("Europe/Paris")).date()


def join_title_body(title: str, body: str) -> str:
    title = (title or "").strip()
    body = (body or "").strip()
    text = f"{title}. {body}".strip(". ") if title else body
    return text or "(sans commentaire)"
