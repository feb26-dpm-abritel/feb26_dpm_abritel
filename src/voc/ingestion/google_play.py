"""Scraper Google Play (API non officielle `google-play-scraper`)."""

from __future__ import annotations

import logging
import random
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from google_play_scraper import Sort, reviews

from voc.config import GOOGLE_PLAY_MAX_PAGES, MAX_REVIEWS_PER_SOURCE, scrape_start_date
from voc.ingestion._http import to_paris_date

LOG = logging.getLogger(__name__)

_BATCH_SIZE = 200


def fetch(app_id: str, brand_code: str, *, since: date | None = None) -> pd.DataFrame:
    """Pagine du plus récent au plus ancien jusqu'à `since` ou la limite de pages."""
    since = since or scrape_start_date()
    rows: list[dict] = []
    token = None

    for page in range(GOOGLE_PLAY_MAX_PAGES):
        try:
            batch, token = reviews(
                app_id,
                lang="fr",
                country="fr",
                sort=Sort.NEWEST,
                count=_BATCH_SIZE,
                continuation_token=token,
            )
        except Exception as e:  # noqa: BLE001
            LOG.warning("google_play[%s] page %s erreur: %s", brand_code, page, e)
            break

        if not batch:
            break

        oldest_in_batch: date | None = None
        for r in batch:
            dt_raw = r["at"]
            if isinstance(dt_raw, datetime) and dt_raw.tzinfo is None:
                dt_utc = dt_raw.astimezone(ZoneInfo("UTC"))
            else:
                dt_utc = dt_raw
            day = to_paris_date(dt_utc)
            oldest_in_batch = (
                day if oldest_in_batch is None or day < oldest_in_batch else oldest_in_batch
            )
            if day < since:
                continue
            rows.append(
                {
                    "source_review_id": r.get("reviewId") or f"gp_{r['at'].isoformat()}",
                    "brand_code": brand_code,
                    "source_code": "google_play",
                    "review_date": dt_utc.isoformat(),
                    "rating": r["score"],
                    "text": (r.get("content") or "").strip() or "(sans commentaire)",
                    "author_handle": r.get("userName") or None,
                    "app_version": r.get("reviewCreatedVersion") or None,
                    "vendor_response": r.get("replyContent") or None,
                    "vendor_response_at": r["repliedAt"].isoformat()
                    if r.get("repliedAt")
                    else None,
                }
            )

        if MAX_REVIEWS_PER_SOURCE and len(rows) >= MAX_REVIEWS_PER_SOURCE:
            break
        if oldest_in_batch and oldest_in_batch < since:
            break
        if token is None:
            break
        time.sleep(0.4 + random.uniform(0, 0.2))

    if MAX_REVIEWS_PER_SOURCE:
        rows = rows[:MAX_REVIEWS_PER_SOURCE]
    LOG.info("google_play[%s] : %d avis collectés", brand_code, len(rows))
    return pd.DataFrame(rows)
