"""Agent policy definitions and resolution.

Resolves the effective policy for an agent via:
  agent.spec.policy → crew.spec.default_agent_policy → DEFAULT_POLICY

Policy data covers tool access mode, budget limits, and sandbox tier.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from blackbeard.resources import parse_ref

__all__ = [
    "DEFAULT_POLICY",
    "AgentPolicy",
    "resolve_policy",
]

logger = logging.getLogger(__name__)


class AgentPolicy:
    """Agent policy after resolution (agent → crew default → global default)."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self._tools_config = spec.get("tools", {})
        self._budget = spec.get("budget", {})
        self._sandbox = spec.get("sandbox", {})
        self._allowed_tools: set[str] = set(self._tools_config.get("allow", []))
        self._denied_tools: set[str] = set(self._tools_config.get("deny", []))

    @property
    def tool_mode(self) -> str:
        """Tool access mode: 'allowlist', 'denylist', or 'all'."""
        return cast("str", self._tools_config.get("mode", "all"))

    @property
    def allowed_tools(self) -> set[str]:
        """Set of allowed tool names (when mode=allowlist)."""
        return self._allowed_tools

    @property
    def denied_tools(self) -> set[str]:
        """Set of denied tool names (when mode=denylist)."""
        return self._denied_tools

    @property
    def max_budget_usd(self) -> float | None:
        """Maximum LLM spend in USD for this agent."""
        return cast("float | None", self._budget.get("max_usd"))

    @property
    def max_tokens(self) -> int | None:
        """Maximum total tokens for this agent."""
        return cast("int | None", self._budget.get("max_tokens"))

    @property
    def minimum_sandbox_tier(self) -> str:
        """Minimum sandbox tier required by policy."""
        return cast("str", self._sandbox.get("minimum_tier", "none"))

    @property
    def delegation_allowed(self) -> bool | None:
        """Whether delegation is allowed.  ``None`` means no constraint."""
        delegation = self.spec.get("delegation")
        if delegation is None:
            return None
        return cast("bool", delegation.get("allowed", True))

    @property
    def delegation_targets(self) -> list[str] | None:
        """Allowed delegation target agent names (None = unrestricted)."""
        delegation = self.spec.get("delegation")
        if delegation is None:
            return None
        targets = delegation.get("targets")
        return list(targets) if targets else None


# Default policy — no restrictions
DEFAULT_POLICY = AgentPolicy({})


def resolve_policy(
    agent_spec: dict[str, Any],
    crew_spec: dict[str, Any] | None = None,
    policies: dict[str, dict[str, Any]] | None = None,
) -> AgentPolicy:
    """Resolve the effective policy for an agent.

    Resolution chain:
    1. agent.spec.policy (ref to AgentPolicy resource)
    2. crew.spec.default_agent_policy (ref to AgentPolicy resource)
    3. DEFAULT_POLICY (no restrictions)

    Args:
        agent_spec: The agent's spec dict
        crew_spec: The crew's spec dict (optional)
        policies: Dict of policy name → policy spec (optional)

    Returns:
        Resolved AgentPolicy
    """
    policies = policies or {}

    agent_policy_ref = agent_spec.get("policy")
    if agent_policy_ref:
        policy_name = _extract_name(agent_policy_ref)
        if policy_name in policies:
            return AgentPolicy(policies[policy_name])
        logger.warning(
            "Agent policy '%s' not found, checking crew default",
            policy_name,
            extra={
                "event": "policy_not_found",
                "policy_name": policy_name,
                "fallback": "crew_default",
            },
        )

    if crew_spec:
        crew_policy_ref = crew_spec.get("default_agent_policy")
        if crew_policy_ref:
            policy_name = _extract_name(crew_policy_ref)
            if policy_name in policies:
                return AgentPolicy(policies[policy_name])
            logger.warning(
                "Crew default policy '%s' not found, using default",
                policy_name,
                extra={
                    "event": "policy_not_found",
                    "policy_name": policy_name,
                    "fallback": "global_default",
                },
            )

    return DEFAULT_POLICY


def _extract_name(ref_or_name: str) -> str:
    """Extract resource name from a ref string or plain name."""
    ref = parse_ref(ref_or_name)
    return ref.name if ref else ref_or_name
