{{ config(materialized='table', alias='dim_ticket_status') }}
SELECT id, code, label, is_terminal FROM {{ ref('seed_ticket_statuses') }}
