"""Error types for the Blackbeard SDK."""

from __future__ import annotations

from typing import Any

import httpx


class BlackbeardApiError(Exception):
    """Raised when the Blackbeard API returns a non-2xx response.

    Attributes:
        status_code: HTTP status code from the response.
        detail: Human-readable error message from the API.
        body: Full parsed response body (if available).
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.body = body
        super().__init__(f"HTTP {status_code}: {detail}")

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return self.status_code >= 500

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404

    @property
    def is_network_error(self) -> bool:
        return self.status_code == 0

    def __repr__(self) -> str:
        return (
            f"BlackbeardApiError(status_code={self.status_code}, "
            f"detail={self.detail!r})"
        )


def raise_for_status(resp: httpx.Response) -> None:
    """Raise ``BlackbeardApiError`` for non-2xx responses."""
    if resp.is_success:
        return
    try:
        body = resp.json()
        fallback = resp.reason_phrase or f"HTTP {resp.status_code}"
        detail = (
            body.get("detail", fallback)
            if isinstance(body, dict)
            else fallback
        )
    except Exception:
        body = None
        detail = resp.reason_phrase or f"HTTP {resp.status_code}"
    raise BlackbeardApiError(resp.status_code, detail, body)
