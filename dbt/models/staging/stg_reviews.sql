{{ config(materialized='view') }}

-- Vue de staging : nettoyage léger + déduplication sur clé naturelle.
-- La clé naturelle est (source_code, source_review_id) : un même avis publié
-- sur deux runs successifs ne génère qu'une ligne.

WITH src AS (
    SELECT * FROM {{ source('raw', 'raw_reviews') }}
),

ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_code, source_review_id
            ORDER BY collected_at DESC
        ) AS rn
    FROM src
)

SELECT
    source_review_id,
    source_code,
    brand_code,
    review_date,
    CAST(rating AS INTEGER)            AS rating,
    text,
    author_handle,
    app_version,
    vendor_response,
    vendor_response_at,
    CASE
        WHEN vendor_response_at IS NOT NULL
        THEN (vendor_response_at::DATE - review_date::DATE)
    END                                AS response_latency_days,
    vendor_response IS NOT NULL        AS vendor_responded,
    is_exploitable,
    exclusion_reason,
    category_code,
    category_source,
    persona_code,
    severity_code,
    severity_rating_score,
    severity_text_score,
    classified_at,
    collected_at
FROM ranked
WHERE rn = 1
