"""Base class for container-based sandbox runtimes.

Extracts the common runtime detection, command building, and process
execution logic shared by ContainerSandbox, GVisorSandbox, and
MicroVMSandbox into a single abstract base class.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Env var keys: only allow alphanumerics and underscores, starting with a
# letter or underscore. Prevents injection of flags via crafted key names.
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Image name allowlist: standard Docker image references.
_IMAGE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:@\-]*$")


def new_sandbox_container_name() -> str:
    """Return a unique container name for one sandboxed execution."""
    return f"bb-sbx-{uuid.uuid4().hex[:16]}"


async def force_remove_container(runtime_bin: str, container_name: str) -> None:
    """Best-effort ``<runtime> rm -f`` for a timed-out sandbox container.

    Killing the runtime CLI process leaves the actual container running
    under the daemon; without removal, repeated timeouts accumulate
    running containers (external claims on CPU/memory) until they exit
    on their own.
    """
    try:
        cleanup = await asyncio.create_subprocess_exec(
            runtime_bin,
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(cleanup.wait(), timeout=10)
    except Exception as exc:
        logger.warning(
            "Failed to remove timed-out container %s",
            container_name,
            exc_info=True,
            extra={
                "event": "sandbox_container_remove_failed",
                "container_name": container_name,
                "error_type": type(exc).__name__,
            },
        )


class SandboxRuntimeError(Exception):
    """Raised when the container runtime encounters an error."""


class SandboxTimeoutError(SandboxRuntimeError):
    """Raised when a sandbox execution exceeds the timeout."""


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Result of a sandboxed container execution."""

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


class BaseSandbox(ABC):
    """Abstract base for container-based sandbox runtimes.

    Provides shared logic for:
    - Container runtime auto-detection (prefers Podman for rootless)
    - Security-hardened command building (cap-drop, no-new-privileges, etc.)
    - Async subprocess execution with timeout handling

    Subclasses implement ``_extra_flags()`` to add runtime-specific flags
    (e.g. ``--runtime=runsc`` for gVisor, ``--runtime=krun`` for MicroVM)
    and ``_runtime_flag`` / ``_default_memory`` / ``_default_timeout``
    for tier-specific defaults.
    """

    # Subclasses should set these class-level defaults.
    _runtime_flag: str = ""  # e.g. "runsc", "krun"; empty = standard container
    _default_memory: str = "256m"
    _default_timeout: int = 30
    _error_prefix: str = "Container"  # for error messages

    def __init__(self, container_runtime: str = "auto") -> None:
        self._runtime = self._detect_runtime(container_runtime)

    @property
    def runtime(self) -> str:
        """The resolved container runtime binary name."""
        return self._runtime

    def _detect_runtime(self, preference: str) -> str:
        """Detect available container runtime.

        When preference is ``"auto"``, checks for Podman first (preferred
        for rootless operation), then Docker.

        Raises:
            SandboxRuntimeError: If no container runtime is found.
        """
        if preference != "auto":
            if shutil.which(preference) is None:
                raise SandboxRuntimeError(f"Container runtime '{preference}' not found on PATH")
            return preference
        # Auto-detect: prefer podman (rootless by default)
        if shutil.which("podman"):
            return "podman"
        if shutil.which("docker"):
            return "docker"
        raise SandboxRuntimeError(
            f"No container runtime found for {self._error_prefix} (install docker or podman)"
        )

    @abstractmethod
    def _extra_flags(self) -> list[str]:
        """Return subclass-specific flags to insert after ``run --rm``.

        For example, gVisor returns ``["--runtime=runsc"]`` and MicroVM
        returns ``["--runtime=krun"]``.  The base container sandbox returns
        an empty list.
        """

    def _build_command(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        memory_limit: str | None = None,
        cpu_limit: float = 1.0,
        network: bool = False,
        read_only: bool = True,
        env: dict[str, str] | None = None,
        container_name: str | None = None,
    ) -> list[str]:
        """Build the container run command with security defaults.

        Raises:
            SandboxRuntimeError: If the image name contains invalid characters.
        """
        # SECURITY: Validate the image name to prevent argument injection.
        if not _IMAGE_RE.fullmatch(image):
            raise SandboxRuntimeError(f"Invalid container image name: {image!r}")

        mem = memory_limit or self._default_memory
        cmd: list[str] = [
            self._runtime,
            "run",
            "--rm",
            *self._extra_flags(),
        ]
        # Named container so a timed-out run can be force-removed (the
        # daemon-owned container outlives the killed CLI process).
        if container_name:
            cmd.extend(["--name", container_name])
        cmd.extend(
            [
                "--memory",
                mem,
                f"--cpus={cpu_limit}",
                "--security-opt",
                "no-new-privileges:true",
                "--cap-drop",
                "ALL",
            ]
        )

        if not network:
            cmd.extend(["--network", "none"])

        if read_only:
            cmd.append("--read-only")

        # SECURITY: Validate env var keys (same rationale as ContainerSandbox).
        if env:
            for k, v in sorted(env.items()):
                if not _ENV_KEY_RE.fullmatch(k):
                    logger.warning(
                        "%s: skipping env var with invalid key: %s",
                        self._error_prefix,
                        k[:50],
                        extra={
                            "event": f"{self._error_prefix.lower()}_invalid_env_key",
                            "key": k[:50],
                        },
                    )
                    continue
                cmd.extend(["-e", f"{k}={v}"])

        if input_data is not None:
            cmd.append("-i")

        cmd.append(image)
        cmd.extend(command)
        return cmd

    async def _execute_subprocess(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        timeout: int | None = None,
        memory_limit: str | None = None,
        cpu_limit: float = 1.0,
        network: bool = False,
        read_only: bool = True,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command in a sandboxed container (shared implementation).

        Subclasses call this from their ``execute()`` method, which may
        have different default parameters or return a subclass-specific
        result type.

        Args:
            image: Container image to run (e.g. ``python:3.13-slim``).
            command: Command and arguments to run inside the container.
            input_data: Optional string to pass via stdin.
            timeout: Maximum wall-clock time in seconds.
            memory_limit: Container memory limit (e.g. ``"256m"``).
            cpu_limit: CPU limit as a float (e.g. ``1.0`` = 1 CPU).
            network: Whether to allow network access (default ``False``).
            read_only: Whether to mount the root filesystem read-only.
            env: Environment variables to set inside the container.

        Returns:
            SandboxResult with exit code, stdout, and stderr.

        Raises:
            SandboxTimeoutError: If the container exceeds the timeout.
            SandboxRuntimeError: If the container runtime fails to start.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        container_name = new_sandbox_container_name()
        cmd = self._build_command(
            image,
            command,
            input_data=input_data,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
            network=network,
            read_only=read_only,
            env=env,
            container_name=container_name,
        )

        logger.info(
            "%s execute: runtime=%s image=%s timeout=%ds",
            self._error_prefix,
            self._runtime,
            image,
            effective_timeout,
            extra={
                "event": f"{self._error_prefix.lower()}_execute",
                "runtime": self._runtime,
                "image": image,
                "timeout": effective_timeout,
                "network": network,
                "read_only": read_only,
                "memory_limit": memory_limit or self._default_memory,
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
            raise SandboxRuntimeError(
                f"Container runtime '{self._runtime}' not found: {exc}"
            ) from exc
        except OSError as exc:
            raise SandboxRuntimeError(
                f"Failed to start {self._error_prefix.lower()} container: {exc}"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input_data.encode() if input_data is not None else None),
                timeout=effective_timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            # The daemon-owned container survives the killed CLI; remove it.
            await force_remove_container(self._runtime, container_name)
            raise SandboxTimeoutError(
                f"{self._error_prefix} timed out after {effective_timeout}s"
            ) from exc

        result = SandboxResult(
            exit_code=proc.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

        logger.info(
            "%s completed: runtime=%s image=%s exit_code=%d",
            self._error_prefix,
            self._runtime,
            image,
            result.exit_code,
            extra={
                "event": f"{self._error_prefix.lower()}_completed",
                "runtime": self._runtime,
                "image": image,
                "exit_code": result.exit_code,
                "stdout_bytes": len(result.stdout),
                "stderr_bytes": len(result.stderr),
            },
        )

        return result
