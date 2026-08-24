"""REST API endpoints for crew execution lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator, Awaitable
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from blackbeard import sse as sse_state
from blackbeard.api import RETRY_HEADERS_30
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth import require_permission
from blackbeard.config import settings
from blackbeard.engine import ExecutionError, ExecutionNotFoundError
from blackbeard.engine import executor as _executor_mod
from blackbeard.http_client import get_litellm_client
from blackbeard.kinds import NAME_PATTERN
from blackbeard.logging_config import anonymize_ip, request_id_var
from blackbeard.models import (
    TERMINAL_STATUSES,
    Execution,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionType,
    User,
    async_session,
    get_session,
)
from blackbeard.models.execution_schemas import (
    ExecutionEventItem,
    ExecutionEventsResponse,
    ExecutionListResponse,
    ExecutionResponse,
    HITLResponseRequest,
    HITLResponseResult,
    KickoffRequest,
    TestRequest,
    TrainRequest,
    contains_redacted_values,
    redact_sensitive_values,
)
from blackbeard.rate_limiter import check_rate_limit, execution_limiter

logger = logging.getLogger(__name__)

_MAX_STREAM_POLLS = 400

# Events fetched per poll; the stream drains consecutive batches so a burst
# larger than one batch is never dropped when the execution turns terminal.
_EVENT_BATCH_SIZE = 50

_SSE_ERROR_TOO_MANY = json.dumps({"detail": "Too many concurrent SSE streams"})
_SSE_ERROR_INTERNAL = json.dumps({"detail": "Internal stream error"})

# Phase threshold for progressive poll backoff (shared by SSE + WS).
_PHASE2_THRESHOLD = 30


def _poll_backoff(polls: int) -> int:
    """Return sleep seconds for progressive backoff: 1s for first 30 polls, then 2s."""
    if polls < _PHASE2_THRESHOLD:
        return 1
    return 2


def _serialize_event(ev: ExecutionEvent) -> dict[str, object]:
    if not ev.data:
        return {"sequence": ev.sequence, "timestamp": ev.timestamp.isoformat()}
    redacted = redact_sensitive_values(ev.data)
    data: dict[str, object] = redacted if redacted is not ev.data else dict(redacted)
    data["sequence"] = ev.sequence
    data["timestamp"] = ev.timestamp.isoformat()
    return data


class _StreamEvent:
    """A single event yielded by the shared execution polling loop."""

    __slots__ = ("data", "event_type", "kind")

    def __init__(self, kind: str, data: dict[str, object], event_type: str = "") -> None:
        self.kind = kind
        self.data = data
        self.event_type = event_type

    @property
    def event_name(self) -> str:
        """Resolve the outgoing event name for SSE/WS dispatch."""
        if self.kind == "event":
            return self.event_type
        if self.kind in ("error", "timeout"):
            return "error"
        return self.kind


_HEARTBEAT_EVENTS: dict[ExecutionStatus, _StreamEvent] = {
    s: _StreamEvent("heartbeat", {"status": s.value}) for s in ExecutionStatus
}


async def _poll_execution(execution_id: UUID) -> AsyncGenerator[_StreamEvent]:
    """Shared polling loop for SSE and WS execution streams.

    Yields _StreamEvent objects; callers decide how to serialize/send them.
    """
    last_status: ExecutionStatus | None = None
    current_status: ExecutionStatus | None = None
    last_event_seq = -1
    prev_had_events = True
    polls = 0

    while polls < _MAX_STREAM_POLLS:
        polls += 1
        async with async_session() as session:
            if last_status is None:
                execution = await _executor_mod.get_execution(session, execution_id)
                if not execution:
                    yield _StreamEvent("error", {"detail": f"Execution '{execution_id}' not found"})
                    return
                current_status = execution.status
                yield _StreamEvent(
                    "status",
                    ExecutionResponse.from_db(execution).model_dump(mode="json"),
                )
                last_status = current_status
            else:
                current_status = await _executor_mod.get_execution_status(session, execution_id)
                if current_status is None:
                    yield _StreamEvent("error", {"detail": f"Execution '{execution_id}' not found"})
                    return

                if current_status != last_status or current_status in TERMINAL_STATUSES:
                    execution = await _executor_mod.get_execution(session, execution_id)
                    if execution:
                        yield _StreamEvent(
                            "status",
                            ExecutionResponse.from_db(execution).model_dump(mode="json"),
                        )
                    last_status = current_status
                else:
                    yield _HEARTBEAT_EVENTS[current_status]

            skip_events = (
                not prev_had_events
                and current_status == last_status
                and current_status not in TERMINAL_STATUSES
            )
            if not skip_events:
                had_events = False
                while True:
                    new_events = await _executor_mod.list_execution_events(
                        session, execution_id, after=last_event_seq, limit=_EVENT_BATCH_SIZE
                    )
                    had_events = had_events or len(new_events) > 0
                    for ev in new_events:
                        yield _StreamEvent("event", _serialize_event(ev), event_type=ev.event_type)
                        last_event_seq = ev.sequence
                    if len(new_events) < _EVENT_BATCH_SIZE:
                        break
                prev_had_events = had_events
            else:
                # Reset so next poll re-checks for events
                prev_had_events = True

            if current_status in TERMINAL_STATUSES:
                return

        await asyncio.sleep(_poll_backoff(polls))

    yield _StreamEvent("timeout", {"detail": "Stream timeout — execution still running"})


async def _require_execution(
    session: AsyncSession,
    execution_id: UUID,
) -> Execution:
    """Load an execution or raise 404."""
    execution = await _executor_mod.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return execution


async def _require_execution_status(
    session: AsyncSession,
    execution_id: UUID,
) -> ExecutionStatus:
    """Load execution status or raise 404."""
    status = await _executor_mod.get_execution_status(session, execution_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return status


async def _run_executor(
    coro: Awaitable[Execution],
    *,
    log_event: str,
    log_resource: str,
    log_project: str,
) -> Execution:
    """Await an executor coroutine, converting its exceptions to HTTP errors."""
    try:
        return await coro
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        logger.error(
            "%s error: resource=%s project=%s: %s",
            log_event,
            log_resource,
            log_project,
            exc,
            exc_info=True,
            extra={
                "event": log_event,
                "resource_name": log_resource,
                "project": log_project,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Execution could not be created. Check server logs.",
        ) from exc


_EXECUTION_RATE_MSG = "Too many execution requests. Try again later."


router = APIRouter(tags=["executions"])


@router.post(
    "/crews/{crew_name}/kickoff",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        404: {"description": "Crew not found in project"},
        422: {"description": "Invalid request body"},
        429: {"description": "Too many execution requests"},
        500: {"description": "Internal execution error"},
    },
)
async def kickoff_crew(
    request: Request,
    response: Response,
    crew_name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Name of the crew to execute",
    ),
    body: KickoffRequest = Body(...),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Project containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("run", "Crew")),
) -> ExecutionResponse:
    """Kick off a crew execution. Returns immediately with status=queued."""
    check_rate_limit(execution_limiter, user, _EXECUTION_RATE_MSG)
    execution = await _run_executor(
        _executor_mod.kickoff(session, crew_name, body.inputs, project, user=user),
        log_event="kickoff_internal_error",
        log_resource=crew_name,
        log_project=project,
    )
    await log_audit(
        session,
        action="execution_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "project": project},
        **audit_from_request(request, user),
    )
    await session.commit()
    response.headers["Location"] = f"/api/v1/executions/{execution.id}"
    return ExecutionResponse.from_db(execution)


@router.post(
    "/crews/{crew_name}/train",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        404: {"description": "Crew not found in project"},
        422: {"description": "Invalid request body"},
        429: {"description": "Too many execution requests"},
        500: {"description": "Internal execution error"},
    },
)
async def train_crew_endpoint(
    request: Request,
    response: Response,
    crew_name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Name of the crew to train",
    ),
    body: TrainRequest = Body(...),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Project containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("run", "Crew")),
) -> ExecutionResponse:
    """Start a crew training run. Returns immediately with status=queued."""
    check_rate_limit(execution_limiter, user, _EXECUTION_RATE_MSG)
    execution = await _run_executor(
        _executor_mod.train_crew(
            session,
            crew_name,
            body.inputs,
            body.n_iterations,
            body.filename,
            project,
            user=user,
        ),
        log_event="train_internal_error",
        log_resource=crew_name,
        log_project=project,
    )
    await log_audit(
        session,
        action="train_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "project": project},
        **audit_from_request(request, user),
    )
    await session.commit()
    response.headers["Location"] = f"/api/v1/executions/{execution.id}"
    return ExecutionResponse.from_db(execution)


@router.post(
    "/crews/{crew_name}/test",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        404: {"description": "Crew not found in project"},
        422: {"description": "Invalid request body"},
        429: {"description": "Too many execution requests"},
        500: {"description": "Internal execution error"},
    },
)
async def test_crew_endpoint(
    request: Request,
    response: Response,
    crew_name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Name of the crew to test",
    ),
    body: TestRequest = Body(...),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Project containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("run", "Crew")),
) -> ExecutionResponse:
    """Start a crew test run. Returns immediately with status=queued."""
    check_rate_limit(execution_limiter, user, _EXECUTION_RATE_MSG)
    execution = await _run_executor(
        _executor_mod.test_crew(
            session,
            crew_name,
            body.inputs,
            body.n_iterations,
            project,
            user=user,
        ),
        log_event="test_internal_error",
        log_resource=crew_name,
        log_project=project,
    )
    await log_audit(
        session,
        action="test_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "project": project},
        **audit_from_request(request, user),
    )
    await session.commit()
    response.headers["Location"] = f"/api/v1/executions/{execution.id}"
    return ExecutionResponse.from_db(execution)


@router.post(
    "/flows/{flow_name}/run",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        202: {"description": "Flow execution queued"},
        404: {"description": "Flow not found"},
        429: {"description": "Too many execution requests"},
        500: {"description": "Internal execution error"},
    },
)
async def run_flow_endpoint(
    request: Request,
    response: Response,
    flow_name: str = Path(
        ...,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Name of the flow to run",
    ),
    body: KickoffRequest = Body(...),
    project: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Project containing the flow",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("run", "Flow")),
) -> ExecutionResponse:
    """Run a flow. Returns immediately with status=queued."""
    check_rate_limit(execution_limiter, user, _EXECUTION_RATE_MSG)
    execution = await _run_executor(
        _executor_mod.run_flow(session, flow_name, body.inputs, project=project, user=user),
        log_event="flow_run_error",
        log_resource=flow_name,
        log_project=project,
    )
    await log_audit(
        session,
        action="flow_started",
        resource_type="Flow",
        resource_id=flow_name,
        detail={"execution_id": str(execution.id), "project": project},
        **audit_from_request(request, user),
    )
    await session.commit()
    response.headers["Location"] = f"/api/v1/executions/{execution.id}"
    return ExecutionResponse.from_db(execution)


@router.get(
    "/executions",
    response_model=ExecutionListResponse,
    responses={200: {"description": "Paginated list of executions"}},
)
async def list_executions(
    crew_name: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by crew name",
    ),
    project: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by project (omit for all projects)",
    ),
    status: ExecutionStatus | None = Query(
        default=None,
        description="Filter by execution status",
    ),
    execution_type: ExecutionType | None = Query(
        default=None,
        description="Filter by execution type (kickoff, train, test, flow)",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_permission("list", "Execution")),
) -> ExecutionListResponse:
    """List executions with optional filters."""
    items, total = await _executor_mod.list_executions(
        session,
        crew_name=crew_name,
        project=project,
        status=status,
        execution_type=execution_type,
        limit=limit,
        offset=offset,
        include_tasks=False,
    )
    return ExecutionListResponse(
        items=[ExecutionResponse.from_db(e, include_tasks=False) for e in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    responses={404: {"description": "Execution not found"}},
)
async def get_execution(
    execution_id: UUID = Path(..., description="Execution UUID"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_permission("get", "Execution")),
) -> ExecutionResponse:
    """Get execution details by ID."""
    execution = await _require_execution(session, execution_id)
    return ExecutionResponse.from_db(execution)


@router.get(
    "/executions/{execution_id}/spend",
    responses={
        200: {"description": "LiteLLM spend data for this execution"},
        404: {"description": "Execution not found"},
        502: {"description": "LiteLLM spend service unavailable"},
    },
)
async def get_execution_spend(
    execution_id: UUID = Path(..., description="Execution UUID"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_permission("get", "Execution")),
) -> Response:
    """Get LiteLLM spend data for an execution's requests."""
    await _require_execution_status(session, execution_id)

    try:
        client = get_litellm_client("litellm-spend", timeout=10)
        resp = await client.get(
            f"{settings.litellm_proxy_url}/spend/logs",
            params={"request_id": str(execution_id)},
            headers={"X-Request-Id": request_id_var.get("-")},
        )
        if resp.status_code == 200:
            return Response(
                content=resp.content,
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )
        logger.warning(
            "LiteLLM spend query returned %d for execution %s",
            resp.status_code,
            execution_id,
            extra={
                "event": "spend_fetch_error",
                "execution_id": str(execution_id),
                "http_status": resp.status_code,
            },
        )
        raise HTTPException(
            status_code=502,
            detail=f"Spend service returned status {resp.status_code}",
            headers=RETRY_HEADERS_30,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(
            "Failed to fetch spend data for execution %s: %s",
            execution_id,
            e,
            exc_info=True,
            extra={
                "event": "spend_fetch_failed",
                "execution_id": str(execution_id),
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Spend service is unavailable. Try again later.",
            headers=RETRY_HEADERS_30,
        ) from e


@router.get(
    "/executions/{execution_id}/events",
    response_model=ExecutionEventsResponse,
    responses={
        200: {"description": "List of execution events for streaming/replay"},
        404: {"description": "Execution not found"},
    },
)
async def list_execution_events(
    execution_id: UUID = Path(..., description="Execution UUID"),
    after: int = Query(default=-1, ge=-1, description="Return events with sequence > after"),
    limit: int = Query(default=200, ge=1, le=1000, description="Max events to return"),
    session: AsyncSession = Depends(get_session),
    _user: User | None = Depends(require_permission("get", "Execution")),
) -> ExecutionEventsResponse:
    """List execution events, optionally after a given sequence number."""
    await _require_execution_status(session, execution_id)

    items = await _executor_mod.list_execution_events(
        session, execution_id, after=after, limit=limit + 1
    )
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    return ExecutionEventsResponse(
        events=[
            ExecutionEventItem(
                sequence=e.sequence,
                event_type=e.event_type,
                timestamp=e.timestamp,
                data=redact_sensitive_values(e.data) if e.data else {},
            )
            for e in items
        ],
        next_sequence=items[-1].sequence if items else after,
        has_more=has_more,
    )


@router.post(
    "/executions/{execution_id}/respond",
    response_model=HITLResponseResult,
    responses={
        200: {"description": "HITL response recorded"},
        404: {"description": "Execution not found"},
        409: {"description": "Execution is not awaiting human input"},
    },
)
async def respond_to_execution(
    request: Request,
    execution_id: UUID = Path(..., description="Execution UUID"),
    body: HITLResponseRequest = Body(...),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("update", "Execution")),
) -> HITLResponseResult:
    """Respond to a human-in-the-loop prompt during execution.

    Records the response as an execution event so the execution listener
    can pick it up. The frontend should poll the events endpoint for
    ``hitl_request`` events and present them to the user.
    """
    status = await _require_execution_status(session, execution_id)
    if status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Execution is in terminal status '{status.value}'",
        )

    await _executor_mod.record_hitl_response(
        session,
        execution_id,
        response=body.response,
        feedback=body.feedback,
    )

    await log_audit(
        session,
        action="hitl_response",
        resource_type="Execution",
        resource_id=str(execution_id),
        detail={"response_length": len(body.response)},
        **audit_from_request(request, user),
    )
    await session.commit()

    return HITLResponseResult(status="recorded", execution_id=str(execution_id))


@router.post(
    "/executions/{execution_id}/retry",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        202: {"description": "New execution created from the original's configuration"},
        404: {"description": "Execution not found"},
        409: {"description": "Can only retry terminal executions"},
        429: {"description": "Too many execution requests"},
        500: {"description": "Internal execution error"},
    },
)
async def retry_execution(
    request: Request,
    response: Response,
    execution_id: UUID = Path(..., description="Execution UUID to retry"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("run", "Crew")),
) -> ExecutionResponse:
    """Retry a failed or cancelled execution.

    Creates a new execution with the same crew, project, and inputs as the
    original. Only terminal executions (completed, failed, cancelled) can be
    retried. Returns the new execution immediately with status=queued.
    """
    check_rate_limit(execution_limiter, user, _EXECUTION_RATE_MSG)
    original = await _require_execution(session, execution_id)
    if original.status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Can only retry terminal executions, current status is '{original.status.value}'"
            ),
        )
    # Stored inputs are redacted at submit time; re-running with placeholder
    # values would silently produce a different execution.
    if original.inputs and contains_redacted_values(original.inputs):
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot retry: the original inputs contained sensitive values that "
                "were redacted before storage. Start a new execution with the "
                "original inputs instead."
            ),
        )

    exec_type = original.execution_type or ExecutionType.KICKOFF
    if exec_type == ExecutionType.FLOW:
        coro = _executor_mod.run_flow(
            session,
            original.crew_name,
            original.inputs,
            project=original.crew_project,
            user=user,
        )
    elif exec_type == ExecutionType.TRAIN:
        coro = _executor_mod.train_crew(
            session,
            original.crew_name,
            original.inputs,
            n_iterations=original.n_iterations or 3,
            filename=original.training_file or "training_data.pkl",
            project=original.crew_project,
            user=user,
        )
    elif exec_type == ExecutionType.TEST:
        coro = _executor_mod.test_crew(
            session,
            original.crew_name,
            original.inputs,
            n_iterations=original.n_iterations or 3,
            project=original.crew_project,
            user=user,
        )
    else:
        coro = _executor_mod.kickoff(
            session,
            original.crew_name,
            original.inputs,
            original.crew_project,
            user=user,
        )

    new_execution = await _run_executor(
        coro,
        log_event="retry_failed",
        log_resource=original.crew_name,
        log_project=original.crew_project,
    )

    await log_audit(
        session,
        action="execution_retried",
        resource_type="Execution",
        resource_id=str(execution_id),
        detail={
            "new_execution_id": str(new_execution.id),
            "crew_name": original.crew_name,
            "project": original.crew_project,
        },
        **audit_from_request(request, user),
    )
    await session.commit()

    response.headers["Location"] = f"/api/v1/executions/{new_execution.id}"
    return ExecutionResponse.from_db(new_execution)


@router.patch(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionResponse,
    responses={
        200: {"description": "Execution cancelled successfully", "model": ExecutionResponse},
        404: {"description": "Execution not found"},
        409: {"description": "Execution already in terminal status"},
    },
)
async def cancel_execution(
    request: Request,
    execution_id: UUID = Path(..., description="Execution UUID"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("delete", "Execution")),
) -> ExecutionResponse:
    """Cancel a queued or running execution."""
    try:
        execution = await _executor_mod.cancel_execution(session, execution_id)
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    await log_audit(
        session,
        action="execution_cancelled",
        resource_type="Execution",
        resource_id=str(execution_id),
        detail={"crew_name": execution.crew_name},
        **audit_from_request(request, user),
    )
    await session.commit()
    return ExecutionResponse.from_db(execution)


@router.get(
    "/executions/{execution_id}/stream",
    responses={
        200: {"description": "SSE stream of execution status and heartbeat events"},
        404: {"description": "Execution not found"},
        429: {"description": "Too many concurrent SSE streams"},
    },
)
async def stream_execution(
    execution_id: UUID = Path(..., description="Execution UUID"),
    _user: User | None = Depends(require_permission("get", "Execution")),
) -> EventSourceResponse:
    """SSE stream of execution status events."""
    async with async_session() as check_session:
        await _require_execution_status(check_session, execution_id)

    logger.info(
        "SSE stream opened: execution_id=%s active=%d/%d",
        execution_id,
        sse_state.get_active_count(),
        settings.max_concurrent_sse,
        extra={
            "event": "sse_stream_opened",
            "execution_id": str(execution_id),
            "active_streams": sse_state.get_active_count(),
            "max_concurrent_sse": settings.max_concurrent_sse,
        },
    )

    async def event_generator() -> AsyncGenerator[dict[str, str]]:
        async with sse_state.acquire_stream() as acquired:
            if not acquired:
                logger.warning(
                    "SSE stream rejected (capacity full): execution_id=%s active=%d/%d",
                    execution_id,
                    sse_state.get_active_count(),
                    settings.max_concurrent_sse,
                    extra={
                        "event": "sse_stream_rejected",
                        "execution_id": str(execution_id),
                        "active_streams": sse_state.get_active_count(),
                        "max_concurrent_sse": settings.max_concurrent_sse,
                    },
                )
                yield {"event": "error", "data": _SSE_ERROR_TOO_MANY}
                return
            try:
                async for item in _poll_execution(execution_id):
                    yield {"event": item.event_name, "data": json.dumps(item.data)}
            except asyncio.CancelledError:
                logger.info(
                    "SSE stream client disconnected: execution_id=%s",
                    execution_id,
                    extra={
                        "event": "sse_stream_disconnected",
                        "execution_id": str(execution_id),
                    },
                )
            except Exception as e:
                logger.error(
                    "SSE stream error: execution_id=%s error=%s",
                    execution_id,
                    e,
                    exc_info=True,
                    extra={
                        "event": "sse_stream_error",
                        "execution_id": str(execution_id),
                        "error_type": type(e).__name__,
                        "error_message": str(e)[:500],
                    },
                )
                yield {"event": "error", "data": _SSE_ERROR_INTERNAL}

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "X-Poll-Interval": "1s/2s (progressive)",
        },
    )


@router.websocket("/executions/{execution_id}/ws")
async def ws_execution(
    websocket: WebSocket,
    execution_id: UUID,
) -> None:
    """WebSocket stream of execution events. Sends JSON frames.

    Authentication: Accepts either ``token`` query parameter (JWT) or
    ``api_key`` query parameter (system API key).  WebSocket connections
    cannot set custom headers, so credentials must be passed via query
    string.
    """
    from blackbeard.auth import validate_ws_auth
    from blackbeard.rate_limiter import is_rate_limited, record_auth_failure

    client_ip = websocket.client.host if websocket.client else "unknown"
    if is_rate_limited(client_ip):
        await websocket.close(code=4429, reason="Too many authentication failures")
        return

    token = websocket.query_params.get("token", "")
    api_key = websocket.query_params.get("api_key", "")

    if not validate_ws_auth(token, api_key):
        record_auth_failure(client_ip)
        logger.warning(
            "WebSocket auth failed: execution_id=%s from %s",
            execution_id,
            anonymize_ip(client_ip),
            extra={
                "event": "ws_auth_failure",
                "execution_id": str(execution_id),
                "client_ip": anonymize_ip(client_ip),
            },
        )
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()

    async with async_session() as check_session:
        check = await _executor_mod.get_execution_status(check_session, execution_id)
    if check is None:
        await websocket.send_json({"event": "error", "data": {"detail": "Execution not found"}})
        await websocket.close(code=4004, reason="Execution not found")
        return

    try:
        # Share the SSE stream cap: each poller holds DB connections, and
        # unbounded WS viewers would exhaust the pool for the whole API.
        async with sse_state.acquire_stream() as acquired:
            if not acquired:
                await websocket.send_json(
                    {"event": "error", "data": {"detail": "Too many concurrent streams"}}
                )
                await websocket.close(code=4429, reason="Too many concurrent streams")
                return
            async for item in _poll_execution(execution_id):
                await websocket.send_json({"event": item.event_name, "data": item.data})
    except WebSocketDisconnect:
        logger.debug(
            "WS client disconnected: execution_id=%s",
            execution_id,
            extra={"event": "ws_client_disconnected", "execution_id": str(execution_id)},
        )
    except Exception as e:
        logger.error(
            "WS stream error: execution_id=%s error=%s",
            execution_id,
            e,
            exc_info=True,
            extra={
                "event": "ws_stream_error",
                "execution_id": str(execution_id),
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
            },
        )
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"event": "error", "data": {"detail": "Internal stream error"}}
            )
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
