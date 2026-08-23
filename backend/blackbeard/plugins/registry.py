"""Thread-safe global registry for plugin handlers."""

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "PluginMeta",
    "PluginRegistry",
    "PluginType",
    "registry",
]


class PluginType(enum.StrEnum):
    """Supported plugin extension points."""

    TOOL = "tool"
    GUARDRAIL = "guardrail"
    AUTH_PROVIDER = "auth_provider"
    EXECUTION_HOOK = "execution_hook"


@dataclass(frozen=True)
class PluginMeta:
    """Metadata describing a registered plugin."""

    name: str
    version: str
    description: str
    plugin_type: PluginType
    entry_point: str = ""


@dataclass
class _PluginEntry:
    """Internal container for a plugin's metadata and handler instance."""

    meta: PluginMeta
    handler: Any


class PluginRegistry:
    """Thread-safe registry for plugin handlers.

    Plugins are keyed by (plugin_type, name). Duplicate registrations
    for the same key replace the previous entry with a warning.
    """

    def __init__(self) -> None:
        self._plugins: dict[tuple[PluginType, str], _PluginEntry] = {}
        self._lock = threading.Lock()

    def register(self, meta: PluginMeta, handler: Any) -> None:
        """Register a plugin handler under its type and name."""
        key = (meta.plugin_type, meta.name)
        with self._lock:
            if key in self._plugins:
                logger.warning(
                    "Replacing existing plugin %s/%s",
                    meta.plugin_type.value,
                    meta.name,
                    extra={
                        "event": "plugin_replaced",
                        "plugin_type": meta.plugin_type.value,
                        "plugin_name": meta.name,
                    },
                )
            self._plugins[key] = _PluginEntry(meta=meta, handler=handler)
            logger.info(
                "Plugin registered: %s/%s v%s",
                meta.plugin_type.value,
                meta.name,
                meta.version,
                extra={
                    "event": "plugin_registered",
                    "plugin_type": meta.plugin_type.value,
                    "plugin_name": meta.name,
                    "plugin_version": meta.version,
                },
            )

    def unregister(self, plugin_type: PluginType, name: str) -> bool:
        """Remove a plugin from the registry. Returns True if it was found."""
        key = (plugin_type, name)
        with self._lock:
            removed = self._plugins.pop(key, None)
        if removed:
            logger.info(
                "Plugin unregistered: %s/%s",
                plugin_type.value,
                name,
                extra={
                    "event": "plugin_unregistered",
                    "plugin_type": plugin_type.value,
                    "plugin_name": name,
                },
            )
            return True
        return False

    def get(self, plugin_type: PluginType, name: str) -> Any | None:
        """Retrieve a plugin handler by type and name, or None if not found."""
        key = (plugin_type, name)
        with self._lock:
            entry = self._plugins.get(key)
        return entry.handler if entry else None

    def get_meta(self, plugin_type: PluginType, name: str) -> PluginMeta | None:
        """Retrieve plugin metadata by type and name."""
        key = (plugin_type, name)
        with self._lock:
            entry = self._plugins.get(key)
        return entry.meta if entry else None

    def list_plugins(self, plugin_type: PluginType | None = None) -> list[PluginMeta]:
        """List metadata for all plugins, optionally filtered by type."""
        with self._lock:
            entries = list(self._plugins.values())
        if plugin_type is not None:
            entries = [e for e in entries if e.meta.plugin_type == plugin_type]
        return [e.meta for e in entries]

    def clear(self) -> None:
        """Remove all registered plugins. Primarily useful for testing."""
        with self._lock:
            self._plugins.clear()


# Module-level singleton
registry = PluginRegistry()
