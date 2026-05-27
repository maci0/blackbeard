"""Tests for gVisor (runsc) sandbox tier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.engine.sandbox.gvisor_runtime import (
    GVisorResult,
    GVisorRuntimeError,
    GVisorSandbox,
    GVisorTimeoutError,
    is_gvisor_available,
)
from blackbeard.engine.sandbox.selector import TIER_ORDER, select_sandbox, tier_rank

# ---------------------------------------------------------------------------
# is_gvisor_available
# ---------------------------------------------------------------------------


class TestIsGVisorAvailable:
    def test_returns_true_when_runsc_present(self):
        with patch("shutil.which", return_value="/usr/bin/runsc"):
            assert is_gvisor_available() is True

    def test_returns_false_when_runsc_absent(self):
        with patch("shutil.which", return_value=None):
            assert is_gvisor_available() is False


# ---------------------------------------------------------------------------
# GVisorResult
# ---------------------------------------------------------------------------


class TestGVisorResult:
    def test_to_dict(self):
        result = GVisorResult(exit_code=0, stdout="hello", stderr="")
        d = result.to_dict()
        assert d == {"exit_code": 0, "stdout": "hello", "stderr": ""}

    def test_frozen(self):
        result = GVisorResult(exit_code=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            result.exit_code = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GVisorSandbox -- runtime detection (mocked)
# ---------------------------------------------------------------------------


class TestGVisorSandboxDetection:
    def test_detect_podman_preferred(self):
        """Auto-detect prefers podman over docker."""

        def _which(cmd):
            if cmd == "runsc":
                return "/usr/bin/runsc"
            return f"/usr/bin/{cmd}"

        with patch("shutil.which", side_effect=_which):
            sandbox = GVisorSandbox(container_runtime="auto")
            assert sandbox.runtime == "podman"

    def test_detect_docker_fallback(self):
        """Falls back to docker when podman is not available."""

        def _which(cmd):
            if cmd == "runsc":
                return "/usr/bin/runsc"
            if cmd == "docker":
                return "/usr/bin/docker"
            return None

        with patch("shutil.which", side_effect=_which):
            sandbox = GVisorSandbox(container_runtime="auto")
            assert sandbox.runtime == "docker"

    def test_detect_none_raises(self):
        """Raises when no runtime is available."""

        def _which(cmd):
            if cmd == "runsc":
                return "/usr/bin/runsc"
            return None

        with (
            patch("shutil.which", side_effect=_which),
            pytest.raises(GVisorRuntimeError, match="No container runtime found"),
        ):
            GVisorSandbox(container_runtime="auto")

    def test_explicit_docker(self):
        def _which(cmd):
            return f"/usr/bin/{cmd}"

        with patch("shutil.which", side_effect=_which):
            sandbox = GVisorSandbox(container_runtime="docker")
            assert sandbox.runtime == "docker"

    def test_explicit_missing_raises(self):
        def _which(cmd):
            if cmd == "runsc":
                return "/usr/bin/runsc"
            return None

        with (
            patch("shutil.which", side_effect=_which),
            pytest.raises(GVisorRuntimeError, match="not found on PATH"),
        ):
            GVisorSandbox(container_runtime="docker")

    def test_warns_when_runsc_not_found(self):
        """Constructor logs a warning when runsc is not on PATH."""

        def _which(cmd):
            if cmd == "runsc":
                return None
            return f"/usr/bin/{cmd}"

        with (
            patch("shutil.which", side_effect=_which),
            patch("blackbeard.engine.sandbox.gvisor_runtime.logger") as mock_logger,
        ):
            sandbox = GVisorSandbox(container_runtime="docker")
            assert sandbox.runtime == "docker"

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "runsc" in call_args[0][0]


# ---------------------------------------------------------------------------
# GVisorSandbox -- command building
# ---------------------------------------------------------------------------


class TestGVisorSandboxCommand:
    def _make_sandbox(self, runtime: str = "docker") -> GVisorSandbox:
        def _which(cmd):
            return f"/usr/bin/{cmd}"

        with patch("shutil.which", side_effect=_which):
            return GVisorSandbox(container_runtime=runtime)

    def test_basic_command(self):
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("python:3.13-slim", ["python", "-c", "print('hi')"])
        assert cmd[0] == "docker"
        assert "run" in cmd
        assert "--rm" in cmd
        assert "--runtime=runsc" in cmd
        assert "python:3.13-slim" in cmd
        assert cmd[-3:] == ["python", "-c", "print('hi')"]

    def test_runtime_runsc_flag(self):
        """The --runtime=runsc flag is always present."""
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"])
        assert "--runtime=runsc" in cmd

    def test_security_defaults(self):
        """Verify all security flags are present by default."""
        sandbox = self._make_sandbox()
        cmd = sandbox._build_command("img", ["cmd"])

        # cap-drop ALL
        assert "--cap-drop" in cmd
        idx = cmd.index("--cap-drop")
        assert cmd[idx + 1] == "ALL"

        # no-new-privileges
        assert "--security-opt" in cmd
        sec_idx = cmd.index("--security-opt")
        assert cmd[sec_idx + 1] == "no-new-privileges:true"

        # network none
        assert "--network" in cmd
        net_idx = cmd.index("--network")
        assert cmd[net_idx + 1] == "none"

        # read-only
        assert "--read-only" in cmd

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
        assert "--runtime=runsc" in cmd


# ---------------------------------------------------------------------------
# GVisorSandbox -- async execution (mocked subprocess)
# ---------------------------------------------------------------------------


class TestGVisorSandboxExecution:
    def _make_sandbox(self, runtime: str = "docker") -> GVisorSandbox:
        def _which(cmd):
            return f"/usr/bin/{cmd}"

        with patch("shutil.which", side_effect=_which):
            return GVisorSandbox(container_runtime=runtime)

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

    async def test_execute_nonzero_exit(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("img", ["cmd"])
            assert result.exit_code == 1
            assert result.stderr == "error msg"

    async def test_execute_timeout(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(GVisorTimeoutError, match="timed out after 5s"),
        ):
            await sandbox.execute("img", ["cmd"], timeout=5)

    async def test_execute_runtime_not_found(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("docker"),
            ),
            pytest.raises(GVisorRuntimeError, match="not found"),
        ):
            await sandbox.execute("img", ["cmd"])

    async def test_execute_os_error(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("Permission denied"),
            ),
            pytest.raises(GVisorRuntimeError, match="Failed to start"),
        ):
            await sandbox.execute("img", ["cmd"])


# ---------------------------------------------------------------------------
# Sandbox selector -- gvisor tier ordering
# ---------------------------------------------------------------------------


class TestGVisorTierOrdering:
    def test_gvisor_between_docker_and_microvm(self):
        """gVisor sits between docker/podman and microvm in isolation strength."""
        assert tier_rank("docker") < tier_rank("gvisor")
        assert tier_rank("podman") < tier_rank("gvisor")
        assert tier_rank("gvisor") < tier_rank("microvm")

    def test_gvisor_above_wasm(self):
        assert tier_rank("wasm") < tier_rank("gvisor")

    def test_gvisor_in_tier_order_list(self):
        assert "gvisor" in TIER_ORDER

    def test_tier_order_contains_all_tiers(self):
        assert TIER_ORDER == ["none", "wasm", "docker", "podman", "gvisor", "microvm"]

    def test_select_gvisor_tier(self):
        assert select_sandbox(tool_tier="gvisor") == "gvisor"

    def test_policy_promotes_to_gvisor(self):
        result = select_sandbox(tool_tier="docker", policy_minimum="gvisor")
        assert result == "gvisor"

    def test_policy_promotes_wasm_to_gvisor(self):
        result = select_sandbox(tool_tier="wasm", policy_minimum="gvisor")
        assert result == "gvisor"

    def test_gvisor_not_demoted_by_docker_policy(self):
        result = select_sandbox(tool_tier="gvisor", policy_minimum="docker")
        assert result == "gvisor"

    def test_microvm_policy_overrides_gvisor(self):
        result = select_sandbox(tool_tier="gvisor", policy_minimum="microvm")
        assert result == "microvm"


# ---------------------------------------------------------------------------
# Schema validation for gvisor tier
# ---------------------------------------------------------------------------


class TestGVisorSchemaValidation:
    """Verify that spec schemas accept the gvisor tier value."""

    def test_tool_schema_accepts_gvisor(self):
        from blackbeard.resources.validator import validate_resource

        spec = {"type": "builtin", "sandbox": "gvisor"}
        errors, _ = validate_resource("Tool", spec)
        assert errors == [], f"Expected no errors for sandbox='gvisor', got {errors}"

    def test_policy_schema_accepts_gvisor(self):
        from blackbeard.resources.validator import validate_resource

        spec = {"sandbox": {"minimum_tier": "gvisor"}}
        errors, _ = validate_resource("AgentPolicy", spec)
        assert errors == [], f"Expected no errors for minimum_tier='gvisor', got {errors}"
