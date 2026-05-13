"""Pydantic schemas for execution API request/response models."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from blackbeard.models.execution import Execution


def _enum_value(v: object) -> str:
    return v.value if isinstance(v, enum.Enum) else str(v)


def _exceeds_depth(obj: object, limit: int = 10, current: int = 0) -> bool:
    if current >= limit:
        return True
    if isinstance(obj, dict):
        return any(_exceeds_depth(v, limit, current + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_exceeds_depth(v, limit, current + 1) for v in obj)
    return False


class KickoffRequest(BaseModel):
    """Request to kick off a crew execution."""

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        max_length=100,
        description="Key-value inputs passed to the crew (max 100 entries)",
    )

    @model_validator(mode="after")
    def _validate_input_sizes(self) -> KickoffRequest:
        max_entries = 100
        max_key_len = 256
        max_val_len = 50_000
        if len(self.inputs) > max_entries:
            raise ValueError(
                f"Too many input entries ({len(self.inputs)}), maximum is {max_entries}"
            )
        for k, v in self.inputs.items():
            if not isinstance(k, str) or len(k) > max_key_len:
                raise ValueError(f"Input key must be a string of at most {max_key_len} chars")
            if isinstance(v, str) and len(v) > max_val_len:
                raise ValueError(f"Input value for '{k}' exceeds {max_val_len} chars")
        if _exceeds_depth(self.inputs):
            raise ValueError("Input nesting exceeds maximum depth of 10 levels")
        return self


class ExecutionTaskResponse(BaseModel):
    """Response for a single task within an execution."""

    id: UUID
    task_name: str
    agent_name: str | None = None
    order: int
    status: str = Field(description="Task status: pending, running, completed, or failed")
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
    status: str = Field(
        description="Execution status: queued, running, completed, failed, or cancelled",
    )
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None = None
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
    def from_db(cls, execution: Execution) -> ExecutionResponse:
        """Build response from a SQLAlchemy Execution model."""
        raw_tasks = execution.tasks or []
        tasks = [
            ExecutionTaskResponse.model_construct(
                id=t.id,
                task_name=t.task_name,
                agent_name=t.agent_name,
                order=t.order,
                status=_enum_value(t.status),
                output=t.output,
                error=t.error,
                tokens_used=t.tokens_used,
                cost_usd=t.cost_usd,
                started_at=t.started_at,
                completed_at=t.completed_at,
            )
            for t in raw_tasks
        ]
        return cls.model_construct(
            id=execution.id,
            crew_name=execution.crew_name,
            crew_namespace=execution.crew_namespace,
            status=_enum_value(execution.status),
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
    limit: int = 100
    offset: int = 0
    has_more: bool = False
