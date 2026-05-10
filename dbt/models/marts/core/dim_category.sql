{{ config(materialized='table', alias='dim_category') }}
SELECT id, code, label, description, is_critical FROM {{ ref('seed_categories') }}
