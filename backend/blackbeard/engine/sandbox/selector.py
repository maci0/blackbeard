"""Sandbox selection logic.

Determines which sandbox tier to use for a tool based on:
1. Tool's declared sandbox tier (tool.spec.sandbox)
2. Agent policy's minimum sandbox tier (policy.spec.sandbox.minimum_tier)
3. System default (none)

Tier ordering: none < wasm < docker = podman < gvisor < microvm
Higher tier = more isolation. Policy floor promotes lower tiers upward.

Docker and podman share the same isolation level (container-based).
gVisor adds syscall-level isolation on top of container runtimes.
MicroVM provides the highest isolation via Firecracker or Cloud Hypervisor.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Tier ordering — higher index = more isolation.
# Docker and podman are at the same level (both provide container isolation).
# gVisor adds syscall-level isolation via runsc on top of docker/podman.
TIER_ORDER = ["none", "wasm", "docker", "podman", "gvisor", "microvm"]
_TIER_RANK: dict[str, int] = {
    "none": 0,
    "wasm": 1,
    "docker": 2,
    "podman": 2,
    "gvisor": 3,
    "microvm": 4,
}


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

    When the policy minimum exceeds the tool's tier, the tool is promoted
    to the policy minimum.  If docker and podman are at the same rank,
    promotion preserves the specific tier name from the policy.
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

    return effective
