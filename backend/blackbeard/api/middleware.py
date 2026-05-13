"""API middleware: auth, request ID, body-size limiting, security headers, error handling."""

from __future__ import annotations

import hmac
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request, Response
    from starlette.middleware.base import RequestResponseEndpoint

from blackbeard.config import settings
from blackbeard.logging_config import request_id_var

logger = logging.getLogger(__name__)

# Paths that don't require authentication
_HEALTH_PATHS = {"/api/v1/health", "/api/v1/health/ready"}
_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
PUBLIC_PATHS = _HEALTH_PATHS | (_DOCS_PATHS if settings.debug else set())

# Pre-extract API key once at import time to avoid SecretStr.get_secret_value() per request
_EXPECTED_API_KEY = settings.blackbeard_api_key.get_secret_value()

# Allowlist pattern for client-supplied request IDs — prevents header injection
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


def get_request_id(request: Request) -> str:
    """Return a validated client-supplied X-Request-Id or a fresh UUID."""
    client_id = request.headers.get("X-Request-Id")
    if client_id and _REQUEST_ID_PATTERN.match(client_id):
        return client_id
    return str(uuid.uuid4())


async def api_key_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Validate X-API-Key header on all non-public endpoints."""
    request_id = get_request_id(request)
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
    if not api_key or not hmac.compare_digest(api_key, _EXPECTED_API_KEY):
        response = JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Set X-API-Key header."},
        )
        response.headers["X-Request-Id"] = request_id
        client_ip = request.client.host if request.client else "unknown"
        duration_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "Auth failed: %s %s from %s (%.0fms)",
            request.method,
            path,
            client_ip,
            duration_ms,
            extra={
                "event": "auth_failure",
                "http_method": request.method,
                "http_path": path,
                "http_status": 401,
                "client_ip": client_ip,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    _log_request(request, response, start)
    return response


def _log_request(request: Request, response: Response, start: float) -> None:
    """Log completed request with method, path, status, and duration."""
    duration_ms = (time.monotonic() - start) * 1000
    status = response.status_code
    path = request.url.path

    # Downgrade health-check probes to DEBUG to avoid log noise from k8s/LB polling
    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    elif path in _HEALTH_PATHS:
        level = logging.DEBUG
    else:
        level = logging.INFO

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")

    logger.log(
        level,
        "%s %s %d %.0fms",
        request.method,
        path,
        status,
        duration_ms,
        extra={
            "event": "http_request",
            "http_method": request.method,
            "http_path": path,
            "http_status": status,
            "duration_ms": round(duration_ms, 1),
            "client_ip": client_ip,
            "user_agent": user_agent,
        },
    )


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-DNS-Prefetch-Control": "off",
}


async def security_headers_middleware(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Add security headers to every response."""
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        if name not in response.headers:
            response.headers[name] = value
    return response


MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


async def body_size_limiter(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Reject requests with bodies exceeding the size limit.

    Checks both Content-Length header (fast reject) and actual body size
    (prevents bypass via chunked transfer encoding without Content-Length).
    """
    # Reuse the request_id already set by api_key_middleware (runs before us in the stack)
    # to keep response headers and log correlation consistent.
    rid = request_id_var.get("-")

    def _reject(status: int, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"detail": detail},
            headers={"X-Request-Id": rid},
        )

    # NOTE: An empty Content-Length header (e.g. "Content-Length: ") will be
    # treated as "no Content-Length present" and fall through to the chunked-body
    # read path below.  This is acceptable because in production, nginx sits in
    # front of the API and enforces its own client_max_body_size for streaming /
    # chunked requests before they reach this middleware.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
        except (ValueError, OverflowError):
            logger.warning(
                "Invalid Content-Length header: %s %s",
                request.method,
                request.url.path,
                extra={
                    "event": "invalid_content_length",
                    "http_method": request.method,
                    "http_path": request.url.path,
                },
            )
            return _reject(400, "Invalid Content-Length header")
        if length > MAX_BODY_BYTES:
            logger.warning(
                "Request body too large: %s %s content_length=%d",
                request.method,
                request.url.path,
                length,
                extra={
                    "event": "request_body_too_large",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "content_length": length,
                },
            )
            max_mb = MAX_BODY_BYTES // (1024 * 1024)
            return _reject(
                413,
                f"Request body too large (limit: {max_mb}MB)",
            )

    if request.method in ("POST", "PUT", "PATCH") and not content_length:
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            logger.warning(
                "Request body too large (chunked): %s %s body_bytes=%d",
                request.method,
                request.url.path,
                len(body),
                extra={
                    "event": "request_body_too_large",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "body_bytes": len(body),
                },
            )
            max_mb = MAX_BODY_BYTES // (1024 * 1024)
            return _reject(
                413,
                f"Request body too large (limit: {max_mb}MB)",
            )

    return await call_next(request)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a sanitized 500 response."""
    rid = request_id_var.get("-")
    logger.error(
        "Unhandled exception on %s %s [request_id=%s]: %s",
        request.method,
        request.url.path,
        rid,
        exc,
        exc_info=True,
        extra={
            "event": "unhandled_exception",
            "error_type": type(exc).__name__,
            "http_method": request.method,
            "http_path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
        headers={"X-Request-Id": rid},
    )
