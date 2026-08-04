"""Multi-replica safety: execution ownership and cron firing dedup.

- executions.worker_id: identity of the API instance owning the background
  thread ("temporal" for durable workflows). Startup recovery only claims
  its own rows, so a restarting replica cannot fail work running elsewhere.
- automation_runs: one row per (automation, scheduled firing time) with a
  unique constraint. Every replica runs its own scheduler; the INSERT winner
  fires, losers skip. Fresh installs get this table from create_all; this
  brings migrated databases in line.

Revision ID: 014
Revises: 013
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS worker_id VARCHAR(255)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_runs (
            id UUID PRIMARY KEY,
            automation_name VARCHAR(255) NOT NULL,
            scheduled_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_automation_run_name_time UNIQUE (automation_name, scheduled_at),
            CONSTRAINT ck_automation_run_name_nonempty CHECK (length(automation_name) >= 1)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_runs")
    op.execute("ALTER TABLE executions DROP COLUMN IF EXISTS worker_id")
