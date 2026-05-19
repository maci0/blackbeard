"""Blackbeard API client."""

from __future__ import annotations

from typing import Any

import httpx

from blackbeard_sdk.auth import AuthMixin
from blackbeard_sdk.executions import ExecutionMixin
from blackbeard_sdk.resources import ResourceMixin


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
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the Blackbeard client.

        Args:
            base_url: Base URL of the Blackbeard API server.
            api_key: API key for X-API-Key header authentication.
            token: JWT access token for Bearer authentication.
            timeout: Default request timeout in seconds.
        """
        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )

    def health(self) -> dict[str, Any]:
        """Check API liveness.

        Returns:
            Health response dict with status, service, version, uptime_s.
        """
        resp = self._http.get("/api/v1/health")
        resp.raise_for_status()
        return resp.json()

    def readiness(self) -> dict[str, Any]:
        """Check API readiness (database, Valkey, LiteLLM connectivity).

        Returns:
            Readiness response dict with component checks.
        """
        resp = self._http.get("/api/v1/health/ready")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> BlackbeardClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"BlackbeardClient(base_url={self._http.base_url!r})"
