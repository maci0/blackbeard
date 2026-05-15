#!/bin/bash
set -euo pipefail
echo "Running database setup..."
timeout "${MIGRATION_TIMEOUT:-120}" python -c '
import asyncio
from sqlalchemy import text
from blackbeard.models.database import engine, Base
from blackbeard.kinds import ResourceKind
from blackbeard.models.execution import ExecutionStatus, TaskStatus
import blackbeard.models.resource
import blackbeard.models.execution

def _create_enum_sql(type_name, enum_cls):
    values = ",".join(f"'"'"'{v.value}'"'"'" for v in enum_cls)
    return f"DO $$ BEGIN CREATE TYPE {type_name} AS ENUM ({values}); EXCEPTION WHEN duplicate_object THEN NULL; END $$"

_NAME_RE = "^[a-z0-9][a-z0-9\\\\-]*$"

# PostgreSQL-only CHECK constraints using the regex ~ operator.
# Defense-in-depth: the API layer already validates these patterns.
# Cannot live in ORM models because tests run on SQLite (no ~ operator).
_PG_CHECKS = [
    f"DO $$ BEGIN ALTER TABLE resources ADD CONSTRAINT ck_resource_name_pattern CHECK (name ~ '"'"'{_NAME_RE}'"'"'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    f"DO $$ BEGIN ALTER TABLE resources ADD CONSTRAINT ck_resource_namespace_pattern CHECK (namespace ~ '"'"'{_NAME_RE}'"'"'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    f"DO $$ BEGIN ALTER TABLE executions ADD CONSTRAINT ck_execution_crew_name_pattern CHECK (crew_name ~ '"'"'{_NAME_RE}'"'"'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
    f"DO $$ BEGIN ALTER TABLE executions ADD CONSTRAINT ck_execution_crew_ns_pattern CHECK (crew_namespace ~ '"'"'{_NAME_RE}'"'"'); EXCEPTION WHEN duplicate_object THEN NULL; END $$",
]

async def migrate():
    async with engine.begin() as conn:
        for stmt in [
            _create_enum_sql("resourcekind", ResourceKind),
            _create_enum_sql("executionstatus", ExecutionStatus),
            _create_enum_sql("taskstatus", TaskStatus),
        ]:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
        # Add PostgreSQL-only regex CHECK constraints (idempotent via EXCEPTION handler)
        for stmt in _PG_CHECKS:
            await conn.execute(text(stmt))
    await engine.dispose()

asyncio.run(migrate())
'
if [ -f alembic.ini ] && [ -d alembic/versions ]; then
  echo "Running alembic migrations..."
  timeout "${MIGRATION_TIMEOUT:-120}" alembic upgrade head
else
  echo "Alembic not configured — skipping migrations."
fi
echo "Starting Blackbeard API..."
exec uvicorn blackbeard.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --log-level "${LOG_LEVEL:-info}" \
  --workers "$(printf '%d' "${WEB_CONCURRENCY:-1}" 2>/dev/null || echo 1)"
