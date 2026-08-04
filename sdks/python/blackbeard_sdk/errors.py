"""Error types for the Blackbeard SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


def _format_detail(detail: Any, fallback: str) -> str:
    """Normalize API error detail (string, list, or object) to a single string.

    FastAPI validation errors return ``detail`` as a list of
    ``{loc, msg, type}`` objects; coercing keeps ``detail`` always a ``str``
    so helpers like ``is_timeout`` never crash on non-string values.
    """
    if detail is None:
        return fallback
    if isinstance(detail, str):
        return detail or fallback
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = item.get("loc", ())
                msg = item.get("msg", str(item))
                loc_parts = [str(x) for x in loc if x != "body"]
                loc_str = ".".join(loc_parts)
                parts.append(f"{loc_str}: {msg}" if loc_str else str(msg))
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else fallback
    return str(detail)


class BlackbeardApiError(Exception):
    """Raised when the Blackbeard API returns a non-2xx response.

    Attributes:
        status_code: HTTP status code from the response (0 for network/timeout).
        detail: Human-readable error message from the API.
        body: Full parsed response body (if available).
        request_id: Value of the ``X-Request-Id`` response header, if present.
        retry_after: Parsed ``Retry-After`` header in seconds, if present.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        body: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.body = body
        self.request_id = request_id
        self.retry_after = retry_after
        super().__init__(f"HTTP {status_code}: {detail}")

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return self.status_code >= 500

    @property
    def is_unauthorized(self) -> bool:
        return self.status_code == 401

    @property
    def is_forbidden(self) -> bool:
        return self.status_code == 403

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404

    @property
    def is_conflict(self) -> bool:
        return self.status_code == 409

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == 429

    @property
    def is_timeout(self) -> bool:
        return self.status_code == 0 and "timed out" in self.detail.lower()

    @property
    def is_network_error(self) -> bool:
        return self.status_code == 0

    def __repr__(self) -> str:
        parts = [
            f"status_code={self.status_code}",
            f"detail={self.detail!r}",
        ]
        if self.request_id is not None:
            parts.append(f"request_id={self.request_id!r}")
        if self.retry_after is not None:
            parts.append(f"retry_after={self.retry_after}")
        return f"BlackbeardApiError({', '.join(parts)})"


def raise_for_status(resp: httpx.Response) -> None:
    """Raise ``BlackbeardApiError`` for non-2xx responses."""
    if resp.is_success:
        return
    fallback = resp.reason_phrase or f"HTTP {resp.status_code}"
    try:
        raw = resp.json()
        body = raw if isinstance(raw, dict) else None
        detail = _format_detail(body.get("detail") if body else None, fallback)
    except ValueError:
        body = None
        detail = fallback

    request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
    retry_raw = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
    retry_after: int | None = None
    if retry_raw is not None:
        try:
            retry_after = int(retry_raw)
        except ValueError:
            retry_after = None

    raise BlackbeardApiError(
        resp.status_code,
        detail,
        body,
        request_id=request_id,
        retry_after=retry_after,
    )
