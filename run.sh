#!/bin/bash
set -euo pipefail

if command -v docker compose &>/dev/null; then
  COMPOSE="docker compose"
elif command -v podman-compose &>/dev/null; then
  COMPOSE="podman-compose"
else
  echo "Error: neither 'docker compose' nor 'podman-compose' found." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it before running in production."
fi

# shellcheck source=.env
. ./.env 2>/dev/null || true
creds="${GOOGLE_APPLICATION_CREDENTIALS:-deploy/docker/empty-credentials.json}"
if [ ! -f "$creds" ]; then
  echo "Warning: GOOGLE_APPLICATION_CREDENTIALS file not found: $creds" >&2
  echo "         Set it in .env or ensure the file exists. Using empty placeholder." >&2
  export GOOGLE_APPLICATION_CREDENTIALS=deploy/docker/empty-credentials.json
fi

echo "Stopping old containers..."
$COMPOSE down --remove-orphans 2>/dev/null || true

echo "Building images..."
$COMPOSE build

echo ""
echo "Starting Blackbeard..."
echo "  API:      http://localhost:8000"
echo "  UI:       http://localhost:3000"
echo "  LiteLLM:  http://localhost:4000"
echo "  Langfuse: http://localhost:3001"
echo ""

$COMPOSE up "$@"
