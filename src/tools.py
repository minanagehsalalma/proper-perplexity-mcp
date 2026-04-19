"""
MCP Tool definitions for Perplexity.

Two tools:
- perplexity_ask: Pro search + reasoning (auto-detected from model name)
- perplexity_research: Deep research mode

Tool descriptions are optimized for LLM agents.
"""

from mcp.types import Tool, ToolAnnotations

from perplexity.config import get_public_model_choices

# Reasoning model keywords — if model name contains these, use reasoning mode
_REASONING_KEYWORDS = ("thinking", "reasoning")
_ASK_MODEL_CHOICES = get_public_model_choices("pro", "reasoning")
_ATTACHMENT_ITEM_SCHEMA = {
    "oneOf": [
        {
            "type": "string",
            "description": "Local path to an image or document to upload with the query.",
        },
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Local file path to upload. Optional when inline base64 data is provided.",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Upload filename override. Required for raw base64 payloads unless the "
                        "base64_data field is a data URL with a recognizable MIME type."
                    ),
                },
                "base64_data": {
                    "type": "string",
                    "description": (
                        "Inline file payload as base64. Data URLs such as "
                        "'data:image/png;base64,...' are also accepted."
                    ),
                },
            },
            "additionalProperties": False,
        },
    ]
}
_ATTACHMENTS_SCHEMA = {
    "type": "array",
    "items": _ATTACHMENT_ITEM_SCHEMA,
    "description": (
        "Optional images or documents to upload with the query. Each item can be either "
        "a local file path string or an object using `path` or `base64_data`."
    ),
}
_RESPONSE_FORMAT_SCHEMA = {
    "type": "string",
    "enum": ["markdown", "json"],
    "description": (
        "Preferred response shape. `markdown` returns a human-readable answer and also includes "
        "structured MCP output. `json` returns the same structured payload rendered as JSON text."
    ),
}
_SOURCE_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "url": {"type": "string"},
    },
    "required": ["url"],
    "additionalProperties": False,
}
_ATTACHMENT_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "mime_type": {"type": ["string", "null"]},
        "size_bytes": {"type": "integer", "minimum": 0},
        "origin": {"type": "string", "enum": ["path", "base64"]},
        "path": {"type": "string"},
    },
    "required": ["filename", "mime_type", "size_bytes", "origin"],
    "additionalProperties": False,
}
_RESULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "error"]},
        "tool": {"type": "string", "enum": ["perplexity_ask", "perplexity_research"]},
        "meta": {
            "type": "object",
            "properties": {
                "requested_mode": {"type": "string"},
                "requested_model": {"type": ["string", "null"]},
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["web", "scholar", "social"]},
                },
                "language": {"type": "string"},
                "response_format": {"type": "string", "enum": ["markdown", "json"]},
            },
            "required": ["requested_mode", "requested_model", "sources", "language", "response_format"],
            "additionalProperties": False,
        },
        "attachments": {
            "type": "array",
            "items": _ATTACHMENT_RESULT_SCHEMA,
        },
        "answer": {"type": "string"},
        "sources": {
            "type": "array",
            "items": _SOURCE_RESULT_SCHEMA,
        },
        "resolved_mode": {"type": "string"},
        "resolved_model": {"type": "string"},
        "requested_model": {"type": "string"},
        "fallback": {"type": "boolean"},
        "fallback_mode": {"type": "string"},
        "fallback_reason": {"type": "string"},
        "original_mode": {"type": "string"},
        "original_model": {"type": ["string", "null"]},
        "error_type": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["status", "tool", "meta", "attachments"],
    "additionalProperties": False,
}


def get_mode_for_tool(name: str, model: str = None) -> str:
    """Determine the Perplexity search mode from tool name and model."""
    if name == "perplexity_research":
        return "deep research"
    # perplexity_ask — auto-detect reasoning mode from model name
    if model and any(kw in model.lower() for kw in _REASONING_KEYWORDS):
        return "reasoning"
    return "pro"


# Default sources per tool
TOOL_DEFAULT_SOURCES = {
    "perplexity_ask": ["web"],
    "perplexity_research": ["web", "scholar"],
}

# Tool definitions for MCP server
TOOLS = [
    Tool(
        name="perplexity_ask",
        annotations=ToolAnnotations(
            title="Perplexity Ask",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
        description=(
            "AI-powered answer engine for tech questions, documentation lookups, and how-to guides. "
            "Perplexity is an AI model (not a search engine) - provide context and specific requirements "
            "in your query for better results. Leave 'model' unset to use Perplexity's default Best mode; "
            "when the user explicitly asks for a Perplexity website model, pass the matching label exactly. "
            "Returns synthesized answers with citations. Supports optional image/document uploads "
            "through `attachments`."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural language question with context. Include specific requirements, "
                        "constraints, or use case. Example: 'How to implement JWT auth in Next.js 14 "
                        "App Router with httpOnly cookies for a SaaS app?'"
                    )
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["web", "scholar", "social"]},
                    "description": "Information sources to search. Default: ['web']"
                },
                "language": {
                    "type": "string",
                    "description": "ISO 639 language code. Default: 'en-US'"
                },
                "model": {
                    "type": "string",
                    "enum": _ASK_MODEL_CHOICES,
                    "description": (
                        "Optional model selection using current Perplexity web-app labels. "
                        "Leave unset for the default Best model. Thinking or Reasoning variants "
                        "automatically switch this tool into reasoning mode."
                    )
                },
                "attachments": _ATTACHMENTS_SCHEMA,
                "response_format": _RESPONSE_FORMAT_SCHEMA,
            },
            "required": ["query"]
        },
        outputSchema=_RESULT_OUTPUT_SCHEMA,
    ),
    Tool(
        name="perplexity_research",
        annotations=ToolAnnotations(
            title="Perplexity Research",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
        description=(
            "Deep research agent for comprehensive analysis of complex topics. "
            "Provide detailed context about what you need and why - this AI model spends more time "
            "gathering and synthesizing information. Returns extensive reports with 10-30+ citations. "
            "Use for architecture decisions, technology comparisons, or thorough investigations. "
            "Supports optional image/document uploads through `attachments`."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Detailed research question with full context. Explain the problem, "
                        "constraints, and what insights you need. Example: 'Best practices for "
                        "LLM API key rotation in production Node.js apps - need patterns for "
                        "zero-downtime rotation, secret storage options, and monitoring.'"
                    )
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["web", "scholar", "social"]},
                    "description": "Information sources. Default: ['web', 'scholar']"
                },
                "language": {
                    "type": "string",
                    "description": "ISO 639 language code. Default: 'en-US'"
                },
                "attachments": _ATTACHMENTS_SCHEMA,
                "response_format": _RESPONSE_FORMAT_SCHEMA,
            },
            "required": ["query"]
        },
        outputSchema=_RESULT_OUTPUT_SCHEMA,
    ),
]
