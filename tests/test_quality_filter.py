"""Tests du filtre qualité (heuristiques déterministes)."""

from voc.refinement.quality_filter import classify


def test_empty_text_is_not_exploitable():
    assert classify(None) == (False, "vide")
    assert classify("") == (False, "vide")
    assert classify("   ") == (False, "vide")


def test_placeholder_is_not_exploitable():
    assert classify("(sans commentaire)") == (False, "placeholder")
    assert classify("N/A") == (False, "placeholder")


def test_too_short_is_not_exploitable():
    assert classify("ko")[0] is False
    assert classify("oui")[0] is False  # 1 mot < MIN_WORDS


def test_emoji_only_is_not_exploitable():
    # Assez d'emojis pour dépasser le seuil de longueur, sinon `trop_court` matche en premier.
    ok, reason = classify("👍👍👍👍👍👍 !!!")
    assert ok is False
    assert reason == "non_textuel"


def test_generic_is_not_exploitable():
    ok, reason = classify("super")
    # 1 seul mot → trop_court (avant generique)
    assert ok is False
    ok, reason = classify("rien à dire")
    assert ok is False
    assert reason == "generique_non_actionnable"


def test_real_review_is_exploitable():
    text = "L'application bug constamment, impossible de finaliser ma réservation."
    assert classify(text) == (True, None)


def test_owner_review_is_exploitable():
    text = "En tant que propriétaire, je n'arrive plus à publier mon annonce."
    assert classify(text) == (True, None)
