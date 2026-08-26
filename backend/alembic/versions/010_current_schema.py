"""Current schema baseline: matches Base.metadata as of this commit.

This migration exists so that ``alembic stamp head`` can mark existing
databases as up-to-date without re-running old migrations.

Revision ID: 010
Revises: None
Create Date: 2026-05-14
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = None  # fresh baseline, ignore old migrations
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema already created by Base.metadata.create_all() in entrypoint.sh.
    # This migration exists only as a version marker.
    pass


def downgrade() -> None:
    pass
