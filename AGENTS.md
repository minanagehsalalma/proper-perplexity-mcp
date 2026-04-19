# Repo Notes

- Use the project-local `.venv` for Python work. On this Windows machine that may require invoking the venv through an unsandboxed command because the launcher resolves back to the system Python install under `AppData`.
- Install backend dependencies with `.\.venv\Scripts\python.exe -m pip install -e .[dev]`.
- The admin HTTP server is `perplexity-server` and serves the Starlette app on port `8123`. This repo does not implement the older `/v1/...` OpenAI-compatible endpoints or an HTTP MCP endpoint on port `8000`.
- Build the admin frontend from [perplexity/server/web](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\perplexity\server\web) before using `/admin/`: `npm ci` then `npm run build`.
- Fast validation path:
  `.\.venv\Scripts\python.exe -m pytest`
  `npm run build` in `perplexity/server/web`
  `npm run lint` in `perplexity/server/web`
- Live Perplexity queries are token/network dependent. Prefer unit tests and local route checks unless the task explicitly requires exercising the upstream service.

## Codex MCP Usage

- When the task needs external research or current documentation for this repo, prefer this repo's own Perplexity MCP surface and follow [docs/harness/codex-perplexity-mcp.md](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\docs\harness\codex-perplexity-mcp.md).
- Use `perplexity_ask` for focused lookups and `perplexity_research` only for broad multi-source investigations that justify a longer run.
- Keep Perplexity prompts narrow and batch by topic. Do not send one mega-prompt covering every vendor, subquestion, and architecture decision at once.
- When a task involves screenshots or other visual inputs, use the MCP tool `attachments` field rather than describing the image manually. `attachments` accepts local file paths or inline `base64_data`.
- When the result will be consumed programmatically or passed into another step, request `response_format: "json"` so the host gets validated `structuredContent` as well as display text.
- If the client supports MCP prompts/resources, check this server's resources and prompts first instead of rediscovering usage guidance from scratch.
- For live verification of the MCP wrapper itself, exercise the real tool entry point in [src/server.py](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\src\server.py) through `src.server.call_tool(...)` with the repo venv so the test covers schema parsing, attachment normalization, pool sync, and formatting.
- The stronger transport-level smoke path is [scripts/smoke-image-upload.ps1](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\scripts\smoke-image-upload.ps1), which uses real stdio MCP transport instead of a direct Python import.
