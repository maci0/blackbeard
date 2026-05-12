"""Execution engine: manages crew execution lifecycle.

Handles kickoff, status tracking, background execution, and result storage.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from blackbeard.config import settings
from blackbeard.engine.loader import ResourceLoader, LoaderError
from blackbeard.langfuse.listener import BlackbeardLangfuseListener
from blackbeard.models.execution import (
    Execution,
    ExecutionStatus,
    ExecutionTask,
    TaskStatus,
)
from blackbeard.kinds import ResourceKind
from blackbeard.models.resource import Resource
from blackbeard.models.database import async_session

logger = logging.getLogger(__name__)

_SAFE_ERROR_PREFIXES = ("Crew '", "Agent '", "Task '", "Tool '", "Resource '", "Kind '")


def _sanitize_error(error_msg: str) -> str:
    """Return a user-safe error string, redacting internal details."""
    if any(error_msg.startswith(p) for p in _SAFE_ERROR_PREFIXES):
        if len(error_msg) > 500:
            return error_msg[:500] + "..."
        return error_msg
    return "Execution failed — check server logs for details"

# Thread pool for running CrewAI (which is synchronous)
_executor = ThreadPoolExecutor(
    max_workers=settings.max_concurrent_executions,
    thread_name_prefix="crew-exec",
)


def shutdown_executor(wait: bool = False) -> None:
    """Shutdown the thread pool executor. Called during app lifespan shutdown."""
    _executor.shutdown(wait=wait, cancel_futures=True)
    logger.info("Execution thread pool shut down")


class ExecutionError(Exception):
    """Raised when execution fails."""


async def _load_crew_resources(
    session: AsyncSession, crew_name: str, namespace: str = "default"
) -> dict[str, Resource]:
    """Load a crew and all its referenced resources from the database.

    Returns a dict keyed by 'Kind/name' for the ResourceLoader.
    """
    result = await session.execute(
        select(Resource).where(
            Resource.kind == ResourceKind.CREW,
            Resource.name == crew_name,
            Resource.namespace == namespace,
        )
    )
    crew = result.scalar_one_or_none()
    if not crew:
        raise ExecutionError(f"Crew '{crew_name}' not found in namespace '{namespace}'")

    # Load ALL resources in the namespace (simpler than recursive ref resolution)
    result = await session.execute(
        select(Resource).where(Resource.namespace == namespace)
    )
    all_resources = result.scalars().all()

    return {f"{r.kind.value}/{r.name}": r for r in all_resources}


async def kickoff(
    session: AsyncSession,
    crew_name: str,
    inputs: dict | None = None,
    namespace: str = "default",
) -> Execution:
    """Start a crew execution.

    Creates an execution record, then runs the crew in a background thread.
    Returns the execution record immediately (status=queued).
    """
    inputs = inputs or {}

    resources = await _load_crew_resources(session, crew_name, namespace)
    crew_key = f"Crew/{crew_name}"
    crew_resource = resources[crew_key]

    execution = Execution(
        crew_name=crew_name,
        crew_namespace=namespace,
        status=ExecutionStatus.QUEUED,
        inputs=inputs,
    )
    session.add(execution)
    # Flush to assign execution.id before creating child ExecutionTask rows.
    await session.flush()

    task_refs = crew_resource.spec.get("tasks", [])
    for i, task_ref in enumerate(task_refs):
        # Extract task name from ref
        task_name = task_ref
        if task_ref.startswith("ref:"):
            parts = task_ref.split("/")
            task_name = parts[-1] if len(parts) > 1 else task_ref

        exec_task = ExecutionTask(
            execution_id=execution.id,
            task_name=task_name,
            order=i,
            status=TaskStatus.PENDING,
        )
        session.add(exec_task)

    await session.commit()

    # Snapshot resource specs for the background thread (detached from session)
    resource_snapshot = {
        key: _snapshot_resource(r) for key, r in resources.items()
    }

    execution_id = execution.id
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        _executor,
        _run_crew_sync,
        execution_id,
        resource_snapshot,
        crew_name,
        inputs,
    )

    # Handle thread pool rejection or unexpected errors
    def _on_thread_error(fut: asyncio.Future) -> None:  # type: ignore[type-arg]
        exc = fut.exception()
        if exc is not None:
            logger.error("Execution %s thread failed: %s", execution_id, exc, exc_info=True)
            error_msg = _sanitize_error(str(exc))
            # Schedule on the main event loop instead of creating a new one
            try:
                asyncio.ensure_future(_mark_failed_async(execution_id, error_msg))
            except RuntimeError:
                # Fallback if no running event loop (shouldn't happen in normal operation)
                _mark_failed_sync(execution_id, error_msg)

    future.add_done_callback(_on_thread_error)

    # Re-fetch with tasks eagerly loaded so callers can access execution.tasks
    loaded = await get_execution(session, execution_id)
    return loaded  # type: ignore[return-value]


def _mark_failed_sync(execution_id: UUID, error: str) -> None:
    """Mark an execution as failed from a synchronous callback."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_mark_failed_async(execution_id, error))
        loop.close()
    except Exception as e:
        logger.error("Failed to mark execution %s as failed: %s", execution_id, e)


async def _mark_failed_async(execution_id: UUID, error: str) -> None:
    """Mark an execution as failed."""
    async with async_session() as session:
        result = await session.execute(
            select(Execution)
            .where(Execution.id == execution_id)
            .with_for_update()
        )
        execution = result.scalar_one_or_none()
        if execution and execution.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
            execution.status = ExecutionStatus.FAILED
            execution.error = error
            execution.completed_at = datetime.now(timezone.utc)
            await session.commit()


def _snapshot_resource(resource: Resource) -> dict:
    """Create a serializable snapshot of a resource for the background thread."""
    return {
        "kind": resource.kind.value,
        "name": resource.name,
        "namespace": resource.namespace,
        "spec": dict(resource.spec) if resource.spec else {},
    }


def _run_crew_sync(
    execution_id: UUID,
    resource_snapshot: dict[str, dict],
    crew_name: str,
    inputs: dict,
) -> None:
    """Run a crew synchronously in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _run_crew_async(execution_id, resource_snapshot, crew_name, inputs)
        )
    finally:
        loop.close()


async def _run_crew_async(
    execution_id: UUID,
    resource_snapshot: dict[str, dict],
    crew_name: str,
    inputs: dict,
) -> None:
    """Run a crew and update the execution record with results."""
    async with async_session() as session:
        execution = await _get_execution_for_update(session, execution_id)
        if not execution:
            logger.error("Execution %s not found when starting run", execution_id)
            return

        if execution.status == ExecutionStatus.CANCELLED:
            logger.info("Execution %s was cancelled before starting", execution_id)
            return

        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.now(timezone.utc)
        await session.commit()

        try:
            mock_resources = {}
            for key, snap in resource_snapshot.items():
                r = Resource()
                r.kind = ResourceKind(snap["kind"])
                r.name = snap["name"]
                r.namespace = snap["namespace"]
                r.spec = snap["spec"]
                mock_resources[key] = r

            langfuse_listener = BlackbeardLangfuseListener(
                execution_id=str(execution_id),
                metadata={"crew_name": crew_name},
            )

            loader = ResourceLoader(mock_resources)
            crew = loader.build_crew(crew_name)

            result = crew.kickoff(inputs=inputs)

            execution = await _get_execution_for_update(session, execution_id)
            if not execution:
                return

            if execution.status == ExecutionStatus.CANCELLED:
                logger.info("Execution %s cancelled during run", execution_id)
                return

            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)

            if hasattr(result, "raw"):
                execution.outputs = {"raw": str(result.raw)}
            elif isinstance(result, str):
                execution.outputs = {"raw": result}
            else:
                execution.outputs = {"raw": str(result)}

            if hasattr(result, "token_usage"):
                usage = result.token_usage
                execution.total_tokens = getattr(usage, "total_tokens", 0) or 0
                execution.prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                execution.completion_tokens = getattr(usage, "completion_tokens", 0) or 0

            if langfuse_listener.trace_id:
                execution.langfuse_trace_id = langfuse_listener.trace_id
                execution.langfuse_trace_url = langfuse_listener.trace_url

            await session.commit()
            logger.info("Execution %s completed successfully", execution_id)

        except Exception as e:
            logger.exception("Execution %s failed: %s", execution_id, e)

            execution = await _get_execution_for_update(session, execution_id)
            if execution and execution.status != ExecutionStatus.CANCELLED:
                execution.status = ExecutionStatus.FAILED
                execution.error = _sanitize_error(str(e))
                execution.completed_at = datetime.now(timezone.utc)
                await session.commit()


async def _get_execution(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution by ID."""
    result = await session.execute(
        select(Execution).where(Execution.id == execution_id)
    )
    return result.scalar_one_or_none()


async def _get_execution_for_update(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution by ID with row lock for status transitions."""
    result = await session.execute(
        select(Execution)
        .where(Execution.id == execution_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_execution(
    session: AsyncSession, execution_id: UUID
) -> Execution | None:
    """Get an execution with its tasks loaded."""
    result = await session.execute(
        select(Execution)
        .options(selectinload(Execution.tasks))
        .where(Execution.id == execution_id)
    )
    return result.scalar_one_or_none()


async def list_executions(
    session: AsyncSession,
    crew_name: str | None = None,
    namespace: str | None = None,
    status: ExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Execution], int]:
    """List executions with optional filters."""
    query = select(Execution)
    count_query = select(func.count(Execution.id))

    if crew_name:
        query = query.where(Execution.crew_name == crew_name)
        count_query = count_query.where(Execution.crew_name == crew_name)

    if namespace:
        query = query.where(Execution.crew_namespace == namespace)
        count_query = count_query.where(Execution.crew_namespace == namespace)

    if status:
        query = query.where(Execution.status == status)
        count_query = count_query.where(Execution.status == status)

    total = (await session.execute(count_query)).scalar() or 0
    query = query.order_by(Execution.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    items = list(result.scalars().all())

    return items, total


async def cancel_execution(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Cancel a queued or running execution."""
    # Lock the row to prevent race conditions with background executor
    result = await session.execute(
        select(Execution)
        .options(selectinload(Execution.tasks))
        .where(Execution.id == execution_id)
        .with_for_update()
    )
    execution = result.scalar_one_or_none()
    if not execution:
        return None

    if execution.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = datetime.now(timezone.utc)
        await session.commit()
    elif execution.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        raise ExecutionError(
            f"Cannot cancel execution in terminal status '{execution.status.value}'"
        )

    return execution
