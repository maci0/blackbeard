"""Tests for AgentPolicy and Guardrail JSON Schema validation."""

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
    errors, _ = validate_resource("AgentPolicy", spec)
    assert errors == []


def test_agent_policy_invalid_mode():
    spec = {"tools": {"mode": "invalid"}}
    errors, _ = validate_resource("AgentPolicy", spec)
    assert len(errors) > 0
    assert any("mode" in e.field and "invalid" in e.message for e in errors)


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
    # All fields are optional — empty spec should pass
    errors, _ = validate_resource("AgentPolicy", {})
    assert errors == []


def test_agent_policy_extra_field():
    spec = {"unknown_field": "bad"}
    errors, _ = validate_resource("AgentPolicy", spec)
    assert len(errors) > 0
    assert any("additional" in e.message.lower() or "unknown_field" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Guardrail schema
# ---------------------------------------------------------------------------


def test_valid_guardrail_function():
    spec = {
        "type": "function",
        "function_path": "mypackage.guardrails.check_pii",
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
    assert any("type" in e.field or "type" in e.message for e in errors)


def test_guardrail_invalid_type():
    spec = {"type": "invalid"}
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    assert any("type" in e.field and "invalid" in e.message for e in errors)


def test_guardrail_invalid_on_fail():
    spec = {"type": "function", "on_fail": "invalid"}
    errors, _ = validate_resource("Guardrail", spec)
    assert len(errors) > 0
    assert any("on_fail" in e.field and "invalid" in e.message for e in errors)


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


def test_flow_step_missing_required_fields():
    spec = {"steps": [{"name": "step-1"}]}  # missing type
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0
    assert any("type" in e.message for e in errors)


def test_flow_invalid_step_type():
    spec = {"steps": [{"name": "step-1", "type": "invalid"}]}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0


def test_flow_step_extra_field():
    spec = {"steps": [{"name": "s", "type": "crew", "unknown": True}]}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0


def test_flow_extra_top_level_field():
    spec = {"steps": [{"name": "s", "type": "crew"}], "unknown_field": True}
    errors, _ = validate_resource("Flow", spec)
    assert len(errors) > 0


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


def test_knowledge_source_extra_field():
    spec = {"type": "string", "unknown_field": True}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0


def test_knowledge_source_chunk_size_bounds():
    # chunk_size minimum is 100
    spec = {"type": "text", "chunk_size": 50}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0

    # chunk_size maximum is 10000
    spec = {"type": "text", "chunk_size": 20000}
    errors, _ = validate_resource("KnowledgeSource", spec)
    assert len(errors) > 0


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


def test_valid_tool_mcp_http():
    spec = {"type": "mcp-http", "url": "http://example.com/mcp"}
    errors, _ = validate_resource("Tool", spec)
    assert errors == []
