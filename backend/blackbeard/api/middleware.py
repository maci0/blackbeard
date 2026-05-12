"""API middleware: authentication, request logging, etc."""

import hmac
import logging
import re
import time
import uuid

from fastapi import Request, Response
from starlette.responses import JSONResponse

from blackbeard.config import settings
from blackbeard.logging_config import request_id_var

logger = logging.getLogger(__name__)

# Paths that don't require authentication
_HEALTH_PATHS = {"/api/v1/health", "/api/v1/health/ready"}
_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
PUBLIC_PATHS = _HEALTH_PATHS | (_DOCS_PATHS if settings.debug else set())

# Allowlist pattern for client-supplied request IDs — prevents header injection
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


def _get_request_id(request: Request) -> str:
    """Return a validated client-supplied X-Request-Id or a fresh UUID."""
    client_id = request.headers.get("X-Request-Id")
    if client_id and _REQUEST_ID_PATTERN.match(client_id):
        return client_id
    return str(uuid.uuid4())


async def api_key_middleware(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
    """Validate X-API-Key header on all non-public endpoints."""
    request_id = _get_request_id(request)
    request_id_var.set(request_id)
    start = time.monotonic()
    path = request.url.path

    # Allow public paths
    if path in PUBLIC_PATHS:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        _log_request(request, response, start)
        return response

    # Allow OPTIONS for CORS preflight
    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    # Check API key — use hmac.compare_digest to prevent timing attacks
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, settings.blackbeard_api_key):
        response = JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Set X-API-Key header."},
        )
        response.headers["X-Request-Id"] = request_id
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Auth failed: %s %s from %s", request.method, path, client_ip)
        return response

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    _log_request(request, response, start)
    return response


def _log_request(request: Request, response: Response, start: float) -> None:
    """Log completed request with method, path, status, and duration."""
    duration_ms = (time.monotonic() - start) * 1000
    status = response.status_code
    level = logging.WARNING if status >= 400 else logging.INFO
    logger.log(level, "%s %s %d %.0fms", request.method, request.url.path, status, duration_ms)
