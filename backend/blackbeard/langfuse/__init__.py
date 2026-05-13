"""Langfuse observability integration."""

from __future__ import annotations

from typing import Any

from blackbeard.langfuse.client import get_langfuse, shutdown_langfuse

__all__ = [
    "BlackbeardLangfuseListener",
    "get_langfuse",
    "shutdown_langfuse",
]


def __getattr__(name: str) -> Any:
    if name == "BlackbeardLangfuseListener":
        from blackbeard.langfuse.listener import BlackbeardLangfuseListener

        globals()["BlackbeardLangfuseListener"] = BlackbeardLangfuseListener
        return BlackbeardLangfuseListener
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
