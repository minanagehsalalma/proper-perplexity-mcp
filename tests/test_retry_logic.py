"""Tests for the current run_query failover behavior."""

from unittest.mock import MagicMock, patch

from perplexity.server.app import run_query


def make_client(*, own: bool = True) -> MagicMock:
    client = MagicMock()
    client.own = own
    client.copilot = float("inf")
    client.file_upload = float("inf")
    return client


def make_pool(sequence, *, fallback_enabled: bool = True) -> MagicMock:
    pool = MagicMock()
    pool.clients = {
        client_id: MagicMock()
        for client_id, _client in sequence
        if client_id is not None
    }
    pool.get_client.side_effect = sequence
    pool.is_fallback_to_auto_enabled.return_value = fallback_enabled
    return pool


@patch("perplexity.server.app.get_pool")
def test_single_account_request_failure_returns_error(mock_get_pool) -> None:
    client = make_client()
    client.search.side_effect = Exception("Network Error")
    pool = make_pool([("primary", client)])
    mock_get_pool.return_value = pool

    result = run_query("test query", mode="auto")

    assert result["status"] == "error"
    assert "Network Error" in result["message"]
    assert client.search.call_count == 1
    pool.mark_client_failure.assert_called_once_with("primary")


@patch("perplexity.server.app.get_pool")
def test_failover_to_valid_account_uses_next_client_once(mock_get_pool) -> None:
    fail_client = make_client()
    fail_client.search.side_effect = Exception("Connection Refused")

    valid_client = make_client()
    valid_client.search.return_value = {
        "answer": "Success Answer",
        "text": [],
    }

    pool = make_pool(
        [
            ("fail_user@example.com", fail_client),
            ("valid_user@example.com", valid_client),
        ]
    )
    mock_get_pool.return_value = pool

    result = run_query("test query", mode="auto")

    assert result["status"] == "ok"
    assert result["data"]["answer"] == "Success Answer"
    assert fail_client.search.call_count == 1
    assert valid_client.search.call_count == 1
    pool.mark_client_failure.assert_called_once_with("fail_user@example.com")
    pool.mark_client_success.assert_called_once_with(
        "valid_user@example.com",
        mode="auto",
    )


@patch("perplexity.server.app.Client")
@patch("perplexity.server.app.get_pool")
def test_pro_quota_failover_uses_next_client_without_anonymous_fallback(
    mock_get_pool, mock_anonymous_client
) -> None:
    fail_client = make_client()
    fail_client.search.side_effect = Exception("Your Pro search quota has run out")

    valid_client = make_client()
    valid_client.search.return_value = {
        "answer": "Pro Answer",
        "text": [],
    }

    pool = make_pool(
        [
            ("fail_user@example.com", fail_client),
            ("valid_user@example.com", valid_client),
        ]
    )
    mock_get_pool.return_value = pool

    result = run_query("test query", mode="pro")

    assert result["status"] == "ok"
    assert result["data"]["answer"] == "Pro Answer"
    assert fail_client.search.call_count == 1
    assert valid_client.search.call_count == 1
    pool.mark_client_failure.assert_called_once_with("fail_user@example.com")
    pool.mark_client_success.assert_called_once_with(
        "valid_user@example.com",
        mode="pro",
    )
    mock_anonymous_client.assert_not_called()
