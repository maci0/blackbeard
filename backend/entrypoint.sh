#!/bin/bash
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Starting Blackbeard API..."
exec uvicorn blackbeard.main:app --host 0.0.0.0 --port 8000
