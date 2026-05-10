"""Catégorisation LLM via Ollama — utilisée en fallback des avis 'non_classe'.

L'heuristique mots-clés tourne en premier (rapide, déterministe). Cette étape
ne traite que les lignes que l'heuristique n'a pas pu classer, pour limiter
le nombre d'appels au LLM.

Le contrat de sortie est strict : le LLM doit répondre par UN code parmi la liste
des catégories valides. Tout autre output est traité comme un échec et la ligne
reste 'non_classe'.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2
import requests

from voc.config import (
    OLLAMA_BASE_URL,
    OLLAMA_ENABLED,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    VOC_PG_DSN,
)

LOG = logging.getLogger(__name__)

# Doit rester aligné avec dbt/seeds/seed_categories.csv.
VALID_CATEGORIES: tuple[str, ...] = (
    "app_fr",
    "transparence_financiere",
    "fiabilite_reservations",
    "service_client",
    "qualite_annonces",
    "parcours_paiement",
    "communication_hote",
    "non_classe",
)

_CATEGORY_DESCRIPTIONS = {
    "app_fr": "Localisation / langue / devise (français manquant, dollars, traduction)",
    "transparence_financiere": "Frais cachés, caution, remboursement, arnaque, opacité tarifaire",
    "fiabilite_reservations": "Annulation, indisponibilité de dernière minute, calendrier, double résa",
    "service_client": "SAV injoignable, support absent, aucune réponse, hotline, chatbot",
    "qualite_annonces": "Photos / description trompeuse, annonce non conforme",
    "parcours_paiement": "Échec de paiement, double prélèvement, 3D Secure, carte refusée",
    "communication_hote": "Hôte/propriétaire qui ne répond pas, messagerie, échange",
    "non_classe": "Aucune catégorie ne s'applique clairement",
}

_PROMPT_TEMPLATE = """Tu es un classifieur d'avis utilisateurs (apps Abritel/Airbnb/Booking).

Réponds UNIQUEMENT par un objet JSON strict de cette forme :
{{"category": "<code>", "confidence": <float entre 0 et 1>}}

Les codes valides et leur signification :
{categories}

Avis à classer :
\"\"\"{text}\"\"\"

JSON :"""


def _build_prompt(text: str) -> str:
    cats = "\n".join(f"- {code}: {desc}" for code, desc in _CATEGORY_DESCRIPTIONS.items())
    return _PROMPT_TEMPLATE.format(categories=cats, text=text.strip().replace('"""', '"'))


def _parse_response(raw: str) -> tuple[str, float] | None:
    """Extrait (category, confidence) du texte renvoyé par Ollama.

    Le modèle peut renvoyer du JSON pur ou du texte autour. On tente d'isoler
    le premier objet JSON contenant 'category'.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Tentative : trouver un fragment {...} dans la réponse
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None

    cat = data.get("category") if isinstance(data, dict) else None
    if cat not in VALID_CATEGORIES:
        return None
    conf = data.get("confidence", 0.5)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    return cat, conf


def classify_with_ollama(
    text: str, *, base_url: str | None = None, model: str | None = None, timeout: int | None = None
) -> tuple[str, float] | None:
    """Appelle Ollama et retourne (category, confidence) ou None en cas d'échec.

    None ⇒ caller garde la valeur heuristique (pas de surcharge).
    """
    if not text or not text.strip():
        return None
    url = (base_url or OLLAMA_BASE_URL).rstrip("/") + "/api/generate"
    payload: dict[str, Any] = {
        "model": model or OLLAMA_MODEL,
        "prompt": _build_prompt(text),
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 80},
        "format": "json",
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout or OLLAMA_TIMEOUT_SECONDS)
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        LOG.warning("Ollama call failed: %s", exc)
        return None

    raw = body.get("response", "") if isinstance(body, dict) else ""
    return _parse_response(raw)


def refine_unclassified(*, dsn: str | None = None) -> dict[str, int]:
    """Met à jour raw.raw_reviews : pour chaque ligne is_exploitable=true et
    category_code='non_classe', appelle Ollama et écrase la catégorie si succès.

    Marque category_source='llm' quand l'override est appliqué, sinon 'heuristic'.
    Retourne {'candidates': N, 'updated': K, 'skipped': S}.
    """
    if not OLLAMA_ENABLED:
        LOG.info("OLLAMA_ENABLED=false — étape LLM ignorée.")
        return {"candidates": 0, "updated": 0, "skipped": 0}

    conn = psycopg2.connect(dsn or VOC_PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Idempotent : ajoute la colonne si elle n'existe pas (cf. loader qui la crée déjà).
            cur.execute(
                "ALTER TABLE raw.raw_reviews "
                "ADD COLUMN IF NOT EXISTS category_source VARCHAR DEFAULT 'heuristic';"
            )
            cur.execute(
                "SELECT source_review_id, source_code, text "
                "FROM raw.raw_reviews "
                "WHERE is_exploitable = TRUE AND category_code = 'non_classe';"
            )
            rows = cur.fetchall()

        candidates = len(rows)
        if not candidates:
            LOG.info("Aucun avis 'non_classe' à reclasser.")
            conn.commit()
            return {"candidates": 0, "updated": 0, "skipped": 0}

        LOG.info("LLM classify: %d candidats", candidates)
        updated = 0
        skipped = 0
        with conn.cursor() as cur:
            for srid, scode, text in rows:
                result = classify_with_ollama(text)
                if result is None or result[0] == "non_classe":
                    skipped += 1
                    continue
                new_cat, _conf = result
                cur.execute(
                    "UPDATE raw.raw_reviews "
                    "SET category_code = %s, category_source = 'llm' "
                    "WHERE source_review_id = %s AND source_code = %s;",
                    (new_cat, srid, scode),
                )
                updated += 1
        conn.commit()
    finally:
        conn.close()

    LOG.info("LLM classify done — updated=%d skipped=%d", updated, skipped)
    return {"candidates": candidates, "updated": updated, "skipped": skipped}
