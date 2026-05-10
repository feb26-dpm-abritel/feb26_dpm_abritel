{{ config(materialized='table', alias='fact_tickets') }}

-- Ticket auto pour avis exploitables, gravité haute, catégorie marquée critique.
-- Statut initial 'open'. Pas de suivi de résolution dans le MVP — la table est
-- recalculée à chaque run (snapshot du backlog ouvert).

WITH critical AS (
    SELECT
        f.id          AS review_id,
        f.collected_at,
        c.severity_id,
        c.category_id
    FROM {{ ref('fact_reviews') }} f
    JOIN {{ ref('fact_classifications') }} c ON c.review_id = f.id
    JOIN {{ ref('dim_severity') }} s          ON s.id = c.severity_id
    JOIN {{ ref('dim_category') }} cat        ON cat.id = c.category_id
    WHERE f.is_exploitable = TRUE
      AND s.code = 'high'
      AND cat.is_critical = TRUE
)

SELECT
    ROW_NUMBER() OVER (ORDER BY collected_at DESC) AS id,
    review_id,
    NULL::VARCHAR                                  AS external_ticket_id,
    1::INTEGER                                     AS status_id,  -- 'open'
    severity_id,
    'csv'::VARCHAR                                 AS channel,
    NULL::VARCHAR                                  AS assignee,
    collected_at                                   AS created_at,
    NULL::TIMESTAMP                                AS resolved_at,
    NULL::VARCHAR                                  AS resolution_notes
FROM critical
