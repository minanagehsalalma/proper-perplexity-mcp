# Contributing

## Setup

1. Create or reuse a project virtual environment.
2. Install backend dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

3. Install frontend dependencies:

```powershell
Set-Location .\perplexity\server\web
npm ci
```

## Validation

Run these before opening a PR:

```powershell
.\.venv\Scripts\python.exe -m pytest
Set-Location .\perplexity\server\web
npm run build
npm run lint
```

## Change Guidelines

- Keep MCP-facing behavior covered by tests.
- When changing attachment behavior, include both validation tests and at least one stdio-path test.
- Prefer narrow prompts, structured outputs, and deterministic validation over ad hoc behavior.
- Do not commit tokens, cookies, generated logs, or local runtime state.
