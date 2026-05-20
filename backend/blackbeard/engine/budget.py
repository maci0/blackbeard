"""Budget and policy helpers for crew execution.

Handles budget limit derivation, policy spec extraction, and PII config.
"""

from __future__ import annotations

import logging
from typing import Any

from blackbeard.engine.policy import resolve_policy
from blackbeard.resources import parse_ref

logger = logging.getLogger(__name__)


def extract_policy_specs(
    resource_snapshot: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Extract AgentPolicy specs from a resource snapshot (policy name -> spec)."""
    return {
        snap["name"]: snap.get("spec", {})
        for snap in resource_snapshot.values()
        if snap.get("kind") == "AgentPolicy"
    }


def get_pii_config(
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
) -> dict[str, Any] | None:
    """Extract PII redaction config from applicable AgentPolicy resources.

    Scans the crew's agents for policy refs (agent-level then crew-level
    default) and returns the first PII config block that has ``enabled=True``.
    Returns ``None`` if no policy enables PII redaction.
    """
    crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
    crew_spec = crew_snap.get("spec", {})
    policy_specs = extract_policy_specs(resource_snapshot)

    # Check each agent's resolved policy for a PII block
    agent_refs = crew_spec.get("agents", [])
    for agent_ref in agent_refs:
        ref = parse_ref(agent_ref)
        if not ref:
            continue
        agent_snap = resource_snapshot.get(f"Agent/{ref.name}", {})
        agent_spec = agent_snap.get("spec", {})

        policy = resolve_policy(agent_spec, crew_spec, policy_specs)
        pii = policy.spec.get("pii")
        if isinstance(pii, dict) and pii.get("enabled"):
            return pii

    # Check crew-level default policy directly
    default_ref = crew_spec.get("default_agent_policy")
    if default_ref:
        name = parse_ref(default_ref)
        policy_name = name.name if name else default_ref
        policy_spec = policy_specs.get(policy_name, {})
        pii = policy_spec.get("pii")
        if isinstance(pii, dict) and pii.get("enabled"):
            return pii

    return None


def derive_budget_limits(
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    policy_specs: dict[str, dict[str, Any]] | None = None,
) -> tuple[float | None, int | None]:
    """Derive the most restrictive budget limits from applicable policies.

    Scans the crew's agents for policy refs (agent-level then crew-level
    default) and returns the minimum ``max_usd`` and ``max_tokens`` across
    all resolved policies.

    Returns:
        ``(max_budget_usd, max_tokens)`` -- either may be ``None`` if no
        policy defines that limit.
    """
    crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
    crew_spec = crew_snap.get("spec", {})

    if policy_specs is None:
        policy_specs = extract_policy_specs(resource_snapshot)

    budgets: list[float] = []
    token_limits: list[int] = []

    # Resolve policy for each agent referenced by the crew
    agent_refs = crew_spec.get("agents", [])
    for agent_ref in agent_refs:
        ref = parse_ref(agent_ref)
        if not ref:
            continue
        agent_snap = resource_snapshot.get(f"Agent/{ref.name}", {})
        agent_spec = agent_snap.get("spec", {})

        policy = resolve_policy(agent_spec, crew_spec, policy_specs)
        if policy.max_budget_usd is not None:
            budgets.append(policy.max_budget_usd)
        if policy.max_tokens is not None:
            token_limits.append(policy.max_tokens)

    max_budget = min(budgets) if budgets else None
    max_tokens = min(token_limits) if token_limits else None

    if max_budget is not None or max_tokens is not None:
        logger.info(
            "Budget limits derived for crew '%s': max_usd=%s max_tokens=%s",
            crew_name,
            max_budget,
            max_tokens,
            extra={
                "event": "budget_limits_derived",
                "crew_name": crew_name,
                "max_budget_usd": max_budget,
                "max_tokens": max_tokens,
                "agent_count": len(agent_refs),
                "policy_count": len(budgets) + len(token_limits),
            },
        )

    return max_budget, max_tokens
