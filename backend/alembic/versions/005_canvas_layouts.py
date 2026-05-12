"""Add canvas_layouts table for Studio visual editor.

Revision ID: 005
Revises: 004
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canvas_layouts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("resource_kind", sa.String(255), nullable=False),
        sa.Column("resource_name", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False, server_default="default"),
        sa.Column("layout", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_canvas_layout_resource",
        "canvas_layouts",
        ["resource_kind", "resource_name", "namespace"],
    )


def downgrade() -> None:
    op.drop_table("canvas_layouts")
