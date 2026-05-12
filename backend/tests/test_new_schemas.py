"""Tests for AgentPolicy and Guardrail JSON Schema validation."""

import pytest

from blackbeard.resources.validator import validate_resource


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
    errors = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_invalid_mode():
    spec = {"tools": {"mode": "invalid"}}
    errors = validate_resource("AgentPolicy", spec)
    assert any("mode" in e.field or "invalid" in e.message for e in errors)


def test_agent_policy_with_budget():
    spec = {
        "budget": {
            "max_usd": 10.0,
            "max_tokens": 50000,
        }
    }
    errors = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_with_sandbox_tier():
    spec = {"sandbox": {"minimum_tier": "wasm"}}
    errors = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_empty_spec():
    # All fields are optional — empty spec should pass
    errors = validate_resource("AgentPolicy", {})
    assert errors == []


def test_agent_policy_extra_field():
    spec = {"unknown_field": "bad"}
    errors = validate_resource("AgentPolicy", spec)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Guardrail schema
# ---------------------------------------------------------------------------


def test_valid_guardrail_function():
    spec = {
        "type": "function",
        "function_path": "mypackage.guardrails.check_pii",
        "on_fail": "reject",
    }
    errors = validate_resource("Guardrail", spec)
    assert errors == []


def test_valid_guardrail_llm():
    spec = {
        "type": "llm",
        "llm_prompt": "Does the output contain PII? Reply yes or no.",
        "on_fail": "warn",
    }
    errors = validate_resource("Guardrail", spec)
    assert errors == []


def test_guardrail_missing_type():
    spec = {"function_path": "mypackage.guardrails.check_pii"}
    errors = validate_resource("Guardrail", spec)
    assert any("type" in e.message or "type" in e.field for e in errors)


def test_guardrail_invalid_type():
    spec = {"type": "invalid"}
    errors = validate_resource("Guardrail", spec)
    assert len(errors) > 0


def test_guardrail_invalid_on_fail():
    spec = {"type": "function", "on_fail": "invalid"}
    errors = validate_resource("Guardrail", spec)
    assert len(errors) > 0


def test_guardrail_all_on_fail_values():
    for on_fail in ("reject", "warn", "log"):
        spec = {"type": "function", "on_fail": on_fail}
        errors = validate_resource("Guardrail", spec)
        assert errors == [], f"Expected no errors for on_fail={on_fail!r}, got {errors}"


def test_guardrail_description_field():
    spec = {"type": "llm", "description": "PII detector", "llm_prompt": "Check for PII."}
    errors = validate_resource("Guardrail", spec)
    assert errors == []
