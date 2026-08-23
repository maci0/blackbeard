"""Plugin SDK: registration, discovery, and lifecycle for extension points.

Supports four plugin types: tools, guardrails, auth providers, and
execution hooks. Plugins are loaded from a configurable directory
at startup and registered in a global registry.

Import from this package root; the implementation lives in ``registry``
and the discovery/loading machinery in ``loader``.
"""

from __future__ import annotations

from blackbeard.plugins.registry import (
    PluginMeta,
    PluginRegistry,
    PluginType,
    registry,
)

__all__ = [
    "PluginMeta",
    "PluginRegistry",
    "PluginType",
    "registry",
]
