"""Tests du notifier Slack (webhook mocké, format message, skip silencieux)."""

from unittest.mock import patch

from voc.activation import slack


def test_format_message_full():
    msg = slack._format_message({"csv": 5, "notion_created": 3}, n_alerts=2)
    assert "5" in msg and "tickets" in msg
    assert "3" in msg and "Notion" in msg
    assert "2" in msg and "alertes" in msg


def test_format_message_empty():
    msg = slack._format_message({"csv": 0, "notion_created": 0}, n_alerts=0)
    assert "Aucun ticket" in msg


@patch("voc.activation.slack.requests.post")
def test_notify_skipped_when_no_webhook(mock_post):
    sent = slack.notify({"csv": 1}, n_alerts=0, webhook_url="")
    assert sent is False
    mock_post.assert_not_called()


@patch("voc.activation.slack.requests.post")
def test_notify_skipped_when_nothing_to_say(mock_post):
    sent = slack.notify(
        {"csv": 0, "notion_created": 0},
        n_alerts=0,
        webhook_url="https://hooks.slack.com/services/X",
    )
    assert sent is False
    mock_post.assert_not_called()


@patch("voc.activation.slack.requests.post")
def test_notify_posts_when_content(mock_post):
    mock_post.return_value.raise_for_status = lambda: None
    sent = slack.notify(
        {"csv": 4, "notion_created": 2},
        n_alerts=1,
        webhook_url="https://hooks.slack.com/services/X",
    )
    assert sent is True
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert "text" in payload
    assert "4" in payload["text"]


@patch("voc.activation.slack.requests.post")
def test_notify_swallows_http_error(mock_post):
    import requests as r

    mock_post.side_effect = r.ConnectionError("slack down")
    sent = slack.notify({"csv": 4}, n_alerts=0, webhook_url="https://hooks.slack.com/services/X")
    assert sent is False
