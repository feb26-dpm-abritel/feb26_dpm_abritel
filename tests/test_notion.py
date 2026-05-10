"""Tests du client Notion (HTTP mocké, idempotence par review_id)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from voc.activation import notion


def _ticket_df():
    return pd.DataFrame(
        [
            {
                "ticket_id": "TICK-0001",
                "review_id": 42,
                "brand": "Abritel",
                "source": "Trustpilot",
                "category": "Service client",
                "severity": "high",
                "rating": 1,
                "owner_team": "sav",
                "occurred_at": pd.Timestamp("2026-04-15"),
                "excerpt": "SAV injoignable depuis 3 semaines, scandale.",
            },
            {
                "ticket_id": "TICK-0002",
                "review_id": 99,
                "brand": "Airbnb",
                "source": "App Store",
                "category": "Parcours paiement",
                "severity": "high",
                "rating": 2,
                "owner_team": "finance",
                "occurred_at": pd.Timestamp("2026-04-20"),
                "excerpt": "Double prélèvement non remboursé.",
            },
        ]
    )


def _mock_query_response(review_ids: list[int]) -> dict:
    return {
        "results": [
            {"properties": {"review_id": {"type": "number", "number": rid}}} for rid in review_ids
        ],
        "has_more": False,
        "next_cursor": None,
    }


@patch("voc.activation.notion.requests.post")
def test_push_skips_existing_review_ids(mock_post):
    df = _ticket_df()

    # 1er POST = query DB (review_id=42 existe déjà), 2e POST = create page (pour review_id=99)
    query_resp = MagicMock()
    query_resp.raise_for_status = lambda: None
    query_resp.json = lambda: _mock_query_response([42])

    create_resp = MagicMock()
    create_resp.raise_for_status = lambda: None
    create_resp.json = lambda: {"id": "page-id"}

    mock_post.side_effect = [query_resp, create_resp]

    stats = notion.push_tickets(df, database_id="dbid", token="tok")
    assert stats == {"created": 1, "skipped": 1}
    # 1 query + 1 create = 2 calls
    assert mock_post.call_count == 2


@patch("voc.activation.notion.requests.post")
def test_push_disabled_when_no_credentials(mock_post):
    df = _ticket_df()
    stats = notion.push_tickets(df, database_id="", token="")
    assert stats == {"created": 0, "skipped": len(df)}
    mock_post.assert_not_called()


@patch("voc.activation.notion.requests.post")
def test_push_handles_api_error_per_row(mock_post):
    import requests as r

    df = _ticket_df().head(1)

    query_resp = MagicMock()
    query_resp.raise_for_status = lambda: None
    query_resp.json = lambda: _mock_query_response([])

    err_resp = MagicMock()
    err_resp.raise_for_status = MagicMock(side_effect=r.HTTPError("400"))

    mock_post.side_effect = [query_resp, err_resp]
    stats = notion.push_tickets(df, database_id="dbid", token="tok")
    assert stats == {"created": 0, "skipped": 1}


def test_build_page_properties_shape():
    row = _ticket_df().iloc[0]
    props = notion._build_page_properties(row)
    assert props["ticket_id"]["title"][0]["text"]["content"] == "TICK-0001"
    assert props["review_id"]["number"] == 42
    assert props["brand"]["select"]["name"] == "Abritel"
    assert props["status"]["select"]["name"] == "open"
    assert props["occurred_at"]["date"]["start"] == "2026-04-15"
