"""Data layer hardening: indexes, webhook URL check, drop redundant index.

- Add composite index for list_executions ORDER BY created_at DESC, id
- Add partial index for non-terminal execution recovery queries
- Recreate audit request_id index as partial (skip NULL rows)
- Drop redundant partial ix_users_api_key (column unique already indexes)
- Enforce webhook URL scheme at the database level

Revision ID: 011
Revises: 010
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # list_executions: ORDER BY created_at DESC, id DESC
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_created_id
        ON executions (created_at DESC, id)
        """
    )
    # recover_stale_executions / cleanup_orphaned_keys filter non-terminal rows
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_execution_nonterminal
        ON executions (status, created_at)
        WHERE status IN ('queued', 'running')
        """
    )
    # Smaller audit request_id index (most rows have NULL request_id)
    op.execute("DROP INDEX IF EXISTS ix_audit_request_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_request_id
        ON audit_logs (request_id)
        WHERE request_id IS NOT NULL
        """
    )
    # Redundant with unique constraint index on users.api_key
    op.execute("DROP INDEX IF EXISTS ix_users_api_key")
    # DB-level scheme guard (idempotent)
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE webhooks
            ADD CONSTRAINT ck_webhook_url_scheme
            CHECK (url LIKE 'http://%' OR url LIKE 'https://%');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
            WHEN undefined_table THEN NULL;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE webhooks DROP CONSTRAINT IF EXISTS ck_webhook_url_scheme;
        EXCEPTION
            WHEN undefined_table THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_users_api_key
        ON users (api_key)
        WHERE api_key IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_audit_request_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_request_id
        ON audit_logs (request_id)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_execution_nonterminal")
    op.execute("DROP INDEX IF EXISTS ix_execution_created_id")
