"""Shared post-mutation side effects for resource-mutating endpoints.

Routers that create/update/delete resources (resources, marketplace,
agency_import, tools_library) all need the same after-commit machinery:
fire-and-forget background tasks, LiteLLM model sync, scheduler reload on
Automation changes, and RBAC cache invalidation. It lives here, not in any
single router, so routers never import sibling router modules.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Request

from blackbeard.auth.authorizer import clear_cache
from blackbeard.kinds import ResourceKind
from blackbeard.litellm import model_sync
from blackbeard.logging_config import log_task_exception

__all__ = [
    "AUTHZ_CACHE_KINDS",
    "AUTOMATION_KIND",
    "drain_background_tasks",
    "fire_and_forget",
    "maybe_reload_scheduler",
    "post_mutation_hooks",
    "sync_llm_to_litellm",
]

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[None]] = set()


def _discard_and_log(task: asyncio.Task[None]) -> None:
    _background_tasks.discard(task)
    log_task_exception(task)


def fire_and_forget(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_discard_and_log)


async def drain_background_tasks(timeout: float = 5.0) -> None:
    """Wait for in-flight background tasks (LiteLLM sync, etc.).

    Called during shutdown to avoid losing fire-and-forget mutations.
    """
    tasks = list(_background_tasks)
    if not tasks:
        return
    _done, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        logger.warning(
            "Cancelled %d background tasks that did not finish within %.1fs",
            len(pending),
            timeout,
            extra={
                "event": "background_tasks_cancelled_on_shutdown",
                "cancelled_count": len(pending),
                "timeout": timeout,
            },
        )


LLM_KIND = "LLMConnection"
AUTHZ_CACHE_KINDS = frozenset({ResourceKind.ROLE.value, ResourceKind.ROLE_BINDING.value})
AUTOMATION_KIND = ResourceKind.AUTOMATION.value


def post_mutation_hooks(
    request: Request,
    kind: str,
    name: str,
    spec: dict[str, Any] | None = None,
) -> None:
    """Fire scheduler/LiteLLM/RBAC side-effects after a resource mutation."""
    fire_and_forget(maybe_reload_scheduler(request, kind))
    fire_and_forget(sync_llm_to_litellm(kind, name, spec))
    if kind in AUTHZ_CACHE_KINDS:
        clear_cache()


async def sync_llm_to_litellm(kind: str, name: str, spec: dict[str, Any] | None) -> None:
    """Push LLMConnection changes to LiteLLM proxy (errors logged, not raised)."""
    if kind != LLM_KIND:
        return
    try:
        if spec is not None:
            await model_sync.add_model(name, spec)
        else:
            await model_sync.delete_model(name)
    except Exception:
        logger.warning(
            "LiteLLM sync failed for %s (non-fatal)",
            name,
            exc_info=True,
            extra={"event": "litellm_sync_failed", "model_name": name},
        )


async def maybe_reload_scheduler(request: Request, kind: str) -> None:
    """Trigger scheduler reload when an Automation resource is modified."""
    if kind != AUTOMATION_KIND:
        return
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            await scheduler.reload()
        except Exception as exc:
            logger.error(
                "Scheduler reload failed after Automation change: "
                "cron schedules may be stale until next restart",
                exc_info=True,
                extra={
                    "event": "scheduler_reload_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
