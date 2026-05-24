"""Tests for sandbox tiers: selector, ContainerSandbox, MicroVMSandbox, WasmSandbox."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.engine.sandbox.container_runtime import (
    ContainerResult,
    ContainerRuntimeError,
    ContainerSandbox,
    ContainerTimeoutError,
)
from blackbeard.engine.sandbox.microvm_runtime import (
    MicroVMResult,
    MicroVMRuntimeError,
    MicroVMSandbox,
    MicroVMTimeoutError,
    is_krun_available,
)
from blackbeard.engine.sandbox.selector import TIER_ORDER, select_sandbox, tier_rank
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
        cache.put("c", c)  # type: ignore[arg-type]
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
        cache.put("c", c)  # type: ignore[arg-type]
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
# WasmSandbox (non-execution tests -- no real .wasm files needed)
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

    def test_tier_rank_docker_equals_podman(self):
        """Docker and podman share the same isolation level."""
        assert tier_rank("docker") == tier_rank("podman")

    def test_tier_rank_podman_less_than_microvm(self):
        assert tier_rank("podman") < tier_rank("microvm")

    def test_tier_rank_unknown_falls_back_to_none(self):
        assert tier_rank("unknown_tier") == 0
        assert tier_rank("unknown_tier") == tier_rank("none")
        assert tier_rank("unknown_tier") < tier_rank("wasm")

    def test_tier_order_list(self):
        """TIER_ORDER contains all six tiers."""
        assert TIER_ORDER == ["none", "wasm", "docker", "podman", "gvisor", "microvm"]

    def test_select_default(self):
        # No policy -> tool tier wins
        assert select_sandbox(tool_tier="none") == "none"
        assert select_sandbox(tool_tier="wasm") == "wasm"

    def test_select_docker_tier(self):
        assert select_sandbox(tool_tier="docker") == "docker"

    def test_select_podman_tier(self):
        assert select_sandbox(tool_tier="podman") == "podman"

    def test_select_microvm_tier(self):
        assert select_sandbox(tool_tier="microvm") == "microvm"

    def test_select_policy_promotes(self):
        # Tool says none, policy requires wasm -> wasm
        result = select_sandbox(tool_tier="none", policy_minimum="wasm")
        assert result == "wasm"

    def test_select_policy_promotes_to_docker(self):
        result = select_sandbox(tool_tier="none", policy_minimum="docker")
        assert result == "docker"

    def test_select_policy_promotes_to_podman(self):
        result = select_sandbox(tool_tier="wasm", policy_minimum="podman")
        assert result == "podman"

    def test_select_policy_promotes_to_microvm(self):
        result = select_sandbox(tool_tier="docker", policy_minimum="microvm")
        assert result == "microvm"

    def test_select_tool_higher_than_policy(self):
        # Tool already at wasm, policy says none -> stays wasm
        result = select_sandbox(tool_tier="wasm", policy_minimum="none")
        assert result == "wasm"

    def test_select_tool_docker_policy_none(self):
        # Tool already at docker, policy says none -> stays docker
        result = select_sandbox(tool_tier="docker", policy_minimum="none")
        assert result == "docker"

    def test_select_tool_microvm_policy_docker(self):
        # Tool already at microvm, policy says docker -> stays microvm
        result = select_sandbox(tool_tier="microvm", policy_minimum="docker")
        assert result == "microvm"

    def test_select_policy_and_tool_both_none(self):
        result = select_sandbox(tool_tier="none", policy_minimum="none")
        assert result == "none"

    def test_select_docker_policy_podman_same_rank(self):
        """When tool is docker and policy is podman (same rank), tool wins."""
        result = select_sandbox(tool_tier="docker", policy_minimum="podman")
        assert result == "docker"

    def test_select_podman_policy_docker_same_rank(self):
        """When tool is podman and policy is docker (same rank), tool wins."""
        result = select_sandbox(tool_tier="podman", policy_minimum="docker")
        assert result == "podman"


# ---------------------------------------------------------------------------
# ContainerResult
# ---------------------------------------------------------------------------


class TestContainerResult:
    def test_to_dict(self):
        result = ContainerResult(exit_code=0, stdout="hello", stderr="")
        d = result.to_dict()
        assert d == {"exit_code": 0, "stdout": "hello", "stderr": ""}

    def test_frozen(self):
        result = ContainerResult(exit_code=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            result.exit_code = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ContainerSandbox -- runtime detection (mocked)
# ---------------------------------------------------------------------------


class TestContainerSandboxDetection:
    def test_detect_podman_preferred(self):
        """Auto-detect prefers podman over docker."""
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            sandbox = ContainerSandbox(runtime="auto")
            assert sandbox.runtime == "podman"

    def test_detect_docker_fallback(self):
        """Falls back to docker when podman is not available."""

        def _which(cmd):
            return "/usr/bin/docker" if cmd == "docker" else None

        with patch("shutil.which", side_effect=_which):
            sandbox = ContainerSandbox(runtime="auto")
            assert sandbox.runtime == "docker"

    def test_detect_none_raises(self):
        """Raises when no runtime is available."""
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(ContainerRuntimeError, match="No container runtime found"),
        ):
            ContainerSandbox(runtime="auto")

    def test_explicit_docker(self):
        with patch("shutil.which", return_value="/usr/bin/docker"):
            sandbox = ContainerSandbox(runtime="docker")
            assert sandbox.runtime == "docker"

    def test_explicit_podman(self):
        with patch("shutil.which", return_value="/usr/bin/podman"):
            sandbox = ContainerSandbox(runtime="podman")
            assert sandbox.runtime == "podman"

    def test_explicit_missing_raises(self):
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(ContainerRuntimeError, match="not found on PATH"),
        ):
            ContainerSandbox(runtime="docker")


# ---------------------------------------------------------------------------
# ContainerSandbox -- command building
# ---------------------------------------------------------------------------


class TestContainerSandboxCommand:
    def _make_sandbox(self, runtime: str = "docker") -> ContainerSandbox:
        with patch("shutil.which", return_value=f"/usr/bin/{runtime}"):
            return ContainerSandbox(runtime=runtime)

    def test_basic_command(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("python:3.13-slim", ["python", "-c", "print('hi')"])
        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "python:3.13-slim" in cmd
        assert cmd[-3:] == ["python", "-c", "print('hi')"]

    def test_security_defaults(self):
        """Verify all security flags are present by default."""
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"])
        assert "--cap-drop" in cmd
        idx = cmd.index("--cap-drop")
        assert cmd[idx + 1] == "ALL"
        assert "--security-opt" in cmd
        sec_idx = cmd.index("--security-opt")
        assert cmd[sec_idx + 1] == "no-new-privileges:true"
        assert "--network" in cmd
        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"
        assert "--read-only" in cmd

    def test_network_enabled(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], network=True)
        assert "--network" not in cmd

    def test_read_only_disabled(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], read_only=False)
        assert "--read-only" not in cmd

    def test_memory_limit(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], memory_limit="512m")
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "512m"

    def test_cpu_limit(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], cpu_limit=2.5)
        assert "--cpus=2.5" in cmd

    def test_env_vars(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], env={"FOO": "bar", "BAZ": "qux"})
        # Should include both env vars in sorted order
        env_pairs = []
        for i, part in enumerate(cmd):
            if part == "-e":
                env_pairs.append(cmd[i + 1])
        assert "BAZ=qux" in env_pairs
        assert "FOO=bar" in env_pairs

    def test_stdin_flag(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], input_data="hello")
        assert "-i" in cmd

    def test_no_stdin_flag_without_input(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], input_data=None)
        assert "-i" not in cmd

    def test_podman_runtime(self):
        sandbox = self._make_sandbox("podman")
        cmd = sandbox._build_command("img", ["cmd"])
        assert cmd[0] == "podman"


# ---------------------------------------------------------------------------
# ContainerSandbox -- async execution (mocked subprocess)
# ---------------------------------------------------------------------------


class TestContainerSandboxExecution:
    def _make_sandbox(self, runtime: str = "docker") -> ContainerSandbox:
        with patch("shutil.which", return_value=f"/usr/bin/{runtime}"):
            return ContainerSandbox(runtime=runtime)

    @pytest.mark.asyncio
    async def test_execute_success(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("python:3.13-slim", ["echo", "hi"])
            assert result.exit_code == 0
            assert result.stdout == "output"
            assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_execute_with_input(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"processed", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute(
                "python:3.13-slim",
                ["python", "-c", "import sys; print(sys.stdin.read())"],
                input_data="test input",
            )
            assert result.exit_code == 0
            assert result.stdout == "processed"
            # Verify input was encoded and passed
            mock_proc.communicate.assert_called_once_with(b"test input")

    @pytest.mark.asyncio
    async def test_execute_nonzero_exit(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("img", ["cmd"])
            assert result.exit_code == 1
            assert result.stderr == "error msg"

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(ContainerTimeoutError, match="timed out after 5s"),
        ):
            await sandbox.execute("img", ["cmd"], timeout=5)

    @pytest.mark.asyncio
    async def test_execute_runtime_not_found(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("docker"),
            ),
            pytest.raises(ContainerRuntimeError, match="not found"),
        ):
            await sandbox.execute("img", ["cmd"])


# ---------------------------------------------------------------------------
# MicroVMResult
# ---------------------------------------------------------------------------


class TestMicroVMResult:
    def test_to_dict(self):
        result = MicroVMResult(exit_code=0, stdout="ok", stderr="")
        d = result.to_dict()
        assert d == {"exit_code": 0, "stdout": "ok", "stderr": ""}

    def test_frozen(self):
        result = MicroVMResult(exit_code=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            result.exit_code = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MicroVMSandbox
# ---------------------------------------------------------------------------


class TestMicroVMSandboxDetection:
    def test_detect_podman_preferred(self):
        """Auto-detect prefers podman over docker."""
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            sandbox = MicroVMSandbox(container_runtime="auto")
            assert sandbox.runtime == "podman"

    def test_detect_docker_fallback(self):
        """Falls back to docker when podman is not available."""

        def _which(cmd):
            if cmd == "docker":
                return "/usr/bin/docker"
            if cmd in ("krun", "crun"):
                return "/usr/bin/crun"
            return None

        with patch("shutil.which", side_effect=_which):
            sandbox = MicroVMSandbox(container_runtime="auto")
            assert sandbox.runtime == "docker"

    def test_detect_none_raises(self):
        """Raises when no container runtime is available."""
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(MicroVMRuntimeError, match="No container runtime found"),
        ):
            MicroVMSandbox(container_runtime="auto")

    def test_explicit_podman(self):
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            sandbox = MicroVMSandbox(container_runtime="podman")
            assert sandbox.runtime == "podman"

    def test_explicit_docker(self):
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            sandbox = MicroVMSandbox(container_runtime="docker")
            assert sandbox.runtime == "docker"

    def test_explicit_missing_raises(self):
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(MicroVMRuntimeError, match="not found on PATH"),
        ):
            MicroVMSandbox(container_runtime="docker")


class TestMicroVMSandboxCommand:
    def _make_sandbox(self, runtime: str = "docker") -> MicroVMSandbox:
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            return MicroVMSandbox(container_runtime=runtime)

    def test_basic_command_uses_krun(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("python:3.13-slim", ["python", "-c", "print('hi')"])
        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "--runtime=krun" in cmd
        assert "python:3.13-slim" in cmd
        assert cmd[-3:] == ["python", "-c", "print('hi')"]

    def test_security_defaults(self):
        """Verify all security flags are present by default."""
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"])
        assert "--cap-drop" in cmd
        idx = cmd.index("--cap-drop")
        assert cmd[idx + 1] == "ALL"
        assert "--security-opt" in cmd
        sec_idx = cmd.index("--security-opt")
        assert cmd[sec_idx + 1] == "no-new-privileges:true"
        assert "--network" in cmd
        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"
        assert "--read-only" in cmd

    def test_default_memory_512m(self):
        """MicroVM default memory is 512m (higher than container tier)."""
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"])
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "512m"

    def test_custom_memory_limit(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], memory_limit="1g")
        idx = cmd.index("--memory")
        assert cmd[idx + 1] == "1g"

    def test_cpu_limit(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], cpu_limit=2.5)
        assert "--cpus=2.5" in cmd

    def test_env_vars(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], env={"FOO": "bar", "BAZ": "qux"})
        env_pairs = []
        for i, part in enumerate(cmd):
            if part == "-e":
                env_pairs.append(cmd[i + 1])
        assert "BAZ=qux" in env_pairs
        assert "FOO=bar" in env_pairs

    def test_stdin_flag(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], input_data="hello")
        assert "-i" in cmd

    def test_no_stdin_flag_without_input(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"], input_data=None)
        assert "-i" not in cmd

    def test_podman_runtime(self):
        sandbox = self._make_sandbox("podman")
        cmd = sandbox._build_command("img", ["cmd"])
        assert cmd[0] == "podman"
        assert "--runtime=krun" in cmd


class TestMicroVMSandboxExecution:
    def _make_sandbox(self, runtime: str = "docker") -> MicroVMSandbox:
        with patch("shutil.which", side_effect=lambda cmd: f"/usr/bin/{cmd}"):
            return MicroVMSandbox(container_runtime=runtime)

    @pytest.mark.asyncio
    async def test_execute_success(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("python:3.13-slim", ["echo", "hi"])
            assert result.exit_code == 0
            assert result.stdout == "output"
            assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_execute_with_input(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"processed", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute(
                "python:3.13-slim",
                ["python", "-c", "import sys; print(sys.stdin.read())"],
                input_data="test input",
            )
            assert result.exit_code == 0
            assert result.stdout == "processed"
            mock_proc.communicate.assert_called_once_with(b"test input")

    @pytest.mark.asyncio
    async def test_execute_nonzero_exit(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("img", ["cmd"])
            assert result.exit_code == 1
            assert result.stderr == "error msg"

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(MicroVMTimeoutError, match="timed out after 10s"),
        ):
            await sandbox.execute("img", ["cmd"], timeout=10)

    @pytest.mark.asyncio
    async def test_execute_default_timeout_60s(self):
        """MicroVM default timeout is 60s (higher than container tier)."""
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(MicroVMTimeoutError, match="timed out after 60s"),
        ):
            await sandbox.execute("img", ["cmd"])

    @pytest.mark.asyncio
    async def test_execute_runtime_not_found(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("docker"),
            ),
            pytest.raises(MicroVMRuntimeError, match="not found"),
        ):
            await sandbox.execute("img", ["cmd"])


class TestIsKrunAvailable:
    def test_krun_available(self):
        def _which(cmd):
            return "/usr/bin/krun" if cmd == "krun" else None

        with patch(
            "blackbeard.engine.sandbox.microvm_runtime.shutil.which",
            side_effect=_which,
        ):
            assert is_krun_available() is True

    def test_crun_available(self):
        def _which(cmd):
            return "/usr/bin/crun" if cmd == "crun" else None

        with patch(
            "blackbeard.engine.sandbox.microvm_runtime.shutil.which",
            side_effect=_which,
        ):
            assert is_krun_available() is True

    def test_neither_available(self):
        with patch(
            "blackbeard.engine.sandbox.microvm_runtime.shutil.which",
            return_value=None,
        ):
            assert is_krun_available() is False


# ---------------------------------------------------------------------------
# Schema validation for new sandbox tiers
# ---------------------------------------------------------------------------


class TestSandboxSchemaValidation:
    """Verify that spec schemas accept the new tier values."""

    def test_tool_schema_accepts_new_tiers(self):
        from blackbeard.resources.validator import validate_resource

        for tier in ("none", "wasm", "docker", "podman", "gvisor", "microvm"):
            spec = {"type": "builtin", "sandbox": tier}
            errors, _ = validate_resource("Tool", spec)
            assert errors == [], f"Expected no errors for sandbox={tier!r}, got {errors}"

    def test_tool_schema_rejects_invalid_tier(self):
        from blackbeard.resources.validator import validate_resource

        spec = {"type": "builtin", "sandbox": "invalid"}
        errors, _ = validate_resource("Tool", spec)
        assert len(errors) > 0

    def test_policy_schema_accepts_new_tiers(self):
        from blackbeard.resources.validator import validate_resource

        for tier in ("none", "wasm", "docker", "podman", "gvisor", "microvm"):
            spec = {"sandbox": {"minimum_tier": tier}}
            errors, _ = validate_resource("AgentPolicy", spec)
            assert errors == [], f"Expected no errors for minimum_tier={tier!r}, got {errors}"

    def test_policy_schema_rejects_invalid_tier(self):
        from blackbeard.resources.validator import validate_resource

        spec = {"sandbox": {"minimum_tier": "invalid"}}
        errors, _ = validate_resource("AgentPolicy", spec)
        assert len(errors) > 0
