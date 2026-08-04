"""Fix list index direction and drop a redundant index.

- Recreate ix_execution_created_id as (created_at DESC, id DESC): migration
  011 created it as (created_at DESC, id ASC), which cannot serve the
  list_executions ORDER BY created_at DESC, id DESC in either scan direction.
  Fresh installs (create_all) already have the correct definition; this
  brings migrated databases in line.
- Drop ix_execution_created_at: its leading column is covered by the
  (created_at DESC, id DESC) composite, so it only adds write overhead.

Revision ID: 013
Revises: 012
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_execution_created_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_created_id
        ON executions (created_at DESC, id DESC)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_execution_created_at")


def downgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_created_at
        ON executions (created_at)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_execution_created_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_created_id
        ON executions (created_at DESC, id)
        """
    )
