"""Détection d'anomalies : pic d'avis critiques sur les 7 derniers jours par catégorie.

Compare le volume d'avis high-severity de la dernière semaine au volume moyen
des 4 semaines précédentes pour chaque (marque × catégorie). Écrit `data/alerts.csv`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
import psycopg2

from voc.config import ALERTS_PATH, VOC_PG_DSN

LOG = logging.getLogger(__name__)

# Postgres ne permet pas de réutiliser un alias d'agrégat dans HAVING comme DuckDB,
# d'où la duplication des MAX/AVG dans la clause HAVING.
_SQL = """
WITH weekly AS (
    SELECT
        b.label                                   AS brand,
        c.label                                   AS category,
        date_trunc('week', r.review_date)::DATE   AS week_start,
        COUNT(*) FILTER (WHERE s.code = 'high')   AS n_high,
        COUNT(*)                                  AS n_total
    FROM marts.fact_reviews r
    JOIN marts.fact_classifications fc ON fc.review_id = r.id
    JOIN marts.dim_severity s          ON s.id  = fc.severity_id
    JOIN marts.dim_brand    b          ON b.id  = r.brand_id
    JOIN marts.dim_category c          ON c.id  = fc.category_id
    WHERE r.is_exploitable = TRUE
    GROUP BY 1, 2, 3
),
last_5w AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY brand, category ORDER BY week_start DESC) AS rn
    FROM weekly
)
SELECT
    brand,
    category,
    MAX(CASE WHEN rn = 1 THEN week_start END) AS current_week,
    MAX(CASE WHEN rn = 1 THEN n_high END)     AS current_high,
    AVG(CASE WHEN rn BETWEEN 2 AND 5 THEN n_high END) AS baseline_avg_high
FROM last_5w
WHERE rn <= 5
GROUP BY brand, category
HAVING MAX(CASE WHEN rn = 1 THEN n_high END) IS NOT NULL
   AND AVG(CASE WHEN rn BETWEEN 2 AND 5 THEN n_high END) IS NOT NULL
   AND AVG(CASE WHEN rn BETWEEN 2 AND 5 THEN n_high END) > 0
   AND MAX(CASE WHEN rn = 1 THEN n_high END) >= 5
   AND MAX(CASE WHEN rn = 1 THEN n_high END)
       >= 2 * AVG(CASE WHEN rn BETWEEN 2 AND 5 THEN n_high END);
"""


def detect(*, dsn: str | None = None) -> int:
    """Calcule les alertes et écrit alerts.csv (overwrite). Retourne le nombre d'alertes."""
    conn = psycopg2.connect(dsn or VOC_PG_DSN)
    try:
        df = pd.read_sql_query(_SQL, conn)
    finally:
        conn.close()

    if df.empty:
        LOG.info("Aucune alerte spike détectée.")
        # On écrit quand même un CSV vide avec en-têtes pour suivi / import BI.
        pd.DataFrame(
            columns=[
                "alert_id",
                "detected_at",
                "brand",
                "category",
                "current_week",
                "current_high",
                "baseline_avg_high",
                "ratio",
            ]
        ).to_csv(ALERTS_PATH, index=False)
        return 0

    df["ratio"] = df["current_high"] / df["baseline_avg_high"]
    df["detected_at"] = datetime.now(UTC).isoformat()
    df["alert_id"] = [f"ALERT-{i + 1:04d}" for i in range(len(df))]
    df = df[
        [
            "alert_id",
            "detected_at",
            "brand",
            "category",
            "current_week",
            "current_high",
            "baseline_avg_high",
            "ratio",
        ]
    ]
    df.to_csv(ALERTS_PATH, index=False)
    LOG.info("Alerts écrites : %s (%d alertes)", ALERTS_PATH, len(df))
    return len(df)
