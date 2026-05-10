{{ config(materialized='table', alias='dim_brand') }}
SELECT id, code, label, is_focus FROM {{ ref('seed_brands') }}
