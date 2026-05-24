"""gVisor (runsc) sandbox for tool execution.

gVisor provides syscall-level isolation -- each container gets its own
application kernel that intercepts and validates syscalls.  Stronger than
standard container isolation (docker/podman) but lighter than MicroVMs.

gVisor runs as an OCI runtime, so it uses Docker or Podman as the container
manager with ``--runtime=runsc``.

Install: https://gvisor.dev/docs/user_guide/install/
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class GVisorTimeoutError(Exception):
    """Raised when a gVisor container execution exceeds the timeout."""


class GVisorRuntimeError(Exception):
    """Raised when the gVisor sandbox encounters a runtime error."""


@dataclass(frozen=True, slots=True)
class GVisorResult:
    """Result of a gVisor-sandboxed container execution."""

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


class GVisorSandbox:
    """Runs tools in gVisor-sandboxed containers via ``--runtime=runsc``.

    Security defaults (defense in depth):
    - ``--runtime=runsc``: syscall-level isolation via gVisor application kernel
    - ``--network none``: no network access
    - ``--read-only``: read-only root filesystem
    - ``--security-opt no-new-privileges:true``: prevent privilege escalation
    - ``--cap-drop ALL``: drop all Linux capabilities
    - ``--rm``: auto-remove container after exit
    - Memory and CPU limits enforced

    Requires ``runsc`` installed on the host. Uses Docker or Podman as the
    underlying container manager.
    """

    def __init__(self, container_runtime: str = "auto") -> None:
        """Initialize the gVisor sandbox.

        Args:
            container_runtime: ``"docker"``, ``"podman"``, or ``"auto"``
                (detect available).  When ``"auto"``, prefers Podman for
                rootless container support.
        """
        self._runtime = self._detect_runtime(container_runtime)
        self._verify_gvisor()

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
            GVisorRuntimeError: If no container runtime is found.
        """
        if preference != "auto":
            if shutil.which(preference) is None:
                raise GVisorRuntimeError(f"Container runtime '{preference}' not found on PATH")
            return preference
        if shutil.which("podman"):
            return "podman"
        if shutil.which("docker"):
            return "docker"
        raise GVisorRuntimeError("No container runtime found for gVisor (install docker or podman)")

    @staticmethod
    def _verify_gvisor() -> None:
        """Check that runsc is available on PATH."""
        if not shutil.which("runsc"):
            logger.warning(
                "runsc (gVisor) not found -- gvisor sandbox tier will fail at "
                "execution time. Install from "
                "https://gvisor.dev/docs/user_guide/install/",
                extra={"event": "gvisor_runsc_not_found"},
            )

    # Env var keys: only allow alphanumerics and underscores, starting
    # with a letter or underscore.
    _ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    # Image name allowlist: standard Docker image references.
    _IMAGE_RE = re.compile(
        r"^[a-zA-Z0-9]"
        r"[a-zA-Z0-9._/:@\-]*$"
    )

    def _build_command(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        memory_limit: str = "256m",
        cpu_limit: float = 1.0,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build the gVisor container run command.

        This method is intentionally separated from ``execute`` for
        testability -- tests can verify the command line without
        spawning a real process.

        Raises:
            GVisorRuntimeError: If the image name or env var keys
                contain invalid characters.
        """
        # SECURITY: Validate the image name to prevent argument injection.
        if not self._IMAGE_RE.match(image):
            raise GVisorRuntimeError(f"Invalid container image name: {image!r}")

        cmd: list[str] = [
            self._runtime,
            "run",
            "--rm",
            "--runtime=runsc",
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

        # SECURITY: Validate env var keys (same rationale as ContainerSandbox).
        if env:
            for k, v in sorted(env.items()):
                if not self._ENV_KEY_RE.match(k):
                    logger.warning(
                        "gVisor: skipping env var with invalid key: %s",
                        k[:50],
                        extra={
                            "event": "gvisor_invalid_env_key",
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

    async def execute(
        self,
        image: str,
        command: list[str],
        *,
        input_data: str | None = None,
        timeout: int = 30,
        memory_limit: str = "256m",
        cpu_limit: float = 1.0,
        env: dict[str, str] | None = None,
    ) -> GVisorResult:
        """Run a command in a gVisor-sandboxed container.

        Uses ``--runtime=runsc`` to route through gVisor's application kernel.
        All syscalls are intercepted and validated by gVisor.

        Args:
            image: Container image to run (e.g. ``python:3.13-slim``).
            command: Command and arguments to run inside the container.
            input_data: Optional string to pass via stdin.
            timeout: Maximum wall-clock time in seconds.
            memory_limit: Container memory limit (e.g. ``"256m"``).
            cpu_limit: CPU limit as a float (e.g. ``1.0`` = 1 CPU).
            env: Environment variables to set inside the container.

        Returns:
            GVisorResult with exit code, stdout, and stderr.

        Raises:
            GVisorTimeoutError: If the container exceeds the timeout.
            GVisorRuntimeError: If the container runtime fails to start.
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
            "gVisor execute: runtime=%s image=%s timeout=%ds",
            self._runtime,
            image,
            timeout,
            extra={
                "event": "gvisor_execute",
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
            raise GVisorRuntimeError(
                f"Container runtime '{self._runtime}' not found: {exc}"
            ) from exc
        except OSError as exc:
            raise GVisorRuntimeError(f"Failed to start gVisor container: {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input_data.encode() if input_data is not None else None),
                timeout=timeout,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise GVisorTimeoutError(f"gVisor container timed out after {timeout}s") from exc

        result = GVisorResult(
            exit_code=proc.returncode or 0,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

        logger.info(
            "gVisor completed: runtime=%s image=%s exit_code=%d",
            self._runtime,
            image,
            result.exit_code,
            extra={
                "event": "gvisor_completed",
                "runtime": self._runtime,
                "image": image,
                "exit_code": result.exit_code,
                "stdout_bytes": len(result.stdout),
                "stderr_bytes": len(result.stderr),
            },
        )

        return result


def is_gvisor_available() -> bool:
    """Check if gVisor (runsc) is installed on PATH."""
    return shutil.which("runsc") is not None
