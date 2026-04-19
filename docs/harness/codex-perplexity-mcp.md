# Codex Perplexity MCP Playbook

This repo exposes Perplexity through two layers:

- MCP stdio wrapper in [src/server.py](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\src\server.py)
- Backend execution engine in [perplexity/server/app.py](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\perplexity\server\app.py)

Use this playbook when Codex needs current external information or needs to validate the Perplexity MCP behavior itself.

## Tool Selection

- Use `perplexity_ask` for focused questions, current docs, bug lookup, API behavior checks, or small comparisons.
- Use `perplexity_research` only when the user explicitly wants deep research or the question genuinely needs a slower multi-source synthesis.
- If the request contains several independent subquestions, split them into separate `perplexity_ask` calls and synthesize locally.
- If the answer will feed another machine step, set `response_format` to `json` so the host gets validated `structuredContent`.

## Non-Tool MCP Surfaces

This server also exposes MCP resources and prompts.

- Check resources for attachment limits, defaults, models, and the Codex playbook.
- Check prompts when you want a reusable template for tool selection, batch planning, or image-analysis query drafting.
- Prefer these built-in MCP surfaces over paraphrasing repo docs from memory when the host can read them.

## Prompt Shape

- Give concrete task context, constraints, and the expected output shape.
- Prefer prompts scoped to one topic cluster or 3-5 vendors at a time.
- Avoid mega-prompts that combine market research, architecture design, migration planning, and code generation in one request.
- If the repo already contains the relevant code or docs, inspect local files first and use Perplexity only for the external gap.

## Attachments

Both MCP tools support `attachments`.

Accepted forms:

```json
{
  "attachments": ["C:\\Users\\ASUS\\Pictures\\screenshot.png"]
}
```

```json
{
  "attachments": [
    {
      "base64_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
    }
  ]
}
```

Rules:

- Prefer local file paths for normal repo work.
- Use inline base64 only when the caller already holds the image in memory.
- Ask concrete questions about the image. Good prompts target visible facts, labels, counts, states, or comparisons.
- For visual validation, compare the response against the actual image instead of only checking that a response exists.
- Respect the attachment guardrails exposed by the server resources: count, per-file size, total size, and supported MIME types.

## Live Verification

When validating the wrapper instead of the Perplexity service in isolation, exercise the real entry point:

- Call `src.server.call_tool(...)`, not just `perplexity.server.app.run_query(...)`.
- Use the repo-local venv: `.\.venv\Scripts\python.exe`.
- Favor a short async inline script in PowerShell that imports `src.server` and awaits `call_tool(...)`.
- For the full transport path, prefer [scripts/smoke-image-upload.ps1](C:\Users\ASUS\Downloads\TEMPDOWNLOADS\perplexity-mcp-main\scripts\smoke-image-upload.ps1), which talks to the stdio MCP server through a real MCP client.

This path verifies:

- MCP input schema usage
- attachment normalization
- pool reload and stale-state refresh
- result formatting
- stderr logging separation from the returned text payload

## Validation Order

Use the cheapest convincing validation first:

1. unit tests
2. local wrapper invocation through `src.server.call_tool(...)`
3. broader live upstream validation only when needed

For image upload changes, prefer a repo-owned screenshot in `docs/images/` for the first live proof because the expected visible facts are easy to verify.

## Practical Defaults

- Default language: `en-US` unless the task clearly requires something else.
- Default sources: let the tool defaults stand unless the request needs `scholar` or `social`.
- Keep model unset unless the user asks for a specific Perplexity website model.
- When reasoning models are requested in `perplexity_ask`, pass the exact label and let the tool auto-switch mode.
