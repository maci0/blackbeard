"""Tests for agent policy enforcement (AgentPolicy, resolve_policy, PolicyDeniedError)."""

import pytest

from blackbeard.engine.policy import (
    DEFAULT_POLICY,
    AgentPolicy,
    PolicyDeniedError,
    resolve_policy,
)

# ---------------------------------------------------------------------------
# DEFAULT_POLICY
# ---------------------------------------------------------------------------


def test_default_policy_allows_all():
    assert DEFAULT_POLICY.tool_mode == "all"
    assert DEFAULT_POLICY.check_tool_access("any-agent", "any_tool") is None
    assert DEFAULT_POLICY.check_tool_access("any-agent", "dangerous_tool") is None


# ---------------------------------------------------------------------------
# Allowlist mode
# ---------------------------------------------------------------------------


def test_allowlist_allows_listed_tool():
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": ["web_search", "calculator"]}})
    result = policy.check_tool_access("agent-1", "web_search")
    assert result is None


def test_allowlist_denies_unlisted_tool():
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": ["web_search"]}})
    with pytest.raises(PolicyDeniedError) as exc_info:
        policy.check_tool_access("agent-1", "file_writer")
    err = exc_info.value
    assert err.agent == "agent-1"
    assert "file_writer" in err.action
    assert err.reason, "PolicyDeniedError must include a reason"


# ---------------------------------------------------------------------------
# Denylist mode
# ---------------------------------------------------------------------------


def test_denylist_allows_unlisted_tool():
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": ["file_writer"]}})
    result = policy.check_tool_access("agent-1", "web_search")
    assert result is None


def test_denylist_denies_listed_tool():
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": ["file_writer"]}})
    with pytest.raises(PolicyDeniedError) as exc_info:
        policy.check_tool_access("agent-1", "file_writer")
    err = exc_info.value
    assert "denylist" in err.reason.lower()


# ---------------------------------------------------------------------------
# All mode
# ---------------------------------------------------------------------------


def test_all_mode_allows_everything():
    policy = AgentPolicy({"tools": {"mode": "all"}})
    assert policy.check_tool_access("agent-1", "any_tool") is None
    assert policy.check_tool_access("agent-1", "another_tool") is None


# ---------------------------------------------------------------------------
# Budget / sandbox properties
# ---------------------------------------------------------------------------


def test_budget_properties():
    policy = AgentPolicy({"budget": {"max_usd": 5.0, "max_tokens": 10000}})
    assert policy.max_budget_usd == 5.0
    assert policy.max_tokens == 10000


def test_budget_properties_missing():
    policy = AgentPolicy({})
    assert policy.max_budget_usd is None
    assert policy.max_tokens is None


def test_minimum_sandbox_tier():
    policy = AgentPolicy({"sandbox": {"minimum_tier": "wasm"}})
    assert policy.minimum_sandbox_tier == "wasm"


def test_minimum_sandbox_tier_default():
    policy = AgentPolicy({})
    assert policy.minimum_sandbox_tier == "none"


# ---------------------------------------------------------------------------
# resolve_policy
# ---------------------------------------------------------------------------


def test_resolve_agent_policy():
    agent_spec = {"role": "researcher", "policy": "strict-policy"}
    policies = {"strict-policy": {"tools": {"mode": "allowlist", "allow": ["web_search"]}}}
    resolved = resolve_policy(agent_spec, policies=policies)
    assert resolved.tool_mode == "allowlist"
    assert resolved.check_tool_access("researcher", "web_search") is None
    with pytest.raises(PolicyDeniedError):
        resolved.check_tool_access("researcher", "file_writer")


def test_resolve_crew_default_policy():
    agent_spec = {"role": "researcher"}  # no agent-level policy
    crew_spec = {"default_agent_policy": "crew-default"}
    policies = {"crew-default": {"tools": {"mode": "denylist", "deny": ["file_writer"]}}}
    resolved = resolve_policy(agent_spec, crew_spec=crew_spec, policies=policies)
    assert resolved.tool_mode == "denylist"


def test_resolve_fallback_to_default():
    agent_spec = {"role": "researcher"}
    resolved = resolve_policy(agent_spec)
    assert resolved is DEFAULT_POLICY


def test_resolve_agent_policy_overrides_crew_default():
    """Agent-level policy should take priority over crew-level default."""
    agent_spec = {"role": "researcher", "policy": "agent-policy"}
    crew_spec = {"default_agent_policy": "crew-policy"}
    policies = {
        "agent-policy": {"tools": {"mode": "allowlist", "allow": ["web_search"]}},
        "crew-policy": {"tools": {"mode": "denylist", "deny": ["file_writer"]}},
    }
    resolved = resolve_policy(agent_spec, crew_spec=crew_spec, policies=policies)
    assert resolved.tool_mode == "allowlist"


def test_resolve_missing_agent_policy_falls_to_crew():
    """If agent references a non-existent policy, fall through to crew default."""
    agent_spec = {"role": "researcher", "policy": "ghost-policy"}
    crew_spec = {"default_agent_policy": "crew-default"}
    policies = {"crew-default": {"tools": {"mode": "all"}}}
    resolved = resolve_policy(agent_spec, crew_spec=crew_spec, policies=policies)
    assert resolved.tool_mode == "all"


# ---------------------------------------------------------------------------
# PolicyDeniedError
# ---------------------------------------------------------------------------


def test_policy_denied_error_message():
    err = PolicyDeniedError(agent="my-agent", action="use tool 'rm'", reason="Tool is in denylist")
    assert "my-agent" in str(err)
    assert "use tool 'rm'" in str(err)
    assert err.agent == "my-agent"
    assert err.action == "use tool 'rm'"
    assert err.reason == "Tool is in denylist"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_allowlist_empty_denies_everything():
    """An allowlist with no entries should deny all tools."""
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": []}})
    with pytest.raises(PolicyDeniedError):
        policy.check_tool_access("agent-1", "any_tool")


def test_denylist_empty_allows_everything():
    """A denylist with no entries should allow all tools."""
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": []}})
    assert policy.check_tool_access("agent-1", "any_tool") is None


def test_default_policy_properties():
    """DEFAULT_POLICY should have no budget or sandbox constraints."""
    assert DEFAULT_POLICY.max_budget_usd is None
    assert DEFAULT_POLICY.max_tokens is None
    assert DEFAULT_POLICY.minimum_sandbox_tier == "none"
    assert DEFAULT_POLICY.allowed_tools == set()
    assert DEFAULT_POLICY.denied_tools == set()


def test_resolve_policy_both_missing_use_default():
    """When both agent and crew policies reference non-existent names, fall to default."""
    agent_spec = {"role": "researcher", "policy": "ghost-agent"}
    crew_spec = {"default_agent_policy": "ghost-crew"}
    resolved = resolve_policy(agent_spec, crew_spec=crew_spec, policies={})
    assert resolved is DEFAULT_POLICY
