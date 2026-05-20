"""Sandbox tier selection and runtime isolation."""

from __future__ import annotations

from blackbeard.engine.sandbox.container_runtime import (
    ContainerResult,
    ContainerRuntimeError,
    ContainerSandbox,
    ContainerTimeoutError,
)
from blackbeard.engine.sandbox.gvisor_runtime import (
    GVisorResult,
    GVisorRuntimeError,
    GVisorSandbox,
    GVisorTimeoutError,
    is_gvisor_available,
)
from blackbeard.engine.sandbox.microvm_runtime import (
    MicroVMError,
    MicroVMResult,
    MicroVMRuntimeError,
    MicroVMSandbox,
    MicroVMTimeoutError,
    is_krun_available,
)
from blackbeard.engine.sandbox.selector import TIER_ORDER, select_sandbox, tier_rank

__all__ = [
    "TIER_ORDER",
    "ContainerResult",
    "ContainerRuntimeError",
    "ContainerSandbox",
    "ContainerTimeoutError",
    "GVisorResult",
    "GVisorRuntimeError",
    "GVisorSandbox",
    "GVisorTimeoutError",
    "MicroVMError",
    "MicroVMResult",
    "MicroVMRuntimeError",
    "MicroVMSandbox",
    "MicroVMTimeoutError",
    "is_gvisor_available",
    "is_krun_available",
    "select_sandbox",
    "tier_rank",
]
