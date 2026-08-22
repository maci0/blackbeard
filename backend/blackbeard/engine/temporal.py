"""Optional Temporal workflow engine for crew execution.

When the ``temporalio`` package is installed and ``TEMPORAL_HOST`` is set,
crew executions are dispatched as Temporal workflows instead of running in
the local ThreadPoolExecutor.  When either condition is not met, this module
degrades gracefully and all public functions become no-ops or raise clear
errors.

The module is safe to import regardless of whether ``temporalio`` is
installed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from blackbeard.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from blackbeard.models import ExecutionType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional imports: graceful degradation when temporalio is not installed
# ---------------------------------------------------------------------------

TEMPORAL_AVAILABLE: bool

try:
    from temporalio import activity, workflow
    from temporalio.client import Client
    from temporalio.common import RetryPolicy
    from temporalio.worker import Worker

    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Workflow input dataclass (serializable, used by both workflow and activity)
# ---------------------------------------------------------------------------


@dataclass
class CrewExecutionInput:
    """Serializable input for the crew execution workflow."""

    execution_id: str
    resource_snapshot: dict[str, dict[str, Any]]
    crew_name: str
    inputs: dict[str, Any]
    execution_type: str  # ExecutionType.value
    n_iterations: int = 1
    training_file: str = "training_data.pkl"


# ---------------------------------------------------------------------------
# Temporal activity and workflow definitions
#
# These are only defined when temporalio is installed.  The conditional
# block uses runtime decorators from the SDK.  We store references in
# module-level variables so the worker and submission code can use them
# without caring about the conditional import.
# ---------------------------------------------------------------------------

# Activity function reference (set inside the TEMPORAL_AVAILABLE block)
_run_crew_activity: Any = None

# Workflow class reference (set inside the TEMPORAL_AVAILABLE block)
_CrewExecutionWorkflow: Any = None


def _register_temporal_definitions() -> None:
    """Register Temporal workflow and activity definitions.

    Called once at import time when temporalio is available.
    Defined as a function so decorators are applied inside a controlled
    scope rather than at module top level.
    """
    global _run_crew_activity, _CrewExecutionWorkflow

    @activity.defn(name="run_crew")
    async def _activity_impl(payload: CrewExecutionInput) -> dict[str, Any]:
        """Temporal activity that runs a crew execution.

        Reuses the existing ``_run_crew_async`` logic from the executor
        module, running inside a Temporal activity context instead of a
        raw thread.
        """
        from uuid import UUID as _UUID

        from blackbeard.models import ExecutionType as _ExecType

        execution_id = _UUID(payload.execution_id)
        execution_type = _ExecType(payload.execution_type)

        from blackbeard.engine.executor import (
            _run_crew_async,
            _thread_session_factory,
        )

        thread_session = _thread_session_factory()

        activity.logger.info(
            "Running crew activity: execution_id=%s crew=%s type=%s",
            payload.execution_id,
            payload.crew_name,
            payload.execution_type,
        )

        await _run_crew_async(
            execution_id,
            payload.resource_snapshot,
            payload.crew_name,
            payload.inputs,
            thread_session,
            execution_type=execution_type,
            n_iterations=payload.n_iterations,
            training_file=payload.training_file,
        )

        return {"execution_id": payload.execution_id, "status": "completed"}

    @workflow.defn(name="CrewExecution")
    class _WorkflowImpl:
        """Temporal workflow for crew execution.

        Dispatches the crew run as a single activity with configurable
        timeouts and retry policies.  Temporal handles scheduling, retries,
        and visibility out of the box.
        """

        @workflow.run
        async def run(self, payload: CrewExecutionInput) -> dict[str, Any]:
            workflow.logger.info(
                "Starting crew execution workflow: execution_id=%s crew=%s",
                payload.execution_id,
                payload.crew_name,
            )

            timeout_s = settings.temporal_workflow_timeout_s

            result: dict[str, Any] = await workflow.execute_activity(
                _run_crew_activity,
                payload,
                start_to_close_timeout=timedelta(seconds=timeout_s),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=5),
                    maximum_attempts=3,
                    non_retryable_error_types=[
                        "ExecutionNotFoundError",
                        "ExecutionError",
                        "ValueError",
                        "KeyError",
                    ],
                ),
            )

            workflow.logger.info(
                "Crew execution workflow completed: execution_id=%s",
                payload.execution_id,
            )
            return result

    _run_crew_activity = _activity_impl
    _CrewExecutionWorkflow = _WorkflowImpl


if TEMPORAL_AVAILABLE:
    _register_temporal_definitions()


# ---------------------------------------------------------------------------
# Worker lifecycle: start / stop
# ---------------------------------------------------------------------------

_worker_task: asyncio.Task[None] | None = None
_worker_stop_event: asyncio.Event | None = None
_temporal_client: Any = None
_temporal_client_lock = asyncio.Lock()


async def _get_temporal_client() -> Any:
    """Return a cached Temporal client, creating one on first call.

    Uses double-checked locking to avoid creating duplicate connections
    when multiple coroutines call concurrently.
    """
    global _temporal_client
    if _temporal_client is not None:
        return _temporal_client

    async with _temporal_client_lock:
        if _temporal_client is not None:
            return _temporal_client

        if not TEMPORAL_AVAILABLE:
            raise RuntimeError("temporalio is not installed")

        host = settings.temporal_host
        if not host:
            raise RuntimeError("TEMPORAL_HOST is not configured")

        _temporal_client = await Client.connect(
            host,
            namespace=settings.temporal_namespace,
        )
        logger.info(
            "Temporal client connected: host=%s namespace=%s",
            host,
            settings.temporal_namespace,
            extra={
                "event": "temporal_client_connected",
                "host": host,
                "namespace": settings.temporal_namespace,
            },
        )
        return _temporal_client


async def start_temporal_worker() -> None:
    """Start the Temporal worker in a background task.

    The worker polls the configured task queue for workflow and activity
    tasks.  Call ``stop_temporal_worker()`` during shutdown.

    Raises RuntimeError if temporalio is not installed or TEMPORAL_HOST
    is not set.
    """
    global _worker_task, _worker_stop_event

    if not TEMPORAL_AVAILABLE:
        raise RuntimeError("temporalio is not installed")
    if not settings.temporal_host:
        raise RuntimeError("TEMPORAL_HOST is not configured")

    if _worker_task is not None and not _worker_task.done():
        logger.warning(
            "Temporal worker already running, skipping duplicate start",
            extra={"event": "temporal_worker_already_running"},
        )
        return

    client = await _get_temporal_client()
    _worker_stop_event = asyncio.Event()

    async def _run_worker() -> None:
        assert _worker_stop_event is not None
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[_CrewExecutionWorkflow],
            activities=[_run_crew_activity],
        )
        logger.info(
            "Temporal worker started: task_queue=%s",
            settings.temporal_task_queue,
            extra={
                "event": "temporal_worker_started",
                "task_queue": settings.temporal_task_queue,
            },
        )
        async with worker:
            await _worker_stop_event.wait()
        logger.info(
            "Temporal worker stopped",
            extra={"event": "temporal_worker_stopped"},
        )

    _worker_task = asyncio.create_task(_run_worker())


async def stop_temporal_worker() -> None:
    """Signal the Temporal worker to stop and wait for it to drain."""
    global _worker_task, _worker_stop_event, _temporal_client

    if _worker_stop_event is not None:
        _worker_stop_event.set()

    if _worker_task is not None:
        try:
            await asyncio.wait_for(_worker_task, timeout=30)
        except TimeoutError:
            logger.warning(
                "Temporal worker did not stop within 30s, cancelling",
                extra={"event": "temporal_worker_stop_timeout"},
            )
            _worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
    _worker_stop_event = None
    _temporal_client = None
    logger.info(
        "Temporal worker shutdown complete",
        extra={"event": "temporal_worker_shutdown_complete"},
    )


# ---------------------------------------------------------------------------
# Execution submission: dispatch a crew run as a Temporal workflow
# ---------------------------------------------------------------------------


async def submit_temporal_execution(
    execution_id: UUID,
    resource_snapshot: dict[str, dict[str, Any]],
    crew_name: str,
    inputs: dict[str, Any],
    execution_type: ExecutionType,
    n_iterations: int = 1,
    training_file: str = "training_data.pkl",
) -> str:
    """Submit a crew execution as a Temporal workflow.

    Returns the Temporal workflow ID (which includes the execution UUID,
    making it easy to correlate).

    Raises RuntimeError if Temporal is not available or not configured.
    """
    if not TEMPORAL_AVAILABLE:
        raise RuntimeError("temporalio is not installed")

    client = await _get_temporal_client()

    payload = CrewExecutionInput(
        execution_id=str(execution_id),
        resource_snapshot=resource_snapshot,
        crew_name=crew_name,
        inputs=inputs,
        execution_type=execution_type.value,
        n_iterations=n_iterations,
        training_file=training_file,
    )

    workflow_id = f"crew-exec-{execution_id}"
    timeout_s = settings.temporal_workflow_timeout_s

    handle = await client.start_workflow(
        _CrewExecutionWorkflow.run,
        payload,
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
        execution_timeout=timedelta(seconds=timeout_s),
    )

    logger.info(
        "Temporal workflow started: workflow_id=%s execution_id=%s crew=%s",
        handle.id,
        execution_id,
        crew_name,
        extra={
            "event": "temporal_workflow_started",
            "workflow_id": handle.id,
            "execution_id": str(execution_id),
            "crew_name": crew_name,
            "execution_type": execution_type.value,
            "task_queue": settings.temporal_task_queue,
        },
    )

    return str(handle.id)
