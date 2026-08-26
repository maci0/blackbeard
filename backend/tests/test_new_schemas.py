"""Tests for AgentPolicy and Guardrail JSON Schema validation."""

import pytest

from blackbeard.resources.validator import validate_resource
from tests.conftest import has_validation_error as _has_error

# ---------------------------------------------------------------------------
# Namespace schema
# ---------------------------------------------------------------------------


def test_valid_namespace_minimal():
    """Namespace with no spec fields should pass (all optional)."""
    errors, _ = validate_resource("Project", {})
    assert errors == []


def test_valid_namespace_with_description():
    spec = {"description": "Default project"}
    errors, _ = validate_resource("Project", spec)
    assert errors == []


def test_valid_namespace_full():
    spec = {
        "description": "Production project",
        "labels": {"team": "backend", "env": "prod"},
        "default_agent_policy": "ref:agent-policies/standard",
        "resource_quota": {
            "max_resources": 500,
            "max_executions_per_hour": 100,
        },
    }
    errors, _ = validate_resource("Project", spec)
    assert errors == []


def test_namespace_extra_field():
    spec = {"unknown_field": "bad"}
    errors, _ = validate_resource("Project", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


def test_namespace_quota_bounds():
    spec = {"resource_quota": {"max_resources": 0}}
    errors, _ = validate_resource("Project", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="max_resources")


def test_namespace_quota_extra_field():
    spec = {"resource_quota": {"max_resources": 10, "unknown": True}}
    errors, _ = validate_resource("Project", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


def test_namespace_labels_value_too_long():
    spec = {"labels": {"team": "x" * 256}}
    errors, _ = validate_resource("Project", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="team")


def test_namespace_kind_registered():
    """Project must exist in kinds registry."""
    from blackbeard.kinds import ALL_KINDS, KIND_TO_PLURAL

    assert "Project" in ALL_KINDS
    assert KIND_TO_PLURAL["Project"] == "projects"


# ---------------------------------------------------------------------------
# AgentPolicy schema
# ---------------------------------------------------------------------------


def test_valid_agent_policy():
    spec = {
        "tools": {
            "mode": "allowlist",
            "allow": ["web_search", "calculator"],
        }
    }
    errors, _ = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_invalid_mode():
    spec = {"tools": {"mode": "invalid"}}
    errors, _ = validate_resource("AgentPolicy", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="mode", msg_contains="invalid")


def test_agent_policy_with_budget():
    spec = {
        "budget": {
            "max_usd": 10.0,
            "max_tokens": 50000,
        }
    }
    errors, _ = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_with_sandbox_tier():
    spec = {"sandbox": {"minimum_tier": "wasm"}}
    errors, _ = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_empty_spec():
    # All fields are optional: empty spec should pass
    errors, _ = validate_resource("AgentPolicy", {})
    assert errors == []


def test_agent_policy_extra_field():
    spec = {"unknown_field": "bad"}
    errors, _ = validate_resource("AgentPolicy", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


# ---------------------------------------------------------------------------
# Guardrail schema
# ---------------------------------------------------------------------------


def test_valid_guardrail_function():
    spec = {
        "type": "function",
        "function_path": "blackbeard.guardrails.check_pii",
        "on_fail": "reject",
    }
    errors, _ = validate_resource("Guardrail", spec)
    assert errors == []


def test_valid_guardrail_llm():
    spec = {
        "type": "llm",
        "llm_prompt": "Does the output contain PII? Reply yes or no.",
        "on_fail": "warn",
    }
    errors, _ = validate_resource("Guardrail", spec)
    assert errors == []


def test_guardrail_missing_type():
    spec = {"function_path": "mypackage.guardrails.check_pii"}
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="type") or _has_error(errors, msg_contains="type")


def test_guardrail_invalid_type():
    spec = {"type": "invalid"}
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="type", msg_contains="invalid")


def test_guardrail_invalid_on_fail():
    spec = {"type": "function", "on_fail": "invalid"}
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="on_fail", msg_contains="invalid")


def test_guardrail_all_on_fail_values():
    for on_fail in ("reject", "warn", "log"):
        spec = {"type": "function", "on_fail": on_fail}
        errors, _ = validate_resource("Guardrail", spec)
        assert errors == [], f"Expected no errors for on_fail={on_fail!r}, got {errors}"


def test_guardrail_description_field():
    spec = {"type": "llm", "description": "PII detector", "llm_prompt": "Check for PII."}
    errors, _ = validate_resource("Guardrail", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# Flow schema
# ---------------------------------------------------------------------------


def test_valid_flow_minimal():
    spec = {
        "steps": [
            {"name": "step-1", "type": "crew", "crew": "ref:crews/my-crew"},
        ],
    }
    errors, _ = validate_resource("Flow", spec)
    assert errors == []


def test_valid_flow_with_router():
    spec = {
        "description": "A multi-step flow",
        "steps": [
            {"name": "classify", "type": "crew", "crew": "ref:crews/classifier"},
            {
                "name": "route",
                "type": "router",
                "listen_to": ["classify"],
                "routes": {"urgent": "handle-urgent", "normal": "handle-normal"},
            },
            {"name": "handle-urgent", "type": "crew", "crew": "ref:crews/urgent-handler"},
            {"name": "handle-normal", "type": "crew", "crew": "ref:crews/normal-handler"},
        ],
        "memory": True,
        "verbose": False,
    }
    errors, _ = validate_resource("Flow", spec)
    assert errors == []


def test_flow_missing_steps():
    spec = {"description": "No steps"}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert any("steps" in e.message for e in errors)


def test_flow_empty_steps():
    spec = {"steps": []}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="steps")


def test_flow_step_missing_required_fields():
    spec = {"steps": [{"name": "step-1"}]}  # missing type
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert any("type" in e.message for e in errors)


def test_flow_invalid_step_type():
    spec = {"steps": [{"name": "step-1", "type": "invalid"}]}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="invalid")


def test_flow_step_extra_field():
    spec = {"steps": [{"name": "s", "type": "crew", "unknown": True}]}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


def test_flow_extra_top_level_field():
    spec = {"steps": [{"name": "s", "type": "crew"}], "unknown_field": True}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


# ---------------------------------------------------------------------------
# KnowledgeSource schema
# ---------------------------------------------------------------------------


def test_valid_knowledge_source_string():
    spec = {"type": "string", "content": "Some knowledge content here."}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


def test_valid_knowledge_source_text():
    spec = {"type": "text", "file_paths": ["data/notes.txt"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


def test_valid_knowledge_source_pdf():
    spec = {"type": "pdf", "file_paths": ["docs/report.pdf"], "chunk_size": 2000}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


def test_valid_knowledge_source_csv():
    spec = {"type": "csv", "file_paths": ["data/results.csv"], "chunk_overlap": 100}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


def test_valid_knowledge_source_json():
    spec = {"type": "json", "file_paths": ["data/config.json"]}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert errors == []


def test_knowledge_source_missing_type():
    spec = {"content": "Some content"}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert any("type" in e.message for e in errors)


def test_knowledge_source_invalid_type():
    spec = {"type": "invalid"}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="type")


def test_knowledge_source_extra_field():
    spec = {"type": "string", "unknown_field": True}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="additional")


def test_knowledge_source_chunk_size_bounds():
    # chunk_size minimum is 100
    spec = {"type": "text", "chunk_size": 50}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="chunk_size")

    # chunk_size maximum is 10000
    spec = {"type": "text", "chunk_size": 20000}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="chunk_size")


def test_knowledge_source_all_types_valid():
    for ks_type in ("text", "pdf", "csv", "json", "excel", "string", "url"):
        spec = {"type": ks_type}
        errors, _ = validate_resource("KnowledgeSource", spec)
        assert errors == [], f"Expected no errors for type={ks_type!r}, got {errors}"


# ---------------------------------------------------------------------------
# MCP tool types
# ---------------------------------------------------------------------------


def test_valid_tool_mcp_stdio():
    spec = {"type": "mcp-stdio", "command": "npx", "args": ["-y", "some-server"]}
    errors, _ = validate_resource("Tool", spec)
    assert errors == []


def test_valid_tool_mcp_http(monkeypatch):
    import socket

    def _fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    spec = {"type": "mcp-http", "url": "http://example.com/mcp"}
    errors, _ = validate_resource("Tool", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# ResourceCreate / ResourceMetadata Pydantic validation
# ---------------------------------------------------------------------------


from pydantic import ValidationError as PydanticValidationError

from blackbeard.models.resource_schemas import ResourceCreate, ResourceMetadata


def test_resource_metadata_rejects_uppercase_name():
    """Resource names must be lowercase alphanumeric + hyphens."""
    with pytest.raises(PydanticValidationError, match="string_pattern_mismatch"):
        ResourceMetadata(name="Invalid_Name")


def test_resource_metadata_rejects_empty_name():
    """Empty name should fail validation."""
    with pytest.raises(PydanticValidationError):
        ResourceMetadata(name="")


def test_resource_metadata_accepts_valid_name():
    meta = ResourceMetadata(name="my-resource")
    assert meta.name == "my-resource"
    assert meta.project == "default"


def test_resource_metadata_label_key_too_long():
    """Label keys exceeding 63 chars should fail."""
    with pytest.raises(PydanticValidationError, match="too long"):
        ResourceMetadata(name="test", labels={"k" * 64: "v"})


def test_resource_metadata_label_value_too_long():
    """Label values exceeding 255 chars should fail."""
    with pytest.raises(PydanticValidationError, match="too long"):
        ResourceMetadata(name="test", labels={"k": "v" * 256})


def test_resource_create_rejects_invalid_kind():
    """Invalid kind should be rejected at the Pydantic level."""
    with pytest.raises(PydanticValidationError, match="Invalid kind"):
        ResourceCreate(
            kind="Widget",
            metadata=ResourceMetadata(name="test"),
            spec={"foo": "bar"},
        )


def test_resource_create_rejects_invalid_api_version():
    """Unsupported apiVersion should be rejected."""
    with pytest.raises(PydanticValidationError, match="Unsupported apiVersion"):
        ResourceCreate(
            apiVersion="blackbeard/v999",
            kind="Agent",
            metadata=ResourceMetadata(name="test"),
            spec={"role": "R", "goal": "G", "backstory": "B"},
        )


def test_resource_create_accepts_valid():
    """Valid ResourceCreate should pass validation."""
    rc = ResourceCreate(
        kind="Agent",
        metadata=ResourceMetadata(name="test"),
        spec={"role": "R", "goal": "G", "backstory": "B"},
    )
    assert rc.kind == "Agent"
    assert rc.apiVersion == "blackbeard/v1"


# ---------------------------------------------------------------------------
# Agent serviceAccount schema validation
# ---------------------------------------------------------------------------


def test_agent_accepts_service_account():
    """Agent spec with valid serviceAccount should pass validation."""
    spec = {
        "role": "R",
        "goal": "G",
        "backstory": "B",
        "serviceAccount": "my-custom-sa",
    }
    errors, _ = validate_resource("Agent", spec)
    assert errors == []


def test_agent_rejects_invalid_service_account():
    """Agent spec with invalid serviceAccount pattern should fail validation."""
    spec = {
        "role": "R",
        "goal": "G",
        "backstory": "B",
        "serviceAccount": "Invalid_SA",
    }
    errors, _ = validate_resource("Agent", spec)
    assert len(errors) > 0
    assert _has_error(errors, field_contains="serviceAccount")


def test_agent_service_account_optional():
    """Agent spec without serviceAccount should pass (it is optional)."""
    spec = {"role": "R", "goal": "G", "backstory": "B"}
    errors, _ = validate_resource("Agent", spec)
    assert errors == []


# ---------------------------------------------------------------------------
# ExecutionResponse identity fields
# ---------------------------------------------------------------------------


def test_execution_response_schema_has_identity_fields():
    """ExecutionResponse schema should declare initiated_by and principal_chain."""
    from blackbeard.models.execution_schemas import ExecutionResponse

    fields = ExecutionResponse.model_fields
    assert "initiated_by" in fields
    assert "principal_chain" in fields


def test_execution_response_identity_defaults():
    """ExecutionResponse identity fields should default to None."""
    from datetime import UTC, datetime

    from blackbeard.models.execution_schemas import ExecutionResponse

    resp = ExecutionResponse(
        id="00000000-0000-0000-0000-000000000000",
        crew_name="test",
        crew_project="default",
        status="queued",
        inputs={},
        created_at=datetime.now(UTC),
    )
    assert resp.initiated_by is None
    assert resp.principal_chain is None
