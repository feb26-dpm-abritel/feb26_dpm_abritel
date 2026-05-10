-- Crée une base de données dédiée aux données métier VoC, à côté de la base `airflow`
-- (qui contient uniquement les metadata Airflow). Exécuté automatiquement au premier
-- démarrage du conteneur Postgres via /docker-entrypoint-initdb.d.

CREATE DATABASE voc;
\connect voc;

-- Schémas correspondant aux étages dbt. Le loader Python crée 'raw' si besoin,
-- les autres sont créés par dbt à la première exécution.
CREATE SCHEMA IF NOT EXISTS raw;
