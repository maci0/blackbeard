"""Tests for Firecracker MicroVM sandbox."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blackbeard.engine.sandbox.firecracker import (
    FirecrackerConfigError,
    FirecrackerError,
    FirecrackerResult,
    FirecrackerRuntimeError,
    FirecrackerSandbox,
    FirecrackerTimeoutError,
    is_firecracker_available,
)
from blackbeard.engine.sandbox.selector import select_microvm_backend

# ---------------------------------------------------------------------------
# FirecrackerResult
# ---------------------------------------------------------------------------


class TestFirecrackerResult:
    def test_to_dict(self):
        result = FirecrackerResult(exit_code=0, stdout="hello", stderr="")
        d = result.to_dict()
        assert d == {"exit_code": 0, "stdout": "hello", "stderr": ""}

    def test_frozen(self):
        result = FirecrackerResult(exit_code=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            result.exit_code = 1  # type: ignore[misc]

    def test_nonzero_exit_code(self):
        result = FirecrackerResult(exit_code=137, stdout="", stderr="killed")
        assert result.exit_code == 137
        assert result.stderr == "killed"

    def test_exception_hierarchy(self):
        """All Firecracker exceptions inherit from FirecrackerError."""
        assert issubclass(FirecrackerConfigError, FirecrackerError)
        assert issubclass(FirecrackerTimeoutError, FirecrackerError)
        assert issubclass(FirecrackerRuntimeError, FirecrackerError)


# ---------------------------------------------------------------------------
# FirecrackerSandbox -- initialization
# ---------------------------------------------------------------------------


class TestFirecrackerSandboxInit:
    def test_init_with_explicit_paths(self):
        sandbox = FirecrackerSandbox(
            bin_path="/usr/local/bin/firecracker",
            kernel_path="/opt/vmlinux.bin",
            rootfs_path="/opt/rootfs.ext4",
            vcpus=2,
            memory_mb=256,
        )
        assert sandbox.bin_path == "/usr/local/bin/firecracker"
        assert sandbox.kernel_path == "/opt/vmlinux.bin"
        assert sandbox.rootfs_path == "/opt/rootfs.ext4"
        assert sandbox.is_configured is True

    def test_init_from_settings(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_bin", "/custom/firecracker"),
            patch.object(settings, "firecracker_kernel", "/custom/vmlinux.bin"),
            patch.object(settings, "firecracker_rootfs", "/custom/rootfs.ext4"),
        ):
            sandbox = FirecrackerSandbox()
            assert sandbox.bin_path == "/custom/firecracker"
            assert sandbox.kernel_path == "/custom/vmlinux.bin"
            assert sandbox.rootfs_path == "/custom/rootfs.ext4"
            assert sandbox.is_configured is True

    def test_init_defaults_when_unconfigured(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_bin", "firecracker"),
            patch.object(settings, "firecracker_kernel", ""),
            patch.object(settings, "firecracker_rootfs", ""),
        ):
            sandbox = FirecrackerSandbox()
            assert sandbox.bin_path == "firecracker"
            assert sandbox.kernel_path == ""
            assert sandbox.rootfs_path == ""
            assert sandbox.is_configured is False

    def test_explicit_paths_override_settings(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_bin", "/settings/firecracker"),
            patch.object(settings, "firecracker_kernel", "/settings/vmlinux.bin"),
            patch.object(settings, "firecracker_rootfs", "/settings/rootfs.ext4"),
        ):
            sandbox = FirecrackerSandbox(
                bin_path="/explicit/firecracker",
                kernel_path="/explicit/vmlinux.bin",
                rootfs_path="/explicit/rootfs.ext4",
            )
            assert sandbox.bin_path == "/explicit/firecracker"
            assert sandbox.kernel_path == "/explicit/vmlinux.bin"
            assert sandbox.rootfs_path == "/explicit/rootfs.ext4"


# ---------------------------------------------------------------------------
# FirecrackerSandbox -- config building
# ---------------------------------------------------------------------------


class TestFirecrackerSandboxConfig:
    def _make_sandbox(self, **kwargs) -> FirecrackerSandbox:
        defaults = {
            "bin_path": "/usr/local/bin/firecracker",
            "kernel_path": "/opt/vmlinux.bin",
            "rootfs_path": "/opt/rootfs.ext4",
            "vcpus": 1,
            "memory_mb": 128,
        }
        defaults.update(kwargs)
        return FirecrackerSandbox(**defaults)

    def test_basic_config_structure(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo hello")

        assert "boot-source" in config
        assert "drives" in config
        assert "machine-config" in config
        assert "network-interfaces" in config

    def test_kernel_path_in_config(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo hello")
        assert config["boot-source"]["kernel_image_path"] == "/opt/vmlinux.bin"

    def test_rootfs_in_drives(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo hello")
        drives = config["drives"]
        assert len(drives) == 1
        assert drives[0]["drive_id"] == "rootfs"
        assert drives[0]["path_on_host"] == "/opt/rootfs.ext4"
        assert drives[0]["is_root_device"] is True
        assert drives[0]["is_read_only"] is True

    def test_machine_config_defaults(self):
        sandbox = self._make_sandbox(vcpus=1, memory_mb=128)
        config = sandbox.build_config("echo hello")
        assert config["machine-config"]["vcpu_count"] == 1
        assert config["machine-config"]["mem_size_mib"] == 128

    def test_machine_config_overrides(self):
        sandbox = self._make_sandbox(vcpus=1, memory_mb=128)
        config = sandbox.build_config("echo hello", vcpus=4, memory_mb=512)
        assert config["machine-config"]["vcpu_count"] == 4
        assert config["machine-config"]["mem_size_mib"] == 512

    def test_no_network_by_default(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo hello")
        assert config["network-interfaces"] == []

    def test_command_in_boot_args(self):
        sandbox = self._make_sandbox()
        command = "python3 -c 'print(42)'"
        config = sandbox.build_config(command)
        boot_args = config["boot-source"]["boot_args"]
        expected_b64 = base64.b64encode(command.encode()).decode("ascii")
        assert f"BB_CMD_B64={expected_b64}" in boot_args

    def test_boot_args_contain_required_params(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo test")
        boot_args = config["boot-source"]["boot_args"]
        assert "console=ttyS0" in boot_args
        assert "reboot=k" in boot_args
        assert "panic=1" in boot_args
        assert "pci=off" in boot_args
        assert "quiet" in boot_args

    def test_env_vars_in_boot_args(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config(
            "echo test",
            env={"FOO": "bar", "BAZ": "qux"},
        )
        boot_args = config["boot-source"]["boot_args"]
        baz_b64 = base64.b64encode(b"qux").decode("ascii")
        foo_b64 = base64.b64encode(b"bar").decode("ascii")
        assert f"BB_ENV_B64_BAZ={baz_b64}" in boot_args
        assert f"BB_ENV_B64_FOO={foo_b64}" in boot_args

    def test_env_vars_sorted(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config(
            "echo test",
            env={"ZEBRA": "z", "ALPHA": "a"},
        )
        boot_args = config["boot-source"]["boot_args"]
        alpha_b64 = base64.b64encode(b"a").decode("ascii")
        zebra_b64 = base64.b64encode(b"z").decode("ascii")
        alpha_pos = boot_args.index(f"BB_ENV_B64_ALPHA={alpha_b64}")
        zebra_pos = boot_args.index(f"BB_ENV_B64_ZEBRA={zebra_b64}")
        assert alpha_pos < zebra_pos

    def test_config_is_valid_json_serializable(self):
        sandbox = self._make_sandbox()
        config = sandbox.build_config("echo hello", env={"KEY": "val"})
        # Should not raise
        serialized = json.dumps(config)
        roundtripped = json.loads(serialized)
        assert roundtripped == config


# ---------------------------------------------------------------------------
# FirecrackerSandbox -- validation
# ---------------------------------------------------------------------------


class TestFirecrackerSandboxValidation:
    def test_config_error_when_kernel_missing(self):
        sandbox = FirecrackerSandbox(
            kernel_path="",
            rootfs_path="/opt/rootfs.ext4",
        )
        with pytest.raises(FirecrackerConfigError, match="FIRECRACKER_KERNEL"):
            sandbox._validate_config()

    def test_config_error_when_rootfs_missing(self):
        sandbox = FirecrackerSandbox(
            kernel_path="/opt/vmlinux.bin",
            rootfs_path="",
        )
        with pytest.raises(FirecrackerConfigError, match="FIRECRACKER_ROOTFS"):
            sandbox._validate_config()

    def test_config_error_when_both_missing(self):
        sandbox = FirecrackerSandbox(kernel_path="", rootfs_path="")
        with pytest.raises(FirecrackerConfigError) as exc_info:
            sandbox._validate_config()
        msg = str(exc_info.value)
        assert "FIRECRACKER_KERNEL" in msg
        assert "FIRECRACKER_ROOTFS" in msg

    def test_no_error_when_configured(self):
        sandbox = FirecrackerSandbox(
            kernel_path="/opt/vmlinux.bin",
            rootfs_path="/opt/rootfs.ext4",
        )
        # Should not raise
        sandbox._validate_config()


# ---------------------------------------------------------------------------
# FirecrackerSandbox -- async execution (mocked subprocess)
# ---------------------------------------------------------------------------


class TestFirecrackerSandboxExecution:
    def _make_sandbox(self) -> FirecrackerSandbox:
        return FirecrackerSandbox(
            bin_path="/usr/local/bin/firecracker",
            kernel_path="/opt/vmlinux.bin",
            rootfs_path="/opt/rootfs.ext4",
        )

    @pytest.mark.asyncio
    async def test_execute_success(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("echo hello")
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
            result = await sandbox.execute("cat", input_data="test input")
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
            result = await sandbox.execute("false")
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
            pytest.raises(FirecrackerTimeoutError, match="timed out after 10s"),
        ):
            await sandbox.execute("sleep 999", timeout=10)

    @pytest.mark.asyncio
    async def test_execute_default_timeout_60s(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=TimeoutError),
            pytest.raises(FirecrackerTimeoutError, match="timed out after 60s"),
        ):
            await sandbox.execute("sleep 999")

    @pytest.mark.asyncio
    async def test_execute_binary_not_found(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("firecracker"),
            ),
            pytest.raises(FirecrackerRuntimeError, match="not found"),
        ):
            await sandbox.execute("echo hello")

    @pytest.mark.asyncio
    async def test_execute_os_error(self):
        sandbox = self._make_sandbox()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=OSError("permission denied"),
            ),
            pytest.raises(FirecrackerRuntimeError, match="Failed to start"),
        ):
            await sandbox.execute("echo hello")

    @pytest.mark.asyncio
    async def test_execute_config_error_when_unconfigured(self):
        sandbox = FirecrackerSandbox(kernel_path="", rootfs_path="")
        with pytest.raises(FirecrackerConfigError):
            await sandbox.execute("echo hello")

    @pytest.mark.asyncio
    async def test_execute_passes_correct_args_to_subprocess(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await sandbox.execute("echo hello")

            call_args = mock_exec.call_args
            # First positional arg is the binary
            assert call_args[0][0] == "/usr/local/bin/firecracker"
            # Should contain --api-sock, --config-file, --no-api
            args_list = list(call_args[0])
            assert "--api-sock" in args_list
            assert "--config-file" in args_list
            assert "--no-api" in args_list

    @pytest.mark.asyncio
    async def test_execute_with_vcpu_and_memory_overrides(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute(
                "echo hello",
                vcpus=4,
                memory_mb=1024,
            )
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_with_env_vars(self):
        sandbox = self._make_sandbox()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute(
                "echo hello",
                env={"MY_VAR": "my_value"},
            )
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_cleans_up_temp_files(self):
        """Temp config and socket dir are removed after execution."""
        sandbox = self._make_sandbox()

        created_files = []
        created_dirs = []

        original_mkstemp = __import__("tempfile").mkstemp
        original_mkdtemp = __import__("tempfile").mkdtemp

        def track_mkstemp(*args, **kwargs):
            fd, path = original_mkstemp(*args, **kwargs)
            created_files.append(path)
            return fd, path

        def track_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            created_dirs.append(path)
            return path

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch(
                "blackbeard.engine.sandbox.firecracker.tempfile.mkstemp",
                side_effect=track_mkstemp,
            ),
            patch(
                "blackbeard.engine.sandbox.firecracker.tempfile.mkdtemp",
                side_effect=track_mkdtemp,
            ),
        ):
            await sandbox.execute("echo hello")

        # All temp files should be cleaned up
        for f in created_files:
            assert not Path(f).exists(), f"Temp file not cleaned up: {f}"
        # All temp dirs should be cleaned up
        for d in created_dirs:
            assert not Path(d).exists(), f"Temp dir not cleaned up: {d}"


# ---------------------------------------------------------------------------
# is_firecracker_available
# ---------------------------------------------------------------------------


class TestIsFirecrackerAvailable:
    def test_available_when_binary_and_kvm_exist(self):
        with (
            patch(
                "blackbeard.engine.sandbox.firecracker.shutil.which",
                return_value="/usr/local/bin/firecracker",
            ),
            patch(
                "blackbeard.engine.sandbox.firecracker.Path.exists",
                return_value=True,
            ),
        ):
            assert is_firecracker_available() is True

    def test_not_available_without_binary(self):
        with (
            patch(
                "blackbeard.engine.sandbox.firecracker.shutil.which",
                return_value=None,
            ),
            patch(
                "blackbeard.engine.sandbox.firecracker.Path.exists",
                return_value=True,
            ),
        ):
            assert is_firecracker_available() is False

    def test_not_available_without_kvm(self):
        with (
            patch(
                "blackbeard.engine.sandbox.firecracker.shutil.which",
                return_value="/usr/local/bin/firecracker",
            ),
            patch(
                "blackbeard.engine.sandbox.firecracker.Path.exists",
                return_value=False,
            ),
        ):
            assert is_firecracker_available() is False

    def test_not_available_without_both(self):
        with (
            patch(
                "blackbeard.engine.sandbox.firecracker.shutil.which",
                return_value=None,
            ),
            patch(
                "blackbeard.engine.sandbox.firecracker.Path.exists",
                return_value=False,
            ),
        ):
            assert is_firecracker_available() is False

    def test_uses_firecracker_bin_setting(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_bin", "/custom/fc"),
            patch(
                "blackbeard.engine.sandbox.firecracker.shutil.which",
                return_value="/custom/fc",
            ) as mock_which,
            patch(
                "blackbeard.engine.sandbox.firecracker.Path.exists",
                return_value=True,
            ),
        ):
            assert is_firecracker_available() is True
            mock_which.assert_called_once_with("/custom/fc")


# ---------------------------------------------------------------------------
# select_microvm_backend
# ---------------------------------------------------------------------------


class TestSelectMicrovmBackend:
    def test_selects_firecracker_when_configured(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_kernel", "/opt/vmlinux.bin"),
            patch(
                "blackbeard.engine.sandbox.firecracker.is_firecracker_available",
                return_value=True,
            ),
        ):
            assert select_microvm_backend() == "firecracker"

    def test_falls_back_to_krun_when_firecracker_unavailable(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_kernel", "/opt/vmlinux.bin"),
            patch(
                "blackbeard.engine.sandbox.firecracker.is_firecracker_available",
                return_value=False,
            ),
            patch(
                "blackbeard.engine.sandbox.microvm_runtime.is_krun_available",
                return_value=True,
            ),
        ):
            assert select_microvm_backend() == "krun"

    def test_selects_krun_when_firecracker_not_configured(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_kernel", ""),
            patch(
                "blackbeard.engine.sandbox.microvm_runtime.is_krun_available",
                return_value=True,
            ),
        ):
            result = select_microvm_backend()
            assert result == "krun"

    def test_returns_none_when_nothing_available(self):
        from blackbeard.config import settings

        with (
            patch.object(settings, "firecracker_kernel", ""),
            patch(
                "blackbeard.engine.sandbox.microvm_runtime.is_krun_available",
                return_value=False,
            ),
        ):
            assert select_microvm_backend() == "none"


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


class TestFirecrackerExports:
    """Verify Firecracker types are exported from the sandbox package."""

    def test_imports_from_package(self):
        from blackbeard.engine.sandbox import (
            FirecrackerConfigError,
            FirecrackerError,
            FirecrackerResult,
            FirecrackerRuntimeError,
            FirecrackerSandbox,
            FirecrackerTimeoutError,
            is_firecracker_available,
            select_microvm_backend,
        )

        # Just verify they imported successfully
        assert FirecrackerSandbox is not None
        assert FirecrackerResult is not None
        assert FirecrackerError is not None
        assert FirecrackerConfigError is not None
        assert FirecrackerTimeoutError is not None
        assert FirecrackerRuntimeError is not None
        assert is_firecracker_available is not None
        assert select_microvm_backend is not None
