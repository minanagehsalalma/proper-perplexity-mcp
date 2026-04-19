"""Smoke-test the Perplexity MCP stdio server with an optional image attachment."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def _run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    server_env = dict(os.environ)
    if args.fake_result_json:
        server_env["PERPLEXITY_MCP_FAKE_RESULT_JSON"] = args.fake_result_json

    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.server"],
        cwd=str(repo_root),
        env=server_env,
    )

    tool_args: dict[str, object] = {
        "query": args.query,
        "response_format": args.response_format,
    }
    if args.image_path:
        tool_args["attachments"] = [str(Path(args.image_path).expanduser())]

    async with stdio_client(server_parameters) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(args.tool, tool_args)

    print(result.content[0].text)
    if args.show_structured and result.structuredContent is not None:
        print("\n--- structuredContent ---")
        print(json.dumps(result.structuredContent, indent=2))

    return 1 if result.isError else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", default="perplexity_ask", choices=["perplexity_ask", "perplexity_research"])
    parser.add_argument(
        "--query",
        default="Look only at the uploaded image and describe the key visible facts.",
        help="Prompt sent to the MCP tool.",
    )
    parser.add_argument("--image-path", help="Optional local image path to upload via attachments.")
    parser.add_argument("--response-format", default="markdown", choices=["markdown", "json"])
    parser.add_argument("--fake-result-json", help="Optional deterministic fake result payload for offline smoke tests.")
    parser.add_argument("--show-structured", action="store_true", help="Print structuredContent after the main result.")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
