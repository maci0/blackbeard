"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from blackbeard.auth.api_key import get_api_key
from blackbeard.auth.authorizer import Authorizer
from blackbeard.auth.jwt import decode_access_token
from blackbeard.config import settings
from blackbeard.kinds import PLURAL_TO_KIND
from blackbeard.models import User, get_session

logger = logging.getLogger(__name__)

# Query-string API key fallback is ONLY for the execution SSE endpoint
# where EventSource cannot set custom headers.  Matching any path that
# happens to end in "/stream" would widen the attack surface (CWE-598).
SSE_STREAM_RE = re.compile(r"^/api/v1/executions/[0-9a-fA-F\-]{36}/stream$")

_METHOD_TO_VERB: dict[str, str] = {
    "GET": "get",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def bearer_401(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def _resolve_bearer_user(
    token: str, session: AsyncSession, *, cached_payload: dict[str, Any] | None = None
) -> User:
    """Decode a JWT Bearer token and return the corresponding active User.

    Raises HTTPException(401) on any validation failure.
    When *cached_payload* is provided (from middleware), skips redundant decode.
    """
    if cached_payload is not None:
        payload = cached_payload
    else:
        try:
            payload = decode_access_token(token)
        except pyjwt.ExpiredSignatureError:
            logger.info("JWT expired", extra={"event": "jwt_expired"})
            raise bearer_401("Token has expired") from None
        except pyjwt.InvalidTokenError:
            logger.warning("JWT invalid", extra={"event": "jwt_invalid"})
            raise bearer_401("Invalid token") from None

    user_id = payload.get("sub")
    if not user_id:
        logger.warning("JWT missing sub claim", extra={"event": "jwt_missing_sub"})
        raise bearer_401("Invalid token payload")

    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(defer(User.password_hash), defer(User.api_key))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        logger.warning(
            "JWT user not found or inactive: sub=%s",
            user_id,
            extra={"event": "jwt_user_invalid", "user_id": str(user_id)},
        )
        raise bearer_401("User not found or inactive")
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Extract authenticated user from JWT Bearer token or API key.

    Returns the User if authentication succeeds, None if no credentials
    are present. The middleware layer handles X-API-Key auth for
    system-level access; this dependency resolves user identity from
    JWT tokens or per-user API keys.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        cached = getattr(request.state, "jwt_payload", None)
        return await _resolve_bearer_user(auth_header[7:], session, cached_payload=cached)

    # Try resolving the X-API-Key to a user (optional — API key may belong to
    # the global system key rather than a user-specific key).
    # Only accept query-string keys on SSE/stream endpoints where EventSource
    # cannot set custom headers — query-string credentials leak via proxy logs,
    # browser history, and Referer headers (CWE-598).
    api_key = request.headers.get("X-API-Key", "")
    if not api_key and SSE_STREAM_RE.match(request.url.path):
        api_key = request.query_params.get("api_key", "")
    if api_key and len(api_key) >= 16:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await session.execute(
            select(User)
            .where(User.api_key == api_key_hash, User.is_active.is_(True))
            .options(defer(User.password_hash), defer(User.api_key))
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user

    return None


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Require an authenticated user. Returns 401 if not authenticated."""
    if user is None:
        logger.warning(
            "Authentication required but no credentials provided",
            extra={"event": "auth_required_no_credentials"},
        )
        raise bearer_401("Authentication required. Provide a Bearer token or user API key.")
    return user


async def require_jwt_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Require authentication via JWT Bearer token only.

    Rejects API key authentication — used for sensitive operations like
    API key management where authenticating with the credential being
    managed would be a security risk.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "JWT-only endpoint called without Bearer token",
            extra={"event": "jwt_only_missing_bearer"},
        )
        raise bearer_401("JWT Bearer token required. API key authentication is not accepted.")

    cached = getattr(request.state, "jwt_payload", None)
    return await _resolve_bearer_user(auth_header[7:], session, cached_payload=cached)


def require_permission(
    verb: str,
    resource_kind: str,
    *,
    require_identity: bool = False,
) -> Callable[..., Coroutine[Any, Any, User | None]]:
    """FastAPI dependency factory for RBAC enforcement.

    Returns a dependency that checks whether the authenticated user has
    the given *verb* on *resource_kind* via Role/RoleBinding resources.
    When ``settings.enforce_rbac`` is ``False`` (the default for dev),
    the check is skipped and any authenticated (or system-key) caller
    is permitted.  When ``True``, a user identity is required.

    If *require_identity* is ``True`` a user identity is always required
    regardless of the ``enforce_rbac`` setting (useful for endpoints such
    as user management that reference ``user.id``).
    """

    if require_identity:

        async def _check_strict(
            user: User = Depends(require_user),
            session: AsyncSession = Depends(get_session),
        ) -> User:
            if not settings.enforce_rbac:
                return user
            authz = Authorizer(session)
            allowed = await authz.check("User", user.email, verb, resource_kind)
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Not authorized to {verb} {resource_kind}",
                )
            return user

        return _check_strict

    async def _check(
        user: User | None = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> User | None:
        if not settings.enforce_rbac:
            return user
        # RBAC is on — user identity is mandatory.
        if user is None:
            raise bearer_401("Authentication required. Provide a Bearer token or user API key.")
        authz = Authorizer(session)
        allowed = await authz.check("User", user.email, verb, resource_kind)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized to {verb} {resource_kind}",
            )
        return user

    return _check


async def check_resource_permission(
    kind_plural: str,
    request: Request,
    user: User | None = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """RBAC dependency for the generic resource CRUD router.

    Derives the verb from the HTTP method and the resource kind from
    the ``kind_plural`` path parameter. When ``settings.enforce_rbac``
    is ``False``, any authenticated (or system-key) caller is permitted.
    When ``True``, a user identity is required for the authorization check.
    """
    if not settings.enforce_rbac:
        return user

    # RBAC is on — user identity is mandatory.
    if user is None:
        raise bearer_401("Authentication required. Provide a Bearer token or user API key.")

    verb = _METHOD_TO_VERB.get(request.method, "get")

    # GET on the collection endpoint (no name segment) is a "list" operation.
    path_parts = request.url.path.rstrip("/").split("/")
    if request.method == "GET" and path_parts[-1] == kind_plural:
        verb = "list"

    kind = PLURAL_TO_KIND.get(kind_plural)
    if kind is None:
        # Unknown kind — let the route handler return 404.
        return user

    authz = Authorizer(session)
    if not await authz.check("User", user.email, verb, kind):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to {verb} {kind}",
        )
    return user


def validate_ws_auth(token: str, api_key: str) -> bool:
    """Validate WebSocket authentication credentials.

    Accepts either a JWT access token or an API key.
    Returns True if authentication succeeds, False otherwise.

    WebSocket connections cannot set custom headers, so credentials
    must be passed via query string parameters.
    """
    if token:
        try:
            decode_access_token(token)
            return True
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError) as exc:
            logger.warning(
                "WebSocket auth: token validation failed",
                exc_info=True,
                extra={
                    "event": "ws_token_invalid",
                    "error_type": type(exc).__name__,
                },
            )

    return bool(api_key and hmac.compare_digest(api_key.encode(), get_api_key().encode()))
