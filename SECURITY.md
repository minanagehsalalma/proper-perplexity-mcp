# Security Policy

## Reporting

If you find a security issue, do not open a public issue with live tokens, cookies, or exploit details.

Report it privately through GitHub security advisories or contact the maintainer directly.

## Sensitive Data Rules

- Never commit `token_pool_config.json` with real credentials.
- Never commit session cookies, screenshots containing secrets, logs with private prompts, or local runtime state.
- Use `token_pool_config.example.json` as the public template.

## Scope

The highest-risk areas in this project are:

- cookie and session-token handling
- attachment uploads
- public examples or docs that might leak personal paths or secrets
- admin endpoints and local configuration handling
