{{ config(materialized='table', alias='dim_date') }}

-- Génère un calendrier 2024-2026 (large pour couvrir toute fenêtre de scraping plausible).
WITH dates AS (
    SELECT generate_series(
        DATE '2024-01-01',
        DATE '2026-12-31',
        INTERVAL '1 day'
    )::DATE AS d
)
SELECT
    CAST(TO_CHAR(d, 'YYYYMMDD') AS INTEGER) AS date_id,
    d                                       AS date,
    EXTRACT(year      FROM d)::INTEGER      AS year,
    EXTRACT(quarter   FROM d)::INTEGER      AS quarter,
    EXTRACT(month     FROM d)::INTEGER      AS month,
    EXTRACT(week      FROM d)::INTEGER      AS week,
    EXTRACT(dow       FROM d)::INTEGER      AS day_of_week,
    EXTRACT(dow       FROM d) IN (0, 6)     AS is_weekend
FROM dates
