#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./run.sh [OPTIONS]

Build and start all Blackbeard services (API, UI, Postgres, Valkey, LiteLLM).
Extra flags are passed through to 'docker compose up'.

Options:
  --detach, -d    Run containers in background
  --help, -h      Show this help

Environment:
  GOOGLE_APPLICATION_CREDENTIALS   Path to GCP credentials JSON (set in .env)

Examples:
  ./run.sh                  # foreground
  ./run.sh --detach         # background
  ./run.sh --force-recreate # rebuild from scratch
EOF
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) usage ;;
  esac
done

if docker compose version &>/dev/null; then
  COMPOSE="docker compose"
elif command -v podman-compose &>/dev/null; then
  COMPOSE="podman-compose"
else
  echo "Error: neither 'docker compose' nor 'podman-compose' found." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Warning: Created .env from .env.example with default credentials." >&2
  echo "         Change BLACKBEARD_API_KEY, JWT_SECRET, and POSTGRES_PASSWORD before deploying." >&2
  echo ""
fi

creds=$(grep -s '^GOOGLE_APPLICATION_CREDENTIALS=' .env | cut -d= -f2- || echo "deploy/docker/empty-credentials.json")
creds="${creds:-deploy/docker/empty-credentials.json}"
if [ ! -f "$creds" ]; then
  echo "Warning: GOOGLE_APPLICATION_CREDENTIALS file not found: $creds" >&2
  echo "         Set it in .env or ensure the file exists. Using empty placeholder." >&2
  creds="deploy/docker/empty-credentials.json"
fi
# podman-compose requires absolute paths for bind mounts
export GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_APPLICATION_CREDENTIALS="$(cd "$(dirname "$creds")" && pwd)/$(basename "$creds")"

echo "Stopping old containers..."
$COMPOSE down --remove-orphans 2>/dev/null || true

echo "Building images..."
$COMPOSE build

echo ""
echo "Starting Blackbeard..."
echo "  API:      http://localhost:8000"
echo "  UI:       http://localhost:3000"
echo "  LiteLLM:  http://localhost:4000"
echo ""

exec $COMPOSE up "$@"
