# Image Airflow custom : ajoute dbt-postgres + dépendances ETL VoC + Playwright Chromium.
FROM apache/airflow:2.10.3-python3.12

USER airflow

COPY airflow/requirements.txt /tmp/requirements.txt
# L'image officielle utilise un venv : pas de --user (et pas de PIP_USER côté env).
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Installer le binaire Chromium pour Playwright (utilisé par le scraper Trustpilot
# pour contourner le challenge AWS WAF).
# Étape 1 (root) : installer les libs système (X11, fontconfig, etc.) via apt-get.
USER root
RUN playwright install-deps chromium

# Étape 2 (airflow) : télécharger le binaire Chromium dans ~/.cache/ms-playwright
# de l'utilisateur airflow (pour qu'il y ait accès au runtime).
USER airflow
RUN playwright install chromium

# Le package src/voc est monté en volume et ajouté au PYTHONPATH
# via la variable d'env PYTHONPATH=/opt/airflow/src dans docker-compose.yml.
