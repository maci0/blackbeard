"""Add AgentPolicy and Guardrail to ResourceKind enum.

Revision ID: 004
Revises: 003
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum values to the resourcekind type
    op.execute("ALTER TYPE resourcekind ADD VALUE IF NOT EXISTS 'AGENT_POLICY'")
    op.execute("ALTER TYPE resourcekind ADD VALUE IF NOT EXISTS 'GUARDRAIL'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # This would require recreating the type, which is complex
    pass
