"""MicroVM sandbox using libkrun for lightweight KVM-based isolation.

libkrun provides lightweight KVM-based VMs without requiring a separate
hypervisor daemon.  Each container gets its own Linux kernel, providing
stronger isolation than standard container runtimes or gVisor.

libkrun integrates as an OCI runtime via ``crun`` with the ``krun`` handler.
Usage: ``podman run --runtime=krun ...`` or ``docker run --runtime=krun ...``

Install: ``apt install crun-krun`` (Ubuntu) or ``dnf install crun-krun``
(Fedora), or build from source.

Requires: KVM access (``/dev/kvm``) on the host.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class MicroVMError(Exception):
    """Raised when the MicroVM sandbox encounters an error."""


class MicroVMTimeoutError(MicroVMError):
    """Raised when a MicroVM execution exceeds the timeout."""


class MicroVMRuntimeError(MicroVMError):
    """Raised when the container runtime or krun fails to start."""


@dataclass(frozen=True, slots=True)
class MicroVMResult:
    """Result of a MicroVM execution."""

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


class MicroVMSandbox:
    """Runs tools in libkrun MicroVMs via the krun OCI runtime.

    libkrun provides lightweight KVM-based VMs without requiring
    a separate hypervisor daemon. Each container gets its own kernel.

    Security defaults (defense in depth):
    - ``--runtime=krun``: each container runs in its own KVM-based VM
    - ``--network none``: no network access
    - ``--read-only``: read-only root filesystem
    - ``--security-opt no-new-privileges:true``: prevent privilege escalation
    - ``--cap-drop ALL``: drop all Linux capabilities
    - ``--rm``: auto-remove container after exit
    - Memory and CPU limits enforced

    Requires: crun with krun support (libkrun), KVM access (/dev/kvm)
    Install: ``apt install crun-krun`` (Ubuntu) or ``dnf install crun-krun``
    (Fedora) or build from source.
    """

    def __init__(self, container_runtime: str = "auto") -> None:
        """Initialize the MicroVM sandbox.

        Args:
            container_runtime: ``"docker"``, ``"podman"``, or ``"auto"``
                (detect available).  When ``"auto"``, prefers Podman for
                rootless container support.
        """
        self._runtime = self._detect_runtime(container_runtime)
        self._verify_krun()

    @property
    def runtime(self) -> str:
        """The resolved container runtime binary name."""
        return self._runtime

    @staticmethod
    def _detect_runtime(preference: str) -> str:
        """Detect available container runtime.

        When preference is ``"auto"``, checks for Podman first (preferred
        for rootless operation), then Docker.

        Raises:
            MicroVMRuntimeError: If no container runtime is found.
        """
        if preference != "auto":
            if shutil.which(preference) is None:
                raise MicroVMRuntimeError(
                    f"Container runtime '{preference}' not found on PATH"
                )
            return preference
        if shutil.which("podman"):
            return "podman"
        if shutil.which("docker"):
            return "docker"
        raise MicroVMRuntimeError(
            "No container runtime found for MicroVM (install docker or podman)"
        )

    @staticmethod
    def _verify_krun() -> None:
        """Check that krun runtime is available on PATH.

        Logs a warning if neither ``krun`` nor ``crun`` is found.
        This is a soft check -- the sandbox will fail at execution time
        if krun is not properly configured in the container runtime.
        """
        if not shutil.which("krun") and not shutil.which("crun"):
            logger.warning(
                "krun/crun not found -- microvm sandbox tier will fail at "
                "execution time. "
                "Install: apt install crun-krun or dnf install crun-krun",
                extra={"event": "microvm_krun_not_found"},
            )

    def _build_command(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        memory_limit: str = "512m",
        cpu_limit: float = 1.0,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build the MicroVM container run command.

        This method is intentionally separated from ``execute`` for
        testability -- tests can verify the command line without
        spawning a real process.
        """
        cmd: list[str] = [
            self._runtime,
            "run",
            "--rm",
            "--runtime=krun",
            "--memory",
            memory_limit,
            f"--cpus={cpu_limit}",
            "--read-only",
            "--network",
            "none",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
        ]

        if env:
            for k, v in sorted(env.items()):
                cmd.extend(["-e", f"{k}={v}"])

        if input_data is not None:
            cmd.append("-i")

        cmd.append(image)
        cmd.extend(command)

        return cmd

    async def execute(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        timeout: int = 60,
        memory_limit: str = "512m",
        cpu_limit: float = 1.0,
        env: dict[str, str] | None = None,
    ) -> MicroVMResult:
        """Run a command in a libkrun MicroVM container.

        Uses ``--runtime=krun`` to route through libkrun's KVM-based VM.
        Each container gets its own kernel and isolated memory space.

        Args:
            image: Container image to run (e.g. ``python:3.13-slim``).
            command: Command and arguments to run inside the container.
            input_data: Optional string to pass via stdin.
            timeout: Maximum wall-clock time in seconds (default 60).
            memory_limit: Container memory limit (default ``"512m"``).
            cpu_limit: CPU limit as a float (e.g. ``1.0`` = 1 CPU).
            env: Environment variables to set inside the container.

        Returns:
            MicroVMResult with exit code, stdout, and stderr.

        Raises:
            MicroVMTimeoutError: If the container exceeds the timeout.
            MicroVMRuntimeError: If the container runtime fails to start.
        """
        cmd = self._build_command(
            image,
            command,
            input_data=input_data,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            env=env,
        )

        logger.info(
            "MicroVM execute: runtime=%s image=%s timeout=%ds",
            self._runtime,
            image,
            timeout,
            extra={
                "event": "microvm_execute",
                "runtime": self._runtime,
                "image": image,
                "timeout": timeout,
                "memory_limit": memory_limit,
            },
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise MicroVMRuntimeError(
                f"Container runtime '{self._runtime}' not found: {exc}"
            ) from exc
        except OSError as exc:
            raise MicroVMRuntimeError(
                f"Failed to start MicroVM container: {exc}"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(
                    input_data.encode() if input_data is not None else None
                ),
                timeout=timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise MicroVMTimeoutError(
                f"MicroVM timed out after {timeout}s"
            ) from exc

        result = MicroVMResult(
            exit_code=proc.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

        logger.info(
            "MicroVM completed: runtime=%s image=%s exit_code=%d",
            self._runtime,
            image,
            result.exit_code,
            extra={
                "event": "microvm_completed",
                "runtime": self._runtime,
                "image": image,
                "exit_code": result.exit_code,
                "stdout_bytes": len(result.stdout),
                "stderr_bytes": len(result.stderr),
            },
        )

        return result


def is_krun_available() -> bool:
    """Check if krun (libkrun) is available on this system."""
    return shutil.which("krun") is not None or shutil.which("crun") is not None
