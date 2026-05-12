"""SQLAlchemy models for execution tracking."""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from blackbeard.models.database import Base


class ExecutionStatus(str, enum.Enum):
    """Execution lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
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
    crew_namespace = Column(String(255), nullable=False, default="default")
    status = Column(Enum(ExecutionStatus), nullable=False, default=ExecutionStatus.QUEUED)
    inputs = Column(JSONB, nullable=False, default=dict)
    outputs = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    # Token / cost tracking
    total_tokens = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0.0)

    # LiteLLM virtual key for this execution
    litellm_key = Column(String(255), nullable=True)

    # Langfuse trace link
    langfuse_trace_id = Column(String(255), nullable=True)
    langfuse_trace_url = Column(String(1024), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tasks = relationship("ExecutionTask", back_populates="execution", cascade="all, delete-orphan", order_by="ExecutionTask.order")

    __table_args__ = (
        Index("ix_execution_status", "status"),
        Index("ix_execution_crew", "crew_name", "crew_namespace"),
    )

    def __repr__(self) -> str:
        return f"<Execution {self.id} crew={self.crew_name} status={self.status.value}>"


class ExecutionTask(Base):
    """Tracks individual task execution within a crew run."""

    __tablename__ = "execution_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False)
    task_name = Column(String(255), nullable=False)
    agent_name = Column(String(255), nullable=True)
    order = Column(Integer, nullable=False, default=0)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Token tracking per task
    tokens_used = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0.0)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    execution = relationship("Execution", back_populates="tasks")
    tool_calls = relationship("ExecutionToolCall", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_exec_task_execution", "execution_id"),
    )


class ExecutionToolCall(Base):
    """Tracks individual tool calls within a task execution."""

    __tablename__ = "execution_tool_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("execution_tasks.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(255), nullable=False)
    input_data = Column(JSONB, nullable=True)
    output_data = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    called_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    task = relationship("ExecutionTask", back_populates="tool_calls")

    __table_args__ = (
        Index("ix_tool_call_task", "task_id"),
    )
