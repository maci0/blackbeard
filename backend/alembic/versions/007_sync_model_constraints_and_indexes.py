"""Sync model constraints and indexes missed in earlier migrations.

Adds: GIN index on resources.labels, check constraints on resources and
executions tables, composite index on executions(status, created_at),
unique constraint on execution_tasks(execution_id, order), and
created_at column on execution_tasks.

Revision ID: 007
Revises: 006
Create Date: 2026-05-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- resources table ---
    op.create_index(
        "ix_resource_labels", "resources", ["labels"],
        postgresql_using="gin",
    )
    op.create_check_constraint(
        "ck_resource_version_positive", "resources",
        "version >= 1",
    )

    # --- executions table ---
    op.create_index(
        "ix_execution_status_created", "executions",
        ["status", "created_at"],
    )
    op.create_check_constraint(
        "ck_execution_total_tokens_nonneg", "executions",
        "total_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_execution_prompt_tokens_nonneg", "executions",
        "prompt_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_execution_completion_tokens_nonneg", "executions",
        "completion_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_execution_cost_nonneg", "executions",
        "cost_usd >= 0",
    )

    # --- execution_tasks table ---
    op.add_column(
        "execution_tasks",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_exec_task_execution_order", "execution_tasks",
        ["execution_id", "order"],
    )
    op.create_check_constraint(
        "ck_exec_task_tokens_nonneg", "execution_tasks",
        "tokens_used >= 0",
    )
    op.create_check_constraint(
        "ck_exec_task_cost_nonneg", "execution_tasks",
        "cost_usd >= 0",
    )


def downgrade() -> None:
    # --- execution_tasks ---
    op.drop_constraint("ck_exec_task_cost_nonneg", "execution_tasks", type_="check")
    op.drop_constraint("ck_exec_task_tokens_nonneg", "execution_tasks", type_="check")
    op.drop_constraint("uq_exec_task_execution_order", "execution_tasks", type_="unique")
    op.drop_column("execution_tasks", "created_at")

    # --- executions ---
    op.drop_constraint("ck_execution_cost_nonneg", "executions", type_="check")
    op.drop_constraint("ck_execution_completion_tokens_nonneg", "executions", type_="check")
    op.drop_constraint("ck_execution_prompt_tokens_nonneg", "executions", type_="check")
    op.drop_constraint("ck_execution_total_tokens_nonneg", "executions", type_="check")
    op.drop_index("ix_execution_status_created", table_name="executions")

    # --- resources ---
    op.drop_constraint("ck_resource_version_positive", "resources", type_="check")
    op.drop_index("ix_resource_labels", table_name="resources")
