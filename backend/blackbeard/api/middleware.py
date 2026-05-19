"""API middleware: auth, request ID, body-size limiting, security headers, error handling."""

from __future__ import annotations

import collections
import hmac
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

import jwt as pyjwt
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request, Response
    from starlette.middleware.base import RequestResponseEndpoint

from blackbeard.auth.jwt import decode_token
from blackbeard.config import settings
from blackbeard.logging_config import request_id_var, user_id_var

logger = logging.getLogger(__name__)

# --- Auth failure rate limiting ---
# Track per-IP failure counts with a sliding window to prevent brute-force attacks.
_AUTH_FAIL_WINDOW_S = 300  # 5-minute window
_AUTH_FAIL_MAX = 20  # max failures per IP within the window
_auth_failures: dict[str, collections.deque[float]] = {}

_HEALTH_PATHS = {"/api/v1/health", "/api/v1/health/ready"}
_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
_AUTH_PATHS = {"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/refresh"}
PUBLIC_PATHS = _HEALTH_PATHS | _AUTH_PATHS | (_DOCS_PATHS if settings.debug else set())

# Default API key from settings; may be replaced at runtime via set_api_key()
_EXPECTED_API_KEY = settings.blackbeard_api_key.get_secret_value()


def set_api_key(key: str) -> None:
    """Replace the expected API key (used by startup to inject ephemeral keys)."""
    global _EXPECTED_API_KEY
    _EXPECTED_API_KEY = key


# Allowlist pattern for client-supplied request IDs — prevents header injection
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


_SENSITIVE_QS_PARAMS = frozenset(
    {"api_key", "token", "secret", "key", "password", "credential", "access_token", "refresh_token"}
)


def _redact_query_string(query: str) -> str:
    """Redact sensitive query parameters (e.g. api_key) before logging.

    Replaces values of known-sensitive parameter names with '[REDACTED]'
    to prevent credential leakage into structured log output.
    """
    if not query:
        return query
    query_lower = query.lower()
    if not any(param in query_lower for param in _SENSITIVE_QS_PARAMS):
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    redacted = [
        (k, "[REDACTED]") if k.lower() in _SENSITIVE_QS_PARAMS else (k, v) for k, v in pairs
    ]
    return urlencode(redacted)


def _check_rate_limit(request: Request, request_id: str, client_ip: str) -> JSONResponse | None:
    """Return a 429 response if client_ip exceeds the auth failure threshold, else None."""
    now = time.monotonic()
    ip_failures = _auth_failures.get(client_ip)
    if ip_failures is None:
        return None
    while ip_failures and ip_failures[0] < now - _AUTH_FAIL_WINDOW_S:
        ip_failures.popleft()
    if not ip_failures:
        del _auth_failures[client_ip]
        return None
    if len(ip_failures) < _AUTH_FAIL_MAX:
        return None
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Too many authentication failures. Try again later.",
            "request_id": request_id,
        },
        headers={"Retry-After": "60"},
    )
    response.headers["X-Request-Id"] = request_id
    logger.warning(
        "Auth rate limited: %s %s from %s (failures=%d)",
        request.method,
        request.url.path,
        client_ip,
        len(ip_failures),
        extra={
            "event": "auth_rate_limited",
            "http_method": request.method,
            "http_path": request.url.path,
            "client_ip": client_ip,
            "failure_count": len(ip_failures),
            "request_id": request_id,
        },
    )
    return response


def _record_auth_failure(client_ip: str) -> None:
    """Record an authentication failure for rate limiting and prune stale entries."""
    now = time.monotonic()
    if client_ip not in _auth_failures:
        _auth_failures[client_ip] = collections.deque(maxlen=_AUTH_FAIL_MAX + 10)
    _auth_failures[client_ip].append(now)
    if len(_auth_failures) > 200:
        cutoff = now - _AUTH_FAIL_WINDOW_S
        stale = [ip for ip, dq in _auth_failures.items() if not dq or dq[-1] < cutoff]
        for ip in stale:
            _auth_failures.pop(ip, None)
        if len(_auth_failures) > 200:
            to_evict = len(_auth_failures) - 200
            by_recency = sorted(
                _auth_failures,
                key=lambda k: _auth_failures[k][-1] if _auth_failures[k] else 0,
            )
            for ip in by_recency[:to_evict]:
                _auth_failures.pop(ip, None)


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
    user_id_var.set("")
    start = time.monotonic()
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"

    if path in PUBLIC_PATHS:
        if path in _AUTH_PATHS:
            rate_limited = _check_rate_limit(request, request_id, client_ip)
            if rate_limited is not None:
                return rate_limited

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id

        if path in _AUTH_PATHS and response.status_code in (401, 403):
            _record_auth_failure(client_ip)

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

    rate_limited = _check_rate_limit(request, request_id, client_ip)
    if rate_limited is not None:
        return rate_limited

    # Validate JWT Bearer token (signature + expiry).  Invalid tokens
    # trigger rate-limit recording to throttle brute-force attempts.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                raise pyjwt.InvalidTokenError("Not an access token")
            user_id_var.set(payload.get("sub", ""))
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError) as jwt_exc:
            _record_auth_failure(client_ip)
            duration_ms = (time.monotonic() - start) * 1000
            jwt_reason = type(jwt_exc).__name__
            logger.warning(
                "JWT auth failed: %s %s from %s reason=%s (%.0fms)",
                request.method,
                path,
                client_ip,
                jwt_reason,
                duration_ms,
                extra={
                    "event": "jwt_auth_failure",
                    "http_method": request.method,
                    "http_path": path,
                    "client_ip": client_ip,
                    "jwt_rejection_reason": jwt_reason,
                    "duration_ms": round(duration_ms, 1),
                    "request_id": request_id,
                },
            )
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or expired Bearer token.",
                    "request_id": request_id,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            response.headers["X-Request-Id"] = request_id
            return response
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        _log_request(request, response, start)
        return response

    # Check API key — always run hmac.compare_digest to prevent timing attacks
    # (even for missing/empty keys, so presence vs absence isn't distinguishable).
    # Fall back to ?api_key= query parameter ONLY for SSE/stream endpoints where
    # EventSource cannot set custom headers.  Query-string credentials leak via
    # proxy logs, browser history, and Referer headers (CWE-598).
    api_key = request.headers.get("X-API-Key", "")
    if not api_key and path.endswith("/stream"):
        api_key = request.query_params.get("api_key", "")
    if not api_key or not hmac.compare_digest(api_key, _EXPECTED_API_KEY):
        _record_auth_failure(client_ip)

        response = JSONResponse(
            status_code=401,
            content={
                "detail": "Invalid or missing API key. Set X-API-Key header.",
                "request_id": request_id,
            },
            headers={"WWW-Authenticate": "ApiKey"},
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
        level = logging.DEBUG
    else:
        level = logging.INFO

    if not logger.isEnabledFor(level):
        return

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")
    content_length = request.headers.get("content-length")
    resp_content_length = response.headers.get("content-length")
    resp_content_type = response.headers.get("content-type", "")
    query_string = _redact_query_string(request.url.query) if request.url.query else None

    user_id = user_id_var.get("")
    extra: dict[str, object] = {
        "event": "http_request",
        "http_method": request.method,
        "http_path": path,
        "http_query": query_string,
        "http_status": status,
        "duration_ms": round(duration_ms, 1),
        "client_ip": client_ip,
        "user_id": user_id or None,
        "user_agent": user_agent[:200] if user_agent else "",
        "content_length": int(content_length)
        if content_length and content_length.isdigit()
        else None,
        "response_content_length": int(resp_content_length)
        if resp_content_length and resp_content_length.isdigit()
        else None,
        "request_id": request_id_var.get("-"),
    }
    if status >= 400:
        extra["response_content_type"] = resp_content_type

    logger.log(
        level,
        "%s %s %d %.0fms",
        request.method,
        path,
        status,
        duration_ms,
        extra=extra,
    )


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'"
    ),
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-DNS-Prefetch-Control": "off",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Download-Options": "noopen",
}


async def security_headers_middleware(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Add security headers to every response."""
    response = await call_next(request)
    skip_csp = settings.debug and request.url.path in _DOCS_PATHS
    for name, value in SECURITY_HEADERS.items():
        if name not in response.headers:
            if skip_csp and name == "Content-Security-Policy":
                continue
            response.headers[name] = value
    return response


MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_BODY_MB = MAX_BODY_BYTES // (1024 * 1024)


async def body_size_limiter(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Reject requests with bodies exceeding the size limit.

    Checks both Content-Length header (fast reject) and actual body size
    (prevents bypass via chunked transfer encoding without Content-Length).
    """
    rid = request_id_var.get("-")

    def _reject(status: int, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"detail": detail, "request_id": rid},
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
        if length < 0:
            logger.warning(
                "Negative Content-Length header: %s %s content_length=%d",
                request.method,
                request.url.path,
                length,
                extra={
                    "event": "invalid_content_length",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "content_length": length,
                    "request_id": rid,
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


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle Pydantic validation errors with request_id for log correlation."""
    from fastapi.encoders import jsonable_encoder

    rid = request_id_var.get("-")
    errors: object = exc.errors() if callable(getattr(exc, "errors", None)) else []
    error_count = len(errors) if isinstance(errors, list) else 0
    logger.info(
        "Validation error: %s %s fields=%d",
        _request.method,
        _request.url.path,
        error_count,
        extra={
            "event": "validation_error",
            "http_method": _request.method,
            "http_path": _request.url.path,
            "error_count": error_count,
            "request_id": rid,
        },
    )
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors), "request_id": rid},
        headers={"X-Request-Id": rid},
    )


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle HTTPException with request_id in body for log correlation."""
    rid = request_id_var.get("-")
    status_code: int = getattr(exc, "status_code", 500)
    detail: object = getattr(exc, "detail", str(exc))
    exc_headers: dict[str, str] = getattr(exc, "headers", None) or {}
    if status_code >= 500:
        uid = user_id_var.get("")
        path = _request.url.path
        logger.error(
            "HTTP %d on %s %s: %s",
            status_code,
            _request.method,
            path,
            str(detail)[:200],
            exc_info=True,
            extra={
                "event": "http_exception",
                "http_method": _request.method,
                "http_path": path,
                "http_status": status_code,
                "error_message": str(detail)[:500],
                "request_id": rid,
                "user_id": uid or None,
            },
        )
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": rid},
        headers={"X-Request-Id": rid, **exc_headers},
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a sanitized 500 response."""
    rid = request_id_var.get("-")
    uid = user_id_var.get("")
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
            "user_id": uid or None,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
        headers={"X-Request-Id": rid},
    )
