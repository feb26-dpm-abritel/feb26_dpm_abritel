{{ config(materialized='table', alias='fact_reviews') }}

WITH base AS (
    SELECT * FROM {{ ref('int_reviews_classified') }}
)

SELECT
    ROW_NUMBER() OVER (ORDER BY review_date, source_review_id) AS id,
    source_review_id,
    source_id,
    brand_id,
    CAST(TO_CHAR(review_date, 'YYYYMMDD') AS INTEGER) AS date_id,
    review_date,
    persona_id,
    rating,
    text,
    'fr'::VARCHAR                                    AS language,
    author_handle,
    app_version,
    vendor_responded,
    vendor_response_at,
    response_latency_days,
    is_exploitable,
    exclusion_reason,
    collected_at
FROM base
