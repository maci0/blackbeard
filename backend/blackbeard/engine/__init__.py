"""Execution engine: crew lifecycle, resource loading, policy, and sandbox."""

__all__ = [
    "ExecutionError",
    "LoaderError",
    "ResourceLoader",
    "shutdown_executor",
]


def __getattr__(name: str):
    if name in ("ExecutionError", "shutdown_executor"):
        from blackbeard.engine.executor import ExecutionError, shutdown_executor
        globals()["ExecutionError"] = ExecutionError
        globals()["shutdown_executor"] = shutdown_executor
        return globals()[name]
    if name in ("LoaderError", "ResourceLoader"):
        from blackbeard.engine.loader import LoaderError, ResourceLoader
        globals()["LoaderError"] = LoaderError
        globals()["ResourceLoader"] = ResourceLoader
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
