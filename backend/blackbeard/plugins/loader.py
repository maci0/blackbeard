"""Plugin discovery and loading from filesystem.

Scans a plugin directory for Python modules that expose a
``blackbeard_plugin`` dict attribute. Each module is imported,
its handler class is instantiated, and the plugin is registered
in the global registry.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from blackbeard.plugins import PluginMeta, PluginRegistry, PluginType, registry

logger = logging.getLogger(__name__)

__all__ = [
    "load_plugin_module",
    "load_plugins",
    "reload_plugin",
]

_TYPE_MAP: dict[str, PluginType] = {
    "tool": PluginType.TOOL,
    "guardrail": PluginType.GUARDRAIL,
    "auth_provider": PluginType.AUTH_PROVIDER,
    "execution_hook": PluginType.EXECUTION_HOOK,
}

# Only allow safe module names to prevent directory traversal or injection
_SAFE_MODULE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Track loaded modules by name for reload support
_loaded_modules: dict[str, str] = {}  # plugin_name -> module_name


def _default_plugin_dir() -> str:
    """Return the default plugin directory path.

    Uses PLUGIN_DIR env var if set, otherwise ``plugins/`` relative to
    the current working directory.
    """
    return os.environ.get("PLUGIN_DIR", "plugins")


def _validate_plugin_dict(plugin_dict: dict[str, Any], module_name: str) -> str | None:
    """Validate a blackbeard_plugin dict. Returns error message or None."""
    required_keys = ("name", "version", "type", "handler")
    missing = [k for k in required_keys if k not in plugin_dict]
    if missing:
        return f"module '{module_name}' blackbeard_plugin missing keys: {', '.join(missing)}"

    plugin_type_str = plugin_dict["type"]
    if plugin_type_str not in _TYPE_MAP:
        return (
            f"module '{module_name}' has unknown plugin type '{plugin_type_str}'. "
            f"Valid types: {', '.join(_TYPE_MAP)}"
        )

    handler_cls = plugin_dict["handler"]
    if not isinstance(handler_cls, type):
        return f"module '{module_name}' handler must be a class, got {type(handler_cls).__name__}"

    return None


def load_plugin_module(
    file_path: str,
    target_registry: PluginRegistry | None = None,
) -> PluginMeta | None:
    """Load a single plugin module from a file path.

    Returns the PluginMeta on success, None on failure. Errors are
    logged but do not propagate, so one bad plugin cannot break startup.
    """
    reg = target_registry or registry
    module_file = Path(file_path)

    if not module_file.is_file() or module_file.suffix != ".py":
        return None

    stem = module_file.stem
    if stem.startswith("_") or not _SAFE_MODULE_NAME.match(stem):
        logger.debug(
            "Skipping non-plugin file: %s",
            module_file.name,
            extra={"event": "plugin_skip_file", "plugin_filename": module_file.name},
        )
        return None

    module_name = f"blackbeard_plugins.{stem}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(module_file))
        if spec is None or spec.loader is None:
            logger.warning(
                "Cannot create import spec for %s",
                file_path,
                extra={"event": "plugin_import_spec_failed", "path": file_path},
            )
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception:
        logger.exception(
            "Failed to import plugin module: %s",
            file_path,
            extra={"event": "plugin_import_failed", "path": file_path},
        )
        return None

    plugin_dict = getattr(module, "blackbeard_plugin", None)
    if plugin_dict is None or not isinstance(plugin_dict, dict):
        logger.debug(
            "Module %s has no blackbeard_plugin dict, skipping",
            stem,
            extra={"event": "plugin_no_descriptor", "module": stem},
        )
        # Clean up from sys.modules since it's not a plugin
        sys.modules.pop(module_name, None)
        return None

    error = _validate_plugin_dict(plugin_dict, stem)
    if error:
        logger.warning(
            "Invalid plugin descriptor in %s: %s",
            stem,
            error,
            extra={"event": "plugin_invalid_descriptor", "module": stem, "error": error},
        )
        sys.modules.pop(module_name, None)
        return None

    plugin_type = _TYPE_MAP[plugin_dict["type"]]
    handler_cls = plugin_dict["handler"]

    try:
        handler_instance = handler_cls()
    except Exception:
        logger.exception(
            "Failed to instantiate plugin handler %s from %s",
            handler_cls.__name__,
            stem,
            extra={
                "event": "plugin_instantiation_failed",
                "module": stem,
                "handler_class": handler_cls.__name__,
            },
        )
        sys.modules.pop(module_name, None)
        return None

    meta = PluginMeta(
        name=plugin_dict["name"],
        version=plugin_dict["version"],
        description=plugin_dict.get("description", ""),
        plugin_type=plugin_type,
        entry_point=str(module_file),
    )

    reg.register(meta, handler_instance)
    _loaded_modules[meta.name] = module_name
    return meta


def load_plugins(
    plugin_dir: str | None = None,
    target_registry: PluginRegistry | None = None,
) -> list[PluginMeta]:
    """Scan a directory for plugin modules and register them.

    Each ``.py`` file in the directory is checked for a ``blackbeard_plugin``
    module-level attribute. Files starting with ``_`` are skipped.

    Args:
        plugin_dir: Directory to scan. Defaults to PLUGIN_DIR env var
            or ``plugins/`` in the working directory.
        target_registry: Registry to use. Defaults to the global singleton.

    Returns:
        List of successfully loaded plugin metadata.
    """
    t0 = time.monotonic()
    resolved_dir = plugin_dir or _default_plugin_dir()
    plugin_path = Path(resolved_dir)

    if not plugin_path.is_dir():
        logger.debug(
            "Plugin directory does not exist: %s (skipping)",
            resolved_dir,
            extra={"event": "plugin_dir_missing", "path": resolved_dir},
        )
        return []

    loaded: list[PluginMeta] = []
    files = sorted(plugin_path.glob("*.py"))
    for file_path in files:
        meta = load_plugin_module(str(file_path), target_registry)
        if meta is not None:
            loaded.append(meta)

    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
    logger.info(
        "Plugin scan complete: %d plugins loaded from %s (%.0fms)",
        len(loaded),
        resolved_dir,
        elapsed_ms,
        extra={
            "event": "plugin_scan_complete",
            "plugin_dir": resolved_dir,
            "loaded_count": len(loaded),
            "scanned_files": len(files),
            "elapsed_ms": elapsed_ms,
        },
    )
    return loaded


def reload_plugin(
    name: str,
    target_registry: PluginRegistry | None = None,
) -> PluginMeta | None:
    """Reload a previously loaded plugin by name.

    Finds the module in sys.modules, re-executes it, and re-registers
    the handler. Returns updated PluginMeta on success, None on failure.
    """
    reg = target_registry or registry
    module_name = _loaded_modules.get(name)
    if module_name is None:
        logger.warning(
            "Cannot reload unknown plugin: %s",
            name,
            extra={"event": "plugin_reload_unknown", "plugin_name": name},
        )
        return None

    module = sys.modules.get(module_name)
    if module is None:
        logger.warning(
            "Plugin module not in sys.modules: %s",
            module_name,
            extra={"event": "plugin_reload_missing_module", "module_name": module_name},
        )
        return None

    file_path = getattr(module, "__file__", None)
    if file_path is None:
        logger.warning(
            "Plugin module has no __file__: %s",
            module_name,
            extra={"event": "plugin_reload_no_file", "module_name": module_name},
        )
        return None

    # Remove old module so load_plugin_module gets a clean import
    sys.modules.pop(module_name, None)

    meta = load_plugin_module(file_path, reg)
    if meta is None:
        logger.warning(
            "Plugin reload failed for: %s",
            name,
            extra={"event": "plugin_reload_failed", "plugin_name": name},
        )
    else:
        logger.info(
            "Plugin reloaded: %s v%s",
            meta.name,
            meta.version,
            extra={
                "event": "plugin_reloaded",
                "plugin_name": meta.name,
                "plugin_version": meta.version,
            },
        )
    return meta
