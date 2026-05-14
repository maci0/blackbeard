"""REST API endpoints for crew execution lifecycle management."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.config import settings
from blackbeard.engine import ExecutionError, executor
from blackbeard.kinds import NAME_PATTERN
from blackbeard.models import TERMINAL_STATUSES, ExecutionStatus, async_session, get_session
from blackbeard.models.execution import ExecutionEvent
from blackbeard.models.execution_schemas import (
    ExecutionListResponse,
    ExecutionResponse,
    KickoffRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["executions"])


@router.post(
    "/crews/{crew_name}/kickoff",
    response_model=ExecutionResponse,
    status_code=202,
    responses={
        404: {"description": "Crew not found in namespace"},
        422: {"description": "Invalid request body"},
    },
)
async def kickoff_crew(
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
) -> ExecutionResponse:
    """Kick off a crew execution. Returns immediately with status=queued."""
    try:
        execution = await executor.kickoff(session, crew_name, body.inputs, namespace)
    except ExecutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        description="Filter by namespace",
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
    items, total = await executor.list_executions(
        session,
        crew_name=crew_name,
        namespace=namespace,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ExecutionListResponse(
        items=[ExecutionResponse.from_db(e) for e in items],
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
    execution = await executor.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ExecutionResponse.from_db(execution)


@router.get(
    "/executions/{execution_id}/spend",
    responses={
        200: {"description": "LiteLLM spend data for this execution"},
        404: {"description": "Execution not found"},
    },
)
async def get_execution_spend(
    execution_id: UUID = Path(..., description="Execution UUID"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get LiteLLM spend data for an execution's requests."""
    execution = await executor.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.litellm_proxy_url}/spend/logs",
                params={"request_id": str(execution_id)},
                headers={
                    "Authorization": f"Bearer {settings.litellm_master_key.get_secret_value()}"
                },
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "LiteLLM spend query failed: execution_id=%s status=%d",
                execution_id,
                resp.status_code,
                extra={
                    "event": "litellm_spend_error",
                    "execution_id": str(execution_id),
                    "http_status": resp.status_code,
                },
            )
            return {"spend_logs": [], "error": f"LiteLLM returned {resp.status_code}"}
    except httpx.RequestError as exc:
        logger.warning(
            "LiteLLM spend request failed: execution_id=%s error=%s",
            execution_id,
            exc,
            extra={
                "event": "litellm_spend_request_error",
                "execution_id": str(execution_id),
                "error_type": type(exc).__name__,
            },
        )
        return {"spend_logs": [], "error": str(exc)}


@router.get(
    "/executions/{execution_id}/events",
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
) -> dict:
    """List execution events, optionally after a given sequence number."""
    # Verify execution exists
    exec_check = await executor.get_execution_status(session, execution_id)
    if exec_check is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    result = await session.execute(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.sequence > after)
        .order_by(ExecutionEvent.sequence)
        .limit(limit)
    )
    items = list(result.scalars())
    return {
        "events": [
            {
                "sequence": e.sequence,
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "data": e.data,
            }
            for e in items
        ],
        "next_sequence": items[-1].sequence if items else after,
    }


@router.patch(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionResponse,
    responses={
        404: {"description": "Execution not found"},
        409: {"description": "Execution already in terminal status"},
    },
)
async def cancel_execution(
    execution_id: UUID = Path(..., description="Execution UUID"),
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    """Cancel a queued or running execution."""
    try:
        execution = await executor.cancel_execution(session, execution_id)
    except ExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ExecutionResponse.from_db(execution)


@router.get(
    "/executions/{execution_id}/stream",
    responses={
        200: {"description": "SSE stream of execution status and heartbeat events"},
        404: {"description": "Execution not found"},
        408: {"description": "Stream timeout — execution still running after ~30 minutes"},
    },
)
async def stream_execution(
    execution_id: UUID = Path(..., description="Execution UUID"),
) -> EventSourceResponse:
    """SSE stream of execution status events."""
    # Validate execution exists before starting SSE stream (lightweight status-only query)
    async with async_session() as check_session:
        check = await executor.get_execution_status(check_session, execution_id)
    if check is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    max_polls = 400  # ~30 min with progressive backoff (1s→3s→5s)
    logger.info(
        "SSE stream opened: execution_id=%s",
        execution_id,
        extra={"event": "sse_stream_opened", "execution_id": str(execution_id)},
    )

    async def event_generator() -> AsyncGenerator[dict[str, str]]:
        last_status: ExecutionStatus | None = None
        current_status: ExecutionStatus | None = None
        last_event_seq = -1
        polls = 0
        try:
            while polls < max_polls:
                polls += 1

                async with async_session() as session:
                    if last_status is None:
                        # First poll: no prior status to compare, fetch full execution data
                        execution = await executor.get_execution(session, execution_id)
                        if not execution:
                            msg = f"Execution '{execution_id}' not found"
                            yield {"event": "error", "data": json.dumps({"detail": msg})}
                            break
                        current_status = execution.status
                        data = ExecutionResponse.from_db(execution).model_dump_json()
                        yield {"event": "status", "data": data}
                        last_status = current_status
                    else:
                        current_status = await executor.get_execution_status(session, execution_id)

                        if current_status is None:
                            msg = f"Execution '{execution_id}' not found"
                            yield {"event": "error", "data": json.dumps({"detail": msg})}
                            break

                        if current_status != last_status or current_status in TERMINAL_STATUSES:
                            execution = await executor.get_execution(session, execution_id)
                            if execution:
                                data = ExecutionResponse.from_db(execution).model_dump_json()
                                yield {"event": "status", "data": data}
                            last_status = current_status
                        else:
                            heartbeat = {"status": current_status.value}
                            yield {"event": "heartbeat", "data": json.dumps(heartbeat)}

                    # Stream new execution events
                    event_result = await session.execute(
                        select(ExecutionEvent)
                        .where(
                            ExecutionEvent.execution_id == execution_id,
                            ExecutionEvent.sequence > last_event_seq,
                        )
                        .order_by(ExecutionEvent.sequence)
                        .limit(50)
                    )
                    new_events = list(event_result.scalars())
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

                if current_status is not None and current_status in TERMINAL_STATUSES:
                    logger.info(
                        "SSE stream closed: execution_id=%s status=%s polls=%d",
                        execution_id,
                        current_status.value,
                        polls,
                        extra={
                            "event": "sse_stream_closed",
                            "execution_id": str(execution_id),
                            "final_status": current_status.value,
                            "polls": polls,
                        },
                    )
                    break

                await asyncio.sleep(1 if polls < 30 else 3 if polls < 60 else 5)
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
                },
            )
            yield {"event": "error", "data": json.dumps({"detail": "Internal stream error"})}

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )
