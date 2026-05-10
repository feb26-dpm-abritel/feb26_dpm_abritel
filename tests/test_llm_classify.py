"""Tests du classifieur LLM (Ollama) — HTTP + connexion Postgres mockés."""

from unittest.mock import MagicMock, patch

from voc.refinement.llm_classify import (
    VALID_CATEGORIES,
    _build_prompt,
    _parse_response,
    classify_with_ollama,
)


def test_valid_categories_aligned_with_seeds():
    # Sécurité : tout code utilisé doit exister dans la seed dbt seed_categories.csv.
    expected = {
        "app_fr",
        "transparence_financiere",
        "fiabilite_reservations",
        "service_client",
        "qualite_annonces",
        "parcours_paiement",
        "communication_hote",
        "non_classe",
    }
    assert set(VALID_CATEGORIES) == expected


def test_build_prompt_contains_text_and_categories():
    p = _build_prompt("L'appli plante au paiement")
    assert "L'appli plante au paiement" in p
    assert "transparence_financiere" in p
    assert "JSON" in p


def test_parse_response_pure_json():
    raw = '{"category": "service_client", "confidence": 0.85}'
    assert _parse_response(raw) == ("service_client", 0.85)


def test_parse_response_embedded_json():
    raw = 'voici la réponse: {"category": "app_fr", "confidence": 0.6} fin'
    assert _parse_response(raw) == ("app_fr", 0.6)


def test_parse_response_invalid_category_returns_none():
    raw = '{"category": "inexistant", "confidence": 0.9}'
    assert _parse_response(raw) is None


def test_parse_response_garbage_returns_none():
    assert _parse_response("pas de json ici") is None
    assert _parse_response("{not json}") is None


def test_parse_response_clamps_confidence():
    out = _parse_response('{"category": "app_fr", "confidence": 5.0}')
    assert out == ("app_fr", 1.0)
    out = _parse_response('{"category": "app_fr", "confidence": -1}')
    assert out == ("app_fr", 0.0)
    out = _parse_response('{"category": "app_fr"}')  # confidence absent → défaut 0.5
    assert out == ("app_fr", 0.5)


@patch("voc.refinement.llm_classify.requests.post")
def test_classify_with_ollama_success(mock_post):
    mock_post.return_value.raise_for_status = lambda: None
    mock_post.return_value.json = lambda: {
        "response": '{"category": "fiabilite_reservations", "confidence": 0.7}'
    }
    out = classify_with_ollama("Réservation annulée à la dernière minute")
    assert out == ("fiabilite_reservations", 0.7)


@patch("voc.refinement.llm_classify.requests.post")
def test_classify_with_ollama_http_error_returns_none(mock_post):
    import requests

    mock_post.side_effect = requests.ConnectionError("ollama down")
    assert classify_with_ollama("test") is None


def test_classify_empty_text_returns_none():
    assert classify_with_ollama("") is None
    assert classify_with_ollama("   ") is None


@patch("voc.refinement.llm_classify.requests.post")
def test_classify_with_ollama_invalid_response(mock_post):
    mock_post.return_value.raise_for_status = lambda: None
    mock_post.return_value.json = lambda: {"response": "je sais pas"}
    assert classify_with_ollama("texte") is None


# --- Tests de l'orchestration refine_unclassified avec psycopg2 mocké ---


def _build_mock_conn(candidate_rows: list[tuple[str, str, str]]) -> tuple:
    """Construit un faux psycopg2.connect() qui retourne `candidate_rows`
    sur le premier SELECT et accepte les UPDATE suivants. Retourne (conn, cur)."""
    cur = MagicMock()
    cur.fetchall.return_value = candidate_rows
    # Le with-block sur conn.cursor() doit retourner le même curseur à chaque fois.
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("voc.refinement.llm_classify.classify_with_ollama")
@patch("voc.refinement.llm_classify.psycopg2.connect")
def test_refine_unclassified_updates_only_candidates(mock_connect, mock_clf):
    from voc.refinement.llm_classify import refine_unclassified

    rows = [("r1", "trustpilot", "Texte non classé par heuristique")]
    conn, cur = _build_mock_conn(rows)
    mock_connect.return_value = conn
    mock_clf.return_value = ("communication_hote", 0.9)

    stats = refine_unclassified(dsn="postgresql://test")

    assert stats == {"candidates": 1, "updated": 1, "skipped": 0}
    # Vérifie qu'un UPDATE a été émis avec la nouvelle catégorie + 'llm'.
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE raw.raw_reviews" in c.args[0]]
    assert len(update_calls) == 1
    sql, params = update_calls[0].args
    assert params == ("communication_hote", "r1", "trustpilot")
    conn.commit.assert_called()


@patch("voc.refinement.llm_classify.classify_with_ollama")
@patch("voc.refinement.llm_classify.psycopg2.connect")
def test_refine_unclassified_skips_when_llm_fails(mock_connect, mock_clf):
    from voc.refinement.llm_classify import refine_unclassified

    rows = [("r1", "trustpilot", "Texte ambigu")]
    conn, cur = _build_mock_conn(rows)
    mock_connect.return_value = conn
    mock_clf.return_value = None  # Ollama injoignable

    stats = refine_unclassified(dsn="postgresql://test")

    assert stats == {"candidates": 1, "updated": 0, "skipped": 1}
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE raw.raw_reviews" in c.args[0]]
    assert len(update_calls) == 0  # Pas d'override
    conn.commit.assert_called()


@patch("voc.refinement.llm_classify.classify_with_ollama")
@patch("voc.refinement.llm_classify.psycopg2.connect")
def test_refine_unclassified_no_candidates(mock_connect, mock_clf):
    from voc.refinement.llm_classify import refine_unclassified

    conn, _cur = _build_mock_conn([])  # aucun avis non_classe
    mock_connect.return_value = conn

    stats = refine_unclassified(dsn="postgresql://test")
    assert stats == {"candidates": 0, "updated": 0, "skipped": 0}
    mock_clf.assert_not_called()
