"""Container sandbox for executing tools in disposable Docker or Podman containers.

Prefers Podman (rootless) over Docker when auto-detecting.
"""

from __future__ import annotations

from blackbeard.engine.sandbox.base import (
    BaseSandbox,
    SandboxResult,
    SandboxRuntimeError,
    SandboxTimeoutError,
)

__all__ = ["ContainerResult", "ContainerRuntimeError", "ContainerSandbox", "ContainerTimeoutError"]

# Aliases kept for the historical per-tier result name (same shape as SandboxResult).
ContainerResult = SandboxResult


class ContainerTimeoutError(SandboxTimeoutError):
    """Raised when a container execution exceeds the timeout."""


class ContainerRuntimeError(SandboxRuntimeError):
    """Raised when the container runtime encounters an error."""


class ContainerSandbox(BaseSandbox):
    """Runs tools in disposable Docker or Podman containers.

    Security defaults (defense in depth):
    - ``--network none``: no network access
    - ``--read-only``: read-only root filesystem
    - ``--security-opt no-new-privileges:true``: prevent privilege escalation
    - ``--cap-drop ALL``: drop all Linux capabilities
    - ``--rm``: auto-remove container after exit
    - Memory and CPU limits enforced
    """

    _error_prefix = "Container"
    _runtime_error_type = ContainerRuntimeError
    _timeout_error_type = ContainerTimeoutError

    def __init__(self, runtime: str = "auto") -> None:
        """Initialize the container sandbox.

        Args:
            runtime: ``"docker"``, ``"podman"``, or ``"auto"`` (detect available).
                     When ``"auto"``, prefers Podman for rootless container support.
        """
        super().__init__(container_runtime=runtime)
