"""Unified sync entry points for running commands in a sandbox tier."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import shlex
import threading
from typing import TYPE_CHECKING

from blackbeard.config import settings

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = logging.getLogger(__name__)

__all__ = [
    "SandboxExecutionError",
    "ensure_sandbox_available",
    "execute_sandboxed",
    "runtime_tier_for_tool",
    "shutdown_sandbox_nest_pool",
]

# Shared pool for nested asyncio.run() when already inside an event loop.
# Avoids creating/destroying a ThreadPoolExecutor per sandboxed tool call.
_nest_pool: concurrent.futures.ThreadPoolExecutor | None = None
_nest_pool_lock = threading.Lock()


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
            raise SandboxExecutionError("wasm sandbox requires the wasmtime package") from exc
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


def _get_nest_pool() -> concurrent.futures.ThreadPoolExecutor:
    """Return a shared pool for nested event-loop sandbox runs."""
    global _nest_pool
    with _nest_pool_lock:
        if _nest_pool is None:
            # Bound workers to concurrent executions so tool fan-out cannot
            # spawn unbounded threads under load.
            workers = max(4, settings.max_concurrent_executions * 2)
            _nest_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="sandbox-nest",
            )
        return _nest_pool


def shutdown_sandbox_nest_pool() -> None:
    """Shut down the nested-loop sandbox pool (app shutdown)."""
    global _nest_pool
    with _nest_pool_lock:
        pool = _nest_pool
        _nest_pool = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _run_coro[T](coro: Coroutine[None, None, T]) -> T:
    """Run an async coroutine from sync tool code (possibly inside an event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return _get_nest_pool().submit(asyncio.run, coro).result()


async def _execute_async(
    tier: str,
    command: list[str],
    *,
    input_data: str | None,
    env: dict[str, str] | None,
    network: bool,
    image: str | None,
) -> tuple[int, str, str]:
    timeout = settings.container_timeout
    memory = settings.container_memory_limit
    image = image or settings.container_default_image

    if tier in ("docker", "podman"):
        from blackbeard.engine.sandbox.container_runtime import ContainerSandbox

        runtime = tier if tier == "podman" else settings.container_runtime
        container = ContainerSandbox(runtime=runtime)
        container_result = await container.execute(
            image,
            command,
            input_data=input_data,
            timeout=timeout,
            memory_limit=memory,
            network=network,
            env=env,
        )
        return container_result.exit_code, container_result.stdout, container_result.stderr

    if tier == "gvisor":
        from blackbeard.engine.sandbox.gvisor_runtime import GVisorSandbox

        gvisor = GVisorSandbox(container_runtime=settings.container_runtime)
        gvisor_result = await gvisor.execute(
            image,
            command,
            input_data=input_data,
            timeout=timeout,
            memory_limit=memory,
            env=env,
        )
        return gvisor_result.exit_code, gvisor_result.stdout, gvisor_result.stderr

    if tier == "microvm":
        from blackbeard.engine.sandbox.selector import select_microvm_backend

        backend = select_microvm_backend()
        if backend == "firecracker":
            from blackbeard.engine.sandbox.firecracker import FirecrackerSandbox

            firecracker = FirecrackerSandbox()
            cmd_str = shlex.join(command)
            fc_result = await firecracker.execute(
                cmd_str,
                input_data=input_data,
                timeout=max(timeout, 60),
                env=env,
            )
            return fc_result.exit_code, fc_result.stdout, fc_result.stderr

        from blackbeard.engine.sandbox.microvm_runtime import MicroVMSandbox

        microvm = MicroVMSandbox(container_runtime=settings.container_runtime)
        microvm_result = await microvm.execute(
            image,
            command,
            input_data=input_data,
            timeout=max(timeout, 60),
            memory_limit=memory,
            env=env,
        )
        return microvm_result.exit_code, microvm_result.stdout, microvm_result.stderr

    raise SandboxExecutionError(f"tier {tier!r} has no command executor")


def execute_sandboxed(
    tier: str,
    command: list[str],
    *,
    input_data: str | None = None,
    env: dict[str, str] | None = None,
    network: bool = False,
    image: str | None = None,
) -> tuple[int, str, str]:
    """Run ``command`` under ``tier``. Returns ``(exit_code, stdout, stderr)``.

    ``image`` overrides ``settings.container_default_image`` for container tiers.
    """
    if tier in ("none", "wasm"):
        raise SandboxExecutionError(f"execute_sandboxed does not support tier={tier!r}")
    ensure_sandbox_available(tier)
    logger.info(
        "Sandbox execute: tier=%s command=%s image=%s network=%s",
        tier,
        command[:3],
        image or settings.container_default_image,
        network,
        extra={
            "event": "sandbox_execute",
            "tier": tier,
            "command0": command[0] if command else "",
            "image": image or settings.container_default_image,
            "network": network,
        },
    )
    return _run_coro(
        _execute_async(
            tier,
            command,
            input_data=input_data,
            env=env,
            network=network,
            image=image,
        )
    )
