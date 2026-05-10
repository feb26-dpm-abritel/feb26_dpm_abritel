{{ config(materialized='view') }}

-- Joint stg_reviews avec les seeds dimensionnelles pour résoudre les FK.

WITH r AS (SELECT * FROM {{ ref('stg_reviews') }}),
     b AS (SELECT id AS brand_id,    code FROM {{ ref('seed_brands') }}),
     s AS (SELECT id AS source_id,   code FROM {{ ref('seed_sources') }}),
     c AS (SELECT id AS category_id, code FROM {{ ref('seed_categories') }}),
     p AS (SELECT id AS persona_id,  code FROM {{ ref('seed_personas') }}),
     v AS (SELECT id AS severity_id, code FROM {{ ref('seed_severities') }})

SELECT
    r.*,
    b.brand_id,
    s.source_id,
    c.category_id,
    p.persona_id,
    v.severity_id
FROM r
LEFT JOIN b ON b.code = r.brand_code
LEFT JOIN s ON s.code = r.source_code
LEFT JOIN c ON c.code = r.category_code
LEFT JOIN p ON p.code = r.persona_code
LEFT JOIN v ON v.code = r.severity_code
