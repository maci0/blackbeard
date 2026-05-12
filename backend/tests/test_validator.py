"""Unit tests for resource validation (JSON Schema + ref format checks).

Covers validate_resource() for all five resource kinds plus error paths.
"""

import pytest

from blackbeard.resources.validator import validate_resource, ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_error(errors: list[ValidationError], field_contains: str = "", msg_contains: str = "") -> bool:
    """Return True if any error matches both optional substrings."""
    for e in errors:
        field_ok = not field_contains or field_contains in e.field
        msg_ok = not msg_contains or msg_contains.lower() in e.message.lower()
        if field_ok and msg_ok:
            return True
    return False


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def test_valid_agent():
    spec = {
        "role": "Research Analyst",
        "goal": "Find insights",
        "backstory": "Years of research experience",
    }
    errors = validate_resource("Agent", spec)
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
    errors = validate_resource("Agent", spec)
    assert errors == []


def test_agent_missing_required():
    """Missing 'role' should produce a validation error."""
    spec = {
        "goal": "Find insights",
        "backstory": "Expert",
    }
    errors = validate_resource("Agent", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="role")


def test_agent_missing_all_required():
    errors = validate_resource("Agent", {})
    fields_mentioned = " ".join(e.message for e in errors)
    assert "role" in fields_mentioned or "goal" in fields_mentioned


def test_agent_extra_field():
    """additionalProperties: false — unknown fields should fail."""
    spec = {
        "role": "Analyst",
        "goal": "Analyse",
        "backstory": "Always has been",
        "unknown_field": "bad",
    }
    errors = validate_resource("Agent", spec)
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
    errors = validate_resource("Task", spec)
    assert errors == []


def test_task_missing_agent():
    spec = {
        "description": "Do something",
        "expected_output": "Some output",
    }
    errors = validate_resource("Task", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="agent")


def test_task_missing_description():
    spec = {
        "expected_output": "Output",
        "agent": "ref:agents/researcher",
    }
    errors = validate_resource("Task", spec)
    assert len(errors) > 0


def test_task_extra_field():
    spec = {
        "description": "Do something",
        "expected_output": "Output",
        "agent": "ref:agents/researcher",
        "not_a_real_field": True,
    }
    errors = validate_resource("Task", spec)
    assert len(errors) > 0


def test_valid_task_with_context():
    spec = {
        "description": "Summarise findings",
        "expected_output": "Summary",
        "agent": "ref:agents/writer",
        "context": ["ref:tasks/gather-data"],
        "async_execution": False,
    }
    errors = validate_resource("Task", spec)
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
    errors = validate_resource("Crew", spec)
    assert errors == []


def test_crew_invalid_process():
    """process must be 'sequential' or 'hierarchical'."""
    spec = {
        "process": "invalid",
        "agents": ["ref:agents/researcher"],
        "tasks": ["ref:tasks/gather-data"],
    }
    errors = validate_resource("Crew", spec)
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="invalid")


def test_crew_missing_agents():
    spec = {
        "process": "sequential",
        "tasks": ["ref:tasks/t1"],
    }
    errors = validate_resource("Crew", spec)
    assert len(errors) > 0


def test_crew_empty_agents_list():
    """agents must have at least one item (minItems: 1)."""
    spec = {
        "process": "sequential",
        "agents": [],
        "tasks": ["ref:tasks/t1"],
    }
    errors = validate_resource("Crew", spec)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


def test_valid_tool():
    spec = {
        "type": "python",
        "class_path": "my_tools.SearchTool",
        "description": "Searches the web",
    }
    errors = validate_resource("Tool", spec)
    assert errors == []


def test_valid_tool_wasm():
    spec = {
        "type": "wasm",
        "wasm_module": "s3://bucket/tool.wasm",
        "sandbox": "wasm",
    }
    errors = validate_resource("Tool", spec)
    assert errors == []


def test_tool_missing_type():
    errors = validate_resource("Tool", {"class_path": "foo.Bar"})
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="type")


def test_tool_invalid_type_enum():
    spec = {"type": "java"}
    errors = validate_resource("Tool", spec)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# LLMConnection
# ---------------------------------------------------------------------------


def test_valid_llm_connection():
    spec = {
        "provider": "openai",
        "model": "gpt-4o",
    }
    errors = validate_resource("LLMConnection", spec)
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
    errors = validate_resource("LLMConnection", spec)
    assert errors == []


def test_llm_connection_missing_model():
    errors = validate_resource("LLMConnection", {"provider": "openai"})
    assert len(errors) > 0
    assert _has_error(errors, msg_contains="model")


def test_llm_connection_missing_provider():
    errors = validate_resource("LLMConnection", {"model": "gpt-4o"})
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Unknown kind
# ---------------------------------------------------------------------------


def test_unknown_kind():
    errors = validate_resource("Widget", {"foo": "bar"})
    assert len(errors) == 1
    assert _has_error(errors, field_contains="kind", msg_contains="unknown")


def test_unknown_kind_returns_immediately():
    """Should not attempt schema validation when kind is unknown."""
    errors = validate_resource("NotARealKind", {})
    assert len(errors) == 1
    assert errors[0].field == "kind"
