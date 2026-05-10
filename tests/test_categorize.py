"""Tests de la catégorisation par mots-clés (codes alignés sur dbt seeds)."""

from voc.refinement.categorize import (
    classify_category,
    classify_persona,
    classify_severity,
)


def test_categorize_financial():
    assert (
        classify_category("J'ai été prélevé deux fois, aucun remboursement")
        == "transparence_financiere"
    )


def test_categorize_cancellation():
    assert (
        classify_category("Réservation annulée 3 jours avant le départ, indisponible")
        == "fiabilite_reservations"
    )


def test_categorize_language():
    assert classify_category("Tout est affiché en dollars sur un site français") == "app_fr"


def test_categorize_service_client():
    assert (
        classify_category("SAV injoignable, aucune réponse depuis 2 semaines") == "service_client"
    )


def test_categorize_unknown_falls_back():
    assert classify_category("ras") == "non_classe"


def test_negation_does_not_trigger_financial():
    # "pas une arnaque" ne doit pas déclencher transparence_financiere
    cat = classify_category("Ce n'est pas une arnaque, j'ai vraiment été content")
    assert cat != "transparence_financiere"


def test_severity_high_on_keyword():
    sev, _, score_text = classify_severity("C'est une arnaque honteuse", 5, "non_classe")
    assert sev == "high"
    assert score_text > 0


def test_severity_high_on_rating_1():
    sev, score_rating, _ = classify_severity("rien à signaler", 1, "non_classe")
    assert sev == "high"
    assert score_rating == 1.0


def test_severity_high_on_rating_2_critical_category():
    sev, _, _ = classify_severity("paiement bloqué", 2, "transparence_financiere")
    assert sev == "high"


def test_severity_low_on_rating_5():
    sev, score_rating, _ = classify_severity("super appli", 5, "non_classe")
    assert sev == "low"
    assert score_rating == 0.0


def test_persona_owner():
    assert classify_persona("Je suis propriétaire et je gère mes annonces") == "proprietaire"


def test_persona_default_locataire():
    assert classify_persona("Je n'ai pas pu réserver mon appartement") == "locataire"
