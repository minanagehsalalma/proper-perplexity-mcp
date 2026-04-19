"""Smoke tests for perplexity.config with console-style output."""

from perplexity import config


def test_api_endpoints_structure() -> None:
    print("console.log -> validating API endpoints and versions")
    assert config.API_BASE_URL.startswith("https://")
    assert config.API_VERSION.count(".") >= 1
    assert config.ENDPOINT_SSE_ASK.startswith(config.API_BASE_URL)


def test_search_modes_and_models() -> None:
    print("console.log -> checking search modes and model mappings")
    assert set(config.SEARCH_MODES) >= {"auto", "pro", "reasoning"}
    pro_models = config.MODEL_MAPPINGS["pro"]
    assert None in pro_models
    assert "Sonar" in pro_models
    assert "GPT-5.4" in pro_models
    assert "deep research" in config.MODEL_MAPPINGS


def test_model_aliases_resolve_current_ui_names() -> None:
    print("console.log -> resolving current Perplexity model aliases")
    assert config.normalize_model_name("pro", "gpt54") == "GPT-5.4"
    assert config.normalize_model_name("pro", "Claude Sonnet 4.6") == "Claude Sonnet 4.6"
    assert (
        config.normalize_model_name("reasoning", "claude46sonnetthinking")
        == "Claude Sonnet 4.6 Thinking"
    )
    assert config.normalize_model_name("reasoning", "grok-4.1-thinking") == "Grok 4.1 Reasoning"
