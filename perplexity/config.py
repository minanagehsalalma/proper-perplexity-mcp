"""
Configuration constants for Perplexity AI API.

This module contains all configurable constants used throughout the library.
Modify these values to customize behavior without changing core code.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

# Load environment variables from .env file
from dotenv import load_dotenv

# Try to load .env from multiple locations
_env_locations = [
    Path.cwd() / ".env",  # Current working directory
    Path(__file__).parent.parent / ".env",  # Project root
    Path.home() / ".perplexity" / ".env",  # User home directory
]

for _env_path in _env_locations:
    if _env_path.exists():
        load_dotenv(_env_path)
        break
else:
    # Load from default location if no .env found
    load_dotenv()

# SOCKS Proxy Configuration
# Format: socks5://[user[:pass]@]host[:port][#remark]
# Examples:
#   socks5://127.0.0.1:1080
#   socks5://user:pass@127.0.0.1:1080
#   socks5://user:pass@127.0.0.1:1080#my-proxy
SOCKS_PROXY: Optional[str] = os.getenv("SOCKS_PROXY", None)


def _normalize_ip_resolve(value: Optional[str]) -> str:
    """Map environment values to curl's supported IP resolution modes."""
    if not value:
        return "ipv4" if os.name == "nt" else "auto"

    normalized = value.strip().lower()
    if normalized in {"4", "ipv4", "v4"}:
        return "ipv4"
    if normalized in {"6", "ipv6", "v6"}:
        return "ipv6"
    return "auto"


# curl_cffi currently hits broken IPv6/dual-stack paths on this Windows machine.
# Prefer IPv4 by default on Windows, but keep an env override for other networks.
PPLX_IP_RESOLVE: str = _normalize_ip_resolve(os.getenv("PPLX_IP_RESOLVE"))

# Token Pool Configuration
# Path to JSON config file containing multiple tokens for load balancing
# Format: {"tokens": [{"id": "user1", "csrf_token": "xxx", "session_token": "yyy"}, ...]}
PPLX_TOKEN_POOL_CONFIG: Optional[str] = os.getenv("PPLX_TOKEN_POOL_CONFIG", None)

# API Configuration
API_BASE_URL = "https://www.perplexity.ai"
API_VERSION = "2.18"
API_TIMEOUT = 30

# Endpoints
ENDPOINT_AUTH_SESSION = f"{API_BASE_URL}/api/auth/session"
ENDPOINT_SSE_ASK = f"{API_BASE_URL}/rest/sse/perplexity_ask"
ENDPOINT_UPLOAD_URL = f"{API_BASE_URL}/rest/uploads/create_upload_url"
ENDPOINT_SOCKET_IO = f"{API_BASE_URL}/socket.io/"
ENDPOINT_RATE_LIMIT = f"{API_BASE_URL}/rest/rate-limit"
ENDPOINT_RATE_LIMIT_STATUS = f"{API_BASE_URL}/rest/rate-limit/status"

# Search Modes
SEARCH_MODES = ["auto", "pro", "reasoning", "deep research"]
SEARCH_SOURCES = ["web", "scholar", "social"]
SEARCH_LANGUAGES = ["en-US", "en-GB", "pt-BR", "es-ES", "fr-FR", "de-DE", "zh-CN"]

# Model Mappings
# These names intentionally follow the Perplexity web app model picker labels where
# we have verified the corresponding internal model IDs.
MODEL_MAPPINGS: Dict[str, Dict[Optional[str], str]] = {
    "auto": {None: "turbo"},
    "pro": {
        None: "pplx_pro",
        "Sonar": "experimental",
        "GPT-5.4": "gpt54",
        "Claude Sonnet 4.6": "claude46sonnet",
        "Grok 4.1": "grok41nonreasoning",
    },
    "reasoning": {
        None: "pplx_reasoning",
        "GPT-5.4 Thinking": "gpt54_thinking",
        "Claude Sonnet 4.6 Thinking": "claude46sonnetthinking",
        "Grok 4.1 Reasoning": "grok41reasoning",
        "Kimi K2.5 Thinking": "kimik25thinking",
    },
    "deep research": {None: "pplx_alpha"},
}

_MODEL_ALIAS_SETS: Dict[str, Dict[str, set[str]]] = {
    "pro": {
        "Sonar": {"sonar", "experimental"},
        "GPT-5.4": {"gpt-5.4", "gpt54"},
        "Claude Sonnet 4.6": {
            "claude sonnet 4.6",
            "claude-sonnet-4.6",
            "claude46sonnet",
        },
        "Grok 4.1": {"grok 4.1", "grok-4.1", "grok41", "grok41nonreasoning"},
    },
    "reasoning": {
        "GPT-5.4 Thinking": {
            "gpt-5.4 thinking",
            "gpt-5.4-thinking",
            "gpt54_thinking",
            "gpt54thinking",
        },
        "Claude Sonnet 4.6 Thinking": {
            "claude sonnet 4.6 thinking",
            "claude-sonnet-4.6-thinking",
            "claude46sonnetthinking",
        },
        "Grok 4.1 Reasoning": {
            "grok 4.1 reasoning",
            "grok 4.1 thinking",
            "grok-4.1-reasoning",
            "grok-4.1-thinking",
            "grok41reasoning",
        },
        "Kimi K2.5 Thinking": {
            "kimi k2.5 thinking",
            "kimi-k2.5-thinking",
            "kimik25thinking",
        },
    },
}

_RESOLVED_MODEL_DISPLAY_NAMES = {
    "turbo": "Auto",
    "pplx_pro": "Best",
    "pplx_reasoning": "Perplexity Reasoning",
    "pplx_alpha": "Deep Research",
}


def _normalize_model_alias(value: str) -> str:
    """Normalize model aliases so UI labels, slugs, and IDs resolve consistently."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


MODEL_ALIASES: Dict[str, Dict[str, str]] = {}
for _mode, _mapping in MODEL_MAPPINGS.items():
    _alias_map: Dict[str, str] = {}
    for _public_name, _internal_name in _mapping.items():
        if _public_name is None:
            _RESOLVED_MODEL_DISPLAY_NAMES.setdefault(_internal_name, _RESOLVED_MODEL_DISPLAY_NAMES.get(_internal_name, _internal_name))
            continue

        _alias_map[_normalize_model_alias(_public_name)] = _public_name
        _alias_map[_normalize_model_alias(_internal_name)] = _public_name
        for _alias in _MODEL_ALIAS_SETS.get(_mode, {}).get(_public_name, set()):
            _alias_map[_normalize_model_alias(_alias)] = _public_name
        _RESOLVED_MODEL_DISPLAY_NAMES.setdefault(_internal_name, _public_name)

    MODEL_ALIASES[_mode] = _alias_map


def get_public_model_choices(*modes: str) -> List[str]:
    """Return the canonical public model labels for the given modes."""
    choices: List[str] = []
    for mode in modes:
        choices.extend(
            model_name
            for model_name in MODEL_MAPPINGS.get(mode, {})
            if model_name is not None
        )
    return choices


def normalize_model_name(mode: str, model: Optional[str]) -> Optional[str]:
    """Resolve a model alias or internal ID to the canonical public label."""
    if model is None:
        return None
    if mode not in MODEL_ALIASES:
        return None
    return MODEL_ALIASES[mode].get(_normalize_model_alias(model))


def get_model_preference(mode: str, model: Optional[str]) -> str:
    """Return the internal model_preference value expected by Perplexity."""
    canonical_model = normalize_model_name(mode, model)
    if model is not None and canonical_model is None:
        raise KeyError(f"Unknown model '{model}' for mode '{mode}'")
    return MODEL_MAPPINGS[mode][canonical_model]


def get_resolved_model_label(model_id: Optional[str]) -> Optional[str]:
    """Map a resolved internal model ID back to a friendly public label when known."""
    if not model_id:
        return None
    return _RESOLVED_MODEL_DISPLAY_NAMES.get(model_id)

# HTTP Headers Template
DEFAULT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",  # noqa: E501
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "dnt": "1",
    "priority": "u=0, i",
    "sec-ch-ua": '"Not;A=Brand";v="24", "Chromium";v="128"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-full-version": '"128.0.6613.120"',
    "sec-ch-ua-full-version-list": '"Not;A=Brand";v="24.0.0.0", "Chromium";v="128.0.6613.120"',  # noqa: E501
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"19.0.0"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",  # noqa: E501
}

# Retry Configuration
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2
RETRY_EXCEPTIONS = (ConnectionError, TimeoutError)

# Logging Configuration
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "DEBUG"
LOG_FILE = "perplexity.log"

# Rate Limiting
RATE_LIMIT_MIN_DELAY = 1.0  # seconds
RATE_LIMIT_MAX_DELAY = 3.0  # seconds
RATE_LIMIT_ENABLED = True

# Admin Authentication
# Set this environment variable to enable admin authentication for pool management
# If not set, admin operations will be disabled for security
ADMIN_TOKEN: Optional[str] = os.getenv("PPLX_ADMIN_TOKEN", None)
