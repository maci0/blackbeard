"""REST API endpoints for crew execution lifecycle management."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
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

from blackbeard.api import sse_state
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import get_current_user
from blackbeard.config import settings
from blackbeard.engine import ExecutionError, ExecutionNotFoundError
from blackbeard.engine import executor as _executor_mod
from blackbeard.http_client import get_client
from blackbeard.kinds import NAME_PATTERN
from blackbeard.logging_config import request_id_var
from blackbeard.models import (
    TERMINAL_STATUSES,
    ExecutionStatus,
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
    KickoffRequest,
    TestRequest,
    TrainRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["executions"])


def _get_spend_client() -> httpx.AsyncClient:
    """Return a shared httpx client for LiteLLM spend queries."""
    key = settings.litellm_master_key.get_secret_value()
    return get_client(
        "litellm-spend",
        timeout=10,
        headers={"Authorization": f"Bearer {key}"},
    )


@router.post(
    "/crews/{crew_name}/kickoff",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        404: {"description": "Crew not found in namespace"},
        422: {"description": "Invalid request body"},
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
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> ExecutionResponse:
    """Kick off a crew execution. Returns immediately with status=queued."""
    try:
        execution = await _executor_mod.kickoff(
            session, crew_name, body.inputs, namespace, user=user
        )
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        # Internal consistency error (e.g., execution vanished after creation)
        logger.error(
            "Kickoff internal error: crew=%s namespace=%s: %s",
            crew_name,
            namespace,
            exc,
            exc_info=True,
            extra={
                "event": "kickoff_internal_error",
                "crew_name": crew_name,
                "namespace": namespace,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Execution could not be created. Check server logs.",
        ) from exc
    await log_audit(
        session,
        action="execution_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "namespace": namespace},
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
        404: {"description": "Crew not found in namespace"},
        422: {"description": "Invalid request body"},
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
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> ExecutionResponse:
    """Start a crew training run. Returns immediately with status=queued."""
    try:
        execution = await _executor_mod.train_crew(
            session,
            crew_name,
            body.inputs,
            body.n_iterations,
            body.filename,
            namespace,
            user=user,
        )
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        logger.error(
            "Train internal error: crew=%s namespace=%s: %s",
            crew_name,
            namespace,
            exc,
            exc_info=True,
            extra={
                "event": "train_internal_error",
                "crew_name": crew_name,
                "namespace": namespace,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Training execution could not be created. Check server logs.",
        ) from exc
    await log_audit(
        session,
        action="train_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "namespace": namespace},
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
        404: {"description": "Crew not found in namespace"},
        422: {"description": "Invalid request body"},
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
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace containing the crew",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> ExecutionResponse:
    """Start a crew test run. Returns immediately with status=queued."""
    try:
        execution = await _executor_mod.test_crew(
            session,
            crew_name,
            body.inputs,
            body.n_iterations,
            namespace,
            user=user,
        )
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        logger.error(
            "Test internal error: crew=%s namespace=%s: %s",
            crew_name,
            namespace,
            exc,
            exc_info=True,
            extra={
                "event": "test_internal_error",
                "crew_name": crew_name,
                "namespace": namespace,
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Test execution could not be created. Check server logs.",
        ) from exc
    await log_audit(
        session,
        action="test_started",
        resource_type="Crew",
        resource_id=crew_name,
        detail={"execution_id": str(execution.id), "namespace": namespace},
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
    namespace: str = Query(
        default="default",
        pattern=NAME_PATTERN,
        max_length=255,
        description="Namespace containing the flow",
    ),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> ExecutionResponse:
    """Run a flow. Returns immediately with status=queued."""
    try:
        execution = await _executor_mod.run_flow(
            session,
            flow_name,
            body.inputs,
            namespace=namespace,
            user=user,
        )
    except ExecutionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_name}' not found") from None
    except ExecutionError as exc:
        logger.error(
            "Flow run failed for '%s': %s",
            flow_name,
            exc,
            extra={
                "event": "flow_run_error",
                "flow_name": flow_name,
                "namespace": namespace,
                "error": str(exc)[:500],
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Flow execution could not be created. Check server logs.",
        ) from exc
    await log_audit(
        session,
        action="flow_started",
        resource_type="Flow",
        resource_id=flow_name,
        detail={"execution_id": str(execution.id), "namespace": namespace},
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
    namespace: str | None = Query(
        default=None,
        pattern=NAME_PATTERN,
        max_length=255,
        description="Filter by namespace (omit for all namespaces)",
    ),
    status: ExecutionStatus | None = Query(
        default=None,
        description="Filter by execution status",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, le=100_000, description="Results to skip"),
    session: AsyncSession = Depends(get_session),
) -> ExecutionListResponse:
    """List executions with optional filters."""
    items, total = await _executor_mod.list_executions(
        session,
        crew_name=crew_name,
        namespace=namespace,
        status=status,
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
) -> ExecutionResponse:
    """Get execution details by ID."""
    execution = await _executor_mod.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
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
) -> Response:
    """Get LiteLLM spend data for an execution's requests."""
    status = await _executor_mod.get_execution_status(session, execution_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    try:
        client = _get_spend_client()
        resp = await client.get(
            f"{settings.litellm_proxy_url}/spend/logs",
            params={"request_id": str(execution_id)},
            headers={"X-Request-Id": request_id_var.get("-")},
        )
        if resp.status_code == 200:
            return Response(content=resp.content, media_type="application/json")
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
            headers={"Retry-After": "30"},
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
            headers={"Retry-After": "30"},
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
) -> ExecutionEventsResponse:
    """List execution events, optionally after a given sequence number."""
    exec_check = await _executor_mod.get_execution_status(session, execution_id)
    if exec_check is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

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
                data=e.data,
            )
            for e in items
        ],
        next_sequence=items[-1].sequence if items else after,
        has_more=has_more,
    )


@router.post(
    "/executions/{execution_id}/respond",
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
    user: User | None = Depends(get_current_user),
) -> dict[str, str]:
    """Respond to a human-in-the-loop prompt during execution.

    Records the response as an execution event so the execution listener
    can pick it up. The frontend should poll the events endpoint for
    ``hitl_request`` events and present them to the user.
    """
    status = await _executor_mod.get_execution_status(session, execution_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
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
        detail={"response": body.response},
        **audit_from_request(request, user),
    )
    await session.commit()

    return {"status": "recorded", "execution_id": str(execution_id)}


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
    user: User | None = Depends(get_current_user),
) -> ExecutionResponse:
    """Cancel a queued or running execution."""
    try:
        execution = await _executor_mod.cancel_execution(session, execution_id)
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not execution:
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
) -> EventSourceResponse:
    """SSE stream of execution status events."""
    if sse_state.semaphore.locked():
        logger.warning(
            "SSE stream rejected: max concurrent streams reached (%d/%d)",
            sse_state.MAX_CONCURRENT_SSE,
            sse_state.MAX_CONCURRENT_SSE,
            extra={
                "event": "sse_stream_rejected",
                "execution_id": str(execution_id),
                "active_streams": sse_state.MAX_CONCURRENT_SSE,
                "max_concurrent_sse": sse_state.MAX_CONCURRENT_SSE,
            },
        )
        raise HTTPException(
            status_code=429,
            detail="Too many concurrent SSE streams",
            headers={"Retry-After": "5"},
        )

    # Lightweight status-only query to avoid loading full execution before SSE starts
    async with async_session() as check_session:
        check = await _executor_mod.get_execution_status(check_session, execution_id)
    if check is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    max_polls = 400  # ~32 min with progressive backoff (2s→3s→5s)
    logger.info(
        "SSE stream opened: execution_id=%s active=%d/%d",
        execution_id,
        sse_state.active_count,
        sse_state.MAX_CONCURRENT_SSE,
        extra={
            "event": "sse_stream_opened",
            "execution_id": str(execution_id),
            "active_streams": sse_state.active_count,
            "max_concurrent_sse": sse_state.MAX_CONCURRENT_SSE,
        },
    )

    async def event_generator() -> AsyncGenerator[dict[str, str]]:
        # Non-blocking acquire: fail fast if all SSE slots are taken.
        # The locked() check in the handler is a fast-path optimization, but
        # between that check and this acquire, other streams can start (TOCTOU).
        acquired = False
        try:
            await asyncio.wait_for(sse_state.semaphore.acquire(), timeout=0)
            acquired = True
            sse_state.active_count += 1
        except TimeoutError:
            msg = json.dumps({"detail": "Too many concurrent SSE streams"})
            yield {"event": "error", "data": msg}
            return
        last_status: ExecutionStatus | None = None
        current_status: ExecutionStatus | None = None
        last_event_seq = -1
        polls = 0
        try:
            try:
                while polls < max_polls:
                    polls += 1
                    async with async_session() as session:
                        if last_status is None:
                            execution = await _executor_mod.get_execution(session, execution_id)
                            if not execution:
                                msg = f"Execution '{execution_id}' not found"
                                yield {
                                    "event": "error",
                                    "data": json.dumps({"detail": msg}),
                                }
                                break
                            current_status = execution.status
                            data = ExecutionResponse.from_db(execution).model_dump_json()
                            yield {"event": "status", "data": data}
                            last_status = current_status
                        else:
                            current_status = await _executor_mod.get_execution_status(
                                session, execution_id
                            )

                            if current_status is None:
                                msg = f"Execution '{execution_id}' not found"
                                yield {
                                    "event": "error",
                                    "data": json.dumps({"detail": msg}),
                                }
                                break

                            if current_status != last_status or current_status in TERMINAL_STATUSES:
                                execution = await _executor_mod.get_execution(session, execution_id)
                                if execution:
                                    data = ExecutionResponse.from_db(execution).model_dump_json()
                                    yield {"event": "status", "data": data}
                                last_status = current_status
                            else:
                                heartbeat = {"status": current_status.value}
                                yield {
                                    "event": "heartbeat",
                                    "data": json.dumps(heartbeat),
                                }

                        new_events = await _executor_mod.list_execution_events(
                            session, execution_id, after=last_event_seq, limit=50
                        )
                        for ev in new_events:
                            yield {
                                "event": ev.event_type,
                                "data": json.dumps(
                                    {
                                        "sequence": ev.sequence,
                                        "timestamp": ev.timestamp.isoformat(),
                                        **ev.data,
                                    }
                                ),
                            }
                            last_event_seq = ev.sequence

                        if current_status in TERMINAL_STATUSES:
                            logger.info(
                                "SSE stream closed: id=%s status=%s polls=%d active=%d/%d",
                                execution_id,
                                current_status.value,
                                polls,
                                sse_state.active_count - 1,
                                sse_state.MAX_CONCURRENT_SSE,
                                extra={
                                    "event": "sse_stream_closed",
                                    "execution_id": str(execution_id),
                                    "final_status": current_status.value,
                                    "polls": polls,
                                    "remaining_streams": sse_state.active_count - 1,
                                },
                            )
                            break

                    await asyncio.sleep(2 if polls < 10 else 3 if polls < 30 else 5)
                else:
                    logger.warning(
                        "SSE stream timeout: execution_id=%s polls=%d",
                        execution_id,
                        polls,
                        extra={
                            "event": "sse_stream_timeout",
                            "execution_id": str(execution_id),
                            "polls": polls,
                        },
                    )
                    msg = "Stream timeout — execution still running"
                    yield {"event": "error", "data": json.dumps({"detail": msg})}
            except asyncio.CancelledError:
                logger.info(
                    "SSE stream client disconnected: execution_id=%s polls=%d",
                    execution_id,
                    polls,
                    extra={
                        "event": "sse_stream_disconnected",
                        "execution_id": str(execution_id),
                        "polls": polls,
                    },
                )
            except Exception as e:
                logger.error(
                    "SSE stream error: execution_id=%s polls=%d error=%s",
                    execution_id,
                    polls,
                    e,
                    exc_info=True,
                    extra={
                        "event": "sse_stream_error",
                        "execution_id": str(execution_id),
                        "polls": polls,
                        "error_type": type(e).__name__,
                        "error_message": str(e)[:500],
                    },
                )
                yield {"event": "error", "data": json.dumps({"detail": "Internal stream error"})}
        finally:
            if acquired:
                sse_state.active_count -= 1
                sse_state.semaphore.release()

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
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
    import hmac

    import jwt as pyjwt

    from blackbeard.api.middleware import _EXPECTED_API_KEY
    from blackbeard.auth.jwt import decode_token

    token = websocket.query_params.get("token", "")
    api_key = websocket.query_params.get("api_key", "")

    authenticated = False
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "access":
                authenticated = True
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
            pass
    if not authenticated and api_key and hmac.compare_digest(api_key, _EXPECTED_API_KEY):
        authenticated = True

    if not authenticated:
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()

    async with async_session() as check_session:
        check = await _executor_mod.get_execution_status(check_session, execution_id)
    if check is None:
        await websocket.send_json({"event": "error", "data": {"detail": "Execution not found"}})
        await websocket.close(code=4004, reason="Execution not found")
        return

    last_status: ExecutionStatus | None = None
    last_event_seq = -1
    polls = 0
    max_polls = 400

    try:
        while polls < max_polls:
            polls += 1
            async with async_session() as session:
                if last_status is None:
                    execution = await _executor_mod.get_execution(session, execution_id)
                    if not execution:
                        await websocket.send_json(
                            {"event": "error", "data": {"detail": "Execution not found"}}
                        )
                        break
                    current_status = execution.status
                    data = json.loads(ExecutionResponse.from_db(execution).model_dump_json())
                    await websocket.send_json({"event": "status", "data": data})
                    last_status = current_status
                else:
                    current_status = await _executor_mod.get_execution_status(
                        session, execution_id
                    )
                    if current_status is None:
                        await websocket.send_json(
                            {"event": "error", "data": {"detail": "Execution not found"}}
                        )
                        break

                    if current_status != last_status or current_status in TERMINAL_STATUSES:
                        execution = await _executor_mod.get_execution(session, execution_id)
                        if execution:
                            data = json.loads(
                                ExecutionResponse.from_db(execution).model_dump_json()
                            )
                            await websocket.send_json({"event": "status", "data": data})
                        last_status = current_status
                    else:
                        await websocket.send_json(
                            {"event": "heartbeat", "data": {"status": current_status.value}}
                        )

                new_events = await _executor_mod.list_execution_events(
                    session, execution_id, after=last_event_seq, limit=50
                )
                for ev in new_events:
                    await websocket.send_json({
                        "event": ev.event_type,
                        "data": {
                            "sequence": ev.sequence,
                            "timestamp": ev.timestamp.isoformat(),
                            **ev.data,
                        },
                    })
                    last_event_seq = ev.sequence

                if current_status in TERMINAL_STATUSES:
                    break

            await asyncio.sleep(2 if polls < 10 else 3 if polls < 30 else 5)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(
            "WS stream error: execution_id=%s error=%s",
            execution_id,
            e,
            extra={
                "event": "ws_stream_error",
                "execution_id": str(execution_id),
                "error_type": type(e).__name__,
            },
        )
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {"event": "error", "data": {"detail": "Internal stream error"}}
            )
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
