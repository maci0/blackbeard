"""gVisor (runsc) sandbox for tool execution.

gVisor provides syscall-level isolation: each container gets its own
application kernel that intercepts and validates syscalls.  Stronger than
standard container isolation (docker/podman) but lighter than MicroVMs.

gVisor runs as an OCI runtime, so it uses Docker or Podman as the container
manager with ``--runtime=runsc``.
Install: https://gvisor.dev/docs/user_guide/install/
"""

from __future__ import annotations

import logging
import shutil

from blackbeard.engine.sandbox.base import (
    BaseSandbox,
    SandboxResult,
    SandboxRuntimeError,
    SandboxTimeoutError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GVisorResult",
    "GVisorRuntimeError",
    "GVisorSandbox",
    "GVisorTimeoutError",
    "is_gvisor_available",
]

# Alias kept for the historical per-tier result name (same shape as SandboxResult).
GVisorResult = SandboxResult


class GVisorTimeoutError(SandboxTimeoutError):
    """Raised when a gVisor container execution exceeds the timeout."""


class GVisorRuntimeError(SandboxRuntimeError):
    """Raised when the gVisor sandbox encounters a runtime error."""


def is_gvisor_available() -> bool:
    """Check if gVisor (runsc) is installed on PATH."""
    return shutil.which("runsc") is not None


class GVisorSandbox(BaseSandbox):
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

    _runtime_flag = "--runtime=runsc"
    _error_prefix = "gVisor"
    _runtime_error_type = GVisorRuntimeError
    _timeout_error_type = GVisorTimeoutError

    def _verify(self) -> None:
        """Warn when runsc is missing; the tier fails at execution time."""
        if not shutil.which("runsc"):
            logger.warning(
                "runsc (gVisor) not found -- gvisor sandbox tier will fail at "
                "execution time. Install from "
                "https://gvisor.dev/docs/user_guide/install/",
                extra={"event": "gvisor_runsc_not_found"},
            )
