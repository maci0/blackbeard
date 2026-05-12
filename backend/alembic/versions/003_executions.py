"""Add executions, execution_tasks, execution_tool_calls tables.

Revision ID: 003
Revises: 002
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

execution_status_enum = sa.Enum(
    "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
    name="executionstatus",
)

task_status_enum = sa.Enum(
    "PENDING", "RUNNING", "COMPLETED", "FAILED",
    name="taskstatus",
)


def upgrade() -> None:
    execution_status_enum.create(op.get_bind(), checkfirst=True)
    task_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("crew_name", sa.String(255), nullable=False),
        sa.Column("crew_namespace", sa.String(255), nullable=False, server_default="default"),
        sa.Column("status", execution_status_enum, nullable=False, server_default="QUEUED"),
        sa.Column("inputs", JSONB, nullable=False, server_default="{}"),
        sa.Column("outputs", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("litellm_key", sa.String(255), nullable=True),
        sa.Column("langfuse_trace_id", sa.String(255), nullable=True),
        sa.Column("langfuse_trace_url", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_execution_status", "executions", ["status"])
    op.create_index("ix_execution_crew", "executions", ["crew_name", "crew_namespace"])

    op.create_table(
        "execution_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("execution_id", UUID(as_uuid=True), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=True),
        sa.Column("order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", task_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exec_task_execution", "execution_tasks", ["execution_id"])

    op.create_table(
        "execution_tool_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("execution_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(255), nullable=False),
        sa.Column("input_data", JSONB, nullable=True),
        sa.Column("output_data", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tool_call_task", "execution_tool_calls", ["task_id"])


def downgrade() -> None:
    op.drop_table("execution_tool_calls")
    op.drop_table("execution_tasks")
    op.drop_table("executions")
    task_status_enum.drop(op.get_bind(), checkfirst=True)
    execution_status_enum.drop(op.get_bind(), checkfirst=True)
