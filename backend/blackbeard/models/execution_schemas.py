"""Pydantic schemas for execution API request/response models."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class KickoffRequest(BaseModel):
    """Request to kick off a crew execution."""

    inputs: dict = Field(default_factory=dict)


class ExecutionTaskResponse(BaseModel):
    """Response for a single task within an execution."""

    id: UUID
    task_name: str
    agent_name: str | None = None
    order: int
    status: str
    output: str | None = None
    error: str | None = None
    tokens_used: int = 0
    cost_usd: Decimal = Decimal("0")
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExecutionResponse(BaseModel):
    """Response for an execution."""

    id: UUID
    crew_name: str
    crew_namespace: str
    status: str
    inputs: dict
    outputs: dict | None = None
    error: str | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tasks: list[ExecutionTaskResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, execution) -> "ExecutionResponse":  # type: ignore[no-untyped-def]
        """Build response from a SQLAlchemy Execution model."""
        tasks = []
        try:
            raw_tasks = execution.tasks or []
        except Exception:
            raw_tasks = []  # Tasks not eagerly loaded (e.g., list endpoint)
        for t in raw_tasks:
            tasks.append(ExecutionTaskResponse(
                id=t.id,
                task_name=t.task_name,
                agent_name=t.agent_name,
                order=t.order,
                status=t.status.value if hasattr(t.status, 'value') else t.status,
                output=t.output,
                error=t.error,
                tokens_used=t.tokens_used,
                cost_usd=t.cost_usd,
                started_at=t.started_at,
                completed_at=t.completed_at,
            ))
        return cls(
            id=execution.id,
            crew_name=execution.crew_name,
            crew_namespace=execution.crew_namespace,
            status=execution.status.value if hasattr(execution.status, 'value') else execution.status,
            inputs=execution.inputs or {},
            outputs=execution.outputs,
            error=execution.error,
            total_tokens=execution.total_tokens,
            prompt_tokens=execution.prompt_tokens,
            completion_tokens=execution.completion_tokens,
            cost_usd=execution.cost_usd,
            langfuse_trace_id=execution.langfuse_trace_id,
            langfuse_trace_url=execution.langfuse_trace_url,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            tasks=tasks,
        )


class ExecutionListResponse(BaseModel):
    """Paginated list of executions."""

    items: list[ExecutionResponse]
    total: int
    limit: int = 50
    offset: int = 0
    has_more: bool = False
