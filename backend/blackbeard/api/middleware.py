"""API middleware: auth, request ID, body-size limiting, security headers, error handling."""

from __future__ import annotations

import collections
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

# --- Auth failure rate limiting ---
# Track per-IP failure counts with a sliding window to prevent brute-force attacks.
_AUTH_FAIL_WINDOW_S = 300  # 5-minute window
_AUTH_FAIL_MAX = 20  # max failures per IP within the window
_auth_failures: dict[str, collections.deque[float]] = {}

_HEALTH_PATHS = {"/api/v1/health", "/api/v1/health/ready"}
_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
PUBLIC_PATHS = _HEALTH_PATHS | (_DOCS_PATHS if settings.debug else set())

# Pre-extract API key once at import time to avoid SecretStr.get_secret_value() per request
_EXPECTED_API_KEY = settings.blackbeard_api_key.get_secret_value()


def set_api_key(key: str) -> None:
    """Replace the expected API key (used by startup to inject ephemeral keys)."""
    global _EXPECTED_API_KEY
    _EXPECTED_API_KEY = key


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

    if path in PUBLIC_PATHS:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        _log_request(request, response, start)
        return response

    if request.method == "OPTIONS":
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        logger.debug(
            "CORS preflight: %s %d",
            path,
            response.status_code,
            extra={
                "event": "cors_preflight",
                "http_path": path,
                "http_status": response.status_code,
                "request_id": request_id,
            },
        )
        return response

    # Rate-limit auth failures per client IP to slow brute-force attacks
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    ip_failures = _auth_failures.get(client_ip)
    if ip_failures is not None:
        # Evict expired entries outside the window
        while ip_failures and ip_failures[0] < now - _AUTH_FAIL_WINDOW_S:
            ip_failures.popleft()
        if len(ip_failures) >= _AUTH_FAIL_MAX:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many authentication failures. Try again later."},
                headers={"Retry-After": "60"},
            )
            response.headers["X-Request-Id"] = request_id
            logger.warning(
                "Auth rate limited: %s %s from %s (failures=%d)",
                request.method,
                path,
                client_ip,
                len(ip_failures),
                extra={
                    "event": "auth_rate_limited",
                    "http_method": request.method,
                    "http_path": path,
                    "client_ip": client_ip,
                    "failure_count": len(ip_failures),
                    "request_id": request_id,
                },
            )
            return response

    # Check API key — always run hmac.compare_digest to prevent timing attacks
    # (even for missing/empty keys, so presence vs absence isn't distinguishable).
    # Fall back to ?api_key= query parameter for SSE endpoints where EventSource
    # cannot set custom headers.
    api_key = request.headers.get("X-API-Key", "") or request.query_params.get("api_key", "")
    if not hmac.compare_digest(api_key, _EXPECTED_API_KEY):
        # Record the failure for rate limiting
        if client_ip not in _auth_failures:
            _auth_failures[client_ip] = collections.deque()
        _auth_failures[client_ip].append(now)
        # Prevent unbounded memory growth: prune stale IPs periodically.
        # Evict expired timestamps from ALL deques (not just the current IP),
        # then remove any IPs with no remaining entries.
        if len(_auth_failures) > 10_000:
            cutoff = now - _AUTH_FAIL_WINDOW_S
            stale = []
            for ip, dq in _auth_failures.items():
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if not dq:
                    stale.append(ip)
            for ip in stale:
                _auth_failures.pop(ip, None)

        response = JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Set X-API-Key header."},
        )
        response.headers["X-Request-Id"] = request_id
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
                "request_id": request_id,
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

    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    elif path in _HEALTH_PATHS:
        # DEBUG to avoid log noise from k8s/LB health polling
        level = logging.DEBUG
    else:
        level = logging.INFO

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")
    content_length = request.headers.get("content-length")
    query_string = str(request.url.query) if request.url.query else None

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
            "http_query": query_string,
            "http_status": status,
            "duration_ms": round(duration_ms, 1),
            "client_ip": client_ip,
            "user_agent": user_agent[:200] if user_agent else "",
            "content_length": int(content_length)
            if content_length and content_length.isdigit()
            else None,
            "request_id": request_id_var.get("-"),
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
_MAX_BODY_MB = MAX_BODY_BYTES // (1024 * 1024)


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

    # An empty Content-Length (e.g. "Content-Length: ") falls through to
    # the chunked-body read path below; a reverse proxy in front of the API
    # should enforce its own body-size limit for defense-in-depth.
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
                    "request_id": rid,
                },
            )
            return _reject(400, "Invalid Content-Length header")
        if length < 0 or length > MAX_BODY_BYTES:
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
                    "request_id": rid,
                },
            )
            return _reject(
                413,
                f"Request body too large (limit: {_MAX_BODY_MB}MB)",
            )

    if request.method in ("POST", "PUT", "PATCH") and not content_length:
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                logger.warning(
                    "Request body too large (chunked): %s %s body_bytes>%d",
                    request.method,
                    request.url.path,
                    MAX_BODY_BYTES,
                    extra={
                        "event": "request_body_too_large",
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "body_bytes": total,
                        "request_id": rid,
                    },
                )
                return _reject(
                    413,
                    f"Request body too large (limit: {_MAX_BODY_MB}MB)",
                )
            chunks.append(chunk)
        # Cache the body so downstream handlers can read it via request.body()
        request._body = b"".join(chunks)

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
            "error_message": str(exc)[:500],
            "http_method": request.method,
            "http_path": request.url.path,
            "request_id": rid,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
        headers={"X-Request-Id": rid},
    )
