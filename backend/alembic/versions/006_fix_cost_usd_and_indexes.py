"""Fix cost_usd Float→Numeric and add missing created_at index.

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix cost_usd from Float to Numeric(10, 6)
    op.alter_column(
        "executions", "cost_usd",
        type_=sa.Numeric(10, 6),
        existing_type=sa.Float,
        existing_nullable=False,
        existing_server_default="0.0",
    )
    op.alter_column(
        "execution_tasks", "cost_usd",
        type_=sa.Numeric(10, 6),
        existing_type=sa.Float,
        existing_nullable=False,
        existing_server_default="0.0",
    )
    # Add missing created_at index on executions
    op.create_index("ix_execution_created_at", "executions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_execution_created_at", table_name="executions")
    op.alter_column(
        "executions", "cost_usd",
        type_=sa.Float,
        existing_type=sa.Numeric(10, 6),
        existing_nullable=False,
        existing_server_default="0.0",
    )
    op.alter_column(
        "execution_tasks", "cost_usd",
        type_=sa.Float,
        existing_type=sa.Numeric(10, 6),
        existing_nullable=False,
        existing_server_default="0.0",
    )
