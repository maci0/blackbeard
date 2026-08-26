"""Write the live OpenAPI schema to frontend/openapi.json.

Run from ``backend/``: ``uv run python scripts/dump_openapi.py``. The frontend's
``bun run generate:api`` regenerates ``src/api/schema.d.ts`` from the result.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Route registration imports config, which refuses insecure defaults outside DEBUG.
os.environ.setdefault("DEBUG", "true")

from blackbeard.main import app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    OUT.write_text(json.dumps(app.openapi(), separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(app.openapi()['paths'])} paths)", file=sys.stderr)  # noqa: T201


if __name__ == "__main__":
    main()
