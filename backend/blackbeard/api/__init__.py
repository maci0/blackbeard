"""REST API layer: routers, middleware, and request/response handling."""

from __future__ import annotations

RETRY_HEADERS_30: dict[str, str] = {"Retry-After": "30"}
