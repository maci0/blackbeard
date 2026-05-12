"""Add resources and resource_refs tables.

Revision ID: 002
Revises: 001
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum values for ResourceKind
resource_kind_enum = sa.Enum(
    "AGENT", "TASK", "CREW", "TOOL", "LLM_CONNECTION",
    name="resourcekind",
)


def upgrade() -> None:
    # Create the enum type
    resource_kind_enum.create(op.get_bind(), checkfirst=True)

    # Resources table
    op.create_table(
        "resources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", resource_kind_enum, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False, server_default="default"),
        sa.Column("labels", JSONB, nullable=False, server_default="{}"),
        sa.Column("spec", JSONB, nullable=False),
        sa.Column("raw_yaml", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_resource_kind", "resources", ["kind"])
    op.create_index("ix_resource_ns_kind", "resources", ["namespace", "kind"])
    op.create_unique_constraint("uq_resource_kind_name_ns", "resources", ["kind", "name", "namespace"])

    # Resource refs table
    op.create_table(
        "resource_refs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_kind", resource_kind_enum, nullable=False),
        sa.Column("target_name", sa.String(255), nullable=False),
        sa.Column("target_namespace", sa.String(255), nullable=False, server_default="default"),
        sa.Column("ref_field", sa.String(255), nullable=False),
    )
    op.create_index("ix_ref_source", "resource_refs", ["source_id"])
    op.create_index("ix_ref_target", "resource_refs", ["target_kind", "target_name", "target_namespace"])


def downgrade() -> None:
    op.drop_table("resource_refs")
    op.drop_table("resources")
    resource_kind_enum.drop(op.get_bind(), checkfirst=True)
