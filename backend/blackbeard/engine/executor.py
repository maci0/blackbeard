"""Execution engine: manages crew execution lifecycle.

Handles kickoff, status tracking, background execution, and result storage.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from crewai.crews.crew_output import CrewOutput
from sqlalchemy import func, select
from sqlalchemy.orm import defer, selectinload

from blackbeard.config import settings
from blackbeard.engine.loader import ResourceLoader
from blackbeard.kinds import ResourceKind
from blackbeard.langfuse import BlackbeardLangfuseListener, get_langfuse
from blackbeard.models import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionStatus,
    ExecutionTask,
    Resource,
    TaskStatus,
    async_session,
)
from blackbeard.resources.refs import parse_ref

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SAFE_ERROR_PREFIXES = ("Crew '", "Agent '", "Task '", "Tool '", "Resource '", "Kind '")

_CREW_RELEVANT_KINDS = (
    ResourceKind.CREW,
    ResourceKind.AGENT,
    ResourceKind.TASK,
    ResourceKind.LLM_CONNECTION,
    ResourceKind.TOOL,
)

_NAMESPACE_RESOURCE_LIMIT = 500


def _sanitize_error(error_msg: str) -> str:
    """Return a user-safe error string, redacting internal details."""
    if error_msg.startswith(_SAFE_ERROR_PREFIXES):
        if len(error_msg) > 500:
            return error_msg[:500] + "..."
        return error_msg
    return "Execution failed — check server logs for details"


# Each crew run gets its own thread + event loop to avoid blocking the main async loop
_executor = ThreadPoolExecutor(
    max_workers=settings.max_concurrent_executions,
    thread_name_prefix="crew-exec",
)


def shutdown_executor(wait: bool = False) -> None:
    """Shutdown the thread pool executor, cancelling pending futures."""
    _executor.shutdown(wait=wait, cancel_futures=True)
    logger.info("Execution thread pool shut down")


class ExecutionError(Exception):
    pass


async def _load_crew_resources(
    session: AsyncSession, crew_name: str, namespace: str = "default"
) -> dict[str, Resource]:
    """Load all resources in the crew's namespace from the database.

    Loads the entire namespace rather than resolving refs recursively.
    Returns a dict keyed by 'Kind/name' for the ResourceLoader.
    """
    result = await session.execute(
        select(Resource)
        .where(Resource.namespace == namespace)
        .where(Resource.kind.in_(_CREW_RELEVANT_KINDS))
        .options(defer(Resource.raw_yaml), defer(Resource.labels))
        .limit(_NAMESPACE_RESOURCE_LIMIT + 1)
    )

    rows = list(result.scalars())
    if len(rows) > _NAMESPACE_RESOURCE_LIMIT:
        logger.warning(
            "Namespace '%s' has >%d resources; some refs may not resolve",
            namespace,
            _NAMESPACE_RESOURCE_LIMIT,
            extra={
                "event": "namespace_resource_limit",
                "namespace": namespace,
                "limit": _NAMESPACE_RESOURCE_LIMIT,
            },
        )
        rows = rows[:_NAMESPACE_RESOURCE_LIMIT]

    resources = {f"{r.kind.value}/{r.name}": r for r in rows}
    if f"Crew/{crew_name}" not in resources:
        raise ExecutionError(f"Crew '{crew_name}' not found in namespace '{namespace}'")

    return resources


async def kickoff(
    session: AsyncSession,
    crew_name: str,
    inputs: dict[str, Any] | None = None,
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

    logger.info(
        "Kickoff: execution_id=%s crew=%s namespace=%s input_keys=%s",
        execution.id,
        crew_name,
        namespace,
        sorted(inputs.keys()),
        extra={
            "event": "execution_kickoff",
            "execution_id": str(execution.id),
            "crew_name": crew_name,
            "namespace": namespace,
        },
    )

    task_refs = crew_resource.spec.get("tasks", [])
    for i, task_ref in enumerate(task_refs):
        ref = parse_ref(task_ref)
        task_name = ref.name if ref else task_ref

        exec_task = ExecutionTask(
            execution_id=execution.id,
            task_name=task_name,
            order=i,
            status=TaskStatus.PENDING,
        )
        session.add(exec_task)

    await session.commit()

    # Snapshot resource specs for the background thread (detached from session)
    resource_snapshot = {key: _snapshot_resource(r) for key, r in resources.items()}

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

    def _on_thread_error(fut: asyncio.Future) -> None:  # type: ignore[type-arg]
        exc = fut.exception()
        if exc is not None:
            logger.error(
                "Execution %s thread failed: %s",
                execution_id,
                exc,
                exc_info=True,
                extra={
                    "event": "execution_thread_failed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "error_type": type(exc).__name__,
                },
            )
            error_msg = _sanitize_error(str(exc))
            # This callback runs on the main event loop thread, so we can
            # schedule the async mark-failed coroutine directly.
            loop.create_task(_mark_failed_async(execution_id, error_msg))  # noqa: RUF006

    future.add_done_callback(_on_thread_error)

    loaded = await get_execution(session, execution_id)
    if loaded is None:
        raise ExecutionError(f"Execution {execution_id} not found after kickoff")
    return loaded


def _mark_failed_sync(execution_id: UUID, error: str) -> None:
    """Mark an execution as failed from a synchronous callback."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_mark_failed_async(execution_id, error))
        loop.close()
    except Exception as e:
        logger.error(
            "Failed to mark execution %s as failed: %s",
            execution_id,
            e,
            exc_info=True,
            extra={
                "event": "execution_mark_failed_error",
                "execution_id": str(execution_id),
                "error_type": type(e).__name__,
            },
        )


async def _mark_failed_async(execution_id: UUID, error: str) -> None:
    """Mark an execution as failed."""
    async with async_session() as session:
        result = await session.execute(
            select(Execution).where(Execution.id == execution_id).with_for_update()
        )
        execution = result.scalar_one_or_none()
        if not execution:
            logger.warning(
                "Cannot mark execution %s as failed: not found",
                execution_id,
                extra={"event": "execution_mark_failed_missing", "execution_id": str(execution_id)},
            )
            return
        if execution.status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
            execution.status = ExecutionStatus.FAILED
            execution.error = error
            execution.completed_at = datetime.now(UTC)
            await session.commit()
        else:
            logger.debug(
                "Execution %s already in terminal state %s, skipping failure update",
                execution_id,
                execution.status.value,
            )


def _snapshot_resource(resource: Resource) -> dict[str, Any]:
    """Snapshot kind/name/namespace/spec for background crew execution.

    Excludes raw_yaml and labels.
    """
    return {
        "kind": resource.kind.value,
        "name": resource.name,
        "namespace": resource.namespace,
        "spec": dict(resource.spec) if resource.spec else {},
    }


def _run_crew_sync(
    execution_id: UUID,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    inputs: dict[str, Any],
) -> None:
    """Run a crew in a dedicated event loop, blocking until completion (for ThreadPoolExecutor)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_crew_async(execution_id, resource_snapshot, crew_name, inputs))
    except Exception:
        logger.exception(
            "Crew thread crashed for execution %s",
            execution_id,
            extra={"event": "crew_thread_crash", "execution_id": str(execution_id)},
        )
        raise
    finally:
        loop.close()


def _thread_session_factory() -> Any:
    """Create a fresh engine+session factory for the current thread's event loop.

    asyncpg connections are bound to the event loop that created them, so the
    executor thread (which runs its own loop) cannot share the main engine.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession as _AsyncSession,
    )
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker as asm,
    )
    from sqlalchemy.ext.asyncio import (
        create_async_engine as cae,
    )

    thread_engine = cae(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
        pool_timeout=30,
    )
    return asm(thread_engine, class_=_AsyncSession, expire_on_commit=False)


async def _run_crew_async(
    execution_id: UUID,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    inputs: dict[str, Any],
) -> None:
    """Run a crew and update the execution record with results."""
    thread_session = _thread_session_factory()
    async with thread_session() as session:
        execution = await _get_execution_for_update(session, execution_id)
        if not execution:
            logger.error(
                "Execution %s not found when starting run",
                execution_id,
                extra={
                    "event": "execution_not_found",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                },
            )
            return

        if execution.status == ExecutionStatus.CANCELLED:
            logger.info(
                "Execution %s was cancelled before starting",
                execution_id,
                extra={
                    "event": "execution_cancelled_before_start",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                },
            )
            return

        running_namespace = execution.crew_namespace
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "Execution %s running: crew=%s",
            execution_id,
            crew_name,
            extra={
                "event": "execution_running",
                "execution_id": str(execution_id),
                "crew_name": crew_name,
                "namespace": running_namespace,
            },
        )

        try:
            mock_resources = {
                key: Resource(
                    kind=ResourceKind(snap["kind"]),
                    name=snap["name"],
                    namespace=snap["namespace"],
                    spec=snap["spec"],
                )
                for key, snap in resource_snapshot.items()
            }

            langfuse_listener = None
            if get_langfuse() is not None:
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
                logger.info(
                    "Execution %s cancelled during run",
                    execution_id,
                    extra={
                        "event": "execution_cancelled_during_run",
                        "execution_id": str(execution_id),
                        "crew_name": crew_name,
                    },
                )
                return

            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(UTC)

            if isinstance(result, CrewOutput):
                execution.outputs = {"raw": result.raw}
                usage = result.token_usage
                execution.total_tokens = usage.total_tokens
                execution.prompt_tokens = usage.prompt_tokens
                execution.completion_tokens = usage.completion_tokens
            else:
                execution.outputs = {"raw": repr(result), "result_type": type(result).__name__}

            if langfuse_listener and langfuse_listener.trace_id:
                execution.langfuse_trace_id = langfuse_listener.trace_id
                execution.langfuse_trace_url = langfuse_listener.trace_url

            await session.commit()
            duration_s = (
                (execution.completed_at - execution.started_at).total_seconds()
                if execution.started_at and execution.completed_at
                else None
            )
            logger.info(
                "Execution %s completed: crew=%s tokens=%d duration_s=%.1f",
                execution_id,
                crew_name,
                execution.total_tokens or 0,
                duration_s or 0,
                extra={
                    "event": "execution_completed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "namespace": execution.crew_namespace,
                    "total_tokens": execution.total_tokens or 0,
                    "prompt_tokens": execution.prompt_tokens or 0,
                    "completion_tokens": execution.completion_tokens or 0,
                    "cost_usd": float(execution.cost_usd) if execution.cost_usd else 0.0,
                    "duration_s": round(duration_s or 0, 1),
                },
            )

        except Exception as e:
            duration_s = (
                (datetime.now(UTC) - execution.started_at).total_seconds()
                if execution is not None and execution.started_at
                else None
            )
            logger.exception(
                "Execution %s failed: %s (duration_s=%.1f)",
                execution_id,
                e,
                duration_s or 0,
                extra={
                    "event": "execution_failed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "namespace": running_namespace,
                    "error_type": type(e).__name__,
                    "duration_s": round(duration_s, 1) if duration_s else None,
                },
            )

            try:
                execution = await _get_execution_for_update(session, execution_id)
                if execution and execution.status != ExecutionStatus.CANCELLED:
                    execution.status = ExecutionStatus.FAILED
                    execution.error = _sanitize_error(str(e))
                    execution.completed_at = datetime.now(UTC)
                    await session.commit()
                    logger.info(
                        "Execution %s marked as failed in DB",
                        execution_id,
                        extra={
                            "event": "execution_marked_failed",
                            "execution_id": str(execution_id),
                        },
                    )
            except Exception as db_err:
                logger.error(
                    "Failed to mark execution %s as failed in DB: %s",
                    execution_id,
                    db_err,
                    exc_info=True,
                    extra={
                        "event": "execution_mark_failed_db_error",
                        "execution_id": str(execution_id),
                        "error_type": type(db_err).__name__,
                    },
                )
                raise


async def _get_execution_for_update(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution by ID with row lock for status transitions."""
    result = await session.execute(
        select(Execution).where(Execution.id == execution_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_execution(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution with its tasks loaded."""
    result = await session.execute(
        select(Execution).options(selectinload(Execution.tasks)).where(Execution.id == execution_id)
    )
    return result.scalar_one_or_none()


async def get_execution_status(session: AsyncSession, execution_id: UUID) -> ExecutionStatus | None:
    """Get only the execution status — lightweight query for polling."""
    result = await session.execute(select(Execution.status).where(Execution.id == execution_id))
    return result.scalar_one_or_none()


async def list_executions(
    session: AsyncSession,
    crew_name: str | None = None,
    namespace: str | None = None,
    status: ExecutionStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Execution], int]:
    """List executions with optional filters."""
    filters = []
    if crew_name:
        filters.append(Execution.crew_name == crew_name)
    if namespace:
        filters.append(Execution.crew_namespace == namespace)
    if status:
        filters.append(Execution.status == status)

    query = select(Execution).where(*filters)
    count_query = select(func.count(Execution.id)).where(*filters)

    query = (
        query.options(selectinload(Execution.tasks))
        .order_by(Execution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    items = list(result.scalars().all())

    if not offset and len(items) < limit:
        total = len(items)
    else:
        total = (await session.execute(count_query)).scalar() or 0

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
        prev_status = execution.status.value
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "Execution %s cancelled: crew=%s previous_status=%s",
            execution_id,
            execution.crew_name,
            prev_status,
            extra={
                "event": "execution_cancelled",
                "execution_id": str(execution_id),
                "crew_name": execution.crew_name,
                "namespace": execution.crew_namespace,
                "previous_status": prev_status,
            },
        )
    elif execution.status in TERMINAL_STATUSES:
        raise ExecutionError(
            f"Cannot cancel execution in terminal status '{execution.status.value}'"
        )

    return execution
