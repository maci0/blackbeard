"""Sandbox selection logic.

Determines which sandbox tier to use for a tool based on:
1. Tool's declared sandbox tier (tool.spec.sandbox)
2. Agent policy's minimum sandbox tier (policy.spec.sandbox.minimum_tier)
3. System default (none)

Tier ordering: none < wasm < docker = podman < gvisor < microvm
Higher tier = more isolation. Policy floor promotes lower tiers upward.

Docker and podman share the same isolation level (container-based).
gVisor adds syscall-level isolation on top of container runtimes.
MicroVM provides the highest isolation via Firecracker or libkrun.

The "microvm" tier supports two backends:
- **Firecracker** (preferred): standalone VMM, each tool gets a dedicated VM
  with its own kernel. Requires firecracker binary + kernel + rootfs + /dev/kvm.
- **libkrun** (fallback): OCI runtime wrapping KVM via crun/krun, uses
  Docker/Podman as the container manager. Lighter setup requirements.

``select_microvm_backend()`` determines which backend to use at runtime.
"""

from __future__ import annotations

import logging
import os

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


def select_microvm_backend() -> str:
    """Determine which MicroVM backend to use at runtime.

    Selection order:
    1. If ``FIRECRACKER_KERNEL`` is set and ``firecracker`` is available,
       use Firecracker.
    2. Else if ``krun``/``crun`` is available, use libkrun.
    3. Else return ``"none"`` (no microvm backend available).

    This function performs lazy imports to avoid circular dependencies
    and to skip availability checks for backends that are not needed.

    Returns:
        ``"firecracker"``, ``"krun"``, or ``"none"``.
    """
    # Check Firecracker first — it provides stronger isolation
    firecracker_kernel = os.environ.get("FIRECRACKER_KERNEL", "")
    if firecracker_kernel:
        from blackbeard.engine.sandbox.firecracker import is_firecracker_available

        if is_firecracker_available():
            logger.info(
                "MicroVM backend: firecracker (kernel=%s)",
                firecracker_kernel,
                extra={
                    "event": "microvm_backend_selected",
                    "backend": "firecracker",
                    "kernel": firecracker_kernel,
                },
            )
            return "firecracker"
        logger.warning(
            "FIRECRACKER_KERNEL is set but firecracker binary or /dev/kvm "
            "not found -- falling back to libkrun",
            extra={
                "event": "firecracker_fallback",
                "kernel": firecracker_kernel,
            },
        )

    # Fall back to libkrun
    from blackbeard.engine.sandbox.microvm_runtime import is_krun_available

    if is_krun_available():
        logger.info(
            "MicroVM backend: krun (libkrun)",
            extra={"event": "microvm_backend_selected", "backend": "krun"},
        )
        return "krun"

    logger.warning(
        "No MicroVM backend available (neither firecracker nor krun found)",
        extra={"event": "microvm_backend_none"},
    )
    return "none"
