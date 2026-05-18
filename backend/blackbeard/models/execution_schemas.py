"""Pydantic schemas for execution API request/response models."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from blackbeard.models.execution import Execution


_SAFE_INPUT_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Keys whose values should be redacted in API responses to prevent
# accidental exposure of secrets passed as crew inputs.
_SENSITIVE_INPUT_KEYS = re.compile(
    r"(password|secret|token|credential|api.?key|auth|private.?key|access.?key)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"


def _redact_sensitive_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of inputs with sensitive-looking values redacted (recursively).

    Returns the original dict unchanged when no keys match and no nested
    structures need walking — avoids a copy on the common-case flat dict.
    """
    if not any(
        _SENSITIVE_INPUT_KEYS.search(k) or isinstance(v, (dict, list))
        for k, v in inputs.items()
    ):
        return inputs
    redacted: dict[str, Any] = {}
    for k, v in inputs.items():
        if _SENSITIVE_INPUT_KEYS.search(k):
            redacted[k] = _REDACTED
        elif isinstance(v, dict):
            redacted[k] = _redact_sensitive_inputs(v)
        elif isinstance(v, list):
            redacted[k] = [
                _redact_sensitive_inputs(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            redacted[k] = v
    return redacted


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
            if not _SAFE_INPUT_KEY.match(k):
                raise ValueError(f"Input key '{k}' is invalid: must match [a-zA-Z_][a-zA-Z0-9_]*")
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
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="Task status",
    )
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
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = Field(
        description="Execution status",
    )
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None = None
    error: str | None = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    initiated_by: str | None = None
    principal_chain: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tasks: list[ExecutionTaskResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(
        cls,
        execution: Execution,
        include_tasks: bool = True,
    ) -> ExecutionResponse:
        """Build response from a SQLAlchemy Execution model.

        When ``include_tasks`` is False, the tasks list is left empty to avoid
        triggering a lazy load (which would fail in async context and is
        expensive in list views).
        """
        tasks: list[ExecutionTaskResponse] = []
        if include_tasks:
            raw_tasks = execution.tasks or []
            tasks = [
                ExecutionTaskResponse.model_construct(
                    id=t.id,
                    task_name=t.task_name,
                    agent_name=t.agent_name,
                    order=t.order,
                    status=t.status.value,
                    output=t.output,
                    error=t.error,
                    tokens_used=t.tokens_used,
                    cost_usd=t.cost_usd,
                    started_at=t.started_at,
                    completed_at=t.completed_at,
                )
                for t in raw_tasks
            ]
        raw_inputs = execution.__dict__.get('inputs')
        initiated_by_raw = execution.__dict__.get('initiated_by')
        return cls.model_construct(
            id=execution.id,
            crew_name=execution.crew_name,
            crew_namespace=execution.crew_namespace,
            status=execution.status.value,
            inputs=_redact_sensitive_inputs(raw_inputs) if raw_inputs else {},
            outputs=execution.__dict__.get('outputs'),
            error=execution.error,
            total_tokens=execution.total_tokens,
            prompt_tokens=execution.prompt_tokens,
            completion_tokens=execution.completion_tokens,
            cost_usd=execution.cost_usd,
            initiated_by=str(initiated_by_raw) if initiated_by_raw else None,
            principal_chain=execution.__dict__.get('principal_chain'),
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


class ExecutionEventItem(BaseModel):
    """Single event from an execution."""

    sequence: int
    event_type: str
    timestamp: datetime
    data: dict[str, Any]


class ExecutionEventsResponse(BaseModel):
    """Response for listing execution events."""

    events: list[ExecutionEventItem]
    next_sequence: int
    has_more: bool = False
