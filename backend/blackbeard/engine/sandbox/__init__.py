"""Sandbox tier selection and runtime isolation.

All symbols are lazy-loaded to avoid importing heavy sandbox backends
(container, firecracker, gvisor, microvm, wasm) at module level.
Import individual submodules directly for type annotations under
TYPE_CHECKING.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "TIER_ORDER",
    "BaseSandbox",
    "ContainerResult",
    "ContainerRuntimeError",
    "ContainerSandbox",
    "ContainerTimeoutError",
    "FirecrackerConfigError",
    "FirecrackerError",
    "FirecrackerResult",
    "FirecrackerRuntimeError",
    "FirecrackerSandbox",
    "FirecrackerTimeoutError",
    "GVisorResult",
    "GVisorRuntimeError",
    "GVisorSandbox",
    "GVisorTimeoutError",
    "MicroVMError",
    "MicroVMResult",
    "MicroVMRuntimeError",
    "MicroVMSandbox",
    "MicroVMTimeoutError",
    "SandboxResult",
    "SandboxRuntimeError",
    "SandboxTimeoutError",
    "is_firecracker_available",
    "is_gvisor_available",
    "is_krun_available",
    "select_microvm_backend",
    "select_sandbox",
    "tier_rank",
]

_ATTR_TO_MODULE: dict[str, str] = {
    "BaseSandbox": "blackbeard.engine.sandbox.base",
    "SandboxResult": "blackbeard.engine.sandbox.base",
    "SandboxRuntimeError": "blackbeard.engine.sandbox.base",
    "SandboxTimeoutError": "blackbeard.engine.sandbox.base",
    "ContainerResult": "blackbeard.engine.sandbox.container_runtime",
    "ContainerRuntimeError": "blackbeard.engine.sandbox.container_runtime",
    "ContainerSandbox": "blackbeard.engine.sandbox.container_runtime",
    "ContainerTimeoutError": "blackbeard.engine.sandbox.container_runtime",
    "FirecrackerConfigError": "blackbeard.engine.sandbox.firecracker",
    "FirecrackerError": "blackbeard.engine.sandbox.firecracker",
    "FirecrackerResult": "blackbeard.engine.sandbox.firecracker",
    "FirecrackerRuntimeError": "blackbeard.engine.sandbox.firecracker",
    "FirecrackerSandbox": "blackbeard.engine.sandbox.firecracker",
    "FirecrackerTimeoutError": "blackbeard.engine.sandbox.firecracker",
    "is_firecracker_available": "blackbeard.engine.sandbox.firecracker",
    "GVisorResult": "blackbeard.engine.sandbox.gvisor_runtime",
    "GVisorRuntimeError": "blackbeard.engine.sandbox.gvisor_runtime",
    "GVisorSandbox": "blackbeard.engine.sandbox.gvisor_runtime",
    "GVisorTimeoutError": "blackbeard.engine.sandbox.gvisor_runtime",
    "is_gvisor_available": "blackbeard.engine.sandbox.gvisor_runtime",
    "MicroVMError": "blackbeard.engine.sandbox.microvm_runtime",
    "MicroVMResult": "blackbeard.engine.sandbox.microvm_runtime",
    "MicroVMRuntimeError": "blackbeard.engine.sandbox.microvm_runtime",
    "MicroVMSandbox": "blackbeard.engine.sandbox.microvm_runtime",
    "MicroVMTimeoutError": "blackbeard.engine.sandbox.microvm_runtime",
    "is_krun_available": "blackbeard.engine.sandbox.microvm_runtime",
    "TIER_ORDER": "blackbeard.engine.sandbox.selector",
    "select_microvm_backend": "blackbeard.engine.sandbox.selector",
    "select_sandbox": "blackbeard.engine.sandbox.selector",
    "tier_rank": "blackbeard.engine.sandbox.selector",
}


def __getattr__(name: str) -> Any:
    module_path = _ATTR_TO_MODULE.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value
