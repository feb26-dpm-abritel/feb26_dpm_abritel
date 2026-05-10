{{ config(materialized='table', alias='dim_persona') }}
SELECT id, code, label FROM {{ ref('seed_personas') }}
