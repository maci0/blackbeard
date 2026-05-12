"""Wasmtime wrapper for executing WASM tools in a sandbox.

Provides isolated execution with:
- Fuel metering (deterministic execution limits)
- Capability-based access control (WASI permissions)
- Module caching (LRU)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import wasmtime

logger = logging.getLogger(__name__)

# Safe environment variables to pass through to WASM tools (never leak secrets)
_SAFE_ENV_VARS = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TZ", "TERM")

# Default fuel limit (~100M instructions ≈ a few seconds of compute)
DEFAULT_FUEL = 100_000_000

# Default module cache size
DEFAULT_CACHE_SIZE = 50


class WasmExecutionError(Exception):
    """Raised when WASM tool execution fails."""


class WasmTimeoutError(WasmExecutionError):
    """Raised when WASM tool runs out of fuel."""


class WasmToolResult:
    """Result of a WASM tool execution."""

    def __init__(self, output: str, success: bool, error: str | None = None, duration_ms: int = 0):
        self.output = output
        self.success = success
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class ModuleCache:
    """Thread-safe LRU cache for compiled WASM modules."""

    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE):
        self._cache: OrderedDict[str, wasmtime.Module] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> wasmtime.Module | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, module: wasmtime.Module) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = module

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


class WasmSandbox:
    """Executes WASM tools in an isolated Wasmtime sandbox."""

    def __init__(
        self,
        fuel_limit: int = DEFAULT_FUEL,
        cache_size: int = DEFAULT_CACHE_SIZE,
        allowed_capabilities: set[str] | None = None,
    ):
        self._fuel_limit = fuel_limit
        self._cache = ModuleCache(max_size=cache_size)
        self._allowed_capabilities = allowed_capabilities or set()

        # Create engine with fuel consumption enabled
        config = wasmtime.Config()
        config.consume_fuel = True
        config.cache = True
        self._engine = wasmtime.Engine(config)

    def _create_store(self) -> wasmtime.Store:
        """Create a new store with fuel limit."""
        store = wasmtime.Store(self._engine)
        store.set_fuel(self._fuel_limit)
        return store

    def _load_module(self, wasm_path: str) -> wasmtime.Module:
        """Load and cache a WASM module."""
        cached = self._cache.get(wasm_path)
        if cached is not None:
            return cached

        path = Path(wasm_path)
        resolved = path.resolve()
        cwd = Path.cwd().resolve()
        if not str(resolved).startswith(str(cwd) + os.sep) and resolved != cwd:
            raise WasmExecutionError(f"Invalid WASM module path: path must be within the application directory")
        if not resolved.exists():
            raise WasmExecutionError(f"WASM module not found: {wasm_path}")

        try:
            module = wasmtime.Module.from_file(self._engine, str(path))
            self._cache.put(wasm_path, module)
            return module
        except wasmtime.WasmtimeError as e:
            raise WasmExecutionError(f"Failed to compile WASM module: {e}") from e

    def _create_linker(self, store: wasmtime.Store) -> wasmtime.Linker:
        """Create a linker with WASI capabilities based on allowed capabilities."""
        linker = wasmtime.Linker(self._engine)

        # Configure WASI with minimal permissions
        wasi_config = wasmtime.WasiConfig()

        # Only inherit stdio if explicitly allowed
        if "stdio" in self._allowed_capabilities:
            wasi_config.inherit_stdout()
            wasi_config.inherit_stderr()

        # Environment variables — only pass safe ones, never leak secrets
        if "env" in self._allowed_capabilities:
            safe_pairs = []
            for key in _SAFE_ENV_VARS:
                val = os.environ.get(key)
                if val:
                    safe_pairs.append((key, val))
            if safe_pairs:
                wasi_config.env = safe_pairs

        store.set_wasi(wasi_config)
        linker.define_wasi()

        return linker

    def invoke(self, wasm_path: str, input_data: str | dict) -> WasmToolResult:
        """Execute a WASM tool with the given input.

        Args:
            wasm_path: Path to the .wasm file
            input_data: JSON string or dict to pass as input

        Returns:
            WasmToolResult with output, success status, and timing
        """
        if isinstance(input_data, dict):
            input_json = json.dumps(input_data)
        else:
            input_json = input_data

        start_time = time.monotonic()

        try:
            store = self._create_store()
            module = self._load_module(wasm_path)
            linker = self._create_linker(store)

            # Instantiate the module
            instance = linker.instantiate(store, module)

            # Look for the 'run' export
            run_func = instance.exports(store).get("run")
            if run_func is None:
                # Try component model style
                raise WasmExecutionError(
                    "WASM module does not export a 'run' function. "
                    "Ensure the module implements the blackbeard:tool interface."
                )

            # Call the function
            result = run_func(store, input_json)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Parse result — could be a string or structured
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    return WasmToolResult(
                        output=parsed.get("output", result),
                        success=parsed.get("success", True),
                        error=parsed.get("error"),
                        duration_ms=duration_ms,
                    )
                except json.JSONDecodeError:
                    return WasmToolResult(
                        output=result,
                        success=True,
                        duration_ms=duration_ms,
                    )
            else:
                return WasmToolResult(
                    output=str(result),
                    success=True,
                    duration_ms=duration_ms,
                )

        except wasmtime.WasmtimeError as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(e)

            # Check for fuel exhaustion
            if "fuel" in error_msg.lower() or "out of fuel" in error_msg.lower():
                raise WasmTimeoutError(
                    f"WASM tool exceeded fuel limit ({self._fuel_limit}): {error_msg}"
                ) from e

            raise WasmExecutionError(f"WASM execution failed: {error_msg}") from e

        except WasmExecutionError:
            raise

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            raise WasmExecutionError(f"Unexpected error during WASM execution: {e}") from e

    def describe(self, wasm_path: str) -> dict | None:
        """Get tool metadata from a WASM module's 'describe' export."""
        try:
            store = self._create_store()
            module = self._load_module(wasm_path)
            linker = self._create_linker(store)
            instance = linker.instantiate(store, module)

            describe_func = instance.exports(store).get("describe")
            if describe_func is None:
                return None

            result = describe_func(store)
            if isinstance(result, str):
                return json.loads(result)
            return None

        except Exception as e:
            logger.warning(f"Failed to get WASM tool description: {e}")
            return None

    @property
    def cache_size(self) -> int:
        """Number of cached modules."""
        return self._cache.size

    def clear_cache(self) -> None:
        """Clear the module cache."""
        self._cache.clear()
