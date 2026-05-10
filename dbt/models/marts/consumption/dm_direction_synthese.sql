{{ config(materialized='table', alias='dm_direction_synthese') }}

-- Synthèse exécutive : 1 ligne par (date × marque). 5 KPI suivis dans le PVB :
-- 1. total_reviews        : volume avis exploitables
-- 2. avg_rating           : note moyenne /5
-- 3. share_critical       : % gravité haute
-- 4. ticket_resolution_rate : tickets résolus / tickets ouverts (snapshot MVP : 0%)
-- 5. gap_vs_competitors   : note Abritel - moyenne (Airbnb, Booking) (négatif = Abritel sous-performe)

WITH per_day_brand AS (
    SELECT
        r.date_id,
        r.brand_id,
        b.code  AS brand_code,
        b.label AS brand_label,
        COUNT(*)                                                AS total_reviews,
        AVG(r.rating)::DOUBLE PRECISION                                   AS avg_rating,
        SUM(CASE WHEN sev.code = 'high' THEN 1 ELSE 0 END) * 1.0
            / NULLIF(COUNT(*), 0)                               AS share_critical
    FROM {{ ref('fact_reviews') }} r
    JOIN {{ ref('fact_classifications') }} fc ON fc.review_id = r.id
    JOIN {{ ref('dim_severity') }} sev        ON sev.id = fc.severity_id
    JOIN {{ ref('dim_brand') }}    b          ON b.id   = r.brand_id
    WHERE r.is_exploitable = TRUE
    GROUP BY r.date_id, r.brand_id, b.code, b.label
),

competitor_avg AS (
    SELECT date_id, AVG(avg_rating) AS competitor_avg_rating
    FROM per_day_brand
    WHERE brand_code IN ('airbnb', 'booking')
    GROUP BY date_id
),

ticket_stats AS (
    SELECT
        date_id,
        COUNT(*)                                               AS tickets_open,
        SUM(CASE WHEN st.is_terminal THEN 1 ELSE 0 END) * 1.0
            / NULLIF(COUNT(*), 0)                              AS resolution_rate
    FROM {{ ref('fact_tickets') }} t
    JOIN {{ ref('fact_reviews') }} r        ON r.id = t.review_id
    JOIN {{ ref('dim_ticket_status') }} st  ON st.id = t.status_id
    GROUP BY date_id
)

SELECT
    p.date_id,
    p.brand_label,
    p.total_reviews,
    ROUND(p.avg_rating::NUMERIC, 2)             AS avg_rating,
    ROUND(p.share_critical::NUMERIC, 3)         AS share_critical,
    COALESCE(ts.resolution_rate, 0)    AS ticket_resolution_rate,
    CASE WHEN p.brand_code = 'abritel' AND ca.competitor_avg_rating IS NOT NULL
         THEN ROUND((p.avg_rating - ca.competitor_avg_rating)::NUMERIC, 2)
         ELSE NULL
    END                                AS gap_vs_competitors
FROM per_day_brand p
LEFT JOIN competitor_avg ca ON ca.date_id = p.date_id
LEFT JOIN ticket_stats   ts ON ts.date_id = p.date_id
