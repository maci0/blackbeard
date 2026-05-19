"""Execution engine: manages crew execution lifecycle.

Handles kickoff, status tracking, background execution, and result storage.
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer, load_only, selectinload

from blackbeard.config import settings
from blackbeard.engine.execution_listener import BlackbeardExecutionListener
from blackbeard.engine.loader import LoaderError, ResourceLoader
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
from blackbeard.models.database import CONNECT_ARGS
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
    """Return a user-safe error string, redacting internal details."""
    if error_msg.startswith(_SAFE_ERROR_PREFIXES):
        if len(error_msg) > _MAX_ERROR_LENGTH:
            return error_msg[:_MAX_ERROR_LENGTH] + "..."
        return error_msg
    return "Execution failed — check server logs for details"


def _extract_policy_specs(
    resource_snapshot: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Extract AgentPolicy specs from a resource snapshot (policy name → spec)."""
    return {
        snap["name"]: snap.get("spec", {})
        for snap in resource_snapshot.values()
        if snap.get("kind") == "AgentPolicy"
    }


def _derive_budget_limits(
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    policy_specs: dict[str, dict[str, Any]] | None = None,
) -> tuple[float | None, int | None]:
    """Derive the most restrictive budget limits from applicable policies.

    Scans the crew's agents for policy refs (agent-level then crew-level
    default) and returns the minimum ``max_usd`` and ``max_tokens`` across
    all resolved policies.

    Returns:
        ``(max_budget_usd, max_tokens)`` — either may be ``None`` if no
        policy defines that limit.
    """
    from blackbeard.engine.policy import resolve_policy

    crew_snap = resource_snapshot.get(f"Crew/{crew_name}", {})
    crew_spec = crew_snap.get("spec", {})

    if policy_specs is None:
        policy_specs = _extract_policy_specs(resource_snapshot)

    budgets: list[float] = []
    token_limits: list[int] = []

    # Resolve policy for each agent referenced by the crew
    agent_refs = crew_spec.get("agents", [])
    for agent_ref in agent_refs:
        ref = parse_ref(agent_ref)
        if not ref:
            continue
        agent_snap = resource_snapshot.get(f"Agent/{ref.name}", {})
        agent_spec = agent_snap.get("spec", {})

        policy = resolve_policy(agent_spec, crew_spec, policy_specs)
        if policy.max_budget_usd is not None:
            budgets.append(policy.max_budget_usd)
        if policy.max_tokens is not None:
            token_limits.append(policy.max_tokens)

    max_budget = min(budgets) if budgets else None
    max_tokens = min(token_limits) if token_limits else None

    if max_budget is not None or max_tokens is not None:
        logger.info(
            "Budget limits derived for crew '%s': max_usd=%s max_tokens=%s",
            crew_name,
            max_budget,
            max_tokens,
            extra={
                "event": "budget_limits_derived",
                "crew_name": crew_name,
                "max_budget_usd": max_budget,
                "max_tokens": max_tokens,
                "agent_count": len(agent_refs),
                "policy_count": len(budgets) + len(token_limits),
            },
        )

    return max_budget, max_tokens


_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


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


def shutdown_executor(wait: bool = False) -> None:
    """Shutdown the thread pool executor and dispose the sync DB engine."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=True)
            _executor = None
    logger.info("Execution thread pool shut down", extra={"event": "executor_shutdown"})
    from blackbeard.engine.execution_listener import dispose_sync_engine

    dispose_sync_engine()
    logger.info("Sync DB engine disposed", extra={"event": "sync_engine_disposed"})


class ExecutionError(Exception):
    pass


class ExecutionNotFoundError(ExecutionError):
    """Raised when the crew or execution cannot be found."""


def _log_task_exception(task: asyncio.Task) -> None:  # type: ignore[type-arg]
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
    session: AsyncSession, crew_name: str, namespace: str = "default"
) -> dict[str, Resource]:
    """Load crew-relevant resources from the namespace (capped at 500).

    Loads by namespace+kind filter rather than resolving refs recursively.
    Returns a dict keyed by 'Kind/name' for the ResourceLoader.
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
    if f"Crew/{crew_name}" not in resources:
        raise ExecutionNotFoundError(f"Crew '{crew_name}' not found in namespace '{namespace}'")

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
        chain["user"] = {"id": str(user.id), "email": user.email}
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
    inputs = inputs or {}

    resources = await _load_crew_resources(session, crew_name, namespace)
    crew_key = f"Crew/{crew_name}"
    crew_resource = resources[crew_key]

    principal_chain = _build_principal_chain(user, crew_name, resources)

    execution = Execution(
        crew_name=crew_name,
        crew_namespace=namespace,
        status=ExecutionStatus.QUEUED,
        inputs=inputs,
        initiated_by=user.id if user is not None else None,
        principal_chain=principal_chain,
    )
    session.add(execution)
    # Flush to assign execution.id before creating child ExecutionTask rows.
    await session.flush()

    task_refs = crew_resource.spec.get("tasks", [])
    pool = get_pool_status()
    pool_saturated = pool["saturated"]
    logger.log(
        logging.WARNING if pool_saturated else logging.INFO,
        "Kickoff: execution_id=%s crew=%s namespace=%s tasks=%d input_keys=%s pool=%d/%d queued=%d",
        execution.id,
        crew_name,
        namespace,
        len(task_refs),
        sorted(inputs.keys()),
        pool["active_threads"],
        pool["max_workers"],
        pool["queued_tasks"],
        extra={
            "event": "execution_kickoff",
            "execution_id": str(execution.id),
            "crew_name": crew_name,
            "namespace": namespace,
            "task_count": len(task_refs),
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

    resource_snapshot = {key: _snapshot_resource(r) for key, r in resources.items()}

    execution_id = execution.id
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        _get_executor(),
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
                    "error_message": str(exc)[:500],
                },
            )
            error_msg = _sanitize_error(str(exc))
            # This callback runs on the main event loop thread, so we can
            # schedule the async mark-failed coroutine directly.
            task = loop.create_task(_mark_failed_async(execution_id, error_msg))
            task.add_done_callback(_log_task_exception)

    future.add_done_callback(_on_thread_error)

    loaded = await get_execution(session, execution_id)
    if loaded is None:
        raise ExecutionError(f"Execution {execution_id} not found after kickoff")
    return loaded


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
    """Shared logic for creating and submitting train/test executions."""
    resources = await _load_crew_resources(session, crew_name, namespace)
    crew_key = f"Crew/{crew_name}"
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

    resource_snapshot = {key: _snapshot_resource(r) for key, r in resources.items()}

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
    each step sequentially (or by dependency graph). Returns the execution
    record immediately (status=queued).
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
    """Snapshot kind/name/namespace/spec for background crew execution."""
    return {
        "kind": resource.kind.value,
        "name": resource.name,
        "namespace": resource.namespace,
        "spec": dict(resource.spec or {}),
    }


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
    thread_session, thread_engine = _thread_session_factory()
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
        loop.run_until_complete(thread_engine.dispose())
        loop.close()


def _thread_session_factory() -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    """Create a fresh engine+session factory for the current thread's event loop.

    asyncpg connections are bound to the event loop that created them, so the
    executor thread (which runs its own loop) cannot share the main engine.
    Returns (session_factory, engine) so callers can dispose the engine.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession as _AsyncSession,
    )
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )

    thread_engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_size=1,
        max_overflow=2,
        pool_pre_ping=True,
        pool_timeout=30,
        pool_recycle=3600,
        connect_args=CONNECT_ARGS,
    )
    factory = async_sessionmaker(thread_engine, class_=_AsyncSession, expire_on_commit=False)
    logger.debug(
        "Thread DB pool created: thread=%s pool_size=1 max_overflow=2",
        threading.current_thread().name,
        extra={
            "event": "thread_db_pool_created",
            "thread_name": threading.current_thread().name,
            "pool_size": 1,
            "max_overflow": 2,
        },
    )
    return factory, thread_engine


def _resolve_eval_llm(
    loader: ResourceLoader,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
) -> str:
    """Resolve an eval LLM model string for crew.test().

    Uses the crew's manager_llm if defined, otherwise falls back to
    the first agent's LLM. Returns a model string (e.g. 'gpt-4o').
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
                logger.debug(
                    "Failed to resolve agent LLM '%s' for eval — trying next agent",
                    llm_ref,
                    exc_info=True,
                )
                continue

    # Last resort: use a reasonable default
    return "gpt-4o"


def _run_flow_steps(
    loader: Any,
    resource_snapshot: dict[str, dict[str, Any]],
    flow_name: str,
    inputs: dict[str, Any],
    listener: Any,
) -> Any:
    """Execute a Flow resource by running its steps sequentially.

    Each step of type "crew" builds and kicks off the referenced crew.
    Step outputs are chained: the result of step N is available to step N+1.
    """
    from crewai.crews.crew_output import CrewOutput

    flow_snap = resource_snapshot.get(f"Flow/{flow_name}")
    if not flow_snap:
        raise LoaderError(f"Flow '{flow_name}' not found in resource snapshot")

    flow_spec = flow_snap.get("spec", {})
    steps = flow_spec.get("steps", [])
    step_outputs: dict[str, Any] = {}
    last_result: Any = None

    for step in steps:
        step_name = step.get("name", "unnamed")
        step_type = step.get("type", "crew")

        if step_type == "crew":
            crew_ref = step.get("crew")
            if not crew_ref:
                logger.warning(
                    "Flow step '%s' has no crew ref — skipped",
                    step_name,
                    extra={
                        "event": "flow_step_skipped",
                        "flow_name": flow_name,
                        "step_name": step_name,
                        "reason": "no_crew_ref",
                    },
                )
                continue

            crew = loader.build_crew(crew_ref.split("/")[-1] if "/" in crew_ref else crew_ref)
            step_inputs = {**inputs, **step_outputs}
            result = crew.kickoff(inputs=step_inputs)

            if isinstance(result, CrewOutput):
                step_outputs[step_name] = result.raw
                last_result = result
            else:
                step_outputs[step_name] = str(result) if result else ""
                last_result = result

            logger.info(
                "Flow step '%s' completed (crew=%s)",
                step_name,
                crew_ref,
                extra={
                    "event": "flow_step_completed",
                    "flow_name": flow_name,
                    "step_name": step_name,
                    "crew_ref": crew_ref,
                },
            )

        elif step_type == "function":
            fn_path = step.get("function_path", "")
            if fn_path and ":" in fn_path:
                module_path, fn_name = fn_path.rsplit(":", 1)
                from blackbeard.resources import (
                    ALLOWED_CALLABLE_MODULE_PREFIXES,
                    BLOCKED_CALLABLE_MODULES,
                )

                top_module = module_path.split(".")[0]
                if top_module in BLOCKED_CALLABLE_MODULES:
                    logger.warning(
                        "Flow step '%s' blocked: module '%s' is not allowed",
                        step_name,
                        top_module,
                        extra={
                            "event": "flow_step_blocked",
                            "flow_name": flow_name,
                            "step_name": step_name,
                            "blocked_module": top_module,
                        },
                    )
                    step_outputs[step_name] = "error: blocked module"
                elif not fn_path.startswith(ALLOWED_CALLABLE_MODULE_PREFIXES):
                    logger.warning(
                        "Flow step '%s' blocked: function_path '%s' not in allowlist",
                        step_name,
                        fn_path,
                        extra={
                            "event": "flow_step_blocked",
                            "flow_name": flow_name,
                            "step_name": step_name,
                            "function_path": fn_path,
                        },
                    )
                    step_outputs[step_name] = "error: function not in allowlist"
                else:
                    try:
                        import importlib

                        mod = importlib.import_module(module_path)
                        fn = getattr(mod, fn_name)
                        step_result = fn({**inputs, **step_outputs})
                        step_outputs[step_name] = step_result
                    except Exception as exc:
                        logger.warning(
                            "Flow function step '%s' failed: %s",
                            step_name,
                            exc,
                            exc_info=True,
                            extra={
                                "event": "flow_function_step_failed",
                                "flow_name": flow_name,
                                "step_name": step_name,
                                "function_path": fn_path,
                                "error_type": type(exc).__name__,
                            },
                        )
                        step_outputs[step_name] = "error: step execution failed"

        elif step_type in ("router", "condition"):
            logger.info(
                "Flow step '%s' (type=%s) — routing not yet implemented, continuing",
                step_name,
                step_type,
                extra={
                    "event": "flow_step_skipped",
                    "flow_name": flow_name,
                    "step_name": step_name,
                    "step_type": step_type,
                    "reason": "not_implemented",
                },
            )

    return last_result


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
            max_budget, max_tokens = _derive_budget_limits(
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
                        metadata={
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                        },
                    )
                    virtual_api_key = key_info["key"]
                    virtual_key = virtual_api_key  # for cleanup in finally

                    # Persist the key reference on the execution row
                    execution = await _get_execution_for_update(session, execution_id)
                    if execution:
                        execution.litellm_key = virtual_api_key
                        await session.commit()
                except VirtualKeyError:
                    logger.warning(
                        "Failed to create virtual key for execution %s — "
                        "proceeding without budget enforcement",
                        execution_id,
                        exc_info=True,
                        extra={
                            "event": "virtual_key_creation_failed",
                            "execution_id": str(execution_id),
                            "crew_name": crew_name,
                        },
                    )
                    virtual_api_key = None

            loader = ResourceLoader(
                mock_resources, api_key=virtual_api_key, policies=policy_specs
            )
            crew = loader.build_crew(crew_name)

            # Wire up execution event listener for real-time streaming.
            listener = BlackbeardExecutionListener(
                execution_id=execution_id,
                db_url=settings.database_url.get_secret_value(),
            )

            if execution_type == ExecutionType.FLOW:
                result = _run_flow_steps(
                    loader, resource_snapshot, crew_name, inputs, listener
                )
            elif execution_type == ExecutionType.TRAIN:
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
                result = crew.kickoff(inputs=inputs)
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
                # crew.test() returns test metrics; store them in outputs
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
                listener.flush()
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
        finally:
            # --- Virtual key cleanup ---
            if virtual_key is not None:
                from blackbeard.litellm.key_manager import VirtualKeyManager

                key_mgr = VirtualKeyManager(
                    proxy_url=settings.litellm_proxy_url,
                    master_key=settings.litellm_master_key.get_secret_value(),
                )
                deleted = await key_mgr.delete_key(virtual_key)
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
        query = query.options(selectinload(Execution.tasks))
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
        total = (await session.execute(count_query)).scalar() or 0

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
        now = datetime.now(UTC)
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = now
        for task in execution.tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.FAILED
                task.error = "Execution cancelled"
                task.completed_at = now
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


async def recover_stale_executions() -> int:
    """Mark any QUEUED or RUNNING executions as FAILED on startup.

    After a crash or restart, in-flight executions cannot resume because the
    background threads and their event loops are gone.  This function should
    be called once during application startup (before accepting traffic) to
    clean up stale rows so users see a clear failure rather than an execution
    that is stuck forever.

    Returns the number of executions recovered.
    """
    now = datetime.now(UTC)
    async with async_session() as session:
        result = await session.execute(
            update(Execution)
            .where(Execution.status.in_([ExecutionStatus.QUEUED, ExecutionStatus.RUNNING]))
            .values(
                status=ExecutionStatus.FAILED,
                error="Execution interrupted by server restart",
                completed_at=now,
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
