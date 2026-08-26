"""Wasmtime wrapper for executing WASM tools in a sandbox.

Provides isolated execution with:
- Fuel metering (instruction-count limits; wall-clock time varies by host CPU)
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
from typing import Any, cast

import wasmtime

logger = logging.getLogger(__name__)

_APP_BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Only pass non-secret env vars into WASM sandboxes
_SAFE_ENV_VARS = ("LANG", "LC_ALL", "TZ", "TERM")

# ~100M instructions; actual wall-clock time varies by host CPU
DEFAULT_FUEL = 100_000_000

DEFAULT_CACHE_SIZE = 50

MAX_OUTPUT_BYTES = 1_024 * 1_024


def _log_extra(execution_id: str | None, **kwargs: Any) -> dict[str, Any]:
    if execution_id:
        kwargs["execution_id"] = execution_id
    return kwargs


class WasmExecutionError(Exception):
    pass


class WasmTimeoutError(WasmExecutionError):
    """Raised when WASM tool runs out of fuel."""


class WasmToolResult:
    """Result of a WASM tool execution."""

    __slots__ = ("duration_ms", "error", "output", "success")

    def __init__(
        self,
        output: str,
        success: bool,
        error: str | None = None,
        duration_ms: int = 0,
    ) -> None:
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

    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE) -> None:
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
                self._cache[key] = module
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
    ) -> None:
        self._fuel_limit = fuel_limit
        self._cache = ModuleCache(max_size=cache_size)
        self._allowed_capabilities = allowed_capabilities or set()

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
        path = Path(wasm_path)
        resolved = path.resolve()

        if not resolved.is_relative_to(_APP_BASE_DIR):
            raise WasmExecutionError(
                "Invalid WASM module path: path must be within the application directory"
            )

        cache_key = str(resolved)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if not resolved.is_file():
            raise WasmExecutionError(f"WASM module not found or not a regular file: {wasm_path}")

        try:
            module = wasmtime.Module.from_file(self._engine, str(resolved))
            self._cache.put(cache_key, module)
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

        # Environment variables: only pass safe ones, never leak secrets
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

    def _instantiate(self, wasm_path: str) -> tuple[wasmtime.Store, wasmtime.Instance]:
        """Create store, load module, link, and instantiate."""
        store = self._create_store()
        module = self._load_module(wasm_path)
        linker = self._create_linker(store)
        instance = linker.instantiate(store, module)
        return store, instance

    def invoke(
        self,
        wasm_path: str,
        input_data: str | dict[str, Any],
        execution_id: str | None = None,
    ) -> WasmToolResult:
        """Execute a WASM tool with the given input.

        Args:
            wasm_path: Path to the .wasm file
            input_data: JSON string or dict to pass as input
            execution_id: Optional execution ID for log correlation

        Returns:
            WasmToolResult with output, success status, and timing
        """
        input_json = json.dumps(input_data) if isinstance(input_data, dict) else input_data

        logger.info(
            "WASM invoke: path=%s input_bytes=%d fuel=%d",
            wasm_path,
            len(input_json),
            self._fuel_limit,
            extra=_log_extra(
                execution_id,
                event="wasm_invoke",
                wasm_path=wasm_path,
                input_bytes=len(input_json),
                fuel_limit=self._fuel_limit,
            ),
        )
        start_time = time.monotonic()

        try:
            store, instance = self._instantiate(wasm_path)

            exports = cast("Any", instance.exports(store))
            run_func = exports.get("run")
            if run_func is None:
                raise WasmExecutionError(
                    "WASM module does not export a 'run' function. "
                    "Ensure the module implements the blackbeard:tool interface."
                )

            result = run_func(store, input_json)

            duration_ms = int((time.monotonic() - start_time) * 1000)
            fuel_remaining = store.get_fuel()
            fuel_consumed = self._fuel_limit - fuel_remaining

            logger.info(
                "WASM completed: path=%s duration_ms=%d fuel_consumed=%d",
                wasm_path,
                duration_ms,
                fuel_consumed,
                extra=_log_extra(
                    execution_id,
                    event="wasm_completed",
                    wasm_path=wasm_path,
                    duration_ms=duration_ms,
                    fuel_consumed=fuel_consumed,
                    fuel_remaining=fuel_remaining,
                ),
            )

            raw = str(result) if not isinstance(result, str) else result
            if len(raw) > MAX_OUTPUT_BYTES:
                raise WasmExecutionError(
                    f"WASM output exceeds size limit ({len(raw)} > {MAX_OUTPUT_BYTES} bytes)"
                )

            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    output = parsed.get("output", result)
                    if not isinstance(output, str):
                        output = json.dumps(output)
                    error = parsed.get("error")
                    if error is not None and not isinstance(error, str):
                        error = str(error)
                    return WasmToolResult(
                        output=output,
                        success=bool(parsed.get("success", True)),
                        error=error,
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
                    output=raw,
                    success=True,
                    duration_ms=duration_ms,
                )

        except wasmtime.WasmtimeError as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(e)

            logger.error(
                "WASM failed: path=%s duration_ms=%d error=%s",
                wasm_path,
                duration_ms,
                error_msg,
                exc_info=True,
                extra=_log_extra(
                    execution_id,
                    event="wasm_failed",
                    wasm_path=wasm_path,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                    error_message=error_msg[:500],
                ),
            )

            if "fuel" in error_msg.lower():
                raise WasmTimeoutError(
                    f"WASM tool exceeded fuel limit ({self._fuel_limit}): {error_msg}"
                ) from e

            raise WasmExecutionError(f"WASM execution failed: {error_msg}") from e

        except WasmExecutionError:
            raise

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "WASM unexpected error: path=%s duration_ms=%d error=%s",
                wasm_path,
                duration_ms,
                e,
                exc_info=True,
                extra=_log_extra(
                    execution_id,
                    event="wasm_unexpected_error",
                    wasm_path=wasm_path,
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                ),
            )
            raise WasmExecutionError(f"Unexpected error during WASM execution: {e}") from e

    def describe(self, wasm_path: str) -> dict[str, Any] | None:
        """Get tool metadata from a WASM module's 'describe' export."""
        try:
            store, instance = self._instantiate(wasm_path)

            exports = cast("Any", instance.exports(store))
            describe_func = exports.get("describe")
            if describe_func is None:
                return None

            result = describe_func(store)
            if isinstance(result, str):
                return cast("dict[str, Any]", json.loads(result))
            return None

        except Exception as e:
            logger.warning(
                "Failed to get WASM tool description: %s",
                e,
                exc_info=True,
                extra={
                    "event": "wasm_describe_failed",
                    "wasm_path": wasm_path,
                    "error_type": type(e).__name__,
                },
            )
            return None

    @property
    def cache_size(self) -> int:
        """Number of cached modules."""
        return self._cache.size

    def clear_cache(self) -> None:
        """Clear the module cache."""
        self._cache.clear()


_shared_sandbox: WasmSandbox | None = None
_shared_sandbox_lock = threading.Lock()


def get_shared_sandbox() -> WasmSandbox:
    """Return the process-wide default sandbox.

    Reuses one wasmtime Engine and module cache across all tool calls:
    per-call construction pays engine setup and module reload every time
    and makes the LRU module cache useless. Stores are still created per
    invoke, so isolation between calls is unchanged.
    """
    global _shared_sandbox
    with _shared_sandbox_lock:
        if _shared_sandbox is None:
            _shared_sandbox = WasmSandbox()
        return _shared_sandbox
