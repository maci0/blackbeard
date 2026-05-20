"""Unit tests for resource validation (JSON Schema + ref format checks).

Covers validate_resource() for all five resource kinds plus error paths.
"""

from blackbeard.resources.exceptions import ValidationError
from blackbeard.resources.validator import validate_resource
from tests.conftest import has_validation_error as _has_error

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def test_valid_agent():
    spec = {
        "role": "Research Analyst",
        "goal": "Find insights",
        "backstory": "Years of research experience",
    }
    errors, _ = validate_resource("Agent", spec)
    assert errors == []


def test_valid_agent_with_optional_fields():
    spec = {
        "role": "Writer",
        "goal": "Write well",
        "backstory": "Always loved writing",
        "llm": "ref:llm-connections/gpt4",
        "tools": ["ref:tools/search"],
        "allow_delegation": False,
        "verbose": True,
        "max_iter": 10,
        "memory": True,
    }
    errors, _ = validate_resource("Agent", spec)
    assert errors == []


def test_agent_missing_required():
    """Missing 'role' should produce a validation error."""
    spec = {
        "goal": "Find insights",
        "backstory": "Expert",
    }
    errors, _ = validate_resource("Agent", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="role")


def test_agent_missing_all_required():
    errors, _ = validate_resource("Agent", {})
    assert len(errors) >= 3
    fields_mentioned = " ".join(e.message.lower() for e in errors)
    assert "role" in fields_mentioned
    assert "goal" in fields_mentioned
    assert "backstory" in fields_mentioned


def test_agent_extra_field():
    """additionalProperties: false — unknown fields should fail."""
    spec = {
        "role": "Analyst",
        "goal": "Analyse",
        "backstory": "Always has been",
        "unknown_field": "bad",
    }
    errors, _ = validate_resource("Agent", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


def test_valid_task():
    spec = {
        "description": "Gather data from the web",
        "expected_output": "A JSON blob of data",
        "agent": "ref:agents/researcher",
    }
    errors, _ = validate_resource("Task", spec)
    assert errors == []


def test_task_missing_agent():
    spec = {
        "description": "Do something",
        "expected_output": "Some output",
    }
    errors, _ = validate_resource("Task", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="agent")


def test_task_missing_description():
    spec = {
        "expected_output": "Output",
        "agent": "ref:agents/researcher",
    }
    errors, _ = validate_resource("Task", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="description")


def test_task_extra_field():
    spec = {
        "description": "Do something",
        "expected_output": "Output",
        "agent": "ref:agents/researcher",
        "not_a_real_field": True,
    }
    errors, _ = validate_resource("Task", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


def test_valid_task_with_context():
    spec = {
        "description": "Summarise findings",
        "expected_output": "Summary",
        "agent": "ref:agents/writer",
        "context": ["ref:tasks/gather-data"],
        "async_execution": False,
    }
    errors, _ = validate_resource("Task", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------


def test_valid_crew():
    spec = {
        "process": "sequential",
        "agents": ["ref:agents/researcher"],
        "tasks": ["ref:tasks/gather-data"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert errors == []


def test_crew_invalid_process():
    """process must be 'sequential' or 'hierarchical'."""
    spec = {
        "process": "invalid",
        "agents": ["ref:agents/researcher"],
        "tasks": ["ref:tasks/gather-data"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="invalid")


def test_crew_missing_agents():
    spec = {
        "process": "sequential",
        "tasks": ["ref:tasks/t1"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="agents")


def test_crew_empty_agents_list():
    """agents must have at least one item (minItems: 1)."""
    spec = {
        "process": "sequential",
        "agents": [],
        "tasks": ["ref:tasks/t1"],
    }
    errors, _ = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="agents")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


def test_valid_tool():
    spec = {
        "type": "python",
        "class_path": "crewai_tools.SearchTool",
        "description": "Searches the web",
    }
    errors, _ = validate_resource("Tool", spec)
    assert errors == []


def test_valid_tool_wasm():
    spec = {
        "type": "wasm",
        "wasm_module": "s3://bucket/tool.wasm",
        "sandbox": "wasm",
    }
    errors, _ = validate_resource("Tool", spec)
    assert errors == []


def test_tool_missing_type():
    errors, _ = validate_resource("Tool", {"class_path": "foo.Bar"})
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="type")


def test_tool_invalid_type_enum():
    spec = {"type": "java"}
    errors, _ = validate_resource("Tool", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="type")


# ---------------------------------------------------------------------------
# LLMConnection
# ---------------------------------------------------------------------------


def test_valid_llm_connection():
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert errors == []


def test_valid_llm_connection_with_parameters():
    spec = {
        "provider": "google",
        "model": "gemini-1.5-pro",
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "vertex": {
            "project": "my-project",
            "location": "us-central1",
        },
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert errors == []


def test_llm_connection_missing_model():
    errors, _ = validate_resource("LLMConnection", {"provider": "openai"})
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="model")


def test_llm_connection_missing_provider():
    errors, _ = validate_resource("LLMConnection", {"model": "gpt-4o"})
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="provider")


# ---------------------------------------------------------------------------
# LLMConnection — SSRF and env-var exfiltration protection
# ---------------------------------------------------------------------------


def test_llm_connection_blocks_internal_base_url():
    """base_url pointing to localhost should be rejected (SSRF protection)."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://localhost:11434",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


def test_llm_connection_blocks_private_ip_base_url():
    """base_url pointing to private IP should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://10.0.0.1:8080/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


def test_llm_connection_blocks_metadata_base_url():
    """base_url pointing to cloud metadata endpoint should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://metadata.google.internal/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


def test_llm_connection_blocks_internal_env_var():
    """api_key_env referencing internal env vars should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key_env": "BLACKBEARD_DB_KEY",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="api_key_env", msg_contains="internal")


def test_llm_connection_blocks_database_env_var():
    """api_key_env referencing DATABASE_ prefixed vars should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "api_key_env": "DATABASE_SECRET",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="api_key_env", msg_contains="internal")


def test_llm_connection_allows_external_base_url(monkeypatch):
    """base_url pointing to a public host should pass with zero validation errors."""
    import socket

    def _fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("104.18.7.145", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# KnowledgeSource — path traversal and SSRF protection
# ---------------------------------------------------------------------------


def test_knowledge_source_blocks_path_traversal():
    """KnowledgeSource file_paths with '../' should be rejected."""
    spec = {"type": "text", "file_paths": ["../../etc/passwd"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="file_paths")


def test_knowledge_source_blocks_absolute_path():
    """KnowledgeSource file_paths with absolute path should be rejected."""
    spec = {"type": "text", "file_paths": ["/etc/passwd"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="file_paths")


def test_knowledge_source_blocks_internal_url():
    """KnowledgeSource urls pointing to localhost should be rejected (SSRF)."""
    spec = {"type": "url", "urls": ["http://localhost:8080/secret"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert _has_error(errors, field_contains="url", msg_contains="internal")


def test_knowledge_source_blocks_metadata_url():
    """KnowledgeSource urls pointing to cloud metadata should be rejected."""
    spec = {"type": "url", "urls": ["http://169.254.169.254/latest/meta-data/"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert _has_error(errors, field_contains="url", msg_contains="internal")


def test_knowledge_source_allows_safe_paths():
    """KnowledgeSource with safe relative paths should pass."""
    spec = {"type": "text", "file_paths": ["data/notes.txt", "docs/guide.pdf"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# Tool — SSRF and env-var exfiltration protection
# ---------------------------------------------------------------------------


def test_tool_blocks_internal_url():
    """Tool spec.url pointing to localhost should be rejected (SSRF)."""
    spec = {"type": "mcp-http", "url": "http://localhost:8080/mcp"}
    errors, _ = validate_resource("Tool", spec)
    assert _has_error(errors, field_contains="url", msg_contains="internal")


def test_tool_blocks_private_ip_url():
    """Tool spec.url pointing to private IP should be rejected."""
    spec = {"type": "mcp-http", "url": "http://10.0.0.1:9090/mcp"}
    errors, _ = validate_resource("Tool", spec)
    assert _has_error(errors, field_contains="url", msg_contains="internal")


def test_tool_blocks_internal_env_var():
    """Tool spec.env referencing internal env vars should be rejected."""
    spec = {"type": "mcp-stdio", "command": "server", "env": {"DATABASE_URL": "postgres://x"}}
    errors, _ = validate_resource("Tool", spec)
    assert _has_error(errors, field_contains="env", msg_contains="restricted")


def test_tool_allows_external_url(monkeypatch):
    """Tool with external URL should pass validation."""
    import socket

    def _fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    spec = {"type": "mcp-http", "url": "https://api.example.com/mcp"}
    errors, _ = validate_resource("Tool", spec)
    assert errors == []


def test_tool_blocks_exact_blocked_env_var():
    """Tool env with exact-match blocked vars (PATH, LD_PRELOAD, HOME) should be rejected."""
    for var in ("PATH", "LD_PRELOAD", "HOME"):
        spec = {"type": "mcp-stdio", "command": "server", "env": {var: "/tmp"}}
        errors, _ = validate_resource("Tool", spec)
        assert _has_error(errors, field_contains="env", msg_contains="restricted"), (
            f"Expected rejection for env var '{var}'"
        )


def test_tool_blocks_env_shell_expansion():
    """Tool env values referencing internal vars via $ expansion should be rejected."""
    spec = {
        "type": "mcp-stdio",
        "command": "server",
        "env": {"MY_VAR": "prefix-$DATABASE_URL"},
    }
    errors, _ = validate_resource("Tool", spec)
    assert _has_error(errors, field_contains="env", msg_contains="shell expansion")


# ---------------------------------------------------------------------------
# URL validation — scheme and embedded credentials
# ---------------------------------------------------------------------------


def test_llm_connection_blocks_ftp_scheme():
    """base_url with non-http(s) scheme should be rejected."""
    spec = {"provider": "openai", "model": "gpt-4o", "base_url": "ftp://evil.com/v1"}
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="http")


def test_llm_connection_blocks_embedded_credentials():
    """base_url with embedded user:pass should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://user:pass@api.example.com/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="credentials")


# ---------------------------------------------------------------------------
# KnowledgeSource — backslash path traversal
# ---------------------------------------------------------------------------


def test_knowledge_source_blocks_backslash_traversal():
    """KnowledgeSource file_paths with backslash traversal should be rejected."""
    spec = {"type": "text", "file_paths": ["..\\..\\etc\\passwd"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="file_paths")


def test_knowledge_source_blocks_tilde_path():
    """KnowledgeSource file_paths starting with ~ should be rejected."""
    spec = {"type": "text", "file_paths": ["~/secret.txt"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="file_paths")


# ---------------------------------------------------------------------------
# LLMConnection — additional SSRF edge cases
# ---------------------------------------------------------------------------


def test_llm_connection_blocks_link_local_ip():
    """base_url pointing to link-local IP (169.254.x.x) should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://169.254.169.254/latest/meta-data",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


def test_llm_connection_blocks_kubernetes_svc():
    """base_url pointing to Kubernetes service domain should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://litellm.default.svc.cluster.local:4000/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


def test_llm_connection_blocks_obfuscated_ip():
    """base_url with decimal IP representation of 127.0.0.1 should be rejected."""
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "http://2130706433:8080/v1",
    }
    errors, _ = validate_resource("LLMConnection", spec)
    assert _has_error(errors, field_contains="base_url", msg_contains="internal")


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


def test_unknown_kind():
    errors, _ = validate_resource("Widget", {"foo": "bar"})
    assert len(errors) == 1
    assert _has_error(errors, field_contains="kind", msg_contains="unknown")


def test_unknown_kind_returns_immediately():
    """Should not attempt schema validation when kind is unknown."""
    errors, _ = validate_resource("NotARealKind", {})
    assert len(errors) == 1
    assert errors[0].field == "kind"


def test_validation_error_to_dict():
    """ValidationError.to_dict() should return field and message."""
    err = ValidationError(field="spec.role", message="Required field missing")
    d = err.to_dict()
    assert d == {"field": "spec.role", "message": "Required field missing"}


# ---------------------------------------------------------------------------
# is_internal_host edge cases (SSRF bypass prevention)
# ---------------------------------------------------------------------------


from blackbeard.resources.validator import is_internal_host


def test_is_internal_host_localhost():
    assert is_internal_host("localhost") is True


def test_is_internal_host_loopback_ip():
    assert is_internal_host("127.0.0.1") is True


def test_is_internal_host_metadata_google():
    assert is_internal_host("metadata.google.internal") is True


def test_is_internal_host_k8s_svc():
    assert is_internal_host("service.default.svc.cluster.local") is True


def test_is_internal_host_trailing_dot():
    """Trailing dot normalization should still detect internal hosts."""
    assert is_internal_host("localhost.") is True


def test_is_internal_host_case_insensitive():
    """SSRF check should be case-insensitive."""
    assert is_internal_host("LOCALHOST") is True
    assert is_internal_host("Metadata.Google.Internal") is True


def test_is_internal_host_external_ok():
    assert is_internal_host("api.openai.com") is False


def test_is_internal_host_private_10():
    assert is_internal_host("10.0.0.1") is True


def test_is_internal_host_private_172():
    assert is_internal_host("172.16.0.1") is True


def test_is_internal_host_private_192():
    assert is_internal_host("192.168.1.1") is True


def test_is_internal_host_link_local():
    assert is_internal_host("169.254.169.254") is True


def test_is_internal_host_ipv6_loopback():
    assert is_internal_host("::1") is True


# ---------------------------------------------------------------------------
# _is_path_traversal edge cases
# ---------------------------------------------------------------------------


from blackbeard.resources.validator import _is_path_traversal


def test_path_traversal_dotdot():
    assert _is_path_traversal("../../etc/passwd") is True


def test_path_traversal_absolute():
    assert _is_path_traversal("/etc/passwd") is True


def test_path_traversal_tilde():
    assert _is_path_traversal("~/secret") is True


def test_path_traversal_backslash():
    assert _is_path_traversal("..\\..\\windows") is True


def test_path_traversal_safe_relative():
    assert _is_path_traversal("data/notes.txt") is False


def test_path_traversal_safe_filename():
    assert _is_path_traversal("report.json") is False


# ---------------------------------------------------------------------------
# validate_resource returns refs on success
# ---------------------------------------------------------------------------


def test_validate_resource_returns_refs():
    """validate_resource should return extracted refs for successful validation."""
    spec = {
        "description": "Test task",
        "expected_output": "Output",
        "agent": "ref:agents/researcher",
        "context": ["ref:tasks/gather-data"],
    }
    errors, refs = validate_resource("Task", spec)
    assert errors == []
    assert refs is not None
    assert len(refs) == 2
    raw_values = {r.raw for r in refs}
    assert "ref:agents/researcher" in raw_values
    assert "ref:tasks/gather-data" in raw_values


def test_validate_resource_no_refs():
    """validate_resource should return empty refs list for specs without refs."""
    spec = {"role": "R", "goal": "G", "backstory": "B"}
    errors, refs = validate_resource("Agent", spec)
    assert errors == []
    assert refs is not None
    assert len(refs) == 0
