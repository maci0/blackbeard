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

from croniter import croniter  # type: ignore[import-untyped]

from blackbeard.kinds import ResourceKind
from blackbeard.models import Resource, async_session

logger = logging.getLogger(__name__)


class AutomationScheduler:
    """Simple cron scheduler that runs as a background task in the FastAPI lifespan."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._reload_lock = asyncio.Lock()

    async def start(self) -> None:
        """Load all enabled automations with cron triggers and schedule them."""
        self._running = True
        try:
            async with async_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import load_only

                result = await session.execute(
                    select(Resource)
                    .options(load_only(Resource.name, Resource.project, Resource.spec))
                    .where(Resource.kind == ResourceKind.AUTOMATION)
                    .order_by(Resource.name)
                    .limit(1000)
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
                project = spec.get("project", automation.project)

                self._schedule(automation.name, cron_expr, target, inputs, project)

            logger.info(
                "Automation scheduler started: %d cron tasks scheduled",
                len(self._tasks),
                extra={
                    "event": "scheduler_started",
                    "cron_task_count": len(self._tasks),
                },
            )
        except Exception:
            self._running = False
            logger.exception(
                "Failed to start automation scheduler — no cron automations will run until restart",
                extra={"event": "scheduler_start_failed"},
            )
            raise

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

    @staticmethod
    def _log_cron_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except Exception:
            return
        if exc is not None:
            logger.error(
                "Cron task '%s' died unexpectedly: %s",
                task.get_name(),
                exc,
                exc_info=exc,
                extra={
                    "event": "cron_task_failed",
                    "task_name": task.get_name(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )

    async def reload(self) -> None:
        """Cancel all tasks and re-load from database.

        Called when Automation resources are created, updated, or deleted
        so that cron schedules stay in sync with the database.
        Serialized via lock to prevent interleaved stop/start cycles
        when multiple resource mutations arrive concurrently.
        """
        async with self._reload_lock:
            logger.info(
                "Automation scheduler reloading",
                extra={"event": "scheduler_reloading"},
            )
            await self.stop()
            await self.start()

    # Minimum interval between cron executions (in seconds).
    # Prevents DoS via ``* * * * *`` (every minute) or sub-minute crons.
    _MIN_INTERVAL_S = 60

    def _schedule(
        self,
        automation_name: str,
        cron_expr: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        project: str,
    ) -> None:
        """Schedule a single cron automation.

        Validates that the cron expression does not fire more often than
        once per minute.  Rejects sub-minute cron expressions (6-field
        second-resolution expressions) and expressions whose consecutive
        firings are less than ``_MIN_INTERVAL_S`` (60s) apart.
        """
        # SECURITY: Reject cron expressions with more than 5 fields
        # (second-resolution crons can fire every second = DoS).
        fields = cron_expr.strip().split()
        if len(fields) > 5:
            logger.warning(
                "Automation '%s': rejecting sub-minute cron expression: %s",
                automation_name,
                cron_expr,
                extra={
                    "event": "cron_too_frequent",
                    "automation_name": automation_name,
                    "cron_expr": cron_expr,
                },
            )
            return

        # Validate that consecutive firings are at least _MIN_INTERVAL_S apart
        try:
            test_cron = croniter(cron_expr, datetime.now(UTC))
            first = test_cron.get_next(datetime)
            second = test_cron.get_next(datetime)
            interval = (second - first).total_seconds()
            if interval < self._MIN_INTERVAL_S:
                logger.warning(
                    "Automation '%s': cron interval too short (%.0fs < %ds): %s",
                    automation_name,
                    interval,
                    self._MIN_INTERVAL_S,
                    cron_expr,
                    extra={
                        "event": "cron_too_frequent",
                        "automation_name": automation_name,
                        "cron_expr": cron_expr,
                        "interval_s": interval,
                    },
                )
                return
        except (ValueError, KeyError):
            logger.error(
                "Invalid cron expression for automation '%s': %s",
                automation_name,
                cron_expr,
                exc_info=True,
                extra={
                    "event": "invalid_cron_expression",
                    "automation_name": automation_name,
                    "cron_expr": cron_expr,
                },
            )
            return

        if automation_name in self._tasks:
            self._tasks[automation_name].cancel()

        task = asyncio.create_task(
            self._run_cron(automation_name, cron_expr, target, inputs, project),
            name=f"cron-{automation_name}",
        )
        task.add_done_callback(self._log_cron_task_exception)
        self._tasks[automation_name] = task

    async def _run_cron(
        self,
        automation_name: str,
        cron_expr: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        project: str,
    ) -> None:
        """Run on cron schedule using croniter."""
        try:
            cron = croniter(cron_expr, datetime.now(UTC))
        except (ValueError, KeyError):
            logger.error(
                "Invalid cron expression for automation '%s': %s",
                automation_name,
                cron_expr,
                exc_info=True,
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
            # SECURITY: Ensure a minimum sleep of 1 second to prevent
            # tight loops if croniter returns a time in the past (clock
            # skew, DST transition, etc.).
            delay = max(delay, 1.0)
            await asyncio.sleep(delay)

            if not self._running:
                break

            await self._trigger_target(automation_name, target, inputs, project)

    async def _trigger_target(
        self,
        automation_name: str,
        target: dict[str, Any],
        inputs: dict[str, Any],
        project: str,
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
                        project=project,
                    )
                else:
                    await kickoff(
                        session,
                        target_name,
                        inputs=inputs,
                        project=project,
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
                    "project": project,
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
                    "project": project,
                },
            )
