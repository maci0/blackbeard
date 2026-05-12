"""REST API endpoints for crew execution lifecycle management."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.engine import executor
from blackbeard.engine.executor import ExecutionError
from blackbeard.models.database import get_session, async_session
from blackbeard.models.execution import ExecutionStatus
from blackbeard.models.execution_schemas import (
    KickoffRequest,
    ExecutionResponse,
    ExecutionListResponse,
)

from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["executions"])


@router.post("/crews/{crew_name}/kickoff", response_model=ExecutionResponse, status_code=202)
async def kickoff_crew(
    crew_name: str = Path(..., pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=255),
    body: KickoffRequest = Body(...),
    namespace: str = Query(default="default", pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=255),
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    """Kick off a crew execution. Returns immediately with status=queued."""
    try:
        execution = await executor.kickoff(session, crew_name, body.inputs, namespace)
    except ExecutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExecutionResponse.from_db(execution)


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    crew_name: str | None = Query(default=None, pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=255),
    namespace: str | None = Query(default=None, pattern=r"^[a-z0-9][a-z0-9\-]*$", max_length=255),
    status: ExecutionStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ExecutionListResponse:
    """List executions with optional filters."""
    try:
        items, total = await executor.list_executions(
            session,
            crew_name=crew_name,
            namespace=namespace,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ExecutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExecutionListResponse(
        items=[ExecutionResponse.from_db(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    """Get execution details by ID."""
    execution = await executor.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return ExecutionResponse.from_db(execution)


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    execution_id: UUID,
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


@router.get("/executions/{execution_id}/stream")
async def stream_execution(execution_id: UUID):
    """SSE stream of execution status events."""
    # Validate execution exists before starting SSE stream
    async with async_session() as check_session:
        check = await executor.get_execution(check_session, execution_id)
    if not check:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")

    max_polls = 1800  # 30 minutes at 1s intervals

    async def event_generator():
        polls = 0
        while polls < max_polls:
            polls += 1
            async with async_session() as poll_session:
                execution = await executor.get_execution(poll_session, execution_id)

            if not execution:
                yield {"event": "error", "data": json.dumps({"message": f"Execution '{execution_id}' not found"})}
                break

            yield {"event": "status", "data": json.dumps(ExecutionResponse.from_db(execution).model_dump(mode="json"))}

            if execution.status.value in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(1)
        else:
            yield {"event": "error", "data": json.dumps({"message": "Stream timeout — execution still running after 30 minutes"})}

    return EventSourceResponse(event_generator())
