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
    logger.warning(
        "Unknown sandbox tier '%s', defaulting to 'none'",
        tier,
        extra={"event": "sandbox_tier_unknown", "tier": tier},
    )
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

    if policy_minimum and tier_rank(policy_minimum) > tier_rank(effective):
        logger.info(
            "Sandbox tier promoted: %s -> %s (policy minimum)",
            effective,
            policy_minimum,
            extra={
                "event": "sandbox_tier_promoted",
                "original_tier": effective,
                "promoted_tier": policy_minimum,
            },
        )
        effective = policy_minimum

    if effective not in ("none", "wasm"):
        logger.warning(
            "Sandbox tier '%s' not yet implemented, falling back to 'wasm'",
            effective,
            extra={
                "event": "sandbox_tier_fallback",
                "requested_tier": effective,
                "fallback_tier": "wasm",
            },
        )
        effective = "wasm"

    return effective
