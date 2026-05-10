{{ config(materialized='table', alias='dm_sav_tickets') }}

-- Vue SAV : un ticket = une ligne, avec contexte avis + délai d'ouverture.

SELECT
    t.id                                                        AS ticket_id,
    t.review_id,
    cat.label                                                   AS category_label,
    sev.label                                                   AS severity_label,
    st.label                                                    AS status_label,
    t.assignee,
    EXTRACT(DAY FROM (current_timestamp - t.created_at))::INTEGER AS days_open,
    SUBSTR(r.text, 1, 280)                                      AS review_excerpt,
    r.vendor_responded,
    b.label                                                     AS brand_label,
    src.label                                                   AS source_label,
    t.created_at
FROM {{ ref('fact_tickets') }} t
JOIN {{ ref('fact_reviews') }}          r   ON r.id   = t.review_id
JOIN {{ ref('fact_classifications') }}  fc  ON fc.review_id = r.id
JOIN {{ ref('dim_category') }}          cat ON cat.id = fc.category_id
JOIN {{ ref('dim_severity') }}          sev ON sev.id = t.severity_id
JOIN {{ ref('dim_ticket_status') }}     st  ON st.id  = t.status_id
JOIN {{ ref('dim_brand') }}             b   ON b.id   = r.brand_id
JOIN {{ ref('dim_source') }}            src ON src.id = r.source_id
