#!/bin/bash
set -euo pipefail
echo "Running database migrations..."
timeout "${MIGRATION_TIMEOUT:-120}" alembic upgrade head
echo "Starting Blackbeard API..."
exec uvicorn blackbeard.main:app --host 0.0.0.0 --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}"
