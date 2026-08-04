"""Execution engine: crew lifecycle management.

Module map:

- ``executor`` — ThreadPoolExecutor path, kickoff/train/test entrypoints
- ``loader`` — Build CrewAI objects from resource snapshots
- ``flow_runner`` — Sequential/flow step execution
- ``execution_listener`` — Event persistence, webhooks, OTEL hooks
- ``policy`` / ``budget`` — AgentPolicy limits and cost alerts
- ``scheduler`` — Cron automations
- ``temporal`` — Optional Temporal workflow adapter (lazy; no hard dep)
- ``sandbox/`` — Tool isolation tiers (container, gVisor, Firecracker, WASM)
- ``memory/`` — External memory backends (e.g. MuninnDB)
- ``assistant`` / ``agency_import`` / ``discovery_tools`` — supporting features

Public re-exports below are the executor lifecycle surface; import other
engine modules by path (e.g. ``blackbeard.engine.loader``).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ExecutionError",
    "ExecutionNotFoundError",
    "get_pool_status",
    "recover_stale_executions",
    "shutdown_executor",
]

_EXECUTOR_ATTRS = frozenset(__all__)


def __getattr__(name: str) -> Any:
    if name not in _EXECUTOR_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module("blackbeard.engine.executor")
    for attr in _EXECUTOR_ATTRS:
        globals()[attr] = getattr(module, attr)
    return globals()[name]
