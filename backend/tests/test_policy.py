"""Tests for agent policy enforcement (AgentPolicy, resolve_policy, PolicyDeniedError)."""

import pytest

from blackbeard.engine.policy import (
    AgentPolicy,
    PolicyDeniedError,
    resolve_policy,
    DEFAULT_POLICY,
)


# ---------------------------------------------------------------------------
# DEFAULT_POLICY
# ---------------------------------------------------------------------------


def test_default_policy_allows_all():
    assert DEFAULT_POLICY.tool_mode == "all"


# ---------------------------------------------------------------------------
# Allowlist mode
# ---------------------------------------------------------------------------


def test_allowlist_allows_listed_tool():
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": ["web_search", "calculator"]}})
    # Should not raise
    policy.check_tool_access("agent-1", "web_search")


def test_allowlist_denies_unlisted_tool():
    policy = AgentPolicy({"tools": {"mode": "allowlist", "allow": ["web_search"]}})
    with pytest.raises(PolicyDeniedError) as exc_info:
        policy.check_tool_access("agent-1", "file_writer")
    err = exc_info.value
    assert err.agent == "agent-1"
    assert "file_writer" in err.action


# ---------------------------------------------------------------------------
# Denylist mode
# ---------------------------------------------------------------------------


def test_denylist_allows_unlisted_tool():
    policy = AgentPolicy({"tools": {"mode": "denylist", "deny": ["file_writer"]}})
    # "web_search" is not in deny list → should not raise
    policy.check_tool_access("agent-1", "web_search")


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
    # Neither of these should raise
    policy.check_tool_access("agent-1", "any_tool")
    policy.check_tool_access("agent-1", "another_tool")


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
