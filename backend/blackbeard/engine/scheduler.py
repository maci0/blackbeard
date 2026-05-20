"""Automation scheduler: runs cron-triggered automations as background tasks.

Loads all enabled Automation resources with cron triggers on startup and
schedules them using croniter. Each cron job kicks off the referenced
Crew or Flow via the existing execution engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from croniter import croniter

from blackbeard.kinds import ResourceKind
from blackbeard.models import Resource, async_session

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """Simple cron scheduler that runs as a background task in the FastAPI lifespan."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    async def start(self) -> None:
        """Load all enabled automations with cron triggers and schedule them."""
        self._running = True
        try:
            async with async_session() as session:
                from sqlalchemy import select

                result = await session.execute(
                    select(Resource).where(Resource.kind == ResourceKind.AUTOMATION)
                )
                automations = list(result.scalars())

            for automation in automations:
                spec = automation.spec or {}
                if not spec.get("enabled", True):
                    continue
                trigger = spec.get("trigger", {})
                if trigger.get("type") != "cron":
                    continue
                cron_expr = trigger.get("cron")
                if not cron_expr:
                    continue
                target = spec.get("target", {})
                inputs = spec.get("inputs", {})
                namespace = spec.get("namespace", automation.namespace)

                self._schedule(automation.name, cron_expr, target, inputs, namespace)

            logger.info(
                "Automation scheduler started: %d cron tasks scheduled",
                len(self._tasks),
                extra={
                    "event": "scheduler_started",
                    "cron_task_count": len(self._tasks),
                },
            )
        except Exception:
            logger.exception(
                "Failed to start automation scheduler",
                extra={"event": "scheduler_start_failed"},
            )

    async def stop(self) -> None:
        """Cancel all scheduled tasks."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            logger.debug(
                "Cancelled cron task: %s",
                name,
                extra={"event": "cron_task_cancelled", "automation_name": name},
            )
        self._tasks.clear()
        logger.info(
            "Automation scheduler stopped",
            extra={"event": "scheduler_stopped"},
        )

    async def reload(self) -> None:
        """Cancel all tasks and re-load from database.

        Called when Automation resources are created, updated, or deleted
        so that cron schedules stay in sync with the database.
        """
        logger.info(
            "Automation scheduler reloading",
            extra={"event": "scheduler_reloading"},
        )
        await self.stop()
        await self.start()

    def _schedule(
        self,
        automation_name: str,
        cron_expr: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        namespace: str,
    ) -> None:
        """Schedule a single cron automation."""
        if automation_name in self._tasks:
            self._tasks[automation_name].cancel()

        task = asyncio.create_task(
            self._run_cron(automation_name, cron_expr, target, inputs, namespace),
            name=f"cron-{automation_name}",
        )
        self._tasks[automation_name] = task

    async def _run_cron(
        self,
        automation_name: str,
        cron_expr: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        namespace: str,
    ) -> None:
        """Run on cron schedule using croniter."""
        try:
            cron = croniter(cron_expr, datetime.now(UTC))
        except (ValueError, KeyError):
            logger.error(
                "Invalid cron expression for automation '%s': %s",
                automation_name,
                cron_expr,
                extra={
                    "event": "invalid_cron_expression",
                    "automation_name": automation_name,
                    "cron_expr": cron_expr,
                },
            )
            return

        while self._running:
            next_dt = cron.get_next(datetime)
            now = datetime.now(UTC)
            delay = (next_dt - now).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

            if not self._running:
                break

            await self._trigger_target(automation_name, target, inputs, namespace)

    async def _trigger_target(
        self,
        automation_name: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        namespace: str,
    ) -> None:
        """Trigger the target Crew or Flow."""
        target_kind = target.get("kind", "Crew")
        target_name = target.get("name", "")

        try:
            from blackbeard.engine.executor import kickoff, run_flow

            async with async_session() as session:
                if target_kind == "Flow":
                    await run_flow(
                        session,
                        target_name,
                        inputs=inputs,
                        namespace=namespace,
                    )
                else:
                    await kickoff(
                        session,
                        target_name,
                        inputs=inputs,
                        namespace=namespace,
                    )

            logger.info(
                "Automation '%s' triggered: %s/%s",
                automation_name,
                target_kind,
                target_name,
                extra={
                    "event": "automation_triggered",
                    "automation_name": automation_name,
                    "target_kind": target_kind,
                    "target_name": target_name,
                    "namespace": namespace,
                },
            )
        except Exception:
            logger.exception(
                "Automation '%s' trigger failed: %s/%s",
                automation_name,
                target_kind,
                target_name,
                extra={
                    "event": "automation_trigger_failed",
                    "automation_name": automation_name,
                    "target_kind": target_kind,
                    "target_name": target_name,
                    "namespace": namespace,
                },
            )
