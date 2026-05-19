"""MicroVM sandbox for executing tools in Firecracker or Cloud Hypervisor VMs.

Provides the highest isolation tier by running tool code inside a
lightweight virtual machine.  This module is a stub for now -- full
MicroVM support requires:
- A hypervisor binary (``firecracker`` or ``cloud-hypervisor``) on PATH
- A Linux kernel image (``vmlinux``)
- A root filesystem image (``rootfs.ext4``)

When these prerequisites are not met, ``execute()`` raises
``NotImplementedError`` with a helpful message directing users to the
container-based tiers (docker/podman) as an alternative.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class MicroVMError(Exception):
    """Raised when the MicroVM sandbox encounters an error."""


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
    """Runs tools in Firecracker or Cloud Hypervisor MicroVMs.

    Requires:
    - ``firecracker`` or ``cloud-hypervisor`` binary on PATH
    - Linux kernel image
    - Root filesystem image

    Currently a stub: ``execute()`` raises ``NotImplementedError``.
    """

    def __init__(self, hypervisor: str = "auto") -> None:
        """Initialize the MicroVM sandbox.

        Args:
            hypervisor: ``"firecracker"``, ``"cloud-hypervisor"``, or ``"auto"``.
        """
        self._hypervisor = self._detect_hypervisor(hypervisor)

    @property
    def hypervisor(self) -> str:
        """The resolved hypervisor binary name."""
        return self._hypervisor

    @staticmethod
    def _detect_hypervisor(preference: str) -> str:
        """Detect available hypervisor.

        When preference is ``"auto"``, checks for Firecracker first,
        then Cloud Hypervisor.

        Raises:
            MicroVMError: If no hypervisor is found.
        """
        if preference != "auto":
            if shutil.which(preference) is None:
                raise MicroVMError(
                    f"Hypervisor '{preference}' not found on PATH"
                )
            return preference
        if shutil.which("firecracker"):
            return "firecracker"
        if shutil.which("cloud-hypervisor"):
            return "cloud-hypervisor"
        raise MicroVMError(
            "No MicroVM hypervisor found (install firecracker or cloud-hypervisor)"
        )

    async def execute(
        self,
        command: str,
        *,
        input_data: str | None = None,
        timeout: int = 30,
        memory_mb: int = 128,
        vcpus: int = 1,
    ) -> MicroVMResult:
        """Run a command in a disposable MicroVM.

        This is currently a stub. Full MicroVM support requires
        kernel and rootfs image configuration.

        Args:
            command: Command to execute inside the VM.
            input_data: Optional string to pass as input.
            timeout: Maximum execution time in seconds.
            memory_mb: VM memory in megabytes.
            vcpus: Number of virtual CPUs.

        Raises:
            NotImplementedError: Always, until full MicroVM support is implemented.
        """
        raise NotImplementedError(
            f"MicroVM sandbox ({self._hypervisor}) requires kernel and rootfs "
            f"image setup. Use 'docker' or 'podman' tier for container-based "
            f"isolation instead."
        )
