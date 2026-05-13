"""Tests for WASM sandbox: ModuleCache, WasmToolResult, WasmSandbox, select_sandbox."""

import pytest

from blackbeard.engine.sandbox.selector import select_sandbox, tier_rank
from blackbeard.engine.sandbox.wasm_runtime import (
    ModuleCache,
    WasmExecutionError,
    WasmSandbox,
    WasmToolResult,
)

# ---------------------------------------------------------------------------
# ModuleCache
# ---------------------------------------------------------------------------


class TestModuleCache:
    def test_cache_put_and_get(self):
        cache = ModuleCache(max_size=10)
        sentinel = object()
        cache.put("key1", sentinel)  # type: ignore[arg-type]
        assert cache.get("key1") is sentinel

    def test_cache_miss_returns_none(self):
        cache = ModuleCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_cache_lru_eviction(self):
        cache = ModuleCache(max_size=2)
        a, b, c = object(), object(), object()
        cache.put("a", a)  # type: ignore[arg-type]
        cache.put("b", b)  # type: ignore[arg-type]
        cache.put("c", c)  # type: ignore[arg-type]  — evicts "a"
        assert cache.get("a") is None
        assert cache.get("b") is b
        assert cache.get("c") is c

    def test_cache_access_refreshes(self):
        cache = ModuleCache(max_size=2)
        a, b, c = object(), object(), object()
        cache.put("a", a)  # type: ignore[arg-type]
        cache.put("b", b)  # type: ignore[arg-type]
        # Access "a" to move it to the end (most-recently-used)
        cache.get("a")
        cache.put("c", c)  # type: ignore[arg-type]  — should evict "b", not "a"
        assert cache.get("a") is a
        assert cache.get("b") is None
        assert cache.get("c") is c

    def test_cache_put_updates_existing_value(self):
        cache = ModuleCache(max_size=10)
        old_val, new_val = object(), object()
        cache.put("key1", old_val)  # type: ignore[arg-type]
        cache.put("key1", new_val)  # type: ignore[arg-type]
        assert cache.get("key1") is new_val
        assert cache.size == 1

    def test_cache_clear(self):
        cache = ModuleCache(max_size=10)
        cache.put("x", object())  # type: ignore[arg-type]
        cache.put("y", object())  # type: ignore[arg-type]
        cache.clear()
        assert cache.size == 0
        assert cache.get("x") is None

    def test_cache_size(self):
        cache = ModuleCache(max_size=10)
        assert cache.size == 0
        cache.put("a", object())  # type: ignore[arg-type]
        assert cache.size == 1
        cache.put("b", object())  # type: ignore[arg-type]
        assert cache.size == 2


# ---------------------------------------------------------------------------
# WasmToolResult
# ---------------------------------------------------------------------------


class TestWasmToolResult:
    def test_tool_result_to_dict(self):
        result = WasmToolResult(output="hello", success=True, error=None, duration_ms=42)
        d = result.to_dict()
        assert d == {"output": "hello", "success": True, "error": None, "duration_ms": 42}

    def test_tool_result_success(self):
        result = WasmToolResult(output="ok", success=True)
        assert result.success is True
        assert result.error is None

    def test_tool_result_failure(self):
        result = WasmToolResult(output="", success=False, error="something went wrong")
        assert result.success is False
        assert result.error == "something went wrong"


# ---------------------------------------------------------------------------
# WasmSandbox (non-execution tests — no real .wasm files needed)
# ---------------------------------------------------------------------------


class TestWasmSandbox:
    def test_sandbox_creation(self):
        sandbox = WasmSandbox(fuel_limit=1_000, cache_size=5)
        assert sandbox.cache_size == 0

    def test_sandbox_invoke_missing_module(self):
        sandbox = WasmSandbox()
        with pytest.raises(WasmExecutionError, match="Invalid WASM module path"):
            sandbox.invoke("/nonexistent/path/tool.wasm", "{}")

    def test_sandbox_cache_size(self):
        sandbox = WasmSandbox(cache_size=3)
        assert sandbox.cache_size == 0

    def test_sandbox_clear_cache(self):
        sandbox = WasmSandbox()
        # Clear on an empty cache should be a no-op
        sandbox.clear_cache()
        assert sandbox.cache_size == 0


# ---------------------------------------------------------------------------
# select_sandbox / tier_rank
# ---------------------------------------------------------------------------


class TestSandboxSelector:
    def test_tier_rank_ordering(self):
        assert tier_rank("none") < tier_rank("wasm")
        assert tier_rank("wasm") < tier_rank("docker")
        assert tier_rank("docker") < tier_rank("microvm")

    def test_tier_rank_unknown_falls_back_to_none(self):
        assert tier_rank("unknown_tier") == 0
        assert tier_rank("unknown_tier") == tier_rank("none")
        assert tier_rank("unknown_tier") < tier_rank("wasm")

    def test_select_default(self):
        # No policy → tool tier wins
        assert select_sandbox(tool_tier="none") == "none"
        assert select_sandbox(tool_tier="wasm") == "wasm"

    def test_select_policy_promotes(self):
        # Tool says none, policy requires wasm → wasm
        result = select_sandbox(tool_tier="none", policy_minimum="wasm")
        assert result == "wasm"

    def test_select_tool_higher_than_policy(self):
        # Tool already at wasm, policy says none → stays wasm
        result = select_sandbox(tool_tier="wasm", policy_minimum="none")
        assert result == "wasm"

    def test_select_unsupported_tier_fallback(self):
        # docker / microvm not supported in MVP → falls back to wasm
        result = select_sandbox(tool_tier="docker")
        assert result == "wasm"

        result = select_sandbox(tool_tier="microvm")
        assert result == "wasm"

    def test_select_policy_promotes_to_unsupported_falls_to_wasm(self):
        # Policy requires docker (unsupported) → falls back to wasm
        result = select_sandbox(tool_tier="none", policy_minimum="docker")
        assert result == "wasm"

    def test_select_policy_and_tool_both_none(self):
        result = select_sandbox(tool_tier="none", policy_minimum="none")
        assert result == "none"
