"""Execution engine: manages crew execution lifecycle.

Handles kickoff, train, test, flow execution, cancellation, status tracking,
background execution, and result storage.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

__all__ = [
    "ExecutionError",
    "ExecutionNotFoundError",
    "cancel_execution",
    "cleanup_orphaned_keys",
    "get_execution",
    "get_execution_status",
    "get_pool_status",
    "kickoff",
    "list_execution_events",
    "list_executions",
    "record_hitl_response",
    "recover_stale_executions",
    "run_flow",
    "shutdown_executor",
    "test_crew",
    "train_crew",
]

from crewai.crews.crew_output import CrewOutput
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import defer, load_only, selectinload

from blackbeard.config import settings
from blackbeard.engine.budget import derive_budget_and_pii as _derive_budget_and_pii
from blackbeard.engine.budget import extract_policy_specs as _extract_policy_specs
from blackbeard.engine.execution_listener import BlackbeardExecutionListener
from blackbeard.engine.flow_runner import call_hook
from blackbeard.engine.flow_runner import run_flow_steps as _run_flow_steps
from blackbeard.engine.loader import ResourceLoader
from blackbeard.kinds import ResourceKind
from blackbeard.logging_config import request_id_var
from blackbeard.models import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTask,
    ExecutionType,
    Resource,
    TaskStatus,
    async_session,
)
from blackbeard.models.database import CONNECT_ARGS, instrument_engine
from blackbeard.resources import parse_ref

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from blackbeard.models.user import User

logger = logging.getLogger(__name__)

_SAFE_ERROR_PREFIXES = (
    *(f"{k.value} '" for k in ResourceKind),
    "Resource '",
    "Kind '",
)

_CREW_RELEVANT_KINDS = (
    ResourceKind.CREW,
    ResourceKind.AGENT,
    ResourceKind.TASK,
    ResourceKind.LLM_CONNECTION,
    ResourceKind.TOOL,
    ResourceKind.KNOWLEDGE_SOURCE,
    ResourceKind.AGENT_POLICY,
    ResourceKind.FLOW,
)

_NAMESPACE_RESOURCE_LIMIT = 500
_MAX_ERROR_LENGTH = 500


def _sanitize_error(error_msg: str) -> str:
    """Return a user-safe error string, redacting internal details and PII."""
    from blackbeard.logging_config import scrub_pii

    if error_msg.startswith(_SAFE_ERROR_PREFIXES):
        sanitized = scrub_pii(error_msg)
        if len(sanitized) > _MAX_ERROR_LENGTH:
            return sanitized[:_MAX_ERROR_LENGTH] + "..."
        return sanitized
    return "Execution failed — check server logs for details"


_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

# Shared database engine and session factory for background executor threads.
# Each thread still creates its own event loop, but they all share one
# connection pool instead of each thread creating a separate engine.
_bg_engine: AsyncEngine | None = None
_bg_session_factory: async_sessionmaker[AsyncSession] | None = None
_bg_engine_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Return the shared executor, creating it on first use (thread-safe)."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=settings.max_concurrent_executions,
                    thread_name_prefix="crew-exec",
                )
    return _executor


def get_pool_status() -> dict[str, object]:
    """Return executor thread pool stats for health/diagnostics."""
    executor = _executor
    if executor is None:
        max_workers = settings.max_concurrent_executions
        return {
            "active_threads": 0,
            "max_workers": max_workers,
            "queued_tasks": 0,
            "saturated": False,
        }
    try:
        active = len(executor._threads)
        queued = executor._work_queue.qsize()
    except AttributeError:
        logger.warning(
            "ThreadPoolExecutor internals unavailable — pool metrics will read 0",
            extra={"event": "pool_status_fallback"},
        )
        active, queued = 0, 0
    max_workers = executor._max_workers
    return {
        "active_threads": active,
        "max_workers": max_workers,
        "queued_tasks": queued,
        "saturated": active >= max_workers and queued > 0,
    }


def _get_bg_engine() -> AsyncEngine:
    """Return the shared background engine, creating it on first use (thread-safe)."""
    global _bg_engine, _bg_session_factory
    if _bg_engine is None:
        with _bg_engine_lock:
            if _bg_engine is None:
                from sqlalchemy.ext.asyncio import (
                    AsyncSession as _AsyncSession,
                )
                from sqlalchemy.ext.asyncio import (
                    async_sessionmaker,
                    create_async_engine,
                )

                bg_pool_size = max(5, settings.max_concurrent_executions + 2)
                bg_max_overflow = bg_pool_size * 2
                engine = create_async_engine(
                    settings.database_url.get_secret_value(),
                    echo=False,
                    pool_size=bg_pool_size,
                    max_overflow=bg_max_overflow,
                    pool_pre_ping=True,
                    pool_timeout=30,
                    pool_recycle=3600,
                    connect_args=CONNECT_ARGS,
                )
                _bg_session_factory = async_sessionmaker(
                    engine, class_=_AsyncSession, expire_on_commit=False
                )
                instrument_engine(engine.sync_engine, label="bg-exec")
                # Publish _bg_engine last: the outer check reads this
                # variable without the lock, so _bg_session_factory must
                # already be visible when another thread sees _bg_engine
                # as non-None.
                _bg_engine = engine
                logger.info(
                    "Shared background DB engine created: pool_size=%d max_overflow=%d",
                    bg_pool_size,
                    bg_max_overflow,
                    extra={
                        "event": "bg_engine_created",
                        "pool_size": bg_pool_size,
                        "max_overflow": bg_max_overflow,
                    },
                )
    return _bg_engine


def shutdown_executor(wait: bool = False) -> None:
    """Shut down the thread pool executor and dispose all background DB engines."""
    global _executor, _bg_engine, _bg_session_factory
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=True)
            _executor = None
    logger.info("Execution thread pool shut down", extra={"event": "executor_shutdown"})

    with _bg_engine_lock:
        bg = _bg_engine
        _bg_engine = None
        _bg_session_factory = None
    if bg is not None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            task = loop.create_task(bg.dispose())
            task.add_done_callback(_log_task_exception)
        else:
            _loop = asyncio.new_event_loop()
            try:
                _loop.run_until_complete(bg.dispose())
            finally:
                _loop.close()
        logger.info("Background DB engine disposed", extra={"event": "bg_engine_disposed"})

    from blackbeard.engine.execution_listener import dispose_sync_engine

    dispose_sync_engine()
    logger.info("Sync DB engine disposed", extra={"event": "sync_engine_disposed"})


class ExecutionError(Exception):
    pass


class ExecutionNotFoundError(ExecutionError):
    """Raised when the crew or execution cannot be found."""


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Log exceptions from fire-and-forget asyncio tasks that would otherwise be silent."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task failed: %s",
            exc,
            exc_info=exc,
            extra={
                "event": "background_task_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
                "task_name": task.get_name(),
            },
        )


async def _load_crew_resources(
    session: AsyncSession,
    crew_name: str,
    namespace: str = "default",
    target_kind: str = "Crew",
) -> dict[str, Resource]:
    """Load crew-relevant resources from the namespace (capped at 500).

    Loads by namespace+kind filter rather than resolving refs recursively.
    Returns a dict keyed by 'Kind/name' for the ResourceLoader.

    Args:
        session: Database session.
        crew_name: Name of the root resource (crew or flow).
        namespace: Resource namespace.
        target_kind: Kind of the root resource (``"Crew"`` or ``"Flow"``).
    """
    result = await session.execute(
        select(Resource)
        .where(Resource.namespace == namespace)
        .where(Resource.kind.in_(_CREW_RELEVANT_KINDS))
        .options(defer(Resource.raw_yaml), defer(Resource.labels))
        .order_by(Resource.kind, Resource.name)
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
    root_key = f"{target_kind}/{crew_name}"
    if root_key not in resources:
        raise ExecutionNotFoundError(
            f"{target_kind} '{crew_name}' not found in namespace '{namespace}'"
        )

    if len(resources) > 100:
        logger.warning(
            "Loaded %d resources for %s '%s' in namespace '%s' — "
            "consider splitting into smaller namespaces for performance",
            len(resources),
            target_kind,
            crew_name,
            namespace,
            extra={
                "event": "large_namespace_load",
                "resource_count": len(resources),
                "crew_name": crew_name,
                "namespace": namespace,
            },
        )

    return resources


def _build_principal_chain(
    user: User | None,
    crew_name: str,
    resources: Mapping[str, Resource | dict[str, Any]],
) -> dict[str, Any]:
    """Build the principal chain for an execution.

    Records the identity context: User (who kicked off) -> Crew -> Agents
    (each with their ServiceAccount).
    """
    chain: dict[str, Any] = {}
    if user is not None:
        chain["user"] = {"id": str(user.id)}
    chain["crew"] = crew_name
    agents: list[dict[str, str]] = []
    for key, r in resources.items():
        if not key.startswith("Agent/"):
            continue
        if isinstance(r, dict):
            spec = r.get("spec", {})
            name = r.get("name", "")
        else:
            spec = r.spec or {}
            name = r.name
        sa = spec.get("serviceAccount", f"sa-{name}")
        agents.append({"name": name, "serviceAccount": sa})
    chain["agents"] = agents
    return chain


async def kickoff(
    session: AsyncSession,
    crew_name: str,
    inputs: dict[str, Any] | None = None,
    namespace: str = "default",
    user: User | None = None,
) -> Execution:
    """Start a crew execution.

    Creates an execution record, then runs the crew in a background thread.
    Returns the execution record immediately (status=queued).
    """
    return await _submit_execution(
        session, crew_name, inputs or {}, namespace, user, ExecutionType.KICKOFF
    )


async def _submit_execution(
    session: AsyncSession,
    crew_name: str,
    inputs: dict[str, Any],
    namespace: str,
    user: User | None,
    execution_type: ExecutionType,
    n_iterations: int | None = None,
    training_file: str | None = None,
) -> Execution:
    """Shared logic for creating and submitting train/test/flow executions."""
    target_kind = "Flow" if execution_type == ExecutionType.FLOW else "Crew"
    resources = await _load_crew_resources(session, crew_name, namespace, target_kind=target_kind)
    crew_key = f"{target_kind}/{crew_name}"
    crew_resource = resources[crew_key]
    principal_chain = _build_principal_chain(user, crew_name, resources)

    execution = Execution(
        crew_name=crew_name,
        crew_namespace=namespace,
        execution_type=execution_type,
        status=ExecutionStatus.QUEUED,
        inputs=inputs,
        n_iterations=n_iterations,
        training_file=training_file,
        initiated_by=user.id if user is not None else None,
        principal_chain=principal_chain,
    )
    session.add(execution)
    await session.flush()

    task_refs = crew_resource.spec.get("tasks", [])
    pool = get_pool_status()
    pool_saturated = pool["saturated"]
    logger.log(
        logging.WARNING if pool_saturated else logging.INFO,
        "%s: execution_id=%s crew=%s namespace=%s n_iterations=%s pool=%d/%d queued=%d",
        execution_type.value.capitalize(),
        execution.id,
        crew_name,
        namespace,
        n_iterations,
        pool["active_threads"],
        pool["max_workers"],
        pool["queued_tasks"],
        extra={
            "event": f"execution_{execution_type.value}",
            "execution_id": str(execution.id),
            "execution_type": execution_type.value,
            "crew_name": crew_name,
            "namespace": namespace,
            "n_iterations": n_iterations,
            "pool_active_threads": pool["active_threads"],
            "pool_max_workers": pool["max_workers"],
            "pool_queued_tasks": pool["queued_tasks"],
            "pool_saturated": pool_saturated,
        },
    )
    if task_refs:
        session.add_all(
            [
                ExecutionTask(
                    execution_id=execution.id,
                    task_name=(ref.name if (ref := parse_ref(task_ref)) else task_ref),
                    order=i,
                    status=TaskStatus.PENDING,
                )
                for i, task_ref in enumerate(task_refs)
            ]
        )

    await session.commit()

    resource_snapshot = _snapshot_crew_resources(resources, crew_name, target_kind=target_kind)

    execution_id = execution.id
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        _get_executor(),
        _run_crew_sync,
        execution_id,
        resource_snapshot,
        crew_name,
        inputs,
        execution_type,
        n_iterations or 1,
        training_file or "training_data.pkl",
    )

    def _on_thread_error(fut: asyncio.Future[None]) -> None:
        exc = fut.exception()
        if exc is not None:
            logger.error(
                "Execution %s thread failed: %s",
                execution_id,
                exc,
                exc_info=exc,
                extra={
                    "event": "execution_thread_failed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
            error_msg = _sanitize_error(str(exc))
            task = loop.create_task(_mark_failed_async(execution_id, error_msg))
            task.add_done_callback(_log_task_exception)

    future.add_done_callback(_on_thread_error)

    loaded = await get_execution(session, execution_id)
    if loaded is None:
        raise ExecutionError(f"Execution {execution_id} not found after {execution_type.value}")
    return loaded


async def train_crew(
    session: AsyncSession,
    crew_name: str,
    inputs: dict[str, Any] | None = None,
    n_iterations: int = 3,
    filename: str = "training_data.pkl",
    namespace: str = "default",
    user: User | None = None,
) -> Execution:
    """Start a crew training run.

    Creates an execution record with type=train, then runs crew.train()
    in a background thread. Returns the execution record immediately (status=queued).
    """
    return await _submit_execution(
        session,
        crew_name,
        inputs or {},
        namespace,
        user,
        ExecutionType.TRAIN,
        n_iterations=n_iterations,
        training_file=filename,
    )


async def test_crew(
    session: AsyncSession,
    crew_name: str,
    inputs: dict[str, Any] | None = None,
    n_iterations: int = 3,
    namespace: str = "default",
    user: User | None = None,
) -> Execution:
    """Start a crew test run.

    Creates an execution record with type=test, then runs crew.test()
    in a background thread. Returns the execution record immediately (status=queued).
    """
    return await _submit_execution(
        session,
        crew_name,
        inputs or {},
        namespace,
        user,
        ExecutionType.TEST,
        n_iterations=n_iterations,
    )


async def run_flow(
    session: AsyncSession,
    flow_name: str,
    inputs: dict[str, Any] | None = None,
    namespace: str = "default",
    user: User | None = None,
) -> Execution:
    """Start a flow execution.

    Loads the Flow resource, resolves all referenced crews, and executes
    each step sequentially. Returns the execution record immediately
    (status=queued).
    """
    return await _submit_execution(
        session,
        flow_name,
        inputs or {},
        namespace,
        user,
        ExecutionType.FLOW,
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
            now = datetime.now(UTC)
            execution.status = ExecutionStatus.FAILED
            execution.error = error
            execution.completed_at = now
            await _fail_pending_tasks(
                session, execution_id, "Execution failed before task started", now
            )
            await session.commit()
        else:
            logger.warning(
                "Execution %s already in terminal state %s, skipping failure update",
                execution_id,
                execution.status.value,
                extra={
                    "event": "execution_already_terminal",
                    "execution_id": str(execution_id),
                    "terminal_status": execution.status.value,
                },
            )


def _snapshot_resource(resource: Resource) -> dict[str, Any]:
    """Snapshot kind/name/namespace/spec for background crew execution."""
    return {
        "kind": resource.kind.value,
        "name": resource.name,
        "namespace": resource.namespace,
        "spec": dict(resource.spec or {}),
    }


_MAX_SNAPSHOT_DEPTH = 20
_MAX_SNAPSHOT_RESOURCES = 200


def _snapshot_crew_resources(
    resources: dict[str, Resource],
    crew_name: str,
    target_kind: str = "Crew",
) -> dict[str, dict[str, Any]]:
    """Snapshot only resources reachable from the root resource via ref resolution.

    Walks crew/flow -> agents/tasks -> tools/llms/knowledge_sources/guardrails/context
    recursively, snapshotting only what the execution actually needs instead of
    the entire namespace (which could be hundreds of resources).
    """
    needed: dict[str, dict[str, Any]] = {}

    def _collect(key: str, depth: int = 0) -> None:
        if key in needed:
            return
        if len(needed) >= _MAX_SNAPSHOT_RESOURCES:
            logger.warning(
                "Snapshot resource limit reached (%d) at key '%s'",
                _MAX_SNAPSHOT_RESOURCES,
                key,
                extra={"event": "snapshot_breadth_limit", "key": key, "count": len(needed)},
            )
            return
        if depth > _MAX_SNAPSHOT_DEPTH:
            logger.warning(
                "Snapshot ref depth limit reached at key '%s' (depth=%d)",
                key,
                depth,
                extra={"event": "snapshot_depth_limit", "key": key, "depth": depth},
            )
            return
        resource = resources.get(key)
        if resource is None:
            logger.warning(
                "Snapshot: referenced resource '%s' not found in namespace — "
                "execution may fail when loader tries to resolve this ref",
                key,
                extra={"event": "snapshot_ref_missing", "key": key, "depth": depth},
            )
            return
        needed[key] = _snapshot_resource(resource)
        spec = resource.spec or {}
        for field in ("agents", "tasks", "tools", "context", "knowledge_sources", "guardrails"):
            for ref_str in spec.get(field, []):
                ref = parse_ref(ref_str)
                if ref:
                    _collect(f"{ref.kind.value}/{ref.name}", depth + 1)
        for field in (
            "agent",
            "llm",
            "manager_llm",
            "manager_agent",
            "default_agent_policy",
            "policy",
        ):
            ref_str = spec.get(field)
            if ref_str and isinstance(ref_str, str):
                ref = parse_ref(ref_str)
                if ref:
                    _collect(f"{ref.kind.value}/{ref.name}", depth + 1)
        # Flow steps reference crews
        for step in spec.get("steps", []):
            crew_ref = step.get("crew") if isinstance(step, dict) else None
            if crew_ref and isinstance(crew_ref, str):
                ref = parse_ref(crew_ref)
                if ref:
                    _collect(f"{ref.kind.value}/{ref.name}", depth + 1)

    _collect(f"{target_kind}/{crew_name}")

    return needed


def _run_crew_sync(
    execution_id: UUID,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    inputs: dict[str, Any],
    execution_type: ExecutionType = ExecutionType.KICKOFF,
    n_iterations: int = 1,
    training_file: str = "training_data.pkl",
) -> None:
    """Run a crew in a dedicated event loop, blocking until completion (for ThreadPoolExecutor)."""
    request_id_var.set(str(execution_id))
    logger.info(
        "Crew thread started: execution_id=%s crew=%s type=%s thread=%s",
        execution_id,
        crew_name,
        execution_type.value,
        threading.current_thread().name,
        extra={
            "event": "crew_thread_started",
            "execution_id": str(execution_id),
            "crew_name": crew_name,
            "execution_type": execution_type.value,
            "thread_name": threading.current_thread().name,
        },
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    thread_session = _thread_session_factory()
    try:
        loop.run_until_complete(
            _run_crew_async(
                execution_id,
                resource_snapshot,
                crew_name,
                inputs,
                thread_session,
                execution_type=execution_type,
                n_iterations=n_iterations,
                training_file=training_file,
            )
        )
    except Exception as exc:
        logger.exception(
            "Crew thread crashed for execution %s: %s",
            execution_id,
            exc,
            extra={
                "event": "crew_thread_crash",
                "execution_id": str(execution_id),
                "crew_name": crew_name,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        )
        raise
    finally:
        # Engine disposal deferred to shutdown_executor (shared across threads).
        loop.close()


def _thread_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory backed by the shared background engine.

    All executor threads share one connection pool and one session factory
    instead of each thread creating its own, which avoids redundant object
    allocation on every execution.

    The shared engine must NOT be disposed per-thread -- ``shutdown_executor``
    handles cleanup at application shutdown.
    """
    _get_bg_engine()
    assert _bg_session_factory is not None
    return _bg_session_factory


def _resolve_eval_llm(
    loader: ResourceLoader,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
) -> str:
    """Resolve an eval LLM model string for crew.test().

    Resolution order: crew's manager_llm → first agent's LLM → 'gpt-4o'.
    """
    crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
    crew_spec = crew_snap.get("spec", {})

    # Prefer manager_llm
    manager_ref = crew_spec.get("manager_llm")
    if manager_ref:
        try:
            llm = loader.build_llm(manager_ref)
            return llm.model
        except Exception:
            logger.warning(
                "Failed to resolve manager_llm '%s' for eval — trying agent LLMs",
                manager_ref,
                exc_info=True,
                extra={
                    "event": "eval_llm_manager_fallback",
                    "crew_name": crew_name,
                    "manager_ref": manager_ref,
                },
            )

    # Fall back to first agent's LLM
    for agent_ref in crew_spec.get("agents", []):
        ref = parse_ref(agent_ref)
        if not ref:
            continue
        agent_snap = resource_snapshot.get(f"Agent/{ref.name}", {})
        agent_spec = agent_snap.get("spec", {})
        llm_ref = agent_spec.get("llm")
        if llm_ref:
            try:
                llm = loader.build_llm(llm_ref)
                return llm.model
            except Exception:
                logger.warning(
                    "Failed to resolve agent LLM '%s' for eval — trying next agent",
                    llm_ref,
                    exc_info=True,
                    extra={
                        "event": "eval_llm_resolve_failed",
                        "llm_ref": llm_ref,
                        "crew_name": crew_name,
                    },
                )
                continue

    # Last resort: use a reasonable default
    logger.info(
        "No eval LLM resolved for crew '%s' — falling back to gpt-4o",
        crew_name,
        extra={
            "event": "eval_llm_default_fallback",
            "crew_name": crew_name,
            "fallback_model": "gpt-4o",
        },
    )
    return "gpt-4o"


async def _run_crew_async(
    execution_id: UUID,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    inputs: dict[str, Any],
    thread_session: async_sessionmaker[AsyncSession],
    execution_type: ExecutionType = ExecutionType.KICKOFF,
    n_iterations: int = 1,
    training_file: str = "training_data.pkl",
) -> None:
    """Run a crew and update the execution record with results."""
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
            "Execution %s running: crew=%s namespace=%s input_keys=%s",
            execution_id,
            crew_name,
            running_namespace,
            sorted(inputs.keys()),
            extra={
                "event": "execution_running",
                "execution_id": str(execution_id),
                "crew_name": crew_name,
                "namespace": running_namespace,
                "input_keys": sorted(inputs.keys()),
            },
        )

        listener: BlackbeardExecutionListener | None = None
        virtual_key: str | None = None
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

            # --- Budget enforcement via LiteLLM virtual keys ---
            virtual_api_key: str | None = None
            policy_specs = _extract_policy_specs(resource_snapshot)
            max_budget, max_tokens, listener_pii_config = _derive_budget_and_pii(
                resource_snapshot, crew_name, policy_specs
            )
            has_budget = max_budget is not None or max_tokens is not None

            if has_budget:
                from blackbeard.litellm.key_manager import (
                    VirtualKeyError,
                    VirtualKeyManager,
                )

                key_mgr = VirtualKeyManager(
                    proxy_url=settings.litellm_proxy_url,
                    master_key=settings.litellm_master_key.get_secret_value(),
                )
                try:
                    key_info = await key_mgr.create_key(
                        name=f"exec-{execution_id}",
                        max_budget=max_budget,
                        max_tokens=max_tokens,
                        duration="4h",
                        metadata={
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                        },
                    )
                    virtual_api_key = key_info["key"]
                    virtual_key = virtual_api_key  # for cleanup in finally

                    execution = await _get_execution_for_update(session, execution_id)
                    if execution:
                        execution.litellm_key = virtual_api_key
                        await session.commit()
                except VirtualKeyError:
                    logger.error(
                        "Failed to create virtual key for execution %s — "
                        "proceeding without budget enforcement",
                        execution_id,
                        exc_info=True,
                        extra={
                            "event": "virtual_key_creation_failed",
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                            "max_budget": max_budget,
                            "max_tokens": max_tokens,
                        },
                    )
                    virtual_api_key = None

            loader = ResourceLoader(mock_resources, api_key=virtual_api_key, policies=policy_specs)

            listener = BlackbeardExecutionListener(
                execution_id=execution_id,
                db_url=settings.database_url.get_secret_value(),
                pii_config=listener_pii_config,
            )

            if execution_type == ExecutionType.FLOW:
                result = _run_flow_steps(loader, resource_snapshot, crew_name, inputs, listener)
            else:
                crew = loader.build_crew(crew_name)
                crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
                crew_spec = crew_snap.get("spec", {})
                hooks = crew_spec.get("hooks", {})

                if execution_type == ExecutionType.TRAIN:
                    crew.train(
                        n_iterations=n_iterations,
                        inputs=inputs,
                        filename=training_file,
                    )
                    result = None
                elif execution_type == ExecutionType.TEST:
                    eval_llm = _resolve_eval_llm(loader, resource_snapshot, crew_name)
                    crew.test(
                        n_iterations=n_iterations,
                        eval_llm=eval_llm,
                        inputs=inputs,
                    )
                    result = None
                else:
                    if hooks.get("before_kickoff"):
                        call_hook(loader, hooks["before_kickoff"], inputs, "before_kickoff")
                    result = crew.kickoff(inputs=inputs)
                    if hooks.get("after_kickoff"):
                        call_hook(loader, hooks["after_kickoff"], result, "after_kickoff")
            listener.flush()

            execution = await _get_execution_for_update(session, execution_id)
            if not execution:
                logger.error(
                    "Execution %s vanished after crew completed — results lost",
                    execution_id,
                    extra={
                        "event": "execution_result_lost",
                        "execution_id": str(execution_id),
                        "crew_name": crew_name,
                    },
                )
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
            elif execution_type == ExecutionType.TRAIN:
                execution.outputs = {
                    "execution_type": "train",
                    "n_iterations": n_iterations,
                    "filename": training_file,
                    "raw": repr(result) if result is not None else None,
                    "result_type": type(result).__name__ if result is not None else "None",
                }
            elif execution_type == ExecutionType.TEST:
                if isinstance(result, dict):
                    execution.outputs = {
                        "execution_type": "test",
                        "n_iterations": n_iterations,
                        "metrics": result,
                    }
                else:
                    execution.outputs = {
                        "execution_type": "test",
                        "n_iterations": n_iterations,
                        "raw": repr(result) if result is not None else None,
                        "result_type": type(result).__name__ if result is not None else "None",
                    }
            else:
                execution.outputs = {"raw": repr(result), "result_type": type(result).__name__}

            # --- PII redaction on outputs ---
            pii_config = listener_pii_config
            if pii_config and pii_config.get("redact_outputs", True) and execution.outputs:
                from blackbeard.pii import redact_dict

                pii_entities = pii_config.get("entities")
                execution.outputs = redact_dict(
                    execution.outputs,
                    entities=pii_entities,
                    config=pii_config,
                )
                logger.info(
                    "PII redaction applied to execution %s outputs",
                    execution_id,
                    extra={
                        "event": "pii_redaction_applied",
                        "execution_id": str(execution_id),
                        "crew_name": crew_name,
                        "target": "outputs",
                    },
                )

            await session.commit()
            duration_s = (
                (execution.completed_at - execution.started_at).total_seconds()
                if execution.started_at and execution.completed_at
                else None
            )
            logger.info(
                "Execution %s completed: crew=%s type=%s tokens=%d duration_s=%.1f",
                execution_id,
                crew_name,
                execution_type.value,
                execution.total_tokens or 0,
                duration_s or 0,
                extra={
                    "event": "execution_completed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "namespace": execution.crew_namespace,
                    "execution_type": execution_type.value,
                    "total_tokens": execution.total_tokens or 0,
                    "prompt_tokens": execution.prompt_tokens or 0,
                    "completion_tokens": execution.completion_tokens or 0,
                    "cost_usd": float(execution.cost_usd) if execution.cost_usd else 0.0,
                    "duration_s": round(duration_s or 0, 1),
                },
            )

        except Exception as e:
            if listener is not None:
                try:
                    listener.flush()
                except Exception as flush_exc:
                    logger.warning(
                        "Listener flush failed during error handling for execution %s: %s",
                        execution_id,
                        flush_exc,
                        exc_info=True,
                        extra={
                            "event": "listener_flush_error_on_failure",
                            "execution_id": str(execution_id),
                            "error_type": type(flush_exc).__name__,
                        },
                    )
            duration_s = (
                (datetime.now(UTC) - execution.started_at).total_seconds()
                if execution is not None and execution.started_at
                else None
            )
            crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
            task_count = len(crew_snap.get("spec", {}).get("tasks", []))
            logger.exception(
                "Execution %s failed: type=%s %s (duration_s=%.1f)",
                execution_id,
                execution_type.value,
                e,
                duration_s or 0,
                extra={
                    "event": "execution_failed",
                    "execution_id": str(execution_id),
                    "crew_name": crew_name,
                    "namespace": running_namespace,
                    "execution_type": execution_type.value,
                    "task_count": task_count,
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:500],
                    "duration_s": round(duration_s, 1) if duration_s else None,
                },
            )

            try:
                execution = await _get_execution_for_update(session, execution_id)
                if execution and execution.status != ExecutionStatus.CANCELLED:
                    now = datetime.now(UTC)
                    execution.status = ExecutionStatus.FAILED
                    execution.error = _sanitize_error(str(e))
                    execution.completed_at = now
                    await _fail_pending_tasks(session, execution_id, "Execution failed", now)
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
                    "Failed to mark execution %s as failed in DB: %s (original error: %s)",
                    execution_id,
                    db_err,
                    e,
                    exc_info=True,
                    extra={
                        "event": "execution_mark_failed_db_error",
                        "execution_id": str(execution_id),
                        "error_type": type(db_err).__name__,
                        "original_error_type": type(e).__name__,
                        "original_error_message": str(e)[:500],
                    },
                )
                raise db_err from e
        finally:
            # --- Virtual key cleanup ---
            # virtual_key is only set when key creation succeeded,
            # which guarantees key_mgr was also created in the same block.
            if virtual_key is not None:
                try:
                    deleted = await key_mgr.delete_key(virtual_key)
                except Exception as key_exc:
                    deleted = False
                    logger.warning(
                        "Virtual key deletion raised for execution %s: %s",
                        execution_id,
                        key_exc,
                        exc_info=True,
                        extra={
                            "event": "virtual_key_delete_exception",
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                            "error_type": type(key_exc).__name__,
                        },
                    )
                if not deleted:
                    logger.warning(
                        "Virtual key cleanup failed for execution %s",
                        execution_id,
                        extra={
                            "event": "virtual_key_cleanup_failed",
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                        },
                    )
                try:
                    exec_row = await _get_execution_for_update(session, execution_id)
                    if exec_row is not None:
                        exec_row.litellm_key = None
                        await session.commit()
                except SQLAlchemyError:
                    logger.warning(
                        "Could not clear litellm_key column for execution %s",
                        execution_id,
                        exc_info=True,
                        extra={
                            "event": "litellm_key_column_clear_failed",
                            "execution_id": str(execution_id),
                        },
                    )


async def _fail_pending_tasks(
    session: AsyncSession,
    execution_id: UUID,
    task_error: str,
    now: datetime,
) -> None:
    """Mark all pending/running tasks as failed for a given execution."""
    await session.execute(
        update(ExecutionTask)
        .where(
            ExecutionTask.execution_id == execution_id,
            ExecutionTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
        .values(
            status=TaskStatus.FAILED,
            error=task_error,
            completed_at=now,
        )
    )


async def _get_execution_for_update(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution by ID with row lock for status transitions."""
    result = await session.execute(
        select(Execution).where(Execution.id == execution_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_execution(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Get an execution with its tasks loaded."""
    result = await session.execute(
        select(Execution)
        .options(selectinload(Execution.tasks), defer(Execution.litellm_key))
        .where(Execution.id == execution_id)
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
    include_tasks: bool = False,
) -> tuple[list[Execution], int]:
    """List executions with optional filters.

    By default, tasks are NOT eagerly loaded to keep list queries fast.
    Pass ``include_tasks=True`` to load tasks (e.g. for detail views).
    """
    filters = []
    if crew_name:
        filters.append(Execution.crew_name == crew_name)
    if namespace:
        filters.append(Execution.crew_namespace == namespace)
    if status:
        filters.append(Execution.status == status)

    query = select(Execution).where(*filters)

    if include_tasks:
        query = query.options(selectinload(Execution.tasks), defer(Execution.litellm_key))
    else:
        query = query.options(
            load_only(
                Execution.id,
                Execution.crew_name,
                Execution.crew_namespace,
                Execution.execution_type,
                Execution.status,
                Execution.n_iterations,
                Execution.training_file,
                Execution.error,
                Execution.total_tokens,
                Execution.prompt_tokens,
                Execution.completion_tokens,
                Execution.cost_usd,
                Execution.initiated_by,
                Execution.principal_chain,
                Execution.created_at,
                Execution.started_at,
                Execution.completed_at,
            )
        )

    query = (
        query.order_by(Execution.created_at.desc(), Execution.id.desc()).limit(limit).offset(offset)
    )
    result = await session.execute(query)
    items = list(result.scalars().all())

    if len(items) < limit and (len(items) > 0 or offset == 0):
        total = offset + len(items)
    else:
        count_query = select(func.count(Execution.id)).where(*filters)
        total = (await session.execute(count_query)).scalar_one()

    return items, total


async def list_execution_events(
    session: AsyncSession,
    execution_id: UUID,
    after: int = -1,
    limit: int = 200,
) -> list[ExecutionEvent]:
    """List execution events after a given sequence number."""
    result = await session.execute(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.sequence > after)
        .order_by(ExecutionEvent.sequence)
        .limit(limit)
    )
    return list(result.scalars())


async def record_hitl_response(
    session: AsyncSession,
    execution_id: UUID,
    response: str,
    feedback: str | None = None,
) -> ExecutionEvent:
    """Record a human-in-the-loop response as an execution event.

    The response is stored as an ``hitl_response`` event that the execution
    listener or CrewAI human_input callback can pick up. For MVP, the
    frontend polls for ``hitl_request`` events and submits responses via
    this function.
    """
    event_data: dict[str, Any] = {"response": response}
    if feedback is not None:
        event_data["feedback"] = feedback

    # Retry loop: the execution listener thread may insert events concurrently,
    # causing sequence collisions on the unique constraint.
    max_attempts = 3
    for attempt in range(max_attempts):
        result = await session.execute(
            select(func.coalesce(func.max(ExecutionEvent.sequence), -1)).where(
                ExecutionEvent.execution_id == execution_id
            )
        )
        max_seq = result.scalar() or -1
        next_seq = max_seq + 1

        event = ExecutionEvent(
            execution_id=execution_id,
            sequence=next_seq,
            event_type="hitl_response",
            timestamp=datetime.now(UTC),
            data=event_data,
        )
        try:
            async with session.begin_nested():
                session.add(event)
                await session.flush()
            break
        except IntegrityError:
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(0.05 * (2**attempt))
            logger.info(
                "HITL response sequence collision for execution %s (attempt %d/%d), retrying",
                execution_id,
                attempt + 1,
                max_attempts,
                extra={
                    "event": "hitl_sequence_collision",
                    "execution_id": str(execution_id),
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                },
            )

    logger.info(
        "HITL response recorded: execution_id=%s seq=%d",
        execution_id,
        next_seq,
        extra={
            "event": "hitl_response_recorded",
            "execution_id": str(execution_id),
            "sequence": next_seq,
        },
    )
    return event


async def cancel_execution(session: AsyncSession, execution_id: UUID) -> Execution | None:
    """Cancel a queued or running execution.

    Does NOT commit — the caller is responsible for committing so that
    the cancellation and any audit log entry are in the same transaction.
    """
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
        now = datetime.now(UTC)
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = now
        for task in execution.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.FAILED
                task.error = "Execution cancelled"
                task.completed_at = now
        await session.flush()
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


async def cleanup_orphaned_keys() -> int:
    """Delete LiteLLM virtual keys from crashed executions.

    Called during app startup.  Finds executions that were in 'running' or
    'queued' status (interrupted by crash) and still have a ``litellm_key``
    set, then deletes those keys from the LiteLLM proxy.

    Returns the number of keys deleted.
    """
    from blackbeard.litellm.key_manager import VirtualKeyManager

    keys_deleted = 0
    key_mgr = VirtualKeyManager(
        proxy_url=settings.litellm_proxy_url,
        master_key=settings.litellm_master_key.get_secret_value(),
    )
    async with async_session() as session:
        stale = await session.execute(
            select(Execution)
            .options(load_only(Execution.id, Execution.litellm_key))
            .where(
                Execution.status.in_([ExecutionStatus.QUEUED, ExecutionStatus.RUNNING]),
                Execution.litellm_key.isnot(None),
            )
            .limit(1000)
        )
        stale_list = list(stale.scalars())

    async def _delete_one(execution: Execution) -> bool:
        try:
            deleted = await key_mgr.delete_key(execution.litellm_key)
            if deleted:
                logger.info(
                    "Orphaned virtual key deleted for execution %s",
                    execution.id,
                    extra={
                        "event": "orphaned_key_deleted",
                        "execution_id": str(execution.id),
                    },
                )
                return True
            logger.warning(
                "Failed to delete orphaned virtual key for execution %s",
                execution.id,
                extra={
                    "event": "orphaned_key_delete_failed",
                    "execution_id": str(execution.id),
                },
            )
        except Exception as del_exc:
            logger.warning(
                "Error deleting orphaned virtual key for execution %s: %s",
                execution.id,
                del_exc,
                exc_info=True,
                extra={
                    "event": "orphaned_key_delete_error",
                    "execution_id": str(execution.id),
                    "error_type": type(del_exc).__name__,
                },
            )
        return False

    if stale_list:
        results = await asyncio.gather(
            *(_delete_one(e) for e in stale_list), return_exceptions=True
        )
        keys_deleted = sum(1 for r in results if r is True)

    if keys_deleted > 0:
        logger.info(
            "Cleaned up %d orphaned virtual keys on startup",
            keys_deleted,
            extra={
                "event": "orphaned_keys_cleanup",
                "keys_deleted": keys_deleted,
            },
        )

    return keys_deleted


async def recover_stale_executions() -> int:
    """Mark any QUEUED or RUNNING executions as FAILED on startup.

    After a crash or restart, in-flight executions cannot resume because the
    background threads and their event loops are gone.  This function should
    be called once during application startup (before accepting traffic) to
    clean up stale rows so users see a clear failure rather than an execution
    that is stuck forever.

    Also cleans up orphaned LiteLLM virtual keys from crashed executions
    before marking them as failed (so the key reference is still available
    for lookup).

    Returns the number of executions recovered.
    """
    # Clean up orphaned virtual keys before marking executions as failed
    try:
        await cleanup_orphaned_keys()
    except Exception:
        logger.warning(
            "Orphaned key cleanup failed — continuing with stale execution recovery",
            exc_info=True,
            extra={"event": "orphaned_key_cleanup_error"},
        )

    now = datetime.now(UTC)
    async with async_session() as session:
        result = await session.execute(
            update(Execution)
            .where(Execution.status.in_([ExecutionStatus.QUEUED, ExecutionStatus.RUNNING]))
            .values(
                status=ExecutionStatus.FAILED,
                error="Execution interrupted by server restart",
                completed_at=now,
                litellm_key=None,
            )
            .returning(Execution.id)
        )
        recovered_ids = list(result.scalars())

        if recovered_ids:
            await session.execute(
                update(ExecutionTask)
                .where(
                    ExecutionTask.execution_id.in_(recovered_ids),
                    ExecutionTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
                )
                .values(
                    status=TaskStatus.FAILED,
                    error="Interrupted by server restart",
                    completed_at=now,
                )
            )

        await session.commit()

    count = len(recovered_ids)
    if count > 0:
        logger.warning(
            "Recovered %d stale executions on startup: %s",
            count,
            [str(eid) for eid in recovered_ids[:10]],
            extra={
                "event": "stale_executions_recovered",
                "count": count,
                "execution_ids": [str(eid) for eid in recovered_ids[:10]],
            },
        )
    else:
        logger.info(
            "No stale executions found on startup",
            extra={"event": "stale_executions_check", "count": 0},
        )
    return count
