"""SQLAlchemy models for execution tracking."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from blackbeard.models.database import Base


class ExecutionType(enum.StrEnum):
    """Execution mode: kickoff, train, test, or flow."""

    KICKOFF = "kickoff"
    TRAIN = "train"
    TEST = "test"
    FLOW = "flow"


class ExecutionStatus(enum.StrEnum):
    """Execution lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)


class TaskStatus(enum.StrEnum):
    """Individual task execution states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Execution(Base):
    """A single crew execution run."""

    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crew_name: Mapped[str] = mapped_column(String(255), nullable=False)
    crew_namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="default",
        server_default=text("'default'"),
    )
    execution_type: Mapped[ExecutionType] = mapped_column(
        Enum(ExecutionType, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ExecutionType.KICKOFF,
        server_default=text("'kickoff'"),
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ExecutionStatus.QUEUED,
        server_default=text("'queued'"),
    )
    n_iterations: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    training_file: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    inputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )

    litellm_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    principal_chain: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list[ExecutionTask]] = relationship(
        "ExecutionTask",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionTask.order",
        lazy="raise",
    )

    __table_args__ = (
        Index(
            "ix_execution_crew_created",
            "crew_name",
            "crew_namespace",
            created_at.desc(),
        ),
        Index("ix_execution_ns_status_created", "crew_namespace", "status", created_at.desc()),
        Index("ix_execution_status_created", "status", "created_at"),
        Index("ix_execution_created_at", "created_at"),
        CheckConstraint("total_tokens >= 0", name="ck_execution_total_tokens_nonneg"),
        CheckConstraint("prompt_tokens >= 0", name="ck_execution_prompt_tokens_nonneg"),
        CheckConstraint("completion_tokens >= 0", name="ck_execution_completion_tokens_nonneg"),
        CheckConstraint("cost_usd >= 0", name="ck_execution_cost_nonneg"),
        CheckConstraint("length(crew_name) >= 1", name="ck_execution_crew_name_nonempty"),
        CheckConstraint("length(crew_namespace) >= 1", name="ck_execution_crew_ns_nonempty"),
        CheckConstraint(
            "status != 'running' OR started_at IS NOT NULL",
            name="ck_execution_running_has_started_at",
        ),
        CheckConstraint(
            "status NOT IN ('completed', 'failed', 'cancelled') OR completed_at IS NOT NULL",
            name="ck_execution_terminal_has_completed_at",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR started_at <= completed_at",
            name="ck_execution_started_before_completed",
        ),
        CheckConstraint(
            "error IS NULL OR status = 'failed'",
            name="ck_execution_error_only_failed",
        ),
        CheckConstraint(
            "status != 'queued' OR started_at IS NULL",
            name="ck_execution_queued_no_started_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Execution {self.id} crew={self.crew_name} "
            f"type={self.execution_type.value} status={self.status.value}>"
        )


class ExecutionTask(Base):
    """Tracks individual task execution within a crew run."""

    __tablename__ = "execution_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=text("'pending'"),
    )
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tokens_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    execution: Mapped[Execution] = relationship("Execution", back_populates="tasks", lazy="raise")
    tool_calls: Mapped[list[ExecutionToolCall]] = relationship(
        "ExecutionToolCall",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ExecutionToolCall.called_at",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint("execution_id", "order", name="uq_exec_task_execution_order"),
        CheckConstraint("tokens_used >= 0", name="ck_exec_task_tokens_nonneg"),
        CheckConstraint("cost_usd >= 0", name="ck_exec_task_cost_nonneg"),
        CheckConstraint('"order" >= 0', name="ck_exec_task_order_nonneg"),
        CheckConstraint("length(task_name) >= 1", name="ck_exec_task_name_nonempty"),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR started_at <= completed_at",
            name="ck_exec_task_started_before_completed",
        ),
        CheckConstraint(
            "status != 'running' OR started_at IS NOT NULL",
            name="ck_exec_task_running_has_started_at",
        ),
        CheckConstraint(
            "status NOT IN ('completed', 'failed') OR completed_at IS NOT NULL",
            name="ck_exec_task_terminal_has_completed_at",
        ),
        CheckConstraint(
            "error IS NULL OR status = 'failed'",
            name="ck_exec_task_error_only_failed",
        ),
    )


class ExecutionToolCall(Base):
    """Tracks individual tool calls within a task execution."""

    __tablename__ = "execution_tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    task: Mapped[ExecutionTask] = relationship(
        "ExecutionTask", back_populates="tool_calls", lazy="raise"
    )

    __table_args__ = (
        Index("ix_tool_call_task_time", "task_id", "called_at"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_tool_call_duration_nonneg",
        ),
        CheckConstraint("length(tool_name) >= 1", name="ck_tool_call_name_nonempty"),
    )


class ExecutionEvent(Base):
    """Append-only log of execution events for real-time streaming."""

    __tablename__ = "execution_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )

    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_exec_event_execution_seq"),
        CheckConstraint("sequence >= 0", name="ck_event_seq_nonneg"),
        CheckConstraint("length(event_type) >= 1", name="ck_event_type_nonempty"),
    )
