"""Configuration centrale (chemins, fenêtre temporelle, limites de scraping, intégrations)."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_FR = ZoneInfo("Europe/Paris")

DATA_DIR = Path(os.getenv("VOC_DATA_DIR", "/opt/airflow/data"))
BRONZE_DIR = DATA_DIR / "bronze"
ALERTS_PATH = DATA_DIR / "alerts.csv"
TICKETS_PATH = DATA_DIR / "tickets.csv"

# --- Data warehouse Postgres (DB séparée de la metastore Airflow) ---
VOC_PG_HOST = os.getenv("VOC_PG_HOST", "postgres")
VOC_PG_PORT = int(os.getenv("VOC_PG_PORT", "5432"))
VOC_PG_USER = os.getenv("VOC_PG_USER", "postgres")
VOC_PG_PASSWORD = os.getenv("VOC_PG_PASSWORD", "postgres")
VOC_PG_DBNAME = os.getenv("VOC_PG_DBNAME", "voc")
VOC_PG_DSN = os.getenv(
    "VOC_PG_DSN",
    f"postgresql://{VOC_PG_USER}:{VOC_PG_PASSWORD}@{VOC_PG_HOST}:{VOC_PG_PORT}/{VOC_PG_DBNAME}",
)


# Fenêtre de scraping MVP : N derniers jours (assez pour démontrer, rapide à scrape).
SCRAPE_WINDOW_DAYS = int(os.getenv("VOC_SCRAPE_WINDOW_DAYS", "30"))

# Plafonds par source pour borner le temps de scraping en démo.
GOOGLE_PLAY_MAX_PAGES = int(os.getenv("VOC_GP_MAX_PAGES", "3"))
APP_STORE_MAX_PAGES = int(os.getenv("VOC_AS_MAX_PAGES", "3"))
TRUSTPILOT_MAX_PAGES_PER_STAR = int(os.getenv("VOC_TP_MAX_PAGES", "2"))

# Cap dur sur le nb d'avis collectés par (source × marque). 0 = désactivé.
MAX_REVIEWS_PER_SOURCE = int(os.getenv("VOC_MAX_REVIEWS_PER_SOURCE", "100"))

# --- Ollama (catégorisation LLM des avis 'non_classe') ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() in {"1", "true", "yes"}

# --- Notion (ticketing) — vide = désactivé (fallback CSV uniquement) ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()

# --- Slack (notifications) — vide = désactivé ---
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()


def scrape_start_date() -> date:
    """Date de début incluse pour le scraping (aujourd'hui − fenêtre)."""
    from datetime import datetime

    today = datetime.now(TZ_FR).date()
    return today - timedelta(days=SCRAPE_WINDOW_DAYS)


def ensure_dirs() -> None:
    """Crée les répertoires de données s'ils n'existent pas."""
    for p in (DATA_DIR, BRONZE_DIR):
        p.mkdir(parents=True, exist_ok=True)


def notion_enabled() -> bool:
    return bool(NOTION_TOKEN and NOTION_DATABASE_ID)


def slack_enabled() -> bool:
    return bool(SLACK_WEBHOOK_URL)
