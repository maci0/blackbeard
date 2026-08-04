#!/usr/bin/env bash
# Copy backend kind registry + schemas into the CLI package (offline validate).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$ROOT/backend/blackbeard/kinds.py" "$ROOT/cli/blackbeard_cli/kinds.py"
cp "$ROOT/backend/blackbeard/resources/spec_schemas.py" "$ROOT/cli/blackbeard_cli/resources/spec_schemas.py"
# Standalone package: rewrite backend import so the CLI does not depend on blackbeard.
# Portable in-place edit (GNU sed -i and BSD sed -i '' differ).
_schema="$ROOT/cli/blackbeard_cli/resources/spec_schemas.py"
_tmp="$(mktemp)"
sed 's/from blackbeard\.kinds import/from blackbeard_cli.kinds import/' "$_schema" > "$_tmp"
mv "$_tmp" "$_schema"
# validator is intentionally thinner in CLI; only re-copy if you merge paths carefully.
echo "Synced kinds.py and spec_schemas.py from backend → cli"
