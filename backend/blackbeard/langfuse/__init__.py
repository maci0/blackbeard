"""Langfuse observability integration."""

from blackbeard.langfuse.client import get_langfuse, shutdown_langfuse

__all__ = [
    "BlackbeardLangfuseListener",
    "get_langfuse",
    "shutdown_langfuse",
]


def __getattr__(name: str):
    if name == "BlackbeardLangfuseListener":
        from blackbeard.langfuse.listener import BlackbeardLangfuseListener
        globals()["BlackbeardLangfuseListener"] = BlackbeardLangfuseListener
        return BlackbeardLangfuseListener
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
