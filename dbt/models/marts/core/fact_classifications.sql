{{ config(materialized='table', alias='fact_classifications') }}

WITH r AS (
    SELECT
        f.id          AS review_id,
        b.category_id,
        b.severity_id,
        b.severity_rating_score,
        b.severity_text_score,
        b.category_source,
        b.classified_at
    FROM {{ ref('fact_reviews') }} f
    JOIN {{ ref('int_reviews_classified') }} b
      ON b.source_review_id = f.source_review_id
     AND b.source_id        = f.source_id
)

SELECT
    ROW_NUMBER() OVER (ORDER BY review_id) AS id,
    review_id,
    category_id,
    severity_id,
    severity_rating_score,
    severity_text_score,
    1.0::DOUBLE PRECISION                            AS confidence,
    COALESCE(category_source, 'heuristic')::VARCHAR AS method,
    classified_at
FROM r
