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

async def migrate():
    async with engine.begin() as conn:
        for stmt in [
            _create_enum_sql("resourcekind", ResourceKind),
            _create_enum_sql("executionstatus", ExecutionStatus),
            _create_enum_sql("taskstatus", TaskStatus),
        ]:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(migrate())
'
echo "Stamping alembic version..."
alembic stamp head 2>/dev/null || true
echo "Running migrations..."
alembic upgrade head 2>/dev/null || true
echo "Starting Blackbeard API..."
exec uvicorn blackbeard.main:app --host 0.0.0.0 --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}"
