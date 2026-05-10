"""Notifications Slack via incoming webhook (1 message par run).

Skip silencieux si SLACK_WEBHOOK_URL absent ou si le run n'a rien produit.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from voc.config import SLACK_WEBHOOK_URL, slack_enabled

LOG = logging.getLogger(__name__)


def _format_message(ticket_stats: dict[str, int], n_alerts: int) -> str:
    created = ticket_stats.get("notion_created", 0)
    csv_n = ticket_stats.get("csv", 0)
    parts = [":bell: *Voice of Customer — run terminé*"]
    if csv_n:
        parts.append(f"• *{csv_n}* tickets critiques détectés ce run")
    if created:
        parts.append(f"• *{created}* nouveaux tickets poussés vers Notion")
    if n_alerts:
        parts.append(f"• :rotating_light: *{n_alerts}* alertes spike (7j vs baseline 4 sem)")
    if len(parts) == 1:
        parts.append("• Aucun ticket critique ni alerte ce run.")
    return "\n".join(parts)


def notify(
    ticket_stats: dict[str, int] | None = None, n_alerts: int = 0, *, webhook_url: str | None = None
) -> bool:
    """Envoie la notification. Retourne True si POST envoyé, False sinon (skip)."""
    url = webhook_url or SLACK_WEBHOOK_URL
    if not url:
        LOG.info("Slack désactivé (SLACK_WEBHOOK_URL vide).")
        return False
    ticket_stats = ticket_stats or {}
    # Skip si rien d'intéressant à dire
    if not (ticket_stats.get("csv", 0) or ticket_stats.get("notion_created", 0) or n_alerts):
        LOG.info("Slack: rien à signaler — skip.")
        return False

    payload: dict[str, Any] = {"text": _format_message(ticket_stats, n_alerts)}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        LOG.info("Slack notif envoyée.")
        return True
    except requests.RequestException as exc:
        LOG.warning("Slack notif failed: %s", exc)
        return False


__all__ = ["notify", "slack_enabled"]
