"""Unit tests for the current MCP stdio surface."""

import logging
import sys
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from mcp.shared.context import RequestContext
from mcp.types import CallToolResult, RequestParams

from src import server as mcp_server


def _result_text(result) -> str:
    if isinstance(result, tuple):
        return result[0][0].text
    if isinstance(result, CallToolResult):
        return result.content[0].text
    return result[0].text


def _structured_result(result):
    if isinstance(result, tuple):
        return result[1]
    if isinstance(result, CallToolResult):
        return result.structuredContent
    return None


@pytest.mark.asyncio
async def test_list_tools_returns_current_toolset() -> None:
    tools = await mcp_server.list_tools()
    assert [tool.name for tool in tools] == [
        "perplexity_ask",
        "perplexity_research",
    ]
    ask_tool = next(tool for tool in tools if tool.name == "perplexity_ask")
    assert ask_tool.inputSchema["properties"]["model"]["enum"] == [
        "Sonar",
        "GPT-5.4",
        "Claude Sonnet 4.6",
        "Grok 4.1",
        "GPT-5.4 Thinking",
        "Claude Sonnet 4.6 Thinking",
        "Grok 4.1 Reasoning",
        "Kimi K2.5 Thinking",
    ]
    assert "attachments" in ask_tool.inputSchema["properties"]
    assert ask_tool.inputSchema["properties"]["response_format"]["enum"] == ["markdown", "json"]
    assert ask_tool.outputSchema["properties"]["status"]["enum"] == ["ok", "error"]


@pytest.mark.asyncio
async def test_list_resources_and_prompts_expose_codex_guidance() -> None:
    resources = await mcp_server.list_resources()
    prompts = await mcp_server.list_prompts()

    assert any(str(resource.uri) == "perplexity://guides/codex-playbook" for resource in resources)
    assert any(prompt.name == "perplexity_image_analysis" for prompt in prompts)


@pytest.mark.asyncio
async def test_read_resource_and_get_prompt_render_expected_content() -> None:
    resource_contents = await mcp_server.read_resource("perplexity://guides/attachments")
    prompt = await mcp_server.get_prompt(
        "perplexity_image_analysis",
        {"image_task": "Identify the monitor status card.", "tool_name": "perplexity_ask"},
    )

    assert "Max attachments" in resource_contents[0].content
    assert "attachments" in prompt.messages[0].content.text
    assert "Identify the monitor status card." in prompt.messages[0].content.text


def test_mcp_logger_uses_stderr_only() -> None:
    console_handlers = [
        handler
        for handler in mcp_server.logger.handlers
        if type(handler) is logging.StreamHandler
    ]
    assert len(console_handlers) == 1
    assert console_handlers[0].stream is sys.stderr
    assert mcp_server.logger.propagate is False


@pytest.mark.asyncio
async def test_call_tool_rejects_unknown_tool() -> None:
    result = await mcp_server.call_tool("unknown_tool", {"query": "hello"})
    assert result.isError is True
    assert "Unknown tool" in _result_text(result)


@pytest.mark.asyncio
async def test_call_tool_uses_reasoning_mode_and_default_sources() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(
            mcp_server,
            "run_query",
            return_value={
                "status": "ok",
                "data": {
                    "answer": "Reasoned answer",
                    "sources": [
                        {
                            "title": "Example",
                            "url": "https://example.com",
                        }
                    ],
                },
            },
        ) as mock_run_query,
    ):
        result = await mcp_server.call_tool(
            "perplexity_ask",
            {
                "query": "How should I test this?",
                "model": "Claude Sonnet 4.6 Thinking",
            },
        )

    mock_run_query.assert_called_once_with(
        query="How should I test this?",
        mode="reasoning",
        model="Claude Sonnet 4.6 Thinking",
        sources=["web"],
        language="en-US",
        files=None,
        fallback_to_auto=True,
    )
    assert _result_text(result).startswith("Reasoned answer")
    assert "Example" in _result_text(result)
    assert _structured_result(result)["meta"]["requested_mode"] == "reasoning"


@pytest.mark.asyncio
async def test_call_tool_supports_path_attachments(tmp_path) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"fake-image")

    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(
            mcp_server,
            "run_query",
            return_value={"status": "ok", "data": {"answer": "Image answer", "sources": []}},
        ) as mock_run_query,
    ):
        result = await mcp_server.call_tool(
            "perplexity_ask",
            {
                "query": "What is in this screenshot?",
                "attachments": [str(image_path)],
            },
        )

    assert _result_text(result) == "Image answer"
    mock_run_query.assert_called_once_with(
        query="What is in this screenshot?",
        mode="pro",
        model=None,
        sources=["web"],
        language="en-US",
        files={"diagram.png": b"fake-image"},
        fallback_to_auto=True,
    )
    assert _structured_result(result)["attachments"][0]["filename"] == "diagram.png"


@pytest.mark.asyncio
async def test_call_tool_supports_inline_image_payloads() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(
            mcp_server,
            "run_query",
            return_value={"status": "ok", "data": {"answer": "Inline answer", "sources": []}},
        ) as mock_run_query,
    ):
        result = await mcp_server.call_tool(
            "perplexity_ask",
            {
                "query": "Describe this upload.",
                "attachments": [{"base64_data": "data:image/png;base64,aGVsbG8="}],
            },
        )

    assert _result_text(result) == "Inline answer"
    mock_run_query.assert_called_once_with(
        query="Describe this upload.",
        mode="pro",
        model=None,
        sources=["web"],
        language="en-US",
        files={"attachment-1.png": b"hello"},
        fallback_to_auto=True,
    )


@pytest.mark.asyncio
async def test_call_tool_rejects_invalid_attachment_payload() -> None:
    result = await mcp_server.call_tool(
        "perplexity_ask",
        {
            "query": "Describe this upload.",
            "attachments": [{"base64_data": "not-base64", "filename": "broken.png"}],
        },
    )

    assert _result_text(result) == "Error (ValidationError): Attachment 1 contains invalid base64 data."


@pytest.mark.asyncio
async def test_call_tool_rejects_oversized_attachment(tmp_path) -> None:
    oversized = tmp_path / "big.png"
    oversized.write_bytes(b"x" * 16)

    with patch.object(mcp_server, "MAX_ATTACHMENT_BYTES", 8):
        result = await mcp_server.call_tool(
            "perplexity_ask",
            {
                "query": "Describe this upload.",
                "attachments": [str(oversized)],
            },
        )

    assert "too large" in _result_text(result)


@pytest.mark.asyncio
async def test_call_tool_supports_json_response_format() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(
            mcp_server,
            "run_query",
            return_value={"status": "ok", "data": {"answer": "Inline answer", "sources": []}},
        ),
    ):
        result = await mcp_server.call_tool(
            "perplexity_ask",
            {
                "query": "Describe this upload.",
                "response_format": "json",
            },
        )

    assert '"status": "ok"' in _result_text(result)
    assert _structured_result(result)["meta"]["response_format"] == "json"


@pytest.mark.asyncio
async def test_call_tool_emits_progress_notifications_for_long_calls() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    session = MagicMock()
    session.send_progress_notification = AsyncMock()
    ctx = RequestContext(
        request_id="req-1",
        meta=RequestParams.Meta(progressToken="token-1"),
        session=session,
        lifespan_context=None,
    )

    def slow_query(**_: object) -> dict[str, object]:
        time.sleep(0.03)
        return {
            "status": "ok",
            "data": {
                "answer": "Deep answer",
                "sources": [],
            },
        }

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(mcp_server, "run_query", side_effect=slow_query),
        patch.object(type(mcp_server.server), "request_context", new_callable=PropertyMock, return_value=ctx),
        patch.object(mcp_server, "PROGRESS_HEARTBEAT_SECONDS", 0.01),
    ):
        result = await mcp_server.call_tool(
            "perplexity_research",
            {"query": "Investigate this in depth."},
        )

    assert _result_text(result) == "Deep answer"
    assert session.send_progress_notification.await_count >= 3
    progress_messages = [call.kwargs["message"] for call in session.send_progress_notification.await_args_list]
    assert progress_messages[0] == "Preparing Perplexity request."
    assert any("still running" in message for message in progress_messages)
    assert progress_messages[-1] == "Perplexity response ready."
    assert all(
        call.kwargs["related_request_id"] == "req-1"
        for call in session.send_progress_notification.await_args_list
    )


@pytest.mark.asyncio
async def test_call_tool_emits_log_notifications_without_progress_token() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    session = MagicMock()
    session.send_log_message = AsyncMock()
    session.send_ping = AsyncMock()
    ctx = RequestContext(
        request_id="req-2",
        meta=None,
        session=session,
        lifespan_context=None,
    )

    def slow_query(**_: object) -> dict[str, object]:
        time.sleep(0.03)
        return {
            "status": "ok",
            "data": {
                "answer": "Deep answer",
                "sources": [],
            },
        }

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(mcp_server, "run_query", side_effect=slow_query),
        patch.object(type(mcp_server.server), "request_context", new_callable=PropertyMock, return_value=ctx),
        patch.object(mcp_server, "PROGRESS_HEARTBEAT_SECONDS", 0.01),
        patch.object(mcp_server, "HEARTBEAT_PING_EVERY", 0),
    ):
        result = await mcp_server.call_tool(
            "perplexity_research",
            {"query": "Investigate this in depth."},
        )

    assert _result_text(result) == "Deep answer"
    assert session.send_log_message.await_count >= 3
    log_messages = [call.kwargs["data"] for call in session.send_log_message.await_args_list]
    assert log_messages[0] == "Preparing Perplexity request."
    assert any("still running" in message for message in log_messages)
    assert log_messages[-1] == "Perplexity response ready."
    assert all(call.kwargs["related_request_id"] == "req-2" for call in session.send_log_message.await_args_list)


@pytest.mark.asyncio
async def test_call_tool_sends_periodic_ping_for_long_calls() -> None:
    pool = MagicMock()
    pool.reload_config.return_value = False
    pool.load_state.return_value = False
    pool.is_state_stale.return_value = False
    pool.refresh_all_rate_limits = AsyncMock()

    session = MagicMock()
    session.send_log_message = AsyncMock()
    session.send_ping = AsyncMock()
    ctx = RequestContext(
        request_id="req-3",
        meta=None,
        session=session,
        lifespan_context=None,
    )

    def slow_query(**_: object) -> dict[str, object]:
        time.sleep(0.03)
        return {
            "status": "ok",
            "data": {
                "answer": "Deep answer",
                "sources": [],
            },
        }

    with (
        patch.object(mcp_server, "get_pool", return_value=pool),
        patch.object(mcp_server, "run_query", side_effect=slow_query),
        patch.object(type(mcp_server.server), "request_context", new_callable=PropertyMock, return_value=ctx),
        patch.object(mcp_server, "PROGRESS_HEARTBEAT_SECONDS", 0.01),
        patch.object(mcp_server, "HEARTBEAT_PING_EVERY", 1),
        patch.object(mcp_server, "HEARTBEAT_PING_TIMEOUT_SECONDS", 0.05),
    ):
        result = await mcp_server.call_tool(
            "perplexity_research",
            {"query": "Investigate this in depth."},
        )

    assert _result_text(result) == "Deep answer"
    assert session.send_ping.await_count >= 1


def test_format_result_includes_fallback_notice_and_sources() -> None:
    text = mcp_server.format_result(
        {
            "status": "ok",
            "data": {
                "fallback": True,
                "fallback_mode": "auto",
                "original_mode": "pro",
                "fallback_reason": "quota_unavailable",
                "requested_model": "Claude Sonnet 4.6 Thinking",
                "resolved_mode": "concise",
                "resolved_model": "turbo",
                "answer": "Fallback answer",
                "sources": [
                    {"title": "One", "url": "https://example.com/1"},
                    {"title": "Two", "url": "https://example.com/2"},
                ],
            },
        }
    )

    assert "Fell back from 'pro' to 'auto'" in text
    assert "Requested: `Claude Sonnet 4.6 Thinking`" in text
    assert "Mode: `concise`" in text
    assert "Model: `turbo`" in text
    assert "Fallback answer" in text
    assert "Sources referenced (2 total)" in text


def test_format_result_mentions_missing_account_config() -> None:
    text = mcp_server.format_result(
        {
            "status": "ok",
            "data": {
                "fallback": True,
                "fallback_mode": "anonymous_auto",
                "original_mode": "pro",
                "fallback_reason": "no_account_configured",
                "answer": "Fallback answer",
                "sources": [],
            },
        }
    )

    assert "no configured Perplexity account token was available" in text
    assert "anonymous auto" in text
