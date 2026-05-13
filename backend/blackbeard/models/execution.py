"""SQLAlchemy models for execution tracking."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
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
from sqlalchemy.orm import relationship

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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crew_name = Column(String(255), nullable=False)
    crew_namespace = Column(
        String(255),
        nullable=False,
        default="default",
        server_default=text("'default'"),
    )
    status = Column(
        Enum(ExecutionStatus, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=ExecutionStatus.QUEUED,
        server_default=text("'queued'"),
    )
    inputs = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    outputs = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    # Token / cost tracking
    total_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    prompt_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    completion_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0.0, server_default=text("0"))

    # LiteLLM virtual key for this execution
    litellm_key = Column(String(255), nullable=True)

    # Langfuse trace link
    langfuse_trace_id = Column(String(255), nullable=True)
    langfuse_trace_url = Column(String(1024), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tasks = relationship(
        "ExecutionTask",
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="ExecutionTask.order",
    )

    __table_args__ = (
        Index("ix_execution_crew", "crew_name", "crew_namespace"),
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_name = Column(String(255), nullable=False)
    agent_name = Column(String(255), nullable=True)
    order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    status = Column(
        Enum(TaskStatus, create_type=False, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=text("'pending'"),
    )
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Token tracking per task
    tokens_used = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0.0, server_default=text("0"))

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    execution = relationship("Execution", back_populates="tasks")
    tool_calls = relationship(
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name = Column(String(255), nullable=False)
    input_data = Column(JSONB, nullable=True)
    output_data = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    called_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    task = relationship("ExecutionTask", back_populates="tool_calls")

    __table_args__ = (
        Index("ix_tool_call_task", "task_id"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_tool_call_duration_nonneg",
        ),
    )
