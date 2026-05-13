"""SQLAlchemy models for execution tracking."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
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
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ExecutionStatus.QUEUED,
        server_default=text("'queued'"),
    )
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

    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    langfuse_trace_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

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
    )

    __table_args__ = (
        Index("ix_execution_crew", "crew_name", "crew_namespace"),
        Index("ix_execution_namespace", "crew_namespace"),
        Index("ix_execution_status_created", "status", "created_at"),
        Index("ix_execution_created_at", "created_at"),
        CheckConstraint("total_tokens >= 0", name="ck_execution_total_tokens_nonneg"),
        CheckConstraint("prompt_tokens >= 0", name="ck_execution_prompt_tokens_nonneg"),
        CheckConstraint("completion_tokens >= 0", name="ck_execution_completion_tokens_nonneg"),
        CheckConstraint("cost_usd >= 0", name="ck_execution_cost_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<Execution {self.id} crew={self.crew_name} status={self.status.value}>"


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

    execution: Mapped[Execution] = relationship("Execution", back_populates="tasks")
    tool_calls: Mapped[list[ExecutionToolCall]] = relationship(
        "ExecutionToolCall",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ExecutionToolCall.called_at",
    )

    __table_args__ = (
        Index("ix_exec_task_execution", "execution_id"),
        UniqueConstraint("execution_id", "order", name="uq_exec_task_execution_order"),
        CheckConstraint("tokens_used >= 0", name="ck_exec_task_tokens_nonneg"),
        CheckConstraint("cost_usd >= 0", name="ck_exec_task_cost_nonneg"),
        CheckConstraint('"order" >= 0', name="ck_exec_task_order_nonneg"),
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

    task: Mapped[ExecutionTask] = relationship("ExecutionTask", back_populates="tool_calls")

    __table_args__ = (
        Index("ix_tool_call_task", "task_id"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_tool_call_duration_nonneg",
        ),
    )
