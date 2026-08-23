#!/usr/bin/env bash
# Copy backend kind registry + schemas into the CLI package (offline validate).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cp "$ROOT/backend/blackbeard/kinds.py" "$ROOT/cli/blackbeard_cli/kinds.py"
cp "$ROOT/backend/blackbeard/resources/spec_schemas.py" "$ROOT/cli/blackbeard_cli/resources/spec_schemas.py"
cp "$ROOT/backend/blackbeard/resources/exceptions.py" "$ROOT/cli/blackbeard_cli/resources/exceptions.py"
cp "$ROOT/backend/blackbeard/resources/refs.py" "$ROOT/cli/blackbeard_cli/resources/refs.py"
# Standalone package: rewrite backend imports so the CLI does not depend on blackbeard.
# Portable in-place edit (GNU sed -i and BSD sed -i '' differ).
for _name in spec_schemas refs; do
    _path="$ROOT/cli/blackbeard_cli/resources/$_name.py"
    _tmp="$(mktemp)"
    sed 's/from blackbeard\.kinds import/from blackbeard_cli.kinds import/' "$_path" > "$_tmp"
    mv "$_tmp" "$_path"
done
# validator is intentionally thinner in CLI; only re-copy if you merge paths carefully.
echo "Synced kinds.py, spec_schemas.py, exceptions.py, refs.py from backend → cli"
