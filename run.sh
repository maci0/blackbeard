#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./run.sh [OPTIONS]

Build and start all Blackbeard services (API, UI, Postgres, Valkey, LiteLLM).
Extra flags are passed through to 'docker compose up'.

Options:
  --detach, -d    Run containers in background
  --prod          Use only docker-compose.yaml (ignore docker-compose.override.yaml
                  bind mounts). Runs the built images as shipped.
  --help, -h      Show this help

Environment:
  GOOGLE_APPLICATION_CREDENTIALS   Path to GCP credentials JSON (set in .env)

Examples:
  ./run.sh                  # foreground (dev override mounts backend source)
  ./run.sh --detach         # background
  ./run.sh --prod           # production-like: no source bind mounts
  ./run.sh --force-recreate # rebuild from scratch
EOF
  exit 0
}

PROD_MODE=false
COMPOSE_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --help|-h) usage ;;
    --prod) PROD_MODE=true ;;
    *) COMPOSE_ARGS+=("$arg") ;;
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

if [ "$PROD_MODE" = "true" ]; then
  # Skip auto-loaded docker-compose.override.yaml so the API runs from the image.
  export COMPOSE_FILE=docker-compose.yaml
  echo "Production-like mode: COMPOSE_FILE=docker-compose.yaml (no source bind mounts)"
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Warning: Created .env from .env.example with local-dev defaults (DEBUG=true)." >&2
  echo "         For production: set DEBUG=false and replace BLACKBEARD_API_KEY," >&2
  echo "         JWT_SECRET, LITELLM_MASTER_KEY, POSTGRES_PASSWORD, and VALKEY_PASSWORD." >&2
  echo ""
fi

# Fail early in --prod when .env still has insecure example values (API would refuse anyway).
if [ "$PROD_MODE" = "true" ]; then
  env_val() { grep -sE "^$1=" .env | head -1 | cut -d= -f2- || true; }
  fail_prod() { echo "Error: --prod blocked: $1" >&2; exit 1; }
  [ "$(env_val DEBUG)" = "true" ] && fail_prod "DEBUG=true (set DEBUG=false for production)"
  case "$(env_val BLACKBEARD_API_KEY)" in
    ""|change-me-in-production) fail_prod "BLACKBEARD_API_KEY is missing or the insecure default" ;;
  esac
  case "$(env_val JWT_SECRET)" in
    ""|change-jwt-secret-in-production!|change-jwt-secret-in-production)
      fail_prod "JWT_SECRET is missing or the insecure default" ;;
  esac
  case "$(env_val LITELLM_MASTER_KEY)" in
    ""|sk-litellm-master-key) fail_prod "LITELLM_MASTER_KEY is missing or the insecure default" ;;
  esac
  case "$(env_val POSTGRES_PASSWORD)" in
    ""|blackbeard) fail_prod "POSTGRES_PASSWORD is missing or the insecure default" ;;
  esac
  case "$(env_val VALKEY_PASSWORD)" in
    ""|valkey-dev-secret) fail_prod "VALKEY_PASSWORD is missing or the insecure default" ;;
  esac
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

# Reproducible image metadata: pin to the commit timestamp when available.
if [ -z "${SOURCE_DATE_EPOCH:-}" ] && command -v git &>/dev/null \
  && git rev-parse --is-inside-work-tree &>/dev/null; then
  SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct 2>/dev/null || true)"
fi
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

echo "Stopping old containers..."
$COMPOSE down --remove-orphans 2>/dev/null || true

echo "Building images..."
$COMPOSE build

DEBUG_MODE=$(grep -s '^DEBUG=' .env | cut -d= -f2 || echo "false")
# Admin password: only needed in DEBUG mode for seed.sh
if [ "$DEBUG_MODE" = "true" ]; then
  export BLACKBEARD_ADMIN_PASSWORD="${BLACKBEARD_ADMIN_PASSWORD:-Blackbeard1}"
fi

echo ""
echo "Starting Blackbeard..."
echo "  UI:       http://localhost:3000"
echo "  API:      http://localhost:8000"
echo "  LiteLLM:  http://localhost:4000"
if [ "$DEBUG_MODE" = "true" ]; then
  echo ""
  echo "  Default login:"
  echo "    Email:    admin@blackbeard.sh"
  echo "    Password: (set BLACKBEARD_ADMIN_PASSWORD or see .admin-credentials after seeding)"
  echo ""
  echo "  Run deploy/seed.sh after startup to create the admin user."
  echo "  Credentials will be saved to .admin-credentials"
fi
echo ""

exec $COMPOSE up "${COMPOSE_ARGS[@]+"${COMPOSE_ARGS[@]}"}"
