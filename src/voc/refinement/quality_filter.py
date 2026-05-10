"""Filtre qualité : marque les avis inexploitables.

Stratégie heuristique (rapide, déterministe, sans dépendance externe) :
- texte trop court (< 5 caractères ou < 2 mots de contenu)
- uniquement des emojis / ponctuation
- placeholder type « (sans commentaire) »
- générique non actionnable (« ok », « bien », « rien à dire »)

Sortie : `is_exploitable` (bool), `exclusion_reason` (str ou None).
"""

from __future__ import annotations

import re
import unicodedata

# Caractères considérés comme non-textuels (emojis, ponctuation)
_NON_TEXT_RE = re.compile(r"[\W\d_]+", flags=re.UNICODE)
_PLACEHOLDER = {"(sans commentaire)", "sans commentaire", "n/a", "na", "..."}
_GENERIC_NONACTIONABLE = {
    "ok",
    "bien",
    "bof",
    "nul",
    "rien à dire",
    "rien a dire",
    "cool",
    "super",
    "top",
    "génial",
    "genial",
    "parfait",
    "good",
    "great",
    "fine",
    "nothing",
}

_MIN_CHARS = 5
_MIN_WORDS = 2


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def classify(text: str | None) -> tuple[bool, str | None]:
    """Retourne (is_exploitable, exclusion_reason)."""
    if not isinstance(text, str) or not text.strip():
        return False, "vide"

    raw = text.strip()
    if raw.lower() in _PLACEHOLDER:
        return False, "placeholder"

    if len(raw) < _MIN_CHARS:
        return False, "trop_court"

    # Si retirer tous les caractères non-alphabétiques laisse < 3 caractères, c'est emojis/ponct.
    letters_only = _NON_TEXT_RE.sub("", raw)
    if len(letters_only) < 3:
        return False, "non_textuel"

    norm = _normalize(raw)
    word_count = len(re.findall(r"\b\w+\b", norm))
    if word_count < _MIN_WORDS:
        return False, "trop_court"

    if norm in _GENERIC_NONACTIONABLE:
        return False, "generique_non_actionnable"

    return True, None
