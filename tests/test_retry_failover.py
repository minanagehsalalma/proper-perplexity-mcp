"""Tests for explicit fallback branches in run_query()."""

from unittest.mock import MagicMock, patch

from perplexity.server.app import run_query


def make_pool(
    sequence,
    *,
    fallback_enabled: bool = True,
    configured_clients=None,
) -> MagicMock:
    pool = MagicMock()
    if configured_clients is None:
        configured_clients = []

    pool.clients = {}
    for client_id, client in configured_clients:
        wrapper = MagicMock()
        wrapper.client = client
        pool.clients[client_id] = wrapper

    pool.get_client.side_effect = sequence
    pool.is_fallback_to_auto_enabled.return_value = fallback_enabled
    return pool


def make_client(*, own: bool = True) -> MagicMock:
    client = MagicMock()
    client.own = own
    client.copilot = float("inf")
    client.file_upload = float("inf")
    return client


@patch("perplexity.server.app.get_pool")
def test_falls_back_to_auto_mode_client_before_anonymous(mock_get_pool) -> None:
    auto_client = make_client()
    auto_client.search.return_value = {
        "answer": "Auto fallback answer",
        "text": [],
    }
    pool = make_pool(
        [(None, None), ("auto-client", auto_client)],
        configured_clients=[("auto-client", auto_client)],
    )
    mock_get_pool.return_value = pool

    result = run_query("test query", mode="pro")

    assert result["status"] == "ok"
    assert result["data"]["answer"] == "Auto fallback answer"
    assert result["data"]["fallback"] is True
    assert result["data"]["fallback_mode"] == "auto"
    assert result["data"]["fallback_reason"] == "requested_mode_unavailable"
    pool.mark_client_success.assert_called_once_with("auto-client", mode="auto")


@patch("perplexity.server.app.Client")
@patch("perplexity.server.app.get_pool")
def test_falls_back_to_anonymous_auto_when_pool_has_no_available_client(
    mock_get_pool, mock_client_class
) -> None:
    anonymous_client = make_client(own=False)
    anonymous_client.search.return_value = {
        "answer": "Anonymous fallback answer",
        "text": [],
    }
    mock_client_class.return_value = anonymous_client

    pool = make_pool(
        [(None, None), (None, None)],
        configured_clients=[("anonymous", anonymous_client)],
    )
    mock_get_pool.return_value = pool

    result = run_query("test query", mode="pro")

    assert result["status"] == "ok"
    assert result["data"]["answer"] == "Anonymous fallback answer"
    assert result["data"]["fallback"] is True
    assert result["data"]["fallback_mode"] == "anonymous_auto"
    assert result["data"]["fallback_reason"] == "no_account_configured"
    mock_client_class.assert_called_once_with({})
    anonymous_client.search.assert_called_once()
