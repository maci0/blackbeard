"""Unified sync entry points for running commands in a sandbox tier."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import shlex
from typing import Any

from blackbeard.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "SandboxExecutionError",
    "ensure_sandbox_available",
    "execute_sandboxed",
    "runtime_tier_for_tool",
]


class SandboxExecutionError(Exception):
    """Raised when a sandboxed command fails or the runtime is unavailable."""


def runtime_tier_for_tool(tier: str, tool_type: str) -> str:
    """Map logical tier to a runtime that can execute this tool type.

    Python/builtin tools cannot run under wasm isolation; promote to docker.
    """
    if tier in ("", "none", None):
        return "none"
    if tool_type == "wasm":
        return "wasm"
    if tier == "wasm":
        return "docker"
    return tier


def ensure_sandbox_available(tier: str) -> None:
    """Raise SandboxExecutionError if the tier cannot run on this host."""
    if tier in ("none", ""):
        return
    if tier == "wasm":
        try:
            import wasmtime  # noqa: F401
        except ImportError as exc:
            raise SandboxExecutionError(
                "wasm sandbox requires the wasmtime package"
            ) from exc
        return
    if tier in ("docker", "podman"):
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        try:
            ContainerSandbox(runtime=tier if tier != "docker" else settings.container_runtime)
        except Exception as exc:
            raise SandboxExecutionError(f"container sandbox unavailable: {exc}") from exc
        return
    if tier == "gvisor":
        from blackbeard.engine.sandbox.gvisor_runtime import is_gvisor_available

        if not is_gvisor_available():
            raise SandboxExecutionError("gvisor (runsc) is not available on this host")
        return
    if tier == "microvm":
        from blackbeard.engine.sandbox.selector import select_microvm_backend

        backend = select_microvm_backend()
        if backend == "none":
            raise SandboxExecutionError(
                "microvm sandbox unavailable (need firecracker+kernel or krun)"
            )
        return
    raise SandboxExecutionError(f"unknown sandbox tier: {tier}")


def _run_coro(coro: Any) -> Any:
    """Run an async coroutine from sync tool code (possibly inside an event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _execute_async(
    tier: str,
    command: list[str],
    *,
    input_data: str | None,
    env: dict[str, str] | None,
    network: bool,
) -> tuple[int, str, str]:
    timeout = settings.container_timeout
    memory = settings.container_memory_limit
    image = settings.container_default_image

    if tier in ("docker", "podman"):
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        runtime = tier if tier == "podman" else settings.container_runtime
        sandbox = ContainerSandbox(runtime=runtime)
        result = await sandbox.execute(
            image,
            command,
            input_data=input_data,
            timeout=timeout,
            memory_limit=memory,
            network=network,
            env=env,
        )
        return result.exit_code, result.stdout, result.stderr

    if tier == "gvisor":
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        sandbox = GVisorSandbox(container_runtime=settings.container_runtime)
        result = await sandbox.execute(
            image,
            command,
            input_data=input_data,
            timeout=timeout,
            memory_limit=memory,
            env=env,
        )
        return result.exit_code, result.stdout, result.stderr

    if tier == "microvm":
        from blackbeard.engine.sandbox.selector import select_microvm_backend

        backend = select_microvm_backend()
        if backend == "firecracker":
            from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

            sandbox = FirecrackerSandbox()
            cmd_str = shlex.join(command)
            result = await sandbox.execute(
                cmd_str,
                input_data=input_data,
                timeout=max(timeout, 60),
                env=env,
            )
            return result.exit_code, result.stdout, result.stderr

        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        sandbox = MicroVMSandbox(container_runtime=settings.container_runtime)
        result = await sandbox.execute(
            image,
            command,
            input_data=input_data,
            timeout=max(timeout, 60),
            memory_limit=memory,
            env=env,
        )
        return result.exit_code, result.stdout, result.stderr

    raise SandboxExecutionError(f"tier {tier!r} has no command executor")


def execute_sandboxed(
    tier: str,
    command: list[str],
    *,
    input_data: str | None = None,
    env: dict[str, str] | None = None,
    network: bool = False,
) -> tuple[int, str, str]:
    """Run ``command`` under ``tier``. Returns ``(exit_code, stdout, stderr)``."""
    if tier in ("none", "wasm"):
        raise SandboxExecutionError(f"execute_sandboxed does not support tier={tier!r}")
    ensure_sandbox_available(tier)
    logger.info(
        "Sandbox execute: tier=%s command=%s",
        tier,
        command[:3],
        extra={"event": "sandbox_execute", "tier": tier, "command0": command[0] if command else ""},
    )
    return _run_coro(
        _execute_async(tier, command, input_data=input_data, env=env, network=network)
    )
