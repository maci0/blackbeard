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

# Admin password — defaults to "Blackbeard1" for dev convenience
export BLACKBEARD_ADMIN_PASSWORD="${BLACKBEARD_ADMIN_PASSWORD:-Blackbeard1}"
DEBUG_MODE=$(grep -s '^DEBUG=' .env | cut -d= -f2 || echo "false")

echo ""
echo "Starting Blackbeard..."
echo "  UI:       http://localhost:3000"
echo "  API:      http://localhost:8000"
echo "  LiteLLM:  http://localhost:4000"
if [ "$DEBUG_MODE" = "true" ]; then
  echo ""
  echo "  Default login:"
  echo "    Email:    admin@blackbeard.sh"
  echo "    Password: (set via BLACKBEARD_ADMIN_PASSWORD, default: see deploy/seed.sh)"
  echo ""
  echo "  (Set BLACKBEARD_ADMIN_PASSWORD to change. Run deploy/seed.sh after startup.)"
fi
echo ""

exec $COMPOSE up "$@"
