#!/bin/bash
set -euo pipefail

# Create .env from .env.example if missing (podman-compose reads it automatically)
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it before running in production."
fi

echo "Starting Blackbeard..."
echo "  API:      http://localhost:8000"
echo "  UI:       http://localhost:3000"
echo "  LiteLLM:  http://localhost:4000"
echo "  Langfuse: http://localhost:3001"
echo ""

podman-compose up "$@"
