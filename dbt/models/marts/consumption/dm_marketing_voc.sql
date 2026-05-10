{{ config(materialized='table', alias='dm_marketing_voc') }}

-- Voice of Customer agrégé : (date × marque × catégorie × persona) →
-- volume, note moyenne, % gravité haute, ratio vs concurrents.

WITH base AS (
    SELECT
        r.date_id,
        r.brand_id,
        fc.category_id,
        r.persona_id,
        r.rating,
        sev.code AS severity_code
    FROM {{ ref('fact_reviews') }} r
    JOIN {{ ref('fact_classifications') }} fc ON fc.review_id = r.id
    JOIN {{ ref('dim_severity') }} sev        ON sev.id = fc.severity_id
    WHERE r.is_exploitable = TRUE
),

agg AS (
    SELECT
        date_id,
        brand_id,
        category_id,
        persona_id,
        COUNT(*)                                                                AS review_count,
        AVG(rating)::DOUBLE PRECISION                                                     AS avg_rating,
        (SUM(CASE WHEN severity_code = 'high' THEN 1 ELSE 0 END) * 1.0
         / NULLIF(COUNT(*), 0))                                                  AS share_high_severity
    FROM base
    GROUP BY date_id, brand_id, category_id, persona_id
),

abritel_baseline AS (
    SELECT category_id, AVG(review_count) AS abritel_volume
    FROM agg a JOIN {{ ref('dim_brand') }} b ON b.id = a.brand_id AND b.code = 'abritel'
    GROUP BY category_id
)

SELECT
    a.date_id,
    b.label  AS brand_label,
    c.label  AS category_label,
    p.label  AS persona_label,
    a.review_count,
    ROUND(a.avg_rating::NUMERIC, 2)         AS avg_rating,
    ROUND(a.share_high_severity::NUMERIC, 3) AS share_high_severity,
    CASE WHEN ab.abritel_volume IS NULL OR ab.abritel_volume = 0
         THEN NULL
         ELSE ROUND((a.review_count * 1.0 / ab.abritel_volume)::NUMERIC, 2)
    END AS ratio_vs_abritel
FROM agg a
JOIN {{ ref('dim_brand') }}    b ON b.id = a.brand_id
JOIN {{ ref('dim_category') }} c ON c.id = a.category_id
JOIN {{ ref('dim_persona') }}  p ON p.id = a.persona_id
LEFT JOIN abritel_baseline ab ON ab.category_id = a.category_id
