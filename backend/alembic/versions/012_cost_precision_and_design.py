"""Widen cost_usd precision for multi-agent spend headroom.

Numeric(10, 6) capped at $9,999.999999 and could overflow high-token runs.
Numeric(14, 6) allows up to ~$99,999,999.999999.

Revision ID: 012
Revises: 011
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE executions
            ALTER COLUMN cost_usd TYPE NUMERIC(14, 6)
            USING cost_usd;
        EXCEPTION
            WHEN undefined_table THEN NULL;
            WHEN undefined_column THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE execution_tasks
            ALTER COLUMN cost_usd TYPE NUMERIC(14, 6)
            USING cost_usd;
        EXCEPTION
            WHEN undefined_table THEN NULL;
            WHEN undefined_column THEN NULL;
        END $$
        """
    )


def downgrade() -> None:
    # Truncating precision is lossy; only reverse type for empty/small values.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE execution_tasks
            ALTER COLUMN cost_usd TYPE NUMERIC(10, 6)
            USING cost_usd;
        EXCEPTION
            WHEN undefined_table THEN NULL;
            WHEN undefined_column THEN NULL;
            WHEN numeric_value_out_of_range THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE executions
            ALTER COLUMN cost_usd TYPE NUMERIC(10, 6)
            USING cost_usd;
        EXCEPTION
            WHEN undefined_table THEN NULL;
            WHEN undefined_column THEN NULL;
            WHEN numeric_value_out_of_range THEN NULL;
        END $$
        """
    )
