"""Orchestre le scraping des 3 sources × N marques et écrit en bronze."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd

from voc.config import BRONZE_DIR, ensure_dirs
from voc.ingestion import app_store, google_play, trustpilot
from voc.ingestion.brands import BRANDS

LOG = logging.getLogger(__name__)


def run() -> str:
    """Scrape tout, fusionne, écrit data/bronze/raw_reviews_<runid>.parquet.

    Retourne le chemin du fichier écrit (utilisé en XCom Airflow).
    """
    ensure_dirs()
    frames: list[pd.DataFrame] = []
    for brand in BRANDS:
        LOG.info("=== %s ===", brand.label)
        frames.append(google_play.fetch(brand.google_play_id, brand.code))
        frames.append(app_store.fetch(brand.app_store_id, brand.code))
        frames.append(trustpilot.fetch(brand.trustpilot_url, brand.code))

    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if df.empty:
        LOG.warning("Aucun avis collecté — sortie vide.")
    else:
        df = df.drop_duplicates(subset=["source_code", "source_review_id"], keep="first")
        df["collected_at"] = datetime.now(UTC).isoformat()

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = BRONZE_DIR / f"raw_reviews_{run_id}.parquet"
    df.to_parquet(out_path, index=False)
    LOG.info("Bronze écrit: %s (%d lignes)", out_path, len(df))
    return str(out_path)
