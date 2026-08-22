"""Container sandbox for executing tools in disposable Docker or Podman containers.

Provides isolated execution with:
- No network access by default
- Read-only filesystem by default
- Memory and CPU limits
- No privileged mode, no new privileges, all capabilities dropped
- Auto-removed after execution

Prefers Podman (rootless) over Docker when auto-detecting.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from typing import Any

from blackbeard.engine.sandbox.base import force_remove_container, new_sandbox_container_name

logger = logging.getLogger(__name__)


class ContainerTimeoutError(Exception):
    """Raised when a container execution exceeds the timeout."""


class ContainerRuntimeError(Exception):
    """Raised when the container runtime encounters an error."""


@dataclass(frozen=True, slots=True)
class ContainerResult:
    """Result of a container execution."""

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


class ContainerSandbox:
    """Runs tools in disposable Docker or Podman containers.

    Security defaults (defense in depth):
    - ``--network none``: no network access
    - ``--read-only``: read-only root filesystem
    - ``--security-opt no-new-privileges:true``: prevent privilege escalation
    - ``--cap-drop ALL``: drop all Linux capabilities
    - ``--rm``: auto-remove container after exit
    - Memory and CPU limits enforced
    """

    def __init__(self, runtime: str = "auto") -> None:
        """Initialize the container sandbox.

        Args:
            runtime: ``"docker"``, ``"podman"``, or ``"auto"`` (detect available).
                     When ``"auto"``, prefers Podman for rootless container support.
        """
        self._runtime = self._detect_runtime(runtime)

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
            ContainerRuntimeError: If no container runtime is found.
        """
        if preference != "auto":
            if shutil.which(preference) is None:
                raise ContainerRuntimeError(f"Container runtime '{preference}' not found on PATH")
            return preference
        # Auto-detect: prefer podman (rootless by default)
        if shutil.which("podman"):
            return "podman"
        if shutil.which("docker"):
            return "docker"
        raise ContainerRuntimeError("No container runtime found (install docker or podman)")

    # Env var keys: only allow alphanumerics and underscores, starting
    # with a letter or underscore.  Prevents injection of flags via
    # crafted key names (e.g. a key starting with ``-``).
    _ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    # Image name allowlist: standard Docker image references
    # (registry/repo:tag@digest).  Rejects anything that could be
    # misinterpreted as a flag (starts with ``-``) or contains shell
    # metacharacters.
    _IMAGE_RE = re.compile(
        r"^[a-zA-Z0-9]"  # must start with alphanumeric
        r"[a-zA-Z0-9._/:@\-]*$"  # rest: alphanumeric, dots, slashes, colons, @, hyphens
    )

    def _build_command(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        memory_limit: str = "256m",
        cpu_limit: float = 1.0,
        network: bool = False,
        read_only: bool = True,
        env: dict[str, str] | None = None,
        container_name: str | None = None,
    ) -> list[str]:
        """Build the container run command with security defaults.

        This method is intentionally separated from ``execute`` for
        testability -- tests can verify the command line without
        spawning a real process.

        Raises:
            ContainerRuntimeError: If the image name or env var keys
                contain invalid characters.
        """
        # SECURITY: Validate the image name to prevent argument injection.
        # A malicious image like ``--privileged`` would be interpreted as
        # a Docker flag rather than an image reference.
        if not self._IMAGE_RE.fullmatch(image):
            raise ContainerRuntimeError(f"Invalid container image name: {image!r}")

        cmd: list[str] = [
            self._runtime,
            "run",
            "--rm",
        ]
        # Named container so a timed-out run can be force-removed (the
        # daemon-owned container outlives the killed CLI process).
        if container_name:
            cmd.extend(["--name", container_name])
        cmd.extend(
            [
                "--memory",
                memory_limit,
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

        # SECURITY: Validate env var keys.  The ``-e KEY=VALUE`` form is
        # passed as two separate arguments to create_subprocess_exec (no
        # shell), so values cannot inject new flags.  However, a key
        # starting with ``-`` in the combined ``-e -flag=value`` form
        # could confuse the container runtime.  Keys are restricted to
        # the POSIX env var character set.
        if env:
            for k, v in sorted(env.items()):
                if not self._ENV_KEY_RE.fullmatch(k):
                    logger.warning(
                        "Container: skipping env var with invalid key: %s",
                        k[:50],
                        extra={
                            "event": "container_invalid_env_key",
                            "key": k[:50],
                        },
                    )
                    continue
                cmd.extend(["-e", f"{k}={v}"])

        if input_data is not None:
            cmd.append("-i")

        # Image name is validated above; safe to append.
        cmd.append(image)

        # SECURITY: Command args are passed as individual list elements
        # to create_subprocess_exec (not through a shell), so they
        # cannot inject additional container flags.  However, validate
        # that no command arg starts with ``-`` in the image position
        # (already handled by placing image before command).
        cmd.extend(command)

        return cmd

    async def execute(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        timeout: int = 30,
        memory_limit: str = "256m",
        cpu_limit: float = 1.0,
        network: bool = False,
        read_only: bool = True,
        env: dict[str, str] | None = None,
    ) -> ContainerResult:
        """Run a command in a disposable container.

        Args:
            image: Container image to run (e.g. ``python:3.13-slim``).
            command: Command and arguments to run inside the container.
            input_data: Optional string to pass via stdin.
            timeout: Maximum wall-clock time in seconds.
            memory_limit: Container memory limit (e.g. ``"256m"``).
            cpu_limit: CPU limit as a float (e.g. ``1.0`` = 1 CPU).
            network: Whether to allow network access (default ``False``).
            read_only: Whether to mount the root filesystem read-only (default ``True``).
            env: Environment variables to set inside the container.

        Returns:
            ContainerResult with exit code, stdout, and stderr.

        Raises:
            ContainerTimeoutError: If the container exceeds the timeout.
            ContainerRuntimeError: If the container runtime fails to start.
        """
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
            "Container execute: runtime=%s image=%s timeout=%ds",
            self._runtime,
            image,
            timeout,
            extra={
                "event": "container_execute",
                "runtime": self._runtime,
                "image": image,
                "timeout": timeout,
                "network": network,
                "read_only": read_only,
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
            raise ContainerRuntimeError(
                f"Container runtime '{self._runtime}' not found: {exc}"
            ) from exc
        except OSError as exc:
            raise ContainerRuntimeError(f"Failed to start container: {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input_data.encode() if input_data is not None else None),
                timeout=timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            # The daemon-owned container survives the killed CLI; remove it.
            await force_remove_container(self._runtime, container_name)
            raise ContainerTimeoutError(f"Container timed out after {timeout}s") from exc

        result = ContainerResult(
            exit_code=proc.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

        logger.info(
            "Container completed: runtime=%s image=%s exit_code=%d",
            self._runtime,
            image,
            result.exit_code,
            extra={
                "event": "container_completed",
                "runtime": self._runtime,
                "image": image,
                "exit_code": result.exit_code,
                "stdout_bytes": len(result.stdout),
                "stderr_bytes": len(result.stderr),
            },
        )

        return result
