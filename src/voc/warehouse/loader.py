"""Charge bronze + raffinement → Postgres raw.raw_reviews (source pour dbt)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from voc.config import BRONZE_DIR, VOC_PG_DSN, ensure_dirs
from voc.refinement import categorize, quality_filter

LOG = logging.getLogger(__name__)


def _read_latest_bronze() -> pd.DataFrame:
    files = sorted(BRONZE_DIR.glob("raw_reviews_*.parquet"))
    if not files:
        raise FileNotFoundError(f"Aucun fichier bronze dans {BRONZE_DIR}")
    latest = files[-1]
    LOG.info("Lecture bronze : %s", latest)
    return pd.read_parquet(latest)


def _refine(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    qf = df["text"].apply(quality_filter.classify)
    df["is_exploitable"] = qf.apply(lambda x: x[0])
    df["exclusion_reason"] = qf.apply(lambda x: x[1])

    df["category_code"] = df["text"].apply(categorize.classify_category)
    df["persona_code"] = df["text"].apply(categorize.classify_persona)

    sev = [
        categorize.classify_severity(t, r, c)
        for t, r, c in zip(df["text"], df["rating"], df["category_code"], strict=True)
    ]
    df["severity_code"] = [s[0] for s in sev]
    df["severity_rating_score"] = [s[1] for s in sev]
    df["severity_text_score"] = [s[2] for s in sev]

    # Source de la catégorie : initialement 'heuristic' partout, sera surchargée
    # à 'llm' par voc.refinement.llm_classify pour les lignes reclassées par Ollama.
    df["category_source"] = "heuristic"

    df["classified_at"] = datetime.now(UTC).isoformat()
    return df


# Colonnes de raw.raw_reviews dans l'ordre de création — le contrat lu par dbt.
_RAW_COLUMNS = [
    "source_review_id",
    "source_code",
    "brand_code",
    "review_date",
    "rating",
    "text",
    "author_handle",
    "app_version",
    "vendor_response",
    "vendor_response_at",
    "collected_at",
    "is_exploitable",
    "exclusion_reason",
    "category_code",
    "category_source",
    "persona_code",
    "severity_code",
    "severity_rating_score",
    "severity_text_score",
    "classified_at",
]

_CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS raw;
-- CASCADE : les views dbt (staging.stg_reviews, etc.) dépendent de cette table.
-- Elles seront recréées par `dbt run` en aval, pas de souci.
DROP TABLE IF EXISTS raw.raw_reviews CASCADE;
CREATE TABLE raw.raw_reviews (
    source_review_id      VARCHAR,
    source_code           VARCHAR,
    brand_code            VARCHAR,
    review_date           TIMESTAMPTZ,
    rating                INTEGER,
    text                  TEXT,
    author_handle         VARCHAR,
    app_version           VARCHAR,
    vendor_response       TEXT,
    vendor_response_at    TIMESTAMPTZ,
    collected_at          TIMESTAMPTZ,
    is_exploitable        BOOLEAN,
    exclusion_reason      VARCHAR,
    category_code         VARCHAR,
    category_source       VARCHAR DEFAULT 'heuristic',
    persona_code          VARCHAR,
    severity_code         VARCHAR,
    severity_rating_score DOUBLE PRECISION,
    severity_text_score   DOUBLE PRECISION,
    classified_at         TIMESTAMPTZ
);
"""


def _df_to_tuples(df: pd.DataFrame) -> list[tuple]:
    """Convertit un DataFrame ordonné en liste de tuples Python compatibles psycopg2."""
    # NaN / NaT → None pour que psycopg2 envoie NULL.
    sanitized = df.where(df.notna(), None)
    return [tuple(row) for row in sanitized.itertuples(index=False, name=None)]


def load(bronze_path: str | None = None, *, dsn: str | None = None) -> int:
    """Charge le dernier bronze + raffinement en Postgres. Retourne nb lignes écrites."""
    ensure_dirs()
    df = pd.read_parquet(Path(bronze_path)) if bronze_path else _read_latest_bronze()
    if df.empty:
        LOG.warning("Bronze vide — aucune insertion en Postgres.")
        return 0

    df = _refine(df)
    df = df.reindex(columns=_RAW_COLUMNS)

    cols_sql = ", ".join(_RAW_COLUMNS)
    insert_sql = f"INSERT INTO raw.raw_reviews ({cols_sql}) VALUES %s"

    conn = psycopg2.connect(dsn or VOC_PG_DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                # 1. (Re)crée le schéma + table.
                cur.execute(_CREATE_TABLE_SQL)
                # 2. Bulk insert.
                execute_values(cur, insert_sql, _df_to_tuples(df), page_size=500)
                # 3. Comptage.
                cur.execute("SELECT COUNT(*) FROM raw.raw_reviews;")
                n = cur.fetchone()[0]
    finally:
        conn.close()

    LOG.info("Postgres raw.raw_reviews chargée : %d lignes", n)
    return int(n)
