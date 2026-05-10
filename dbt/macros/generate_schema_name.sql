{# Override par défaut de dbt qui préfixe les schémas par <target_schema>_<custom_schema>.
   Ici les configs `+schema: marts` doivent produire réellement `marts.*` (PostgreSQL),
   sans préfixe indésirable — pour matcher les requêtes Python (`voc.activation.*`). #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
