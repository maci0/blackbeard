"""Sandbox selection logic.

Determines which sandbox tier to use for a tool based on:
1. Tool's declared sandbox tier (tool.spec.sandbox)
2. Agent policy's minimum sandbox tier (policy.spec.sandbox.minimum_tier)
3. System default (none)

Tier ordering: none < wasm < docker < microvm
Higher tier = more isolation. Policy floor promotes lower tiers upward.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Tier ordering — higher index = more isolation
TIER_ORDER = ["none", "wasm", "docker", "microvm"]
_TIER_RANK: dict[str, int] = {name: i for i, name in enumerate(TIER_ORDER)}


def tier_rank(tier: str) -> int:
    """Get the numeric rank of a sandbox tier."""
    rank = _TIER_RANK.get(tier)
    if rank is not None:
        return rank
    logger.warning(f"Unknown sandbox tier '{tier}', defaulting to 'none'")
    return 0


def select_sandbox(
    tool_tier: str = "none",
    policy_minimum: str | None = None,
    system_default: str = "none",
) -> str:
    """Select the effective sandbox tier for a tool.

    Returns the highest tier among:
    - tool's declared tier
    - policy's minimum tier
    - system default
    """
    effective = tool_tier or system_default

    if policy_minimum:
        if tier_rank(policy_minimum) > tier_rank(effective):
            logger.info(
                f"Sandbox tier promoted: {effective} → {policy_minimum} (policy minimum)"
            )
            effective = policy_minimum

    # MVP: only support none and wasm
    if effective not in ("none", "wasm"):
        logger.warning(f"Sandbox tier '{effective}' not supported in MVP, falling back to 'wasm'")
        effective = "wasm"

    return effective
