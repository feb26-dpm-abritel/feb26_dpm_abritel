{{ config(materialized='table', alias='dim_source') }}
SELECT id, code, label, type, url FROM {{ ref('seed_sources') }}
