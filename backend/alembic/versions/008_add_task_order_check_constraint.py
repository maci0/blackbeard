"""Add missing check constraint on execution_tasks.order.

The model defines ck_exec_task_order_nonneg but no prior migration
creates it, leaving production databases without this enforcement.

Revision ID: 008
Revises: 007
Create Date: 2026-05-13

"""
from collections.abc import Sequence

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_exec_task_order_nonneg", "execution_tasks",
        '"order" >= 0',
    )


def downgrade() -> None:
    op.drop_constraint("ck_exec_task_order_nonneg", "execution_tasks", type_="check")
