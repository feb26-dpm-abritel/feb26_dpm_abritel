"""Génération de tickets pour les avis critiques.

Règle MVP : tout avis exploitable, gravité 'high' et catégorie marquée
`is_critical=true` génère un ticket statut `open` routé vers l'équipe owner.

Sorties :
- `data/tickets.csv` (audit local, overwrite à chaque run)
- Notion database (idempotent par `review_id`) si NOTION_TOKEN/DATABASE_ID configurés
"""

from __future__ import annotations

import logging

import pandas as pd
import psycopg2

from voc.activation import notion
from voc.config import TICKETS_PATH, VOC_PG_DSN, notion_enabled

LOG = logging.getLogger(__name__)

_SQL = """
WITH critical AS (
    SELECT
        r.id                          AS review_id,
        r.review_date                 AS occurred_at,
        b.label                       AS brand,
        s.label                       AS source,
        c.label                       AS category,
        sev.label                     AS severity,
        r.rating,
        SUBSTR(r.text, 1, 280)        AS excerpt,
        c.code                        AS category_code,
        sev.code                      AS severity_code
    FROM marts.fact_reviews r
    JOIN marts.fact_classifications fc ON fc.review_id = r.id
    JOIN marts.dim_brand    b   ON b.id   = r.brand_id
    JOIN marts.dim_source   s   ON s.id   = r.source_id
    JOIN marts.dim_category c   ON c.id   = fc.category_id
    JOIN marts.dim_severity sev ON sev.id = fc.severity_id
    WHERE r.is_exploitable = TRUE
      AND sev.code = 'high'
      AND c.is_critical = TRUE
)
SELECT
    'TICK-' || LPAD(ROW_NUMBER() OVER (ORDER BY occurred_at DESC)::TEXT, 4, '0') AS ticket_id,
    review_id,
    occurred_at,
    brand,
    source,
    category,
    severity,
    rating,
    'open'                                                    AS status,
    CASE category_code
        WHEN 'transparence_financiere' THEN 'finance'
        WHEN 'parcours_paiement'       THEN 'finance'
        WHEN 'service_client'          THEN 'sav'
        WHEN 'fiabilite_reservations'  THEN 'sav'
        WHEN 'app_fr'                  THEN 'produit'
        WHEN 'qualite_annonces'        THEN 'trust_safety'
        WHEN 'communication_hote'      THEN 'sav'
        ELSE 'sav'
    END                                                       AS owner_team,
    excerpt
FROM critical;
"""


def generate(*, dsn: str | None = None) -> dict[str, int]:
    """Génère les tickets en CSV + Notion (si configuré).

    Retourne {'csv': N, 'notion_created': K, 'notion_skipped': S}.
    """
    conn = psycopg2.connect(dsn or VOC_PG_DSN)
    try:
        df = pd.read_sql_query(_SQL, conn)
    finally:
        conn.close()

    df.to_csv(TICKETS_PATH, index=False)
    LOG.info("Tickets CSV écrits : %s (%d tickets)", TICKETS_PATH, len(df))

    stats = {"csv": len(df), "notion_created": 0, "notion_skipped": 0}
    if notion_enabled() and not df.empty:
        result = notion.push_tickets(df)
        stats["notion_created"] = result.get("created", 0)
        stats["notion_skipped"] = result.get("skipped", 0)
    return stats
