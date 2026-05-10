{{ config(materialized='table', alias='dim_severity') }}
SELECT id, code, label, rank FROM {{ ref('seed_severities') }}
