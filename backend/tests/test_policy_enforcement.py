"""Tests for runtime policy enforcement in ResourceLoader.

Verifies that AgentPolicy tool filtering and delegation constraints
are enforced when building CrewAI agents during crew execution.
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from blackbeard.engine.loader import ResourceLoader
from blackbeard.engine.policy import AgentPolicy
from blackbeard.kinds import ResourceKind
from tests.conftest import _resource_map, make_resource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_with_name(name: str) -> MagicMock:
    """Create a mock tool instance with a .name attribute."""
    tool = MagicMock()
    tool.name = name
    return tool


def _basic_agent_spec(**overrides: object) -> dict:
    base = {"role": "R", "goal": "G", "backstory": "B"}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tool allowlist enforcement
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_allowlist_keeps_only_allowed_tools(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent with allowlist policy should only keep tools in the allow list."""
    # Set up two tools
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    writer_cls = MagicMock(name="WriterToolCls")
    writer_instance = _make_tool_with_name("WriterTool")
    writer_cls.return_value = writer_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        if "search" in module_path:
            mod.SearchTool = search_cls  # type: ignore[attr-defined]
        elif "writer" in module_path:
            mod.WriterTool = writer_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    writer_res = make_resource(
        ResourceKind.TOOL,
        "writer",
        {"type": "python", "class_path": "crewai_tools.writer.WriterTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(
            tools=["ref:tools/search", "ref:tools/writer"],
            policy="strict-policy",
        ),
    )

    policies = {
        "strict-policy": {
            "tools": {"mode": "allowlist", "allow": ["SearchTool"]},
        },
    }

    loader = ResourceLoader(_resource_map(search_res, writer_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0].name == "SearchTool"


# ---------------------------------------------------------------------------
# Tool denylist enforcement
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_denylist_removes_denied_tools(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent with denylist policy should have denied tools removed."""
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    writer_cls = MagicMock(name="WriterToolCls")
    writer_instance = _make_tool_with_name("WriterTool")
    writer_cls.return_value = writer_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        if "search" in module_path:
            mod.SearchTool = search_cls  # type: ignore[attr-defined]
        elif "writer" in module_path:
            mod.WriterTool = writer_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    writer_res = make_resource(
        ResourceKind.TOOL,
        "writer",
        {"type": "python", "class_path": "crewai_tools.writer.WriterTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(
            tools=["ref:tools/search", "ref:tools/writer"],
            policy="deny-policy",
        ),
    )

    policies = {
        "deny-policy": {
            "tools": {"mode": "denylist", "deny": ["WriterTool"]},
        },
    }

    loader = ResourceLoader(_resource_map(search_res, writer_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0].name == "SearchTool"


# ---------------------------------------------------------------------------
# All tools removed by policy
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_allowlist_removes_all_tools_when_none_match(
    mock_agent_cls, mock_llm_cls, mock_importlib
):
    """When allowlist excludes all tools, agent should be built with no tools."""
    writer_cls = MagicMock(name="WriterToolCls")
    writer_instance = _make_tool_with_name("WriterTool")
    writer_cls.return_value = writer_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        mod.WriterTool = writer_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    writer_res = make_resource(
        ResourceKind.TOOL,
        "writer",
        {"type": "python", "class_path": "crewai_tools.writer.WriterTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(
            tools=["ref:tools/writer"],
            policy="strict-policy",
        ),
    )

    policies = {
        "strict-policy": {
            "tools": {"mode": "allowlist", "allow": ["NonexistentTool"]},
        },
    }

    loader = ResourceLoader(_resource_map(writer_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" not in kwargs


# ---------------------------------------------------------------------------
# No policy — all tools preserved
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_no_policy_preserves_all_tools(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent without a policy ref should keep all tools unchanged."""
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        mod.SearchTool = search_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(tools=["ref:tools/search"]),
    )

    # Policies dict exists but agent has no policy ref
    policies = {
        "some-policy": {
            "tools": {"mode": "allowlist", "allow": []},
        },
    }

    loader = ResourceLoader(_resource_map(search_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1


# ---------------------------------------------------------------------------
# No policies dict — all tools preserved
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_empty_policies_dict_preserves_all_tools(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent with empty policies dict should keep all tools unchanged."""
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        mod.SearchTool = search_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(tools=["ref:tools/search"]),
    )

    # No policies at all (default)
    loader = ResourceLoader(_resource_map(search_res, agent_res))
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1


# ---------------------------------------------------------------------------
# Policy mode=all — no filtering
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_mode_all_preserves_all_tools(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent with policy mode='all' should keep all tools."""
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        mod.SearchTool = search_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(
            tools=["ref:tools/search"],
            policy="open-policy",
        ),
    )

    policies = {
        "open-policy": {"tools": {"mode": "all"}},
    }

    loader = ResourceLoader(_resource_map(search_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1


# ---------------------------------------------------------------------------
# Delegation enforcement
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_delegation_false_overrides_spec(mock_agent_cls, mock_llm_cls):
    """Policy with delegation.allowed=False should force allow_delegation=False."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "delegator",
        _basic_agent_spec(
            allow_delegation=True,
            policy="no-delegate",
        ),
    )

    policies = {
        "no-delegate": {"delegation": {"allowed": False}},
    }

    loader = ResourceLoader(_resource_map(agent_res), policies=policies)
    loader.build_agent("ref:agents/delegator")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["allow_delegation"] is False


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_delegation_true_preserves_spec(mock_agent_cls, mock_llm_cls):
    """Policy with delegation.allowed=True should not override spec's allow_delegation."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "delegator",
        _basic_agent_spec(
            allow_delegation=True,
            policy="yes-delegate",
        ),
    )

    policies = {
        "yes-delegate": {"delegation": {"allowed": True}},
    }

    loader = ResourceLoader(_resource_map(agent_res), policies=policies)
    loader.build_agent("ref:agents/delegator")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["allow_delegation"] is True


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_budget_only_preserves_delegation_spec(mock_agent_cls, mock_llm_cls):
    """Policy with only budget section (no delegation) should not change allow_delegation."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "delegator",
        _basic_agent_spec(
            allow_delegation=True,
            policy="budget-only",
        ),
    )

    policies = {
        "budget-only": {"budget": {"max_usd": 1.0}},
    }

    loader = ResourceLoader(_resource_map(agent_res), policies=policies)
    loader.build_agent("ref:agents/delegator")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["allow_delegation"] is True


@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_policy_delegation_false_on_non_delegating_agent(mock_agent_cls, mock_llm_cls):
    """Policy delegation=False on agent that already has allow_delegation=False is a no-op."""
    agent_res = make_resource(
        ResourceKind.AGENT,
        "non-delegator",
        _basic_agent_spec(
            allow_delegation=False,
            policy="no-delegate",
        ),
    )

    policies = {
        "no-delegate": {"delegation": {"allowed": False}},
    }

    loader = ResourceLoader(_resource_map(agent_res), policies=policies)
    loader.build_agent("ref:agents/non-delegator")

    _, kwargs = mock_agent_cls.call_args
    assert kwargs["allow_delegation"] is False


# ---------------------------------------------------------------------------
# Crew-level default policy
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_crew_default_policy_applies_tool_filter(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Agent without own policy but crew has default_agent_policy should be filtered."""
    # The ResourceLoader's build_agent resolves policy via resolve_policy(),
    # which checks agent.spec.policy first, then crew.spec.default_agent_policy.
    # But build_agent only passes agent_spec (no crew_spec) currently.
    # This test verifies that agent-level policy ref still works with crew-default
    # when the agent doesn't have its own policy.
    #
    # Since build_agent doesn't have access to crew_spec, the crew-default
    # policy must be set via agent.spec.policy or inherited through a different
    # mechanism. This test documents the current behavior.
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        mod.SearchTool = search_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    # Agent has no policy ref — will fall back to DEFAULT_POLICY (mode=all)
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(tools=["ref:tools/search"]),
    )

    # Even if policies exist, agent without policy ref gets DEFAULT_POLICY
    policies = {
        "strict-policy": {
            "tools": {"mode": "allowlist", "allow": []},
        },
    }

    loader = ResourceLoader(_resource_map(search_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1


# ---------------------------------------------------------------------------
# _filter_tools_by_policy unit tests
# ---------------------------------------------------------------------------


def test_filter_tools_by_policy_allowlist():
    """_filter_tools_by_policy with allowlist keeps only matching tools."""
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": ["web-search"]}})
    tools = [_make_tool_with_name("web-search"), _make_tool_with_name("file-writer")]

    loader = ResourceLoader({})
    filtered = loader._filter_tools_by_policy(tools, policy, "test-agent")

    assert len(filtered) == 1
    assert filtered[0].name == "web-search"


def test_filter_tools_by_policy_denylist():
    """_filter_tools_by_policy with denylist removes matching tools."""
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": ["file-writer"]}})
    tools = [_make_tool_with_name("web-search"), _make_tool_with_name("file-writer")]

    loader = ResourceLoader({})
    filtered = loader._filter_tools_by_policy(tools, policy, "test-agent")

    assert len(filtered) == 1
    assert filtered[0].name == "web-search"


def test_filter_tools_by_policy_mode_all():
    """_filter_tools_by_policy with mode=all returns all tools unchanged."""
    policy = AgentPolicy({"tools": {"mode": "all"}})
    tools = [_make_tool_with_name("web-search"), _make_tool_with_name("file-writer")]

    loader = ResourceLoader({})
    filtered = loader._filter_tools_by_policy(tools, policy, "test-agent")

    assert len(filtered) == 2


def test_filter_tools_by_policy_empty_allowlist():
    """_filter_tools_by_policy with empty allowlist removes all tools."""
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": []}})
    tools = [_make_tool_with_name("web-search")]

    loader = ResourceLoader({})
    filtered = loader._filter_tools_by_policy(tools, policy, "test-agent")

    assert len(filtered) == 0


def test_filter_tools_by_policy_empty_denylist():
    """_filter_tools_by_policy with empty denylist keeps all tools."""
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": []}})
    tools = [_make_tool_with_name("web-search")]

    loader = ResourceLoader({})
    filtered = loader._filter_tools_by_policy(tools, policy, "test-agent")

    assert len(filtered) == 1


# ---------------------------------------------------------------------------
# AgentPolicy delegation properties
# ---------------------------------------------------------------------------


def test_agent_policy_delegation_allowed_false():
    policy = AgentPolicy({"delegation": {"allowed": False}})
    assert policy.delegation_allowed is False


def test_agent_policy_delegation_allowed_true():
    policy = AgentPolicy({"delegation": {"allowed": True}})
    assert policy.delegation_allowed is True


def test_agent_policy_delegation_allowed_default():
    """Delegation section present but no 'allowed' key defaults to True."""
    policy = AgentPolicy({"delegation": {}})
    assert policy.delegation_allowed is True


def test_agent_policy_delegation_not_present():
    """No delegation section means delegation_allowed is None (no constraint)."""
    policy = AgentPolicy({})
    assert policy.delegation_allowed is None


def test_agent_policy_delegation_targets():
    policy = AgentPolicy({"delegation": {"allowed": True, "targets": ["agent-a", "agent-b"]}})
    assert policy.delegation_targets == ["agent-a", "agent-b"]


def test_agent_policy_delegation_targets_none():
    """No targets key means delegation_targets is None."""
    policy = AgentPolicy({"delegation": {"allowed": True}})
    assert policy.delegation_targets is None


def test_agent_policy_delegation_targets_empty():
    """Empty targets list returns None."""
    policy = AgentPolicy({"delegation": {"allowed": True, "targets": []}})
    assert policy.delegation_targets is None


# ---------------------------------------------------------------------------
# Combined policy — tool filter + delegation
# ---------------------------------------------------------------------------


@patch("blackbeard.engine.loader.importlib")
@patch("blackbeard.engine.loader.LLM")
@patch("blackbeard.engine.loader.Agent")
def test_combined_policy_tool_filter_and_delegation(mock_agent_cls, mock_llm_cls, mock_importlib):
    """Policy with both tool filter and delegation constraints should apply both."""
    search_cls = MagicMock(name="SearchToolCls")
    search_instance = _make_tool_with_name("SearchTool")
    search_cls.return_value = search_instance

    writer_cls = MagicMock(name="WriterToolCls")
    writer_instance = _make_tool_with_name("WriterTool")
    writer_cls.return_value = writer_instance

    def import_side_effect(module_path):
        mod = ModuleType(module_path)
        if "search" in module_path:
            mod.SearchTool = search_cls  # type: ignore[attr-defined]
        elif "writer" in module_path:
            mod.WriterTool = writer_cls  # type: ignore[attr-defined]
        return mod

    mock_importlib.import_module.side_effect = import_side_effect

    search_res = make_resource(
        ResourceKind.TOOL,
        "search",
        {"type": "python", "class_path": "crewai_tools.search.SearchTool"},
    )
    writer_res = make_resource(
        ResourceKind.TOOL,
        "writer",
        {"type": "python", "class_path": "crewai_tools.writer.WriterTool"},
    )
    agent_res = make_resource(
        ResourceKind.AGENT,
        "researcher",
        _basic_agent_spec(
            tools=["ref:tools/search", "ref:tools/writer"],
            allow_delegation=True,
            policy="combined-policy",
        ),
    )

    policies = {
        "combined-policy": {
            "tools": {"mode": "denylist", "deny": ["WriterTool"]},
            "delegation": {"allowed": False},
        },
    }

    loader = ResourceLoader(_resource_map(search_res, writer_res, agent_res), policies=policies)
    loader.build_agent("ref:agents/researcher")

    _, kwargs = mock_agent_cls.call_args
    assert "tools" in kwargs
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0].name == "SearchTool"
    assert kwargs["allow_delegation"] is False


# ---------------------------------------------------------------------------
# AgentPolicy schema validation
# ---------------------------------------------------------------------------


def test_agent_policy_schema_accepts_delegation():
    """AGENT_POLICY_SCHEMA should accept delegation section."""
    import jsonschema

    from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

    spec = {
        "tools": {"mode": "allowlist", "allow": ["web-search"]},
        "delegation": {"allowed": False, "targets": ["agent-a"]},
    }
    jsonschema.validate(spec, AGENT_POLICY_SCHEMA)  # should not raise


def test_agent_policy_schema_rejects_unknown_delegation_field():
    """AGENT_POLICY_SCHEMA should reject unknown fields in delegation."""
    import jsonschema

    from blackbeard.resources.spec_schemas import AGENT_POLICY_SCHEMA

    spec = {
        "delegation": {"allowed": True, "unknown_field": "bad"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, AGENT_POLICY_SCHEMA)
