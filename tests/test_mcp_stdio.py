"""End-to-end stdio integration tests for the MCP server."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.mark.asyncio
async def test_stdio_transport_exposes_tools_resources_prompts_and_structured_results(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    image_path = tmp_path / "shot.png"
    image_path.write_bytes(b"fake-image")

    fake_result = {
        "status": "ok",
        "data": {
            "answer": "Stub answer",
            "sources": [{"title": "Example", "url": "https://example.com"}],
            "resolved_mode": "SEARCH",
            "resolved_model": "pplx_pro",
        },
    }

    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.server"],
        cwd=str(repo_root),
        env={
            **dict(os.environ),
            "PERPLEXITY_MCP_FAKE_RESULT_JSON": json.dumps(fake_result),
        },
    )

    async with stdio_client(server_parameters) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            resources = (await session.list_resources()).resources
            prompts = (await session.list_prompts()).prompts
            prompt = await session.get_prompt(
                "perplexity_image_analysis",
                {"image_task": "Identify the monitor state.", "tool_name": "perplexity_ask"},
            )
            attachments_resource = await session.read_resource("perplexity://guides/attachments")
            result = await session.call_tool(
                "perplexity_ask",
                {
                    "query": "Describe the uploaded image.",
                    "attachments": [str(image_path)],
                    "response_format": "json",
                },
            )

    assert any(tool.name == "perplexity_ask" for tool in tools)
    assert any(str(resource.uri) == "perplexity://guides/attachments" for resource in resources)
    assert any(prompt_item.name == "perplexity_image_analysis" for prompt_item in prompts)
    assert "attachments" in prompt.messages[0].content.text
    assert "Max attachments" in attachments_resource.contents[0].text
    assert result.isError is False
    assert result.structuredContent["answer"] == "Stub answer"
    assert result.structuredContent["attachments"][0]["filename"] == "shot.png"
    assert '"response_format": "json"' in result.content[0].text
