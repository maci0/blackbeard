"""Blackbeard API client."""

from __future__ import annotations

import os
from typing import Any

import httpx

from blackbeard_sdk.auth import AuthMixin
from blackbeard_sdk.errors import BlackbeardApiError, raise_for_status
from blackbeard_sdk.executions import ExecutionMixin
from blackbeard_sdk.resources import ResourceMixin

# Re-export so tests/consumers can import from the top-level package
__all__ = ["BlackbeardClient", "BlackbeardApiError"]


class BlackbeardClient(AuthMixin, ResourceMixin, ExecutionMixin):
    """Client for the Blackbeard Agent Management Platform API.

    Supports authentication via API key (X-API-Key header) or JWT Bearer
    token (obtained via login()). All methods return plain dicts.

    Usage with API key::

        client = BlackbeardClient(
            base_url="http://localhost:8000",
            api_key="your-api-key",
        )
        agents = client.list("Agent")

    Usage with JWT::

        client = BlackbeardClient(base_url="http://localhost:8000")
        client.login("user@example.com", "password123")
        agents = client.list("Agent")

    Environment variable fallbacks (used when no explicit argument is passed):

    - ``BLACKBEARD_BASE_URL``: API server URL (default ``http://localhost:8000``)
    - ``BLACKBEARD_API_KEY``: API key for X-API-Key authentication
    - ``BLACKBEARD_TOKEN``: JWT access token for Bearer authentication
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize the Blackbeard client.

        Args:
            base_url: Base URL of the Blackbeard API server.  Falls back to
                ``BLACKBEARD_BASE_URL`` env var, then ``http://localhost:8000``.
            api_key: API key for X-API-Key header authentication.  Falls back
                to ``BLACKBEARD_API_KEY`` env var.
            token: JWT access token for Bearer authentication.  Falls back to
                ``BLACKBEARD_TOKEN`` env var.
            timeout: Default request timeout in seconds.
            transport: Custom httpx transport (useful for testing with mock
                transports or custom connection pooling).
        """
        if not base_url:
            base_url = os.environ.get("BLACKBEARD_BASE_URL", "http://localhost:8000")
        if api_key is None:
            api_key = os.environ.get("BLACKBEARD_API_KEY")
        if token is None:
            token = os.environ.get("BLACKBEARD_TOKEN")

        self._api_key = api_key
        self._token = token
        self._timeout = timeout
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif api_key:
            headers["X-API-Key"] = api_key

        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "headers": headers,
            "timeout": timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport

        self._http = httpx.Client(**kwargs)

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send an HTTP request, wrapping transport errors in BlackbeardApiError.

        All mixin methods should use this instead of calling ``self._http``
        directly so that network failures, timeouts, and HTTP errors are
        reported through a single, consistent error type.
        """
        try:
            resp = self._http.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise BlackbeardApiError(
                0, f"{method} {url}: request timed out after {self._timeout}s"
            ) from exc
        except httpx.TransportError as exc:
            msg = str(exc) or "Network request failed"
            raise BlackbeardApiError(0, f"{method} {url}: {msg}") from exc
        raise_for_status(resp)
        return resp

    def health(self) -> dict[str, Any]:
        """Check API liveness.

        Returns:
            Health response dict with status, service, version, uptime_s.
        """
        return self._send("GET", "/api/v1/health").json()

    def readiness(self) -> dict[str, Any]:
        """Check API readiness (database, Valkey, LiteLLM connectivity).

        Returns:
            Readiness response dict with component checks.
        """
        return self._send("GET", "/api/v1/health/ready").json()

    def list_audit_logs(
        self,
        *,
        action: str | None = None,
        actor_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List audit log entries with optional filters.

        Args:
            action: Filter by action (e.g. 'resource_created').
            actor_id: Filter by actor ID.
            resource_type: Filter by resource type (e.g. 'Agent').
            resource_id: Filter by resource ID.
            limit: Maximum number of results (1-1000).
            offset: Number of results to skip.

        Returns:
            List of audit log entry dicts.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if action:
            params["action"] = action
        if actor_id:
            params["actor_id"] = actor_id
        if resource_type:
            params["resource_type"] = resource_type
        if resource_id:
            params["resource_id"] = resource_id
        return self._send(
            "GET", "/api/v1/audit-logs", params=params
        ).json()["items"]

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> BlackbeardClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"BlackbeardClient(base_url={self._http.base_url!r})"
