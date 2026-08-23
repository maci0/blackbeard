"""Tests for per-execution budget enforcement via LiteLLM virtual keys.

Tests the budget derivation logic, VirtualKeyManager, and integration
with the executor and loader.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from blackbeard.engine.budget import derive_budget_and_pii as _derive
from blackbeard.engine.budget import (
    derive_budget_and_pii as _derive_budget_and_pii,
)
from blackbeard.engine.loader import ResourceLoader
from blackbeard.kinds import ResourceKind
from blackbeard.litellm.key_manager import VirtualKeyError, VirtualKeyManager
from tests.conftest import _resource_map, make_resource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policy_spec(*, max_usd: float | None = None, max_tokens: int | None = None) -> dict[str, Any]:
    """Build a minimal AgentPolicy spec with budget limits."""
    budget: dict[str, Any] = {}
    if max_usd is not None:
        budget["max_usd"] = max_usd
    if max_tokens is not None:
        budget["max_tokens"] = max_tokens
    return {"budget": budget} if budget else {}


def _make_snapshot(
    *,
    crew_name: str = "test-crew",
    agent_names: list[str] | None = None,
    agent_policy_refs: dict[str, str] | None = None,
    crew_default_policy: str | None = None,
    policies: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a resource snapshot dict for budget derivation tests."""
    agent_names = agent_names or ["agent-a"]
    agent_policy_refs = agent_policy_refs or {}
    policies = policies or {}

    snapshot: dict[str, dict[str, Any]] = {}

    # Add agents
    for name in agent_names:
        agent_spec: dict[str, Any] = {
            "role": "R",
            "goal": "G",
            "backstory": "B",
        }
        if name in agent_policy_refs:
            agent_spec["policy"] = agent_policy_refs[name]
        snapshot[f"Agent/{name}"] = {
            "kind": "Agent",
            "name": name,
            "project": "default",
            "spec": agent_spec,
        }

    # Add crew
    crew_spec: dict[str, Any] = {
        "process": "sequential",
        "agents": [f"ref:agents/{n}" for n in agent_names],
        "tasks": [],
    }
    if crew_default_policy:
        crew_spec["default_agent_policy"] = crew_default_policy
    snapshot[f"Crew/{crew_name}"] = {
        "kind": "Crew",
        "name": crew_name,
        "project": "default",
        "spec": crew_spec,
    }

    # Add policies
    for pname, pspec in policies.items():
        snapshot[f"AgentPolicy/{pname}"] = {
            "kind": "AgentPolicy",
            "name": pname,
            "project": "default",
            "spec": pspec,
        }

    return snapshot


# ---------------------------------------------------------------------------
# Tests — derive_budget_and_pii
# ---------------------------------------------------------------------------


def test_derive_no_policies_returns_none():
    """Without any policies, both limits should be None."""
    snapshot = _make_snapshot()
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget is None
    assert max_tokens is None


def test_derive_single_policy_with_max_usd():
    """A single agent policy with max_usd should be returned."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/budget-policy"},
        policies={"budget-policy": _policy_spec(max_usd=5.0)},
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 5.0
    assert max_tokens is None


def test_derive_single_policy_with_max_tokens():
    """A single agent policy with max_tokens should be returned."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/token-policy"},
        policies={"token-policy": _policy_spec(max_tokens=10000)},
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget is None
    assert max_tokens == 10000


def test_derive_single_policy_with_both_limits():
    """A policy with both max_usd and max_tokens should return both."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/full-policy"},
        policies={"full-policy": _policy_spec(max_usd=2.5, max_tokens=5000)},
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 2.5
    assert max_tokens == 5000


def test_derive_multiple_agents_takes_minimum():
    """With multiple agents, the most restrictive (minimum) limits win."""
    snapshot = _make_snapshot(
        agent_names=["agent-a", "agent-b"],
        agent_policy_refs={
            "agent-a": "ref:agent-policies/loose-policy",
            "agent-b": "ref:agent-policies/tight-policy",
        },
        policies={
            "loose-policy": _policy_spec(max_usd=10.0, max_tokens=50000),
            "tight-policy": _policy_spec(max_usd=2.0, max_tokens=10000),
        },
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 2.0
    assert max_tokens == 10000


def test_derive_partial_policies_only_limits_from_present():
    """When only some agents have policies, derive from the available ones."""
    snapshot = _make_snapshot(
        agent_names=["agent-a", "agent-b"],
        agent_policy_refs={
            "agent-a": "ref:agent-policies/budget-only",
        },
        policies={
            "budget-only": _policy_spec(max_usd=3.0),
        },
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 3.0
    assert max_tokens is None


def test_derive_crew_default_policy():
    """When agents don't have explicit policies, crew default is used."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        crew_default_policy="ref:agent-policies/default-policy",
        policies={"default-policy": _policy_spec(max_usd=7.5, max_tokens=20000)},
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 7.5
    assert max_tokens == 20000


def test_derive_agent_policy_overrides_crew_default():
    """Agent-level policy takes precedence over crew default."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/agent-policy"},
        crew_default_policy="ref:agent-policies/crew-default",
        policies={
            "agent-policy": _policy_spec(max_usd=1.0),
            "crew-default": _policy_spec(max_usd=100.0),
        },
    )
    max_budget, _, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 1.0


def test_derive_missing_policy_falls_through():
    """When referenced policy doesn't exist, falls back to crew default."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/nonexistent"},
        crew_default_policy="ref:agent-policies/fallback",
        policies={
            "fallback": _policy_spec(max_usd=5.0),
        },
    )
    max_budget, _, _, _ = _derive(snapshot, "test-crew")
    assert max_budget == 5.0


def test_derive_empty_policy_no_limits():
    """A policy with no budget section results in no limits."""
    snapshot = _make_snapshot(
        agent_names=["agent-a"],
        agent_policy_refs={"agent-a": "ref:agent-policies/empty-policy"},
        policies={"empty-policy": {}},
    )
    max_budget, max_tokens, _, _ = _derive(snapshot, "test-crew")
    assert max_budget is None
    assert max_tokens is None


def test_derive_warn_above_cap_is_clamped():
    """A warn threshold above the winning hard cap is clamped to the cap.

    Otherwise the cost_alert event could never fire before LiteLLM blocks
    spend at the cap.
    """
    snapshot = _make_snapshot(
        agent_names=["agent-a", "agent-b"],
        agent_policy_refs={
            "agent-a": "ref:agent-policies/cap-policy",
            "agent-b": "ref:agent-policies/alert-policy",
        },
        policies={
            "cap-policy": _policy_spec(max_usd=5.0),
            "alert-policy": {"budget": {"alerts": {"warn_at_usd": 10.0}}},
        },
    )
    _, _, _, alerts = _derive_budget_and_pii(snapshot, "test-crew")
    assert alerts == {"warn_at_usd": 5.0}


def test_derive_warn_below_cap_unchanged():
    """A warn threshold below the winning cap passes through untouched."""
    snapshot = _make_snapshot(
        agent_names=["agent-a", "agent-b"],
        agent_policy_refs={
            "agent-a": "ref:agent-policies/cap-policy",
            "agent-b": "ref:agent-policies/alert-policy",
        },
        policies={
            "cap-policy": _policy_spec(max_usd=5.0),
            "alert-policy": {"budget": {"alerts": {"warn_at_usd": 2.5, "warn_at_tokens": 100}}},
        },
    )
    _, max_tokens, _, alerts = _derive_budget_and_pii(snapshot, "test-crew")
    assert alerts == {"warn_at_usd": 2.5, "warn_at_tokens": 100}
    assert max_tokens is None


def test_derive_warn_tokens_clamped_to_token_cap():
    """A warn token threshold above the winning max_tokens is clamped."""
    snapshot = _make_snapshot(
        agent_names=["agent-a", "agent-b"],
        agent_policy_refs={
            "agent-a": "ref:agent-policies/cap-policy",
            "agent-b": "ref:agent-policies/alert-policy",
        },
        policies={
            "cap-policy": _policy_spec(max_tokens=10000),
            "alert-policy": {"budget": {"alerts": {"warn_at_tokens": 50000}}},
        },
    )
    _, _, _, alerts = _derive_budget_and_pii(snapshot, "test-crew")
    assert alerts == {"warn_at_tokens": 10000}


# ---------------------------------------------------------------------------
# Tests — VirtualKeyManager
# ---------------------------------------------------------------------------


_KEY_GEN_REQ = httpx.Request("POST", "http://litellm:4000/key/generate")
_KEY_DEL_REQ = httpx.Request("POST", "http://litellm:4000/key/delete")


async def test_create_key_success():
    """VirtualKeyManager.create_key() returns key info on success."""
    mock_response = httpx.Response(
        200,
        json={"key": "sk-virtual-123", "key_alias": "exec-abc"},
        request=_KEY_GEN_REQ,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        result = await mgr.create_key(
            name="exec-abc",
            max_budget=5.0,
            max_tokens=10000,
        )

    assert result["key"] == "sk-virtual-123"
    assert result["key_alias"] == "exec-abc"


async def test_create_key_sends_correct_payload():
    """VirtualKeyManager.create_key() sends the right payload to LiteLLM."""
    mock_response = httpx.Response(
        200,
        json={"key": "sk-virtual-456", "key_alias": "exec-xyz"},
        request=_KEY_GEN_REQ,
    )
    captured_kwargs: dict[str, Any] = {}

    async def capture_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        captured_kwargs["url"] = url
        return mock_response

    with patch("httpx.AsyncClient.post", side_effect=capture_post):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        await mgr.create_key(
            name="exec-xyz",
            max_budget=3.0,
            max_tokens=5000,
            metadata={"crew_name": "my-crew"},
        )

    assert captured_kwargs["url"] == "http://litellm:4000/key/generate"
    payload = captured_kwargs["json"]
    assert payload["key_alias"] == "exec-xyz"
    assert payload["max_budget"] == 3.0
    assert payload["tpm_limit"] == 5000
    assert payload["metadata"]["crew_name"] == "my-crew"
    assert "Bearer sk-master-key" in captured_kwargs["headers"]["Authorization"]


async def test_create_key_without_limits():
    """VirtualKeyManager.create_key() omits budget fields when not provided."""
    mock_response = httpx.Response(
        200,
        json={"key": "sk-virtual-nolimit", "key_alias": "exec-nolimit"},
        request=_KEY_GEN_REQ,
    )
    captured_kwargs: dict[str, Any] = {}

    async def capture_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        return mock_response

    with patch("httpx.AsyncClient.post", side_effect=capture_post):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        await mgr.create_key(name="exec-nolimit")

    payload = captured_kwargs["json"]
    assert "max_budget" not in payload
    assert "tpm_limit" not in payload


async def test_create_key_http_error():
    """VirtualKeyManager.create_key() raises VirtualKeyError on HTTP errors."""
    mock_response = httpx.Response(
        500,
        json={"error": "Internal server error"},
        request=httpx.Request("POST", "http://litellm:4000/key/generate"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        with pytest.raises(VirtualKeyError, match="500"):
            await mgr.create_key(name="exec-fail")


async def test_create_key_missing_key_in_response():
    """VirtualKeyManager.create_key() raises when response lacks 'key'."""
    mock_response = httpx.Response(
        200,
        json={"key_alias": "exec-nokey"},
        request=_KEY_GEN_REQ,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        with pytest.raises(VirtualKeyError, match="missing 'key'"):
            await mgr.create_key(name="exec-nokey")


async def test_create_key_connection_error():
    """VirtualKeyManager.create_key() raises VirtualKeyError on connection errors."""
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        with pytest.raises(VirtualKeyError, match="request failed"):
            await mgr.create_key(name="exec-connfail")


async def test_delete_key_success():
    """VirtualKeyManager.delete_key() returns True on success."""
    mock_response = httpx.Response(200, json={"deleted": True}, request=_KEY_DEL_REQ)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        result = await mgr.delete_key("sk-virtual-123")

    assert result is True


async def test_delete_key_sends_correct_payload():
    """VirtualKeyManager.delete_key() sends the right payload."""
    mock_response = httpx.Response(200, json={"deleted": True}, request=_KEY_DEL_REQ)
    captured_kwargs: dict[str, Any] = {}

    async def capture_post(url, **kwargs):
        captured_kwargs.update(kwargs)
        captured_kwargs["url"] = url
        return mock_response

    with patch("httpx.AsyncClient.post", side_effect=capture_post):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000/",
            master_key="sk-master-key",
        )
        await mgr.delete_key("sk-virtual-456")

    assert captured_kwargs["url"] == "http://litellm:4000/key/delete"
    assert captured_kwargs["json"] == {"keys": ["sk-virtual-456"]}


async def test_delete_key_failure_returns_false():
    """VirtualKeyManager.delete_key() returns False on errors (no exception)."""
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        result = await mgr.delete_key("sk-virtual-fail")

    assert result is False


async def test_delete_key_http_error_returns_false():
    """VirtualKeyManager.delete_key() returns False on HTTP status errors."""
    mock_response = httpx.Response(
        404,
        json={"error": "Key not found"},
        request=httpx.Request("POST", "http://litellm:4000/key/delete"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000",
            master_key="sk-master-key",
        )
        result = await mgr.delete_key("sk-nonexistent")

    assert result is False


# ---------------------------------------------------------------------------
# Tests — ResourceLoader api_key override
# ---------------------------------------------------------------------------


def test_loader_uses_master_key_by_default():
    """Without an api_key override, build_llm() uses the master key."""
    llm_resource = make_resource(
        ResourceKind.LLM_CONNECTION,
        "test-llm",
        {"provider": "openai", "model": "gpt-4"},
    )
    resources = _resource_map(llm_resource)
    loader = ResourceLoader(resources)
    llm = loader.build_llm("ref:llm-connections/test-llm")
    assert llm.api_key == "sk-litellm-master-key"


def test_loader_uses_override_api_key():
    """When api_key is provided, build_llm() uses it instead of master key."""
    llm_resource = make_resource(
        ResourceKind.LLM_CONNECTION,
        "test-llm",
        {"provider": "openai", "model": "gpt-4"},
    )
    resources = _resource_map(llm_resource)
    loader = ResourceLoader(resources, api_key="sk-virtual-exec-key")
    llm = loader.build_llm("ref:llm-connections/test-llm")
    assert llm.api_key == "sk-virtual-exec-key"


def test_loader_multiple_llms_use_same_override():
    """All LLMs built by the same loader use the same api_key override."""
    llm_a = make_resource(
        ResourceKind.LLM_CONNECTION,
        "llm-a",
        {"provider": "openai", "model": "gpt-4"},
    )
    llm_b = make_resource(
        ResourceKind.LLM_CONNECTION,
        "llm-b",
        {"provider": "vertex_ai", "model": "gemini-pro"},
    )
    resources = _resource_map(llm_a, llm_b)
    loader = ResourceLoader(resources, api_key="sk-virtual-shared")
    result_a = loader.build_llm("ref:llm-connections/llm-a")
    result_b = loader.build_llm("ref:llm-connections/llm-b")
    assert result_a.api_key == "sk-virtual-shared"
    assert result_b.api_key == "sk-virtual-shared"


# ---------------------------------------------------------------------------
# Tests — VirtualKeyManager URL handling
# ---------------------------------------------------------------------------


async def test_proxy_url_trailing_slash_stripped():
    """Trailing slash in proxy_url should be stripped."""
    mock_response = httpx.Response(
        200,
        json={"key": "sk-virtual-stripped", "key_alias": "test"},
        request=_KEY_GEN_REQ,
    )
    captured_url = None

    async def capture_post(url, **kwargs):
        nonlocal captured_url
        captured_url = url
        return mock_response

    with patch("httpx.AsyncClient.post", side_effect=capture_post):
        mgr = VirtualKeyManager(
            proxy_url="http://litellm:4000/",
            master_key="sk-master",
        )
        await mgr.create_key(name="test")

    assert captured_url == "http://litellm:4000/key/generate"


# ---------------------------------------------------------------------------
# Tests — AgentPolicy kinds loaded by executor
# ---------------------------------------------------------------------------


def test_crew_relevant_kinds_includes_agent_policy():
    """_CREW_RELEVANT_KINDS should include AgentPolicy so policies are loaded."""
    from blackbeard.engine.executor import _CREW_RELEVANT_KINDS

    assert ResourceKind.AGENT_POLICY in _CREW_RELEVANT_KINDS
