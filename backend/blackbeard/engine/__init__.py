"""Execution engine: crew lifecycle management."""

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
