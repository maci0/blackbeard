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
    "MicroVMError",
    "MicroVMResult",
    "MicroVMRuntimeError",
    "MicroVMSandbox",
    "MicroVMTimeoutError",
    "is_krun_available",
]

# Alias kept for the historical per-tier result name (same shape as SandboxResult).
MicroVMResult = SandboxResult


class MicroVMError(SandboxRuntimeError):
    """Raised when the MicroVM sandbox encounters an error."""


class MicroVMTimeoutError(MicroVMError, SandboxTimeoutError):
    """Raised when a MicroVM execution exceeds the timeout."""


class MicroVMRuntimeError(MicroVMError):
    """Raised when the container runtime or krun fails to start."""


def is_krun_available() -> bool:
    """Check if krun (libkrun) is available on this system."""
    return shutil.which("krun") is not None or shutil.which("crun") is not None


class MicroVMSandbox(BaseSandbox):
    """Runs tools in libkrun MicroVMs via the krun OCI runtime.

    Security defaults (defense in depth):
    - ``--runtime=krun``: each container runs in its own KVM-based VM
    - ``--network none``: no network access
    - ``--read-only``: read-only root filesystem
    - ``--security-opt no-new-privileges:true``: prevent privilege escalation
    - ``--cap-drop ALL``: drop all Linux capabilities
    - ``--rm``: auto-remove container after exit
    - Memory and CPU limits enforced

    Requires: crun with krun support (libkrun), KVM access (/dev/kvm)
    """

    _runtime_flag = "--runtime=krun"
    _default_memory = "512m"
    _default_timeout = 60
    _error_prefix = "MicroVM"
    _runtime_error_type = MicroVMRuntimeError
    _timeout_error_type = MicroVMTimeoutError

    def _verify(self) -> None:
        """Warn when neither krun nor crun is found; soft check only."""
        if not shutil.which("krun") and not shutil.which("crun"):
            logger.warning(
                "krun/crun not found: microvm sandbox tier will fail at "
                "execution time. "
                "Install: apt install crun-krun or dnf install crun-krun",
                extra={"event": "microvm_krun_not_found"},
            )
