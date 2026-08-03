#!/usr/bin/env bash
# Copy backend kind registry + schemas into the CLI package (offline validate).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$ROOT/backend/blackbeard/kinds.py" "$ROOT/cli/blackbeard_cli/kinds.py"
cp "$ROOT/backend/blackbeard/resources/spec_schemas.py" "$ROOT/cli/blackbeard_cli/resources/spec_schemas.py"
# validator is intentionally thinner in CLI; only re-copy if you merge paths carefully.
echo "Synced kinds.py and spec_schemas.py from backend → cli"
