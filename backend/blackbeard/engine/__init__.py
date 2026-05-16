"""Execution engine: crew lifecycle and resource loading."""

from __future__ import annotations

from typing import Any

__all__ = [
    "ExecutionError",
    "ExecutionNotFoundError",
    "get_pool_status",
    "recover_stale_executions",
    "shutdown_executor",
]

_LAZY_IMPORTS: dict[str, tuple[str, ...]] = {
    "blackbeard.engine.executor": (
        "ExecutionError",
        "ExecutionNotFoundError",
        "get_pool_status",
        "recover_stale_executions",
        "shutdown_executor",
    ),
}

_NAME_TO_MODULE = {name: mod for mod, names in _LAZY_IMPORTS.items() for name in names}


def __getattr__(name: str) -> Any:
    module_path = _NAME_TO_MODULE.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    for attr in _LAZY_IMPORTS[module_path]:
        globals()[attr] = getattr(module, attr)
    return globals()[name]
