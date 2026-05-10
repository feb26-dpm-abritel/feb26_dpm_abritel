"""Client Notion pour pousser les tickets dans une database.

Idempotent : avant de créer un ticket, on filtre la DB Notion par `review_id`.
Si une page existe déjà, on skip (les runs daily ne dupliquent pas).

Schéma Notion attendu (à créer côté UI) — propriétés :
    - ticket_id      (Title)            — ex: TICK-0001
    - review_id      (Number)           — clé d'idempotence
    - brand          (Select)           — Abritel / Airbnb / Booking
    - source         (Select)           — Trustpilot / Google Play / App Store
    - category       (Select)           — libellé catégorie
    - severity       (Select)           — high / medium / low
    - rating         (Number)
    - status         (Select)           — open / in_progress / done (défaut: open)
    - owner_team     (Select)           — sav / finance / produit / trust_safety
    - occurred_at    (Date)
    - excerpt        (Rich text)        — premiers 280 caractères de l'avis
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests

from voc.config import NOTION_DATABASE_ID, NOTION_TOKEN

LOG = logging.getLogger(__name__)

_NOTION_VERSION = "2022-06-28"
_API_BASE = "https://api.notion.com/v1"


def _headers(token: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token or NOTION_TOKEN}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _existing_review_ids(database_id: str, token: str | None = None) -> set[int]:
    """Retourne l'ensemble des review_id déjà présents dans la DB Notion (paginé)."""
    url = f"{_API_BASE}/databases/{database_id}/query"
    cursor: str | None = None
    seen: set[int] = set()
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=_headers(token), json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            rid_prop = props.get("review_id", {})
            rid = rid_prop.get("number") if rid_prop.get("type") == "number" else None
            if rid is not None:
                seen.add(int(rid))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return seen


def _build_page_properties(row: pd.Series) -> dict[str, Any]:
    return {
        "ticket_id": {"title": [{"text": {"content": str(row["ticket_id"])}}]},
        "review_id": {"number": int(row["review_id"])},
        "brand": {"select": {"name": str(row["brand"])}},
        "source": {"select": {"name": str(row["source"])}},
        "category": {"select": {"name": str(row["category"])}},
        "severity": {"select": {"name": str(row["severity"])}},
        "rating": {"number": int(row["rating"]) if pd.notna(row["rating"]) else None},
        "status": {"select": {"name": str(row.get("status", "open"))}},
        "owner_team": {"select": {"name": str(row["owner_team"])}},
        "occurred_at": {"date": {"start": pd.Timestamp(row["occurred_at"]).date().isoformat()}},
        "excerpt": {"rich_text": [{"text": {"content": str(row["excerpt"])[:1900]}}]},
    }


def push_tickets(
    df: pd.DataFrame, *, database_id: str | None = None, token: str | None = None
) -> dict[str, int]:
    """Pousse les tickets manquants dans la DB Notion. Retourne {created, skipped}."""
    db = database_id or NOTION_DATABASE_ID
    tk = token or NOTION_TOKEN
    if not (db and tk):
        LOG.info("Notion désactivé (NOTION_TOKEN/NOTION_DATABASE_ID absents).")
        return {"created": 0, "skipped": len(df)}
    if df.empty:
        return {"created": 0, "skipped": 0}

    existing = _existing_review_ids(db, tk)
    LOG.info("Notion: %d tickets déjà présents.", len(existing))

    created = 0
    skipped = 0
    url = f"{_API_BASE}/pages"
    for _, row in df.iterrows():
        try:
            rid = int(row["review_id"])
        except (TypeError, ValueError):
            skipped += 1
            continue
        if rid in existing:
            skipped += 1
            continue
        payload = {
            "parent": {"database_id": db},
            "properties": _build_page_properties(row),
        }
        try:
            resp = requests.post(url, headers=_headers(tk), json=payload, timeout=30)
            resp.raise_for_status()
            created += 1
        except requests.RequestException as exc:
            LOG.warning("Notion create failed (review_id=%s): %s", rid, exc)
            skipped += 1
    LOG.info("Notion push: created=%d skipped=%d", created, skipped)
    return {"created": created, "skipped": skipped}
