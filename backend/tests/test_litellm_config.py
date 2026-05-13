"""Unit tests for generate_litellm_config().

These are pure unit tests — no database required.  Each test constructs
lightweight Resource stubs and calls the config generator directly.
"""

import yaml

from blackbeard.litellm.config_gen import generate_litellm_config
from blackbeard.kinds import ResourceKind
from blackbeard.models.resource import Resource


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_llm_conn(name: str, spec: dict) -> Resource:
    r = Resource()
    r.kind = ResourceKind.LLM_CONNECTION
    r.name = name
    r.namespace = "default"
    r.spec = spec
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generate_config_vertex_ai():
    """vertex_ai provider should produce 'vertex_ai/<model>' in litellm_params."""
    conn = make_llm_conn(
        "claude-conn",
        {"provider": "vertex_ai", "model": "claude-sonnet-4-6"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    assert len(config["model_list"]) == 1
    entry = config["model_list"][0]
    assert entry["model_name"] == "claude-conn"
    assert entry["litellm_params"]["model"] == "vertex_ai/claude-sonnet-4-6"


def test_generate_config_openai():
    """openai provider should pass model string through unchanged."""
    conn = make_llm_conn(
        "gpt4-conn",
        {"provider": "openai", "model": "gpt-4o"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    entry = config["model_list"][0]
    assert entry["litellm_params"]["model"] == "gpt-4o"


def test_generate_config_generic_provider():
    """Unknown provider should produce '<provider>/<model>'."""
    conn = make_llm_conn(
        "custom-conn",
        {"provider": "anthropic", "model": "claude-3-opus"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    entry = config["model_list"][0]
    assert entry["litellm_params"]["model"] == "anthropic/claude-3-opus"


def test_generate_config_multiple_models():
    """Multiple LLMConnections should produce multiple model_list entries."""
    conns = [
        make_llm_conn("conn-1", {"provider": "openai", "model": "gpt-4o"}),
        make_llm_conn("conn-2", {"provider": "vertex_ai", "model": "gemini-pro"}),
        make_llm_conn("conn-3", {"provider": "anthropic", "model": "claude-3-sonnet"}),
    ]
    config_str = generate_litellm_config(conns)
    config = yaml.safe_load(config_str)

    assert len(config["model_list"]) == 3
    names = [e["model_name"] for e in config["model_list"]]
    assert "conn-1" in names
    assert "conn-2" in names
    assert "conn-3" in names


def test_generate_config_with_parameters():
    """temperature and max_tokens in spec.parameters should appear in litellm_params."""
    conn = make_llm_conn(
        "tuned-conn",
        {
            "provider": "openai",
            "model": "gpt-4o",
            "parameters": {"temperature": 0.3, "max_tokens": 1024},
        },
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    params = config["model_list"][0]["litellm_params"]
    assert params["temperature"] == 0.3
    assert params["max_tokens"] == 1024


def test_generate_config_with_api_key_env():
    """api_key_env in spec should become 'os.environ/<env>' in litellm_params."""
    conn = make_llm_conn(
        "keyed-conn",
        {"provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    params = config["model_list"][0]["litellm_params"]
    assert params["api_key"] == "os.environ/OPENAI_API_KEY"


def test_generate_config_with_base_url():
    """base_url in spec should become api_base in litellm_params."""
    conn = make_llm_conn(
        "local-conn",
        {"provider": "openai", "model": "local-model", "base_url": "http://localhost:11434"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    params = config["model_list"][0]["litellm_params"]
    assert params["api_base"] == "http://localhost:11434"


def test_generate_config_empty_list():
    """Empty list of connections should produce a valid config with all sections."""
    config_str = generate_litellm_config([])
    config = yaml.safe_load(config_str)

    assert config["model_list"] == []
    assert "litellm_settings" in config
    assert "general_settings" in config
    assert "router_settings" in config


def test_generate_config_structure():
    """Generated config should include all required top-level sections."""
    conn = make_llm_conn("any", {"provider": "openai", "model": "gpt-4o"})
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    assert "model_list" in config
    assert "litellm_settings" in config
    assert "general_settings" in config
    assert "router_settings" in config
    assert config["litellm_settings"]["drop_params"] is True
    assert config["litellm_settings"]["num_retries"] == 3


def test_generate_config_vertex_ai_includes_project_location():
    """vertex_ai with vertex spec should include vertex_project/vertex_location."""
    conn = make_llm_conn(
        "vertex-explicit",
        {
            "provider": "vertex_ai",
            "model": "claude-sonnet-4-6",
            "vertex": {"project": "my-gcp-project", "location": "us-central1"},
        },
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    params = config["model_list"][0]["litellm_params"]
    assert params["vertex_project"] == "my-gcp-project"
    assert params["vertex_location"] == "us-central1"


def test_generate_config_is_valid_yaml():
    """Output should always be parseable YAML."""
    conns = [
        make_llm_conn(f"conn-{i}", {"provider": "openai", "model": f"model-{i}"})
        for i in range(5)
    ]
    config_str = generate_litellm_config(conns)
    parsed = yaml.safe_load(config_str)
    assert isinstance(parsed, dict)


def test_generate_config_model_name_with_special_chars():
    """Model names with dots/slashes should be preserved in litellm_params."""
    conn = make_llm_conn(
        "special-conn",
        {"provider": "vertex_ai", "model": "claude-3.5-sonnet@20240620"},
    )
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    entry = config["model_list"][0]
    assert entry["model_name"] == "special-conn"
    assert "claude-3.5-sonnet@20240620" in entry["litellm_params"]["model"]


def test_generate_config_no_parameters_key():
    """Connections without 'parameters' should not inject temperature/max_tokens."""
    conn = make_llm_conn("bare-conn", {"provider": "openai", "model": "gpt-4o"})
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)

    params = config["model_list"][0]["litellm_params"]
    assert "temperature" not in params
    assert "max_tokens" not in params
