{{ config(materialized='table', alias='dm_finance_litiges') }}

-- Avis financiers ou parcours paiement : flag SLA réponse hôte/marque.

SELECT
    r.id                          AS review_id,
    r.date_id,
    b.label                       AS brand_label,
    src.label                     AS source_label,
    cat.code                      AS category_code,
    cat.label                     AS category_label,
    sev.label                     AS severity_label,
    r.rating,
    r.vendor_responded,
    r.response_latency_days,
    SUBSTR(r.text, 1, 280)        AS review_excerpt,
    r.review_date
FROM {{ ref('fact_reviews') }} r
JOIN {{ ref('fact_classifications') }} fc ON fc.review_id = r.id
JOIN {{ ref('dim_category') }} cat        ON cat.id = fc.category_id
JOIN {{ ref('dim_severity') }} sev        ON sev.id = fc.severity_id
JOIN {{ ref('dim_brand') }}    b          ON b.id   = r.brand_id
JOIN {{ ref('dim_source') }}   src        ON src.id = r.source_id
WHERE r.is_exploitable = TRUE
  AND cat.code IN ('transparence_financiere', 'parcours_paiement')
