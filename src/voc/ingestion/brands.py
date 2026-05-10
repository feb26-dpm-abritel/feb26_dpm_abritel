"""Configuration multi-marques : Abritel, Airbnb, Booking."""

from __future__ import annotations

from typing import NamedTuple


class Brand(NamedTuple):
    """Une marque à scraper sur les 3 sources publiques."""

    code: str  # identifiant interne (utilisé en clé)
    label: str  # nom affichable
    google_play_id: str
    app_store_id: str
    trustpilot_url: str


BRANDS: list[Brand] = [
    Brand(
        code="abritel",
        label="Abritel",
        google_play_id="com.vacationrentals.homeaway",
        app_store_id="642441300",
        trustpilot_url="https://fr.trustpilot.com/review/abritel.fr",
    ),
    Brand(
        code="airbnb",
        label="Airbnb",
        google_play_id="com.airbnb.android",
        app_store_id="401626263",
        trustpilot_url="https://fr.trustpilot.com/review/airbnb.fr",
    ),
    Brand(
        code="booking",
        label="Booking",
        google_play_id="com.booking",
        app_store_id="367003839",
        trustpilot_url="https://fr.trustpilot.com/review/www.booking.com",
    ),
]
