"""Execution engine: crew lifecycle and resource loading."""

from __future__ import annotations

from typing import Any

__all__ = [
    "ExecutionError",
    "ExecutionNotFoundError",
    "LoaderError",
    "ResourceLoader",
    "get_execution",
    "get_execution_status",
    "list_execution_events",
    "recover_stale_executions",
    "shutdown_executor",
]


def __getattr__(name: str) -> Any:
    if name in (
        "ExecutionError",
        "ExecutionNotFoundError",
        "recover_stale_executions",
        "shutdown_executor",
    ):
        from blackbeard.engine.executor import (
            ExecutionError,
            ExecutionNotFoundError,
            recover_stale_executions,
            shutdown_executor,
        )

        globals()["ExecutionError"] = ExecutionError
        globals()["ExecutionNotFoundError"] = ExecutionNotFoundError
        globals()["recover_stale_executions"] = recover_stale_executions
        globals()["shutdown_executor"] = shutdown_executor
        return globals()[name]
    if name in ("LoaderError", "ResourceLoader"):
        from blackbeard.engine.loader import LoaderError, ResourceLoader

        globals()["LoaderError"] = LoaderError
        globals()["ResourceLoader"] = ResourceLoader
        return globals()[name]
    if name in ("get_execution", "get_execution_status", "list_execution_events"):
        from blackbeard.engine.executor import (
            get_execution,
            get_execution_status,
            list_execution_events,
        )

        globals()["get_execution"] = get_execution
        globals()["get_execution_status"] = get_execution_status
        globals()["list_execution_events"] = list_execution_events
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
