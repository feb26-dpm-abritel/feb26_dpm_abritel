"""Catégorisation par mots-clés + sévérité + persona.

Les codes catégorie / sévérité / persona correspondent aux seeds dbt
(cf. dbt/seeds/seed_categories.csv, seed_severities.csv, seed_personas.csv).
"""

from __future__ import annotations

import re
import unicodedata

# --- Normalisation ---


def _normalize(text: str) -> str:
    t = text.lower()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# --- Catégories (codes alignés avec dbt/seeds/seed_categories.csv) ---

_NEGATION_RE = re.compile(
    r"(?:pas|plus|jamais|aucun|aucune|ni|not|no)\s+(?:du\s+tout\s+|d'|une?\s+|de\s+|a\s+)?"
    r"(?:arnaque|escroc|escroquerie|fraude|scam|voleur|bug|beug"
    r"|complique|complexe|confus|confusing|difficile|difficult|complicated)"
)

_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "app_fr",
        (
            "francais",
            "anglais",
            "allemand",
            "langue",
            "traduction",
            "traduire",
            "dollars",
            "devise",
            "$",
            "currency",
            "vrbo",
            "indicatif",
        ),
    ),
    (
        "fiabilite_reservations",
        (
            "annule",
            "annulee",
            "annulation",
            "annuler",
            "indisponible",
            "derniere minute",
            "non garanti",
            "non confirme",
            "pas disponible",
            "calendrier",
            "disponibilite",
            "check-in",
            "check-out",
            "double reservation",
        ),
    ),
    (
        "transparence_financiere",
        (
            "caution",
            "remboursement",
            "rembourse",
            "refund",
            "paiement",
            "payment",
            "frais",
            "facture",
            "prix",
            "tarif",
            "argent",
            "carte bancaire",
            "prelevement",
            "depot",
            "arnaque",
            "scam",
            "escroquerie",
            "voleur",
            "commission",
            "surfacturation",
            "supplement",
            "acompte",
        ),
    ),
    (
        "parcours_paiement",
        (
            "paiement refuse",
            "carte refusee",
            "transaction echouee",
            "double prelevement",
            "preauthorisation",
            "preautorisation",
            "3d secure",
            "stripe",
            "paypal",
        ),
    ),
    (
        "service_client",
        (
            "service client",
            "customer service",
            "sav",
            "support",
            "assistance",
            "conseiller",
            "joindre",
            "injoignable",
            "aucune reponse",
            "reclamation",
            "interlocuteur",
            "tchat",
            "hotline",
            "chatbot",
        ),
    ),
    (
        "qualite_annonces",
        (
            "annonce",
            "photo",
            "description",
            "non conforme",
            "trompeuse",
            "fausse annonce",
            "annonce indisponible",
        ),
    ),
    (
        "communication_hote",
        (
            "hote",
            "proprietaire",
            "reponse hote",
            "hote ne repond",
            "communication",
            "message",
            "contact hote",
            "contact proprietaire",
        ),
    ),
]

_VALID_CATEGORIES = {code for code, _ in _CATEGORY_KEYWORDS} | {"non_classe"}


def classify_category(text: str) -> str:
    """Retourne le code catégorie le plus pertinent (ou 'non_classe')."""
    if not isinstance(text, str) or not text.strip():
        return "non_classe"
    t = _NEGATION_RE.sub("", _normalize(text))
    scored = [(code, sum(1 for kw in kws if kw in t)) for code, kws in _CATEGORY_KEYWORDS]
    scored.sort(key=lambda x: x[1], reverse=True)
    if scored and scored[0][1] > 0:
        return scored[0][0]
    return "non_classe"


# --- Sévérité ---

_SEVERITY_HIGH_KEYWORDS = (
    "arnaque",
    "escroquerie",
    "escroc",
    "fraude",
    "scandale",
    "honte",
    "honteux",
    "tribunal",
    "justice",
    "avocat",
    "plainte",
    "illegal",
    "voleur",
    "inadmissible",
    "inacceptable",
    "danger",
    "dangereux",
    "insalubre",
)


def classify_severity(text: str, rating: int, category_code: str) -> tuple[str, float, float]:
    """Retourne (severity_code, score_rating, score_text).

    - severity_code ∈ {low, medium, high}
    - score_rating ∈ [0,1] : dérivé de la note (1→1.0, 5→0.0)
    - score_text   ∈ [0,1] : présence de mots-clés gravité
    """
    rating = int(rating) if rating else 0
    score_rating = max(0.0, min(1.0, (5 - rating) / 4)) if rating else 0.0

    t = _normalize(text or "")
    n_kw = sum(1 for kw in _SEVERITY_HIGH_KEYWORDS if kw in t)
    score_text = min(1.0, n_kw / 2)  # 2 mots-clés ou plus → 1.0

    if score_text >= 0.5:
        return "high", score_rating, score_text
    if rating == 1:
        return "high", score_rating, score_text
    if rating == 2 and category_code in {
        "transparence_financiere",
        "fiabilite_reservations",
        "parcours_paiement",
    }:
        return "high", score_rating, score_text
    if rating == 2:
        return "medium", score_rating, score_text
    return "low", score_rating, score_text


# --- Persona ---

_OWNER_PATTERNS = (
    "je suis proprietaire",
    "je suis hote",
    "en tant qu'hote",
    "en tant que proprietaire",
    "mon annonce",
    "mes annonces",
    "mon bien",
    "mes biens",
    "mes voyageurs",
    "mes locataires",
    "espace proprietaire",
    "espace hote",
    "publier mon annonce",
    "publier une annonce",
    "gerer mes reservations",
)


def classify_persona(text: str) -> str:
    """Retourne le code persona ('locataire', 'proprietaire' ou 'indetermine')."""
    if not isinstance(text, str) or not text.strip():
        return "indetermine"
    t = _normalize(text)
    if any(p in t for p in _OWNER_PATTERNS):
        return "proprietaire"
    return "locataire"
