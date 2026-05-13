#!/bin/bash
set -euo pipefail
echo "Running database setup..."
timeout "${MIGRATION_TIMEOUT:-120}" python -c "
import asyncio
from sqlalchemy import text
from blackbeard.models.database import engine, Base
import blackbeard.models.resource
import blackbeard.models.execution

async def migrate():
    async with engine.begin() as conn:
        for stmt in [
            \"DO \$\$ BEGIN CREATE TYPE resourcekind AS ENUM ('Agent','Task','Crew','Tool','LLMConnection','AgentPolicy','Guardrail'); EXCEPTION WHEN duplicate_object THEN NULL; END \$\$\",
            \"DO \$\$ BEGIN CREATE TYPE executionstatus AS ENUM ('queued','running','completed','failed','cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END \$\$\",
            \"DO \$\$ BEGIN CREATE TYPE taskstatus AS ENUM ('pending','running','completed','failed'); EXCEPTION WHEN duplicate_object THEN NULL; END \$\$\",
        ]:
            await conn.execute(text(stmt))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(migrate())
"
echo "Starting Blackbeard API..."
exec uvicorn blackbeard.main:app --host 0.0.0.0 --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}"
