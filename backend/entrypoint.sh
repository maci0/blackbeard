#!/bin/bash
set -euo pipefail
echo "Running database setup..."
timeout "${MIGRATION_TIMEOUT:-120}" python -m blackbeard.db_setup
if [ -f alembic.ini ] && [ -d alembic/versions ]; then
  echo "Running alembic migrations..."
  timeout "${MIGRATION_TIMEOUT:-120}" alembic upgrade head
else
  echo "Alembic not configured: skipping migrations."
fi
echo "Starting Blackbeard API..."
reload_flag=""
if [ "${DEBUG:-false}" = "true" ] && [ "${WEB_CONCURRENCY:-1}" = "1" ]; then
  reload_flag="--reload"
fi
if [ -n "${LOG_LEVEL:-}" ]; then
  # uvicorn's --log-level choices are lowercase and case-sensitive
  uvi_log_level="${LOG_LEVEL,,}"
elif [ "${DEBUG:-false}" = "true" ]; then
  uvi_log_level="debug"
else
  uvi_log_level="info"
fi
# WEB_CONCURRENCY must be a positive integer or uvicorn refuses to start.
# Validate here so a stray value cannot crash the container at boot.
workers="${WEB_CONCURRENCY:-1}"
case "$workers" in
  ""|*[!0-9]*) workers=1 ;;
esac
if (( workers < 1 )); then
  workers=1
fi

exec uvicorn blackbeard.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --log-level "$uvi_log_level" \
  --workers "$workers" \
  ${reload_flag:+"$reload_flag"}
