"""API middleware: auth, request ID, body-size limiting, security headers, error handling."""

from __future__ import annotations

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

from blackbeard.audit import get_client_ip
from blackbeard.auth.api_key import get_api_key
from blackbeard.auth.dependencies import SSE_STREAM_RE
from blackbeard.auth.jwt import decode_access_token
from blackbeard.config import settings
from blackbeard.logging_config import anonymize_ip, request_id_var, scrub_pii, user_id_var
from blackbeard.rate_limiter import is_rate_limited_with_count, record_auth_failure

logger = logging.getLogger(__name__)

_HEALTH_PATHS = {"/api/v1/health", "/api/v1/health/ready", "/.well-known/agent-card.json"}
_DOCS_PATHS = {"/docs", "/openapi.json", "/redoc"}
_AUTH_PATHS = {"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/refresh"}
_OIDC_PATHS = {"/api/v1/auth/oidc/login", "/api/v1/auth/oidc/callback", "/api/v1/config/public"}
PUBLIC_PATHS = (
    _HEALTH_PATHS | _AUTH_PATHS | _OIDC_PATHS | (_DOCS_PATHS if settings.debug else set())
)

_AUTOMATION_WEBHOOK_RE = re.compile(r"^/api/v1/automations/[a-z0-9][a-z0-9\-]*/webhook$")

# Allowlist pattern for client-supplied request IDs — prevents header injection
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


_SENSITIVE_QS_PARAMS = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "key",
        "password",
        "credential",
        "access_token",
        "refresh_token",
        "email",
        "ssn",
        "phone",
        "name",
        "display_name",
        "username",
        "address",
        "zip_code",
        "postal_code",
        "credit_card",
        "card_number",
        "date_of_birth",
        "dob",
        "birthdate",
        "birthday",
        "birth_date",
        "ip_address",
        "authorization",
        "bearer",
        "jwt",
    }
)


def _redact_query_string(query: str) -> str:
    """Redact sensitive query parameters before logging.

    Parameter names in ``_SENSITIVE_QS_PARAMS`` have their values replaced
    with '[REDACTED]' to prevent credential/PII leakage into log output.
    """
    if not query:
        return query
    query_lower = query.lower()
    if not any(param in query_lower for param in _SENSITIVE_QS_PARAMS):
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    if not pairs:
        return query
    needs_redaction = False
    redacted = []
    for k, v in pairs:
        if k.lower() in _SENSITIVE_QS_PARAMS:
            redacted.append((k, "[REDACTED]"))
            needs_redaction = True
        else:
            redacted.append((k, v))
    if not needs_redaction:
        return query
    return urlencode(redacted)


def _check_rate_limit(request: Request, request_id: str, client_ip: str) -> JSONResponse | None:
    """Return a 429 response if client_ip exceeds the auth failure threshold, else None."""
    limited, failure_count = is_rate_limited_with_count(client_ip)
    if not limited:
        return None
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Too many authentication failures. Try again later.",
            "request_id": request_id,
        },
        headers={"Retry-After": str(settings.auth_fail_window_seconds)},
    )
    response.headers["X-Request-Id"] = request_id
    logger.warning(
        "Auth rate limited: %s %s from %s (failures=%d)",
        request.method,
        request.url.path,
        anonymize_ip(client_ip),
        failure_count,
        extra={
            "event": "auth_rate_limited",
            "http_method": request.method,
            "http_path": request.url.path,
            "client_ip": client_ip,
            "failure_count": failure_count,
            "request_id": request_id,
        },
    )
    return response


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
    client_ip = get_client_ip(request) or "unknown"

    if path in PUBLIC_PATHS:
        if path in _AUTH_PATHS:
            rate_limited = _check_rate_limit(request, request_id, client_ip)
            if rate_limited is not None:
                return rate_limited

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id

        if path in _AUTH_PATHS and response.status_code in (401, 403, 409):
            record_auth_failure(client_ip)

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

    # Automation webhook paths use their own HMAC auth inside the route
    # handler — let them through without requiring an API key or JWT.
    # Rate limiting runs ABOVE this check so brute-force attempts against
    # webhook secrets are throttled.
    if _AUTOMATION_WEBHOOK_RE.match(path):
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        _log_request(request, response, start)
        return response

    # Validate JWT Bearer token (signature + expiry).  Invalid tokens
    # trigger rate-limit recording to throttle brute-force attempts.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
            user_id_var.set(payload.get("sub", ""))
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError) as jwt_exc:
            record_auth_failure(client_ip)
            duration_ms = (time.monotonic() - start) * 1000
            jwt_reason = type(jwt_exc).__name__
            logger.warning(
                "JWT auth failed: %s %s from %s reason=%s (%.0fms)",
                request.method,
                path,
                anonymize_ip(client_ip),
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
    if not api_key and SSE_STREAM_RE.match(path):
        api_key = request.query_params.get("api_key", "")
    if not hmac.compare_digest(api_key, get_api_key()):
        record_auth_failure(client_ip)

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
            anonymize_ip(client_ip),
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

    client_ip = get_client_ip(request) or "unknown"
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
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-DNS-Prefetch-Control": "off",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Download-Options": "noopen",
}

_SECURITY_HEADERS_LIST = list(SECURITY_HEADERS.items())
_SECURITY_HEADERS_NO_CSP = [
    (k, v) for k, v in _SECURITY_HEADERS_LIST if k != "Content-Security-Policy"
]


async def security_headers_middleware(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Add security headers to every response."""
    response = await call_next(request)
    skip_csp = settings.debug and request.url.path in _DOCS_PATHS
    headers = _SECURITY_HEADERS_NO_CSP if skip_csp else _SECURITY_HEADERS_LIST
    for name, value in headers:
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
    errors_fn = getattr(exc, "errors", None)
    errors: object = errors_fn() if callable(errors_fn) else []
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
    # Strip 'input' and 'ctx' from each error to prevent leaking submitted
    # values (e.g. passwords) in the HTTP response body.
    if isinstance(errors, list):
        errors = [
            {k: v for k, v in e.items() if k not in ("input", "ctx")} if isinstance(e, dict) else e
            for e in errors
        ]
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
        scrubbed_detail = scrub_pii(str(detail)[:500])
        logger.error(
            "HTTP %d on %s %s: %s",
            status_code,
            _request.method,
            path,
            scrubbed_detail[:200],
            exc_info=True,
            extra={
                "event": "http_exception",
                "http_method": _request.method,
                "http_path": path,
                "http_status": status_code,
                "error_message": scrubbed_detail,
                "request_id": rid,
                "user_id": uid or None,
            },
        )
        if status_code == 500:
            detail = "Internal server error"
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": rid},
        headers={"X-Request-Id": rid, **exc_headers},
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a sanitized 500 response."""
    rid = request_id_var.get("-")
    uid = user_id_var.get("")
    scrubbed_error = scrub_pii(str(exc)[:500])
    logger.error(
        "Unhandled exception on %s %s [request_id=%s]: %s",
        request.method,
        request.url.path,
        rid,
        scrubbed_error,
        exc_info=True,
        extra={
            "event": "unhandled_exception",
            "error_type": type(exc).__name__,
            "error_message": scrubbed_error,
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
