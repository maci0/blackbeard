"""Firecracker MicroVM sandbox for maximum isolation.

Each tool execution gets a dedicated Firecracker VM with its own kernel,
providing stronger isolation than libkrun (which wraps OCI containers).
Firecracker is a standalone VMM that creates lightweight VMs directly,
without depending on Docker/Podman container runtimes.

Requires:
- ``firecracker`` binary on PATH or via ``FIRECRACKER_BIN``
- Linux kernel image (``vmlinux.bin``) via ``FIRECRACKER_KERNEL``
- Root filesystem image (``rootfs.ext4``) via ``FIRECRACKER_ROOTFS``
- KVM access (``/dev/kvm``) on the host

Setup: see ``docs/firecracker-setup.md``
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum stdout/stderr capture size (10 MB)
_MAX_OUTPUT_BYTES = 10 * 1024 * 1024


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FirecrackerError(Exception):
    """Base exception for Firecracker sandbox errors."""


class FirecrackerConfigError(FirecrackerError):
    """Raised when Firecracker is not properly configured."""


class FirecrackerTimeoutError(FirecrackerError):
    """Raised when a Firecracker VM exceeds the execution timeout."""


class FirecrackerRuntimeError(FirecrackerError):
    """Raised when the Firecracker binary fails to start or crashes."""


@dataclass(frozen=True, slots=True)
class FirecrackerResult:
    """Result of a Firecracker VM execution."""

    exit_code: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class FirecrackerSandbox:
    """Runs tools in Firecracker MicroVMs.

    Each execution creates a dedicated VM with its own kernel and
    root filesystem.  The VM is destroyed after execution completes.

    Security defaults (defense in depth):
    - Dedicated kernel per VM (full kernel-level isolation)
    - Read-only root filesystem (``is_read_only: true``)
    - No network interfaces by default
    - Enforced vCPU and memory limits
    - VM is destroyed after each execution (no state leakage)
    - No access to host filesystem beyond the rootfs image

    Requires: ``firecracker`` binary, kernel image, rootfs image,
    ``/dev/kvm`` access.
    """

    def __init__(
        self,
        bin_path: str | None = None,
        kernel_path: str | None = None,
        rootfs_path: str | None = None,
        vcpus: int = 1,
        memory_mb: int = 128,
    ) -> None:
        """Initialize the Firecracker sandbox.

        Args:
            bin_path: Path to the ``firecracker`` binary.
                Falls back to ``FIRECRACKER_BIN`` env var, then ``firecracker``
                on PATH.
            kernel_path: Path to the Linux kernel image (``vmlinux.bin``).
                Falls back to ``FIRECRACKER_KERNEL`` env var.
            rootfs_path: Path to the root filesystem image (``rootfs.ext4``).
                Falls back to ``FIRECRACKER_ROOTFS`` env var.
            vcpus: Number of virtual CPUs per VM (default 1).
            memory_mb: Memory allocation per VM in MiB (default 128).
        """
        from blackbeard.config import settings

        self._bin = bin_path or settings.firecracker_bin
        self._kernel = kernel_path or settings.firecracker_kernel
        self._rootfs = rootfs_path or settings.firecracker_rootfs
        self._vcpus = vcpus
        self._memory_mb = memory_mb

        if not self._kernel or not self._rootfs:
            logger.warning(
                "Firecracker kernel/rootfs not configured. "
                "Set FIRECRACKER_KERNEL and FIRECRACKER_ROOTFS env vars.",
                extra={
                    "event": "firecracker_not_configured",
                    "kernel_set": bool(self._kernel),
                    "rootfs_set": bool(self._rootfs),
                },
            )

    @property
    def bin_path(self) -> str:
        """The resolved Firecracker binary path."""
        return self._bin

    @property
    def kernel_path(self) -> str:
        """The configured kernel image path."""
        return self._kernel

    @property
    def rootfs_path(self) -> str:
        """The configured rootfs image path."""
        return self._rootfs

    @property
    def is_configured(self) -> bool:
        """Whether kernel and rootfs paths are set."""
        return bool(self._kernel) and bool(self._rootfs)

    def _validate_config(self) -> None:
        """Validate that kernel and rootfs paths are configured.

        Raises:
            FirecrackerConfigError: If kernel or rootfs path is missing.
        """
        missing: list[str] = []
        if not self._kernel:
            missing.append("FIRECRACKER_KERNEL")
        if not self._rootfs:
            missing.append("FIRECRACKER_ROOTFS")
        if missing:
            raise FirecrackerConfigError(
                f"Firecracker requires {', '.join(missing)} to be set. "
                "See docs/firecracker-setup.md for configuration instructions."
            )

    def build_config(
        self,
        command: str,
        *,
        vcpus: int | None = None,
        memory_mb: int | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build Firecracker VM configuration JSON.

        This method is intentionally public for testability: tests can
        verify the configuration structure without spawning a real VM.

        The ``command`` is injected into the kernel boot args so that
        init inside the rootfs can execute it.  The rootfs must contain
        an init process that reads the ``BB_CMD`` parameter from
        ``/proc/cmdline`` and runs it.

        Args:
            command: Shell command to execute inside the VM.
            vcpus: Override default vCPU count for this execution.
            memory_mb: Override default memory (MiB) for this execution.
            env: Environment variables to pass (encoded in boot args).

        Returns:
            A dict representing the Firecracker JSON config file.
        """
        effective_vcpus = vcpus if vcpus is not None else self._vcpus
        effective_memory = memory_mb if memory_mb is not None else self._memory_mb

        # Build boot args: quiet console + command passed via base64
        # encoding.  The rootfs init script reads BB_CMD_B64 from
        # /proc/cmdline and base64-decodes it before executing.
        #
        # SECURITY: Kernel boot args are space-delimited key=value pairs.
        # Passing the raw command directly allows an attacker to inject
        # additional boot parameters (e.g. ``init=/bin/sh``) via spaces
        # or other special characters in the command string.  Base64
        # encoding eliminates spaces, quotes, and shell metacharacters
        # from the boot args payload entirely.
        cmd_b64 = base64.b64encode(command.encode()).decode("ascii")
        boot_args_parts = [
            "console=ttyS0",
            "reboot=k",
            "panic=1",
            "pci=off",
            "quiet",
            f"BB_CMD_B64={cmd_b64}",
        ]

        # Inject env vars as base64-encoded BB_ENV_B64_<key>=<b64value>
        # boot args.  Key names are validated to contain only
        # alphanumerics and underscores to prevent parameter injection.
        if env:
            for k, v in sorted(env.items()):
                if not _ENV_KEY_RE.fullmatch(k):
                    logger.warning(
                        "Firecracker: skipping env var with invalid key: %s",
                        k[:50],
                        extra={
                            "event": "firecracker_invalid_env_key",
                            "key": k[:50],
                        },
                    )
                    continue
                v_b64 = base64.b64encode(v.encode()).decode("ascii")
                boot_args_parts.append(f"BB_ENV_B64_{k}={v_b64}")

        config: dict[str, Any] = {
            "boot-source": {
                "kernel_image_path": self._kernel,
                "boot_args": " ".join(boot_args_parts),
            },
            "drives": [
                {
                    "drive_id": "rootfs",
                    "path_on_host": self._rootfs,
                    "is_root_device": True,
                    "is_read_only": True,
                },
            ],
            "machine-config": {
                "vcpu_count": effective_vcpus,
                "mem_size_mib": effective_memory,
            },
            "network-interfaces": [],
        }
        return config

    async def execute(
        self,
        command: str,
        *,
        input_data: str | None = None,
        timeout: int = 60,
        vcpus: int | None = None,
        memory_mb: int | None = None,
        env: dict[str, str] | None = None,
    ) -> FirecrackerResult:
        """Run a command in a Firecracker MicroVM.

        Creates a temporary VM config, starts a Firecracker process,
        waits for completion, and destroys the VM.  Each invocation
        is fully isolated.

        Args:
            command: Shell command to execute inside the VM.
            input_data: Optional string to pass via stdin to the
                Firecracker process (forwarded to the VM's serial console).
            timeout: Maximum wall-clock time in seconds (default 60).
            vcpus: Override default vCPU count for this execution.
            memory_mb: Override default memory (MiB) for this execution.
            env: Environment variables to set inside the VM.

        Returns:
            FirecrackerResult with exit code, stdout, and stderr.

        Raises:
            FirecrackerConfigError: If kernel/rootfs paths are not configured.
            FirecrackerTimeoutError: If the VM exceeds the timeout.
            FirecrackerRuntimeError: If the Firecracker binary fails to start.
        """
        self._validate_config()

        config = self.build_config(
            command,
            vcpus=vcpus,
            memory_mb=memory_mb,
            env=env,
        )

        # Write VM config to a temp file.
        # SECURITY: Use mkstemp for config (atomically created) and
        # TemporaryDirectory for the socket (avoids mktemp TOCTOU race
        # where an attacker could predict or pre-create the path).
        config_fd, config_path = tempfile.mkstemp(suffix=".json", prefix="fc-")
        socket_dir = tempfile.mkdtemp(prefix="fc-sock-")
        socket_path = os.path.join(socket_dir, "api.sock")

        try:
            with os.fdopen(config_fd, "w") as config_file:
                json.dump(config, config_file)

            t0 = asyncio.get_event_loop().time()
            logger.info(
                "Firecracker execute: bin=%s kernel=%s timeout=%ds vcpus=%d mem=%dMiB",
                self._bin,
                self._kernel,
                timeout,
                config["machine-config"]["vcpu_count"],
                config["machine-config"]["mem_size_mib"],
                extra={
                    "event": "firecracker_execute",
                    "bin": self._bin,
                    "kernel": self._kernel,
                    "rootfs": self._rootfs,
                    "timeout": timeout,
                    "vcpus": config["machine-config"]["vcpu_count"],
                    "memory_mib": config["machine-config"]["mem_size_mib"],
                },
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    self._bin,
                    "--api-sock",
                    socket_path,
                    "--config-file",
                    config_path,
                    "--no-api",
                    stdin=asyncio.subprocess.PIPE if input_data is not None else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise FirecrackerRuntimeError(
                    f"Firecracker binary '{self._bin}' not found: {exc}"
                ) from exc
            except OSError as exc:
                raise FirecrackerRuntimeError(f"Failed to start Firecracker VM: {exc}") from exc

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input_data.encode() if input_data is not None else None),
                    timeout=timeout,
                )
            except TimeoutError as exc:
                proc.kill()
                await proc.wait()
                raise FirecrackerTimeoutError(f"Firecracker VM timed out after {timeout}s") from exc

            # Truncate oversized output to prevent memory issues
            stdout_str = stdout_bytes[:_MAX_OUTPUT_BYTES].decode(errors="replace")
            stderr_str = stderr_bytes[:_MAX_OUTPUT_BYTES].decode(errors="replace")

            result = FirecrackerResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_str,
                stderr=stderr_str,
            )

            duration_ms = round((asyncio.get_event_loop().time() - t0) * 1000, 1)
            logger.info(
                "Firecracker completed: exit=%d stdout=%d stderr=%d duration_ms=%.0f",
                result.exit_code,
                len(result.stdout),
                len(result.stderr),
                duration_ms,
                extra={
                    "event": "firecracker_completed",
                    "exit_code": result.exit_code,
                    "stdout_bytes": len(result.stdout),
                    "stderr_bytes": len(result.stderr),
                    "duration_ms": duration_ms,
                },
            )

            return result

        finally:
            # Clean up temp files: never leave config or socket on disk
            Path(config_path).unlink(missing_ok=True)
            shutil.rmtree(socket_dir, ignore_errors=True)


def is_firecracker_available() -> bool:
    """Check if Firecracker is installed and /dev/kvm exists.

    Both conditions must be met:
    - ``firecracker`` binary is on PATH (or at FIRECRACKER_BIN)
    - ``/dev/kvm`` exists (required for KVM acceleration)

    Returns:
        True if Firecracker can be used on this system.
    """
    from blackbeard.config import settings

    has_binary = shutil.which(settings.firecracker_bin) is not None
    has_kvm = Path("/dev/kvm").exists()
    return has_binary and has_kvm
