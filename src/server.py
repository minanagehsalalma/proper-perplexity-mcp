"""
MCP Server for Perplexity AI.

Thin MCP wrapper over the perplexity backend with LLM-optimized tool definitions.
Uses ClientPool with weighted rotation, exponential backoff, and multi-level fallback.
Shares pool state via pool_state.json for cross-process monitor coordination.
"""

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    ResourceTemplate,
    TextContent,
)

from perplexity.config import get_public_model_choices, get_resolved_model_label
from perplexity.exceptions import ValidationError
from perplexity.server.app import run_query, get_pool
from .tools import TOOLS, get_mode_for_tool, TOOL_DEFAULT_SOURCES

# Configuration from environment
TIMEOUT_SECONDS = int(os.getenv("PERPLEXITY_TIMEOUT", "900"))  # 15 min default for research
MAX_ATTACHMENTS = int(os.getenv("PERPLEXITY_MAX_ATTACHMENTS", "4"))
MAX_ATTACHMENT_BYTES = int(os.getenv("PERPLEXITY_MAX_ATTACHMENT_BYTES", str(10 * 1024 * 1024)))
MAX_TOTAL_ATTACHMENT_BYTES = int(
    os.getenv("PERPLEXITY_MAX_TOTAL_ATTACHMENT_BYTES", str(20 * 1024 * 1024))
)
PROGRESS_TOTAL = 100.0
PROGRESS_HEARTBEAT_SECONDS = float(os.getenv("PERPLEXITY_PROGRESS_HEARTBEAT", "15"))
PROGRESS_HEARTBEAT_START = 15.0
PROGRESS_HEARTBEAT_STEP = 10.0
PROGRESS_HEARTBEAT_MAX = 95.0
HEARTBEAT_PING_EVERY = max(0, int(os.getenv("PERPLEXITY_HEARTBEAT_PING_EVERY", "4")))
HEARTBEAT_PING_TIMEOUT_SECONDS = float(os.getenv("PERPLEXITY_HEARTBEAT_PING_TIMEOUT", "5"))
_ATTACHMENT_ALLOWED_MIME_PREFIXES = ("image/",)
_ATTACHMENT_ALLOWED_MIME_TYPES = {
    "application/json",
    "application/msword",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/markdown",
    "text/plain",
}
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CODEX_PLAYBOOK_PATH = _REPO_ROOT / "docs" / "harness" / "codex-perplexity-mcp.md"
_ATTACHMENTS_RESOURCE_URI = "perplexity://guides/attachments"
_DEFAULTS_RESOURCE_URI = "perplexity://guides/defaults"
_CODEX_RESOURCE_URI = "perplexity://guides/codex-playbook"
_MODELS_RESOURCE_URI = "perplexity://metadata/models"
_PROMPT_BATCH_RESEARCH = "perplexity_batch_research"
_PROMPT_IMAGE_ANALYSIS = "perplexity_image_analysis"
_PROMPT_TOOL_SELECTION = "perplexity_tool_selection"

def _configure_logger() -> logging.Logger:
    """Keep MCP logs on stderr so stdout remains protocol-only."""
    logger = logging.getLogger("perplexity-mcp")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = _configure_logger()

# Valid tool names for dispatch
_VALID_TOOLS = {t.name for t in TOOLS}

# Create server instance
server = Server(
    "perplexity-mcp",
    instructions=(
        "Use perplexity_ask for focused lookups and perplexity_research for broader investigations. "
        "Use attachments for screenshots or documents instead of describing them manually. "
        "Prefer narrow, topic-batched prompts over mega-prompts."
    ),
)


def _summarize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Redact bulky attachment payloads before writing request args to logs."""
    summary = dict(arguments)
    for key in ("attachments", "files"):
        value = summary.get(key)
        if value:
            count = len(value) if isinstance(value, list) else 1
            summary[key] = f"<{count} attachment(s)>"
    return summary


def _format_bytes(num_bytes: int) -> str:
    """Return a compact human-readable byte count."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def _resolve_attachment_mime_type(filename: str, inferred_mime: str | None = None) -> str | None:
    """Guess the MIME type for an attachment."""
    return inferred_mime or mimetypes.guess_type(filename)[0]


def _validate_attachment_mime_type(mime_type: str | None, index: int) -> None:
    """Reject unsupported attachment types before upload."""
    if mime_type is None:
        raise ValidationError(
            f"Attachment {index} type could not be determined. Use a supported file extension or a data URL."
        )
    if mime_type in _ATTACHMENT_ALLOWED_MIME_TYPES:
        return
    if any(mime_type.startswith(prefix) for prefix in _ATTACHMENT_ALLOWED_MIME_PREFIXES):
        return
    raise ValidationError(
        f"Attachment {index} type '{mime_type}' is not supported. "
        "Allowed types include common images, PDF, text, JSON, CSV, and Office documents."
    )


def _validate_attachment_size(size_bytes: int, total_bytes: int, index: int) -> None:
    """Validate per-file and total attachment size guardrails."""
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            f"Attachment {index} is too large ({_format_bytes(size_bytes)}). "
            f"Max per file is {_format_bytes(MAX_ATTACHMENT_BYTES)}."
        )
    if total_bytes + size_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
        raise ValidationError(
            f"Attachments exceed total upload budget of {_format_bytes(MAX_TOTAL_ATTACHMENT_BYTES)}."
        )


def _build_attachment_manifest_entry(
    *,
    filename: str,
    mime_type: str | None,
    size_bytes: int,
    origin: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Return structured metadata for an uploaded attachment."""
    entry: dict[str, Any] = {
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "origin": origin,
    }
    if path is not None:
        entry["path"] = path
    return entry


def _load_fake_result_from_env() -> dict[str, Any] | None:
    """Load a deterministic test response when configured for integration tests."""
    raw = os.getenv("PERPLEXITY_MCP_FAKE_RESULT_JSON")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("PERPLEXITY_MCP_FAKE_RESULT_JSON is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValidationError("PERPLEXITY_MCP_FAKE_RESULT_JSON must decode to an object.")
    return payload


def _decode_attachment_payload(base64_data: str, index: int) -> tuple[bytes, str | None]:
    """Decode raw base64 or a data URL payload for an attachment."""
    payload = base64_data.strip()
    mime_type = None

    if payload.startswith("data:"):
        header, separator, payload = payload.partition(",")
        if not separator or ";base64" not in header:
            raise ValidationError(
                f"Attachment {index} uses an invalid data URL. Expected 'data:<mime>;base64,<payload>'."
            )
        mime_type = header[5:].split(";", 1)[0] or None

    try:
        return base64.b64decode("".join(payload.split()), validate=True), mime_type
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(f"Attachment {index} contains invalid base64 data.") from exc


def _store_attachment(
    normalized: dict[str, bytes],
    filename: str,
    payload: bytes,
    index: int,
) -> None:
    """Store an attachment while guarding against duplicate filenames."""
    cleaned_filename = filename.strip()
    if not cleaned_filename:
        raise ValidationError(f"Attachment {index} must include a non-empty filename.")
    if cleaned_filename in normalized:
        raise ValidationError(
            f"Duplicate attachment filename '{cleaned_filename}'. Rename one of the attachments."
        )
    normalized[cleaned_filename] = payload


def _normalize_tool_attachments(arguments: dict[str, Any]) -> tuple[dict[str, bytes] | None, list[dict[str, Any]]]:
    """Convert MCP attachment input into the file mapping expected by run_query()."""
    raw_attachments = arguments.get("attachments")
    legacy_files = arguments.get("files")

    if raw_attachments and legacy_files:
        raise ValidationError("Use either 'attachments' or 'files', not both.")

    attachments = raw_attachments if raw_attachments is not None else legacy_files
    if attachments is None:
        return None, []
    if not isinstance(attachments, list):
        raise ValidationError("attachments must be an array of file paths or attachment objects.")
    if len(attachments) > MAX_ATTACHMENTS:
        raise ValidationError(f"Too many attachments. Max allowed is {MAX_ATTACHMENTS}.")

    normalized: dict[str, bytes] = {}
    manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for index, item in enumerate(attachments, start=1):
        if isinstance(item, str):
            path = Path(item).expanduser()
            if not path.is_file():
                raise ValidationError(f"Attachment {index} path does not exist: {item}")
            size_bytes = path.stat().st_size
            _validate_attachment_size(size_bytes, total_bytes, index)
            mime_type = _resolve_attachment_mime_type(path.name)
            _validate_attachment_mime_type(mime_type, index)
            payload = path.read_bytes()
            _store_attachment(normalized, path.name, payload, index)
            total_bytes += size_bytes
            manifest.append(
                _build_attachment_manifest_entry(
                    filename=path.name,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    origin="path",
                    path=str(path),
                )
            )
            continue

        if not isinstance(item, dict):
            raise ValidationError(
                f"Attachment {index} must be a string path or an object, got {type(item).__name__}."
            )

        path_value = item.get("path")
        if path_value is not None:
            if not isinstance(path_value, str) or not path_value.strip():
                raise ValidationError(f"Attachment {index} has an invalid 'path' value.")
            path = Path(path_value).expanduser()
            if not path.is_file():
                raise ValidationError(f"Attachment {index} path does not exist: {path_value}")
            filename = item.get("filename") or path.name
            if not isinstance(filename, str):
                raise ValidationError(f"Attachment {index} has an invalid 'filename' value.")
            size_bytes = path.stat().st_size
            _validate_attachment_size(size_bytes, total_bytes, index)
            mime_type = _resolve_attachment_mime_type(filename)
            _validate_attachment_mime_type(mime_type, index)
            payload = path.read_bytes()
            _store_attachment(normalized, filename, payload, index)
            total_bytes += size_bytes
            manifest.append(
                _build_attachment_manifest_entry(
                    filename=filename,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    origin="path",
                    path=str(path),
                )
            )
            continue

        base64_data = item.get("base64_data")
        if not isinstance(base64_data, str) or not base64_data.strip():
            raise ValidationError(
                f"Attachment {index} must include either 'path' or a non-empty 'base64_data' field."
            )

        payload, inferred_mime = _decode_attachment_payload(base64_data, index)
        filename = item.get("filename")
        if filename is None:
            if inferred_mime:
                ext = mimetypes.guess_extension(inferred_mime) or ".bin"
                filename = f"attachment-{index}{ext}"
            else:
                raise ValidationError(
                    f"Attachment {index} must include 'filename' when base64_data is raw base64."
                )
        if not isinstance(filename, str):
            raise ValidationError(f"Attachment {index} has an invalid 'filename' value.")
        size_bytes = len(payload)
        _validate_attachment_size(size_bytes, total_bytes, index)
        mime_type = _resolve_attachment_mime_type(filename, inferred_mime)
        _validate_attachment_mime_type(mime_type, index)
        _store_attachment(normalized, filename, payload, index)
        total_bytes += size_bytes
        manifest.append(
            _build_attachment_manifest_entry(
                filename=filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                origin="base64",
            )
        )

    return normalized, manifest


def _read_repo_text(path: Path) -> str:
    """Read a UTF-8 repo text file for MCP resources."""
    return path.read_text(encoding="utf-8")


def _resource_text(uri: str) -> str:
    """Render text content for a known MCP resource URI."""
    if uri == _ATTACHMENTS_RESOURCE_URI:
        return (
            "Perplexity MCP attachments\n\n"
            f"- Max attachments: {MAX_ATTACHMENTS}\n"
            f"- Max per attachment: {_format_bytes(MAX_ATTACHMENT_BYTES)}\n"
            f"- Max total attachment bytes: {_format_bytes(MAX_TOTAL_ATTACHMENT_BYTES)}\n"
            "- Accepted MIME families: image/*, PDF, text/plain, text/markdown, text/csv, application/json, common Office documents\n"
            "- Use local file paths for normal work and inline base64/data URLs only when the caller already holds the file in memory\n"
            "- Prefer concrete visual questions over generic prompts like 'analyze this image'\n"
        )
    if uri == _DEFAULTS_RESOURCE_URI:
        return (
            "Perplexity MCP defaults\n\n"
            f"- Ask default sources: {', '.join(TOOL_DEFAULT_SOURCES['perplexity_ask'])}\n"
            f"- Research default sources: {', '.join(TOOL_DEFAULT_SOURCES['perplexity_research'])}\n"
            f"- Timeout: {TIMEOUT_SECONDS}s\n"
            "- Leave model unset unless the caller explicitly asks for a specific Perplexity website label\n"
            "- Prefer `response_format=json` when structured downstream consumption matters\n"
        )
    if uri == _MODELS_RESOURCE_URI:
        pro_models = ", ".join(get_public_model_choices("pro"))
        reasoning_models = ", ".join(get_public_model_choices("reasoning"))
        return (
            "Perplexity MCP model catalog\n\n"
            f"- Pro / ask labels: {pro_models}\n"
            f"- Reasoning-capable labels: {reasoning_models}\n"
            "- `perplexity_ask` automatically switches to reasoning mode when the chosen model label contains 'Thinking' or 'Reasoning'\n"
        )
    if uri == _CODEX_RESOURCE_URI:
        return _read_repo_text(_CODEX_PLAYBOOK_PATH)
    raise ValueError(f"Unknown resource: {uri}")


def _make_prompt_message(text: str) -> PromptMessage:
    """Build a simple prompt message."""
    return PromptMessage(role="user", content=TextContent(type="text", text=text))


def _render_prompt(name: str, arguments: dict[str, str] | None) -> tuple[str, list[PromptMessage]]:
    """Render a named MCP prompt template."""
    args = arguments or {}

    if name == _PROMPT_TOOL_SELECTION:
        user_goal = args.get("user_goal", "Need a Perplexity prompt and tool choice for an external lookup.")
        return (
            "Choose the right Perplexity MCP tool and prompt shape.",
            [
                _make_prompt_message(
                    "Decide whether this should use `perplexity_ask` or `perplexity_research`. "
                    "Then write the final Perplexity query in one compact block.\n\n"
                    f"Goal: {user_goal}\n"
                    "Rules:\n"
                    "- Prefer `perplexity_ask` for focused lookups.\n"
                    "- Use `perplexity_research` only for broad multi-source investigations.\n"
                    "- Split unrelated subtopics into separate asks instead of one mega-prompt.\n"
                )
            ],
        )

    if name == _PROMPT_BATCH_RESEARCH:
        topic = args.get("topic", "the user's research topic")
        constraints = args.get("constraints", "No extra constraints provided.")
        return (
            "Break a broad research goal into Perplexity-sized batches.",
            [
                _make_prompt_message(
                    "Create 2-4 focused Perplexity research batches for this topic. "
                    "Each batch should be independently answerable and small enough for a single call.\n\n"
                    f"Topic: {topic}\n"
                    f"Constraints: {constraints}\n"
                    "For each batch, include:\n"
                    "1. suggested tool (`perplexity_ask` or `perplexity_research`)\n"
                    "2. the exact query text\n"
                    "3. what evidence that batch is meant to gather\n"
                )
            ],
        )

    if name == _PROMPT_IMAGE_ANALYSIS:
        image_task = args.get("image_task", "Identify the most important visible facts in the uploaded image.")
        tool_name = args.get("tool_name", "perplexity_ask")
        return (
            "Write a strong visual-analysis prompt for Perplexity attachments.",
            [
                _make_prompt_message(
                    f"Draft the final `{tool_name}` query for an uploaded image.\n\n"
                    f"Image task: {image_task}\n"
                    "Rules:\n"
                    "- Refer to the uploaded image instead of restating imaginary details.\n"
                    "- Ask for concrete visible facts, labels, counts, states, or comparisons.\n"
                    "- Keep the prompt narrow enough that the answer can be visually verified.\n"
                    "- Assume the image is passed through the tool `attachments` field.\n"
                )
            ],
        )

    raise ValueError(f"Unknown prompt: {name}")


def _get_request_state():
    """Return the current request session, progress token, and request id when available."""
    try:
        ctx = server.request_context
    except LookupError:
        return None, None, None

    meta = getattr(ctx, "meta", None)
    progress_token = getattr(meta, "progressToken", None)
    return ctx.session, progress_token, getattr(ctx, "request_id", None)


async def _send_progress_update(progress: float, message: str) -> None:
    """Emit a best-effort progress notification without failing the tool call."""
    session, progress_token, request_id = _get_request_state()
    if session is None or progress_token is None:
        return

    try:
        await session.send_progress_notification(
            progress_token,
            progress,
            total=PROGRESS_TOTAL,
            message=message,
            related_request_id=request_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.debug("Progress notification failed: %s", exc)


async def _send_log_update(message: str, level: str = "info") -> None:
    """Emit a request-scoped log notification when progress notifications are unavailable."""
    session, progress_token, request_id = _get_request_state()
    if session is None or progress_token is not None:
        return

    try:
        await session.send_log_message(
            level=level,
            data=message,
            logger="perplexity-mcp",
            related_request_id=request_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.debug("Log notification failed: %s", exc)


async def _send_ping() -> None:
    """Best-effort ping fallback for clients that ignore notifications during tool calls."""
    session, _, _ = _get_request_state()
    if session is None:
        return

    try:
        await asyncio.wait_for(
            session.send_ping(),
            timeout=HEARTBEAT_PING_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.debug("Heartbeat ping failed: %s", exc)


async def _publish_status(progress: float, message: str, level: str = "info") -> None:
    """Emit the richest liveness signal supported by the current client."""
    await _send_progress_update(progress, message)
    await _send_log_update(message, level=level)


async def _progress_heartbeat(stop_event: asyncio.Event, mode: str) -> None:
    """Keep long-running tool calls alive with periodic progress notifications."""
    started_at = asyncio.get_running_loop().time()
    progress = PROGRESS_HEARTBEAT_START
    beat_count = 0

    while True:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PROGRESS_HEARTBEAT_SECONDS)
            return
        except asyncio.TimeoutError:
            elapsed = int(asyncio.get_running_loop().time() - started_at)
            progress = min(PROGRESS_HEARTBEAT_MAX, progress + PROGRESS_HEARTBEAT_STEP)
            beat_count += 1
            await _publish_status(
                progress,
                f"Perplexity {mode} is still running ({elapsed}s elapsed).",
            )
            if HEARTBEAT_PING_EVERY and beat_count % HEARTBEAT_PING_EVERY == 0:
                await _send_ping()


def _build_structured_result(
    *,
    name: str,
    mode: str,
    model: str | None,
    sources: list[str],
    language: str,
    response_format: str,
    attachments: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Build structured output for MCP hosts that consume JSON results."""
    structured: dict[str, Any] = {
        "status": result.get("status", "error"),
        "tool": name,
        "meta": {
            "requested_mode": mode,
            "requested_model": model,
            "sources": sources,
            "language": language,
            "response_format": response_format,
        },
        "attachments": attachments,
    }

    if result.get("status") == "ok":
        structured.update(result.get("data", {}))
    else:
        structured["error_type"] = result.get("error_type", "Unknown")
        structured["message"] = result.get("message", "Request failed.")

    return structured


def _make_error_tool_result(
    *,
    name: str,
    mode: str,
    model: str | None,
    sources: list[str],
    language: str,
    response_format: str,
    attachments: list[dict[str, Any]],
    message: str,
    error_type: str = "ValidationError",
) -> CallToolResult:
    """Return a consistent MCP error result with structured content."""
    structured = _build_structured_result(
        name=name,
        mode=mode,
        model=model,
        sources=sources,
        language=language,
        response_format=response_format,
        attachments=attachments,
        result={"status": "error", "error_type": error_type, "message": message},
    )
    content_text = (
        json.dumps(structured, indent=2)
        if response_format == "json"
        else f"Error ({error_type}): {message}"
    )
    return CallToolResult(
        content=[TextContent(type="text", text=content_text)],
        structuredContent=structured,
        isError=True,
    )


@server.list_tools()
async def list_tools():
    """List available Perplexity tools."""
    return TOOLS


@server.list_resources()
async def list_resources() -> list[Resource]:
    """Expose static MCP resources that help clients use the server well."""
    return [
        Resource(
            uri=_ATTACHMENTS_RESOURCE_URI,
            name="Attachment Guide",
            description="Supported attachment formats, limits, and usage guidance for image/document uploads.",
            mimeType="text/plain",
        ),
        Resource(
            uri=_DEFAULTS_RESOURCE_URI,
            name="Default Settings",
            description="Tool defaults, timeout behavior, and response-format guidance.",
            mimeType="text/plain",
        ),
        Resource(
            uri=_MODELS_RESOURCE_URI,
            name="Model Catalog",
            description="Current public model labels and reasoning-mode behavior.",
            mimeType="text/plain",
        ),
        Resource(
            uri=_CODEX_RESOURCE_URI,
            name="Codex Playbook",
            description="Codex-specific Perplexity MCP guidance for this repository.",
            mimeType="text/markdown",
        ),
    ]


@server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """Expose a template for direct tool metadata lookups."""
    return [
        ResourceTemplate(
            uriTemplate="perplexity://tool/{tool_name}",
            name="Tool Metadata",
            description="Human-readable guidance for a single MCP tool by name.",
            mimeType="text/plain",
        )
    ]


@server.read_resource()
async def read_resource(uri) -> list[ReadResourceContents]:
    """Read a known MCP resource URI."""
    uri_str = str(uri)
    if uri_str.startswith("perplexity://tool/"):
        tool_name = unquote(urlparse(uri_str).path.rsplit("/", 1)[-1])
        tool = next((item for item in TOOLS if item.name == tool_name), None)
        if tool is None:
            raise ValueError(f"Unknown resource: {uri_str}")
        content = (
            f"{tool.name}\n\n"
            f"{tool.description or 'No description.'}\n\n"
            f"Input keys: {', '.join(tool.inputSchema.get('properties', {}).keys())}"
        )
        return [ReadResourceContents(content=content, mime_type="text/plain")]

    return [ReadResourceContents(content=_resource_text(uri_str), mime_type="text/plain")]


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """Expose prompt templates that help hosts compose better Perplexity requests."""
    return [
        Prompt(
            name=_PROMPT_TOOL_SELECTION,
            description="Choose the right Perplexity tool and compose a focused query.",
            arguments=[
                PromptArgument(
                    name="user_goal",
                    description="The external-information goal to satisfy.",
                    required=True,
                )
            ],
        ),
        Prompt(
            name=_PROMPT_BATCH_RESEARCH,
            description="Split a broad investigation into smaller Perplexity batches.",
            arguments=[
                PromptArgument(name="topic", description="Broad topic to research.", required=True),
                PromptArgument(name="constraints", description="Optional scope or output constraints.", required=False),
            ],
        ),
        Prompt(
            name=_PROMPT_IMAGE_ANALYSIS,
            description="Write a concrete image-analysis prompt for the attachments field.",
            arguments=[
                PromptArgument(name="image_task", description="What to verify from the image.", required=True),
                PromptArgument(name="tool_name", description="Which Perplexity tool will be called.", required=False),
            ],
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None = None):
    """Render a named MCP prompt."""
    description, messages = _render_prompt(name, arguments)
    return GetPromptResult(description=description, messages=messages)


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]):
    """
    Handle tool calls by delegating to run_query().

    Before each query:
    1. Loads shared pool state from pool_state.json (noop if unchanged)
    2. If state is stale, refreshes rate limits via API (no queries consumed)
    3. For research: checks if any account has research quota
    4. Delegates to run_query() which handles rotation and fallback
    """
    logger.info("Tool call: %s with args: %s", name, _summarize_arguments(arguments))

    if name not in _VALID_TOOLS:
        return _make_error_tool_result(
            name=name,
            mode="unknown",
            model=None,
            sources=[],
            language="en-US",
            response_format="markdown",
            attachments=[],
            message=f"Unknown tool: {name}. Available: {list(_VALID_TOOLS)}",
            error_type="UnknownTool",
        )

    # Extract arguments
    query = arguments.get("query", "")
    model = arguments.get("model")
    mode = get_mode_for_tool(name, model)
    sources = arguments.get("sources") or TOOL_DEFAULT_SOURCES.get(name, ["web"])
    language = arguments.get("language", "en-US")
    response_format = arguments.get("response_format", "markdown")
    try:
        files, attachment_manifest = _normalize_tool_attachments(arguments)
    except ValidationError as exc:
        return _make_error_tool_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=[],
            message=str(exc),
        )

    await _publish_status(5.0, "Preparing Perplexity request.")
    if attachment_manifest:
        total_bytes = sum(item["size_bytes"] for item in attachment_manifest)
        await _publish_status(
            10.0,
            f"Validated {len(attachment_manifest)} attachment(s) totaling {_format_bytes(total_bytes)}.",
        )

    try:
        fake_result = _load_fake_result_from_env()
    except ValidationError as exc:
        return _make_error_tool_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=attachment_manifest,
            message=str(exc),
        )
    if fake_result is not None:
        await _publish_status(20.0, "Using configured test response.")
        await _publish_status(95.0, "Formatting Perplexity response.")
        structured = _build_structured_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=attachment_manifest,
            result=fake_result,
        )
        content_text = (
            json.dumps(structured, indent=2)
            if response_format == "json"
            else format_result(fake_result)
        )
        await _publish_status(PROGRESS_TOTAL, "Perplexity response ready.")
        return ([TextContent(type="text", text=content_text)], structured)

    # Sync shared pool state before query (MCP is read-only, HTTP server owns config)
    pool = get_pool(config_writable=False)
    await _publish_status(12.0, "Loading token pool state.")
    pool.reload_config()  # Pick up tokens added/removed via web UI
    pool.load_state()

    # Lazy rate-limit refresh — if state is stale (>1h), refresh via API (zero quota cost)
    if pool.is_state_stale(max_age_hours=1):
        logger.info("Rate limits stale, refreshing via API...")
        try:
            await _publish_status(15.0, "Refreshing account rate limits.")
            await pool.refresh_all_rate_limits()
        except Exception as e:
            logger.warning(f"Rate limit refresh failed: {e}")

    await _publish_status(
        20.0,
        f"Dispatching request to Perplexity {mode}.",
    )
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_progress_heartbeat(heartbeat_stop, mode))

    try:
        # Run synchronous run_query() in thread pool with timeout
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: run_query(
                    query=query,
                    mode=mode,
                    model=model,
                    sources=sources,
                    language=language,
                    files=files,
                    fallback_to_auto=True,
                )
            ),
            timeout=TIMEOUT_SECONDS
        )

        # Format response
        await _publish_status(95.0, "Formatting Perplexity response.")
        structured = _build_structured_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=attachment_manifest,
            result=result,
        )
        text = json.dumps(structured, indent=2) if response_format == "json" else format_result(result)
        await _publish_status(PROGRESS_TOTAL, "Perplexity response ready.")
        logger.info(f"Tool {name} completed (status={result.get('status')}, mode={mode})")
        return ([TextContent(type="text", text=text)], structured)

    except asyncio.TimeoutError:
        await _publish_status(
            PROGRESS_HEARTBEAT_MAX,
            f"Perplexity {mode} exceeded the configured timeout.",
            level="warning",
        )
        error_msg = (
            f"Request timed out after {TIMEOUT_SECONDS}s. "
            f"For research queries, try setting PERPLEXITY_TIMEOUT higher in your environment."
        )
        logger.error(error_msg)
        return _make_error_tool_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=attachment_manifest,
            message=error_msg,
            error_type="TimeoutError",
        )

    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {e}"
        logger.exception(error_msg)
        return _make_error_tool_result(
            name=name,
            mode=mode,
            model=model,
            sources=sources,
            language=language,
            response_format=response_format,
            attachments=attachment_manifest,
            message=error_msg,
            error_type=type(e).__name__,
        )
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


def format_result(result: dict) -> str:
    """Format run_query() result for MCP output.

    run_query() returns:
        {"status": "ok", "data": {"answer": ..., "sources": [...]}}
        {"status": "error", "error_type": ..., "message": ...}
    """
    if result.get("status") == "error":
        error_type = result.get("error_type", "Unknown")
        message = result.get("message", "Request failed.")
        return f"Error ({error_type}): {message}"

    data = result.get("data", {})
    parts = []

    # Fallback notice
    if data.get("fallback"):
        fallback_mode = data.get("fallback_mode", "auto").replace("_", " ")
        original_mode = data.get("original_mode", "unknown")
        fallback_reason = data.get("fallback_reason", "requested_mode_unavailable")

        if fallback_reason == "no_account_configured":
            notice = (
                f"*Note: Used '{fallback_mode}' because no configured "
                f"Perplexity account token was available for '{original_mode}'.*\n"
            )
        elif fallback_reason == "quota_unavailable":
            notice = (
                f"*Note: Fell back from '{original_mode}' to '{fallback_mode}' "
                f"because account quota for '{original_mode}' was unavailable.*\n"
            )
        else:
            notice = (
                f"*Note: Fell back from '{original_mode}' to '{fallback_mode}' "
                f"because the requested mode was unavailable.*\n"
            )

        parts.append(notice)

    metadata_bits = []
    if requested_model := data.get("requested_model"):
        metadata_bits.append(f"Requested: `{requested_model}`")
    if resolved_mode := data.get("resolved_mode"):
        metadata_bits.append(f"Mode: `{resolved_mode}`")
    if resolved_model := data.get("resolved_model"):
        resolved_label = get_resolved_model_label(resolved_model)
        if resolved_label and resolved_label != resolved_model:
            metadata_bits.append(f"Model: `{resolved_model}` ({resolved_label})")
        else:
            metadata_bits.append(f"Model: `{resolved_model}`")

    if metadata_bits:
        parts.append("*" + " | ".join(metadata_bits) + "*\n")

    # Main answer
    if answer := data.get("answer"):
        parts.append(answer)

    # Sources
    if sources := data.get("sources"):
        total = len(sources)
        shown_limit = 30

        parts.append(f"\n\n## Sources referenced ({total} total)")
        for i, source in enumerate(sources[:shown_limit], 1):
            url = source.get("url", "")
            title = source.get("title", url)
            parts.append(f"{i}. [{title}]({url})")

        if total > shown_limit:
            parts.append(f"\n*+ {total - shown_limit} more sources*")

    return "\n".join(parts) if parts else "No response received."


async def run_server():
    """Run the MCP server."""
    logger.info("Starting Perplexity MCP server...")

    # Initialize pool on startup to validate config
    try:
        pool = get_pool(config_writable=False)
        client_count = len(pool.clients)
        logger.info(f"Initialized pool with {client_count} client(s)")

        # Load shared state from monitor (if available)
        if pool.load_state():
            logger.info("Loaded shared pool state from monitor")
    except Exception as e:
        logger.warning(f"Pool initialization failed: {e}")
        logger.warning("Server will start but tools may fail until config is fixed")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point for the MCP server."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
