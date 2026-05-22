"""LiteLLM virtual key management for per-execution budget enforcement.

Creates and deletes short-lived virtual keys via the LiteLLM proxy's
``/key/generate`` and ``/key/delete`` endpoints.  Each execution gets its
own key with budget limits derived from the applicable AgentPolicy.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from blackbeard.http_client import get_client

logger = logging.getLogger(__name__)


class VirtualKeyError(Exception):
    """Raised when a LiteLLM virtual key operation fails."""


class VirtualKeyManager:
    """Manage LiteLLM virtual keys for per-execution budget enforcement.

    Uses the LiteLLM proxy's admin API (authenticated with the master key)
    to create and delete virtual keys with budget constraints.

    An optional ``client`` parameter allows injecting a shared
    ``httpx.AsyncClient`` instead of creating one per call.  When omitted,
    a module-level shared client is obtained via ``get_client()``.
    """

    def __init__(
        self,
        proxy_url: str,
        master_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._proxy_url = proxy_url.rstrip("/")
        self._master_key = master_key
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        """Return the shared httpx client for LiteLLM key operations."""
        if self._client is not None:
            return self._client
        return get_client(
            "litellm-keys",
            timeout=10.0,
            headers={
                "Authorization": f"Bearer {self._master_key}",
                "Content-Type": "application/json",
            },
        )

    async def create_key(
        self,
        *,
        name: str,
        max_budget: float | None = None,
        max_tokens: int | None = None,
        duration: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a virtual key with optional budget limits.

        Args:
            name: Human-readable key name (e.g. ``exec-<uuid>``).
            max_budget: Maximum spend in USD.  ``None`` means unlimited.
            max_tokens: Maximum total tokens (mapped to LiteLLM ``tpm_limit``).
                ``None`` means unlimited.
            duration: Key TTL as a duration string (e.g. ``"4h"``, ``"30m"``).
                ``None`` means no expiry.  Sets auto-expiration so keys are
                cleaned up even if the process crashes before ``delete_key``.
            metadata: Arbitrary metadata stored on the key.

        Returns:
            Dict with at least ``key`` (the API key string) and
            ``key_alias`` fields from the LiteLLM response.

        Raises:
            VirtualKeyError: On HTTP or protocol errors.
        """
        payload: dict[str, Any] = {"key_alias": name}
        if max_budget is not None:
            payload["max_budget"] = max_budget
        if max_tokens is not None:
            payload["tpm_limit"] = max_tokens
        if duration is not None:
            payload["duration"] = duration
        if metadata is not None:
            payload["metadata"] = metadata

        try:
            client = self._get_client()
            resp = await client.post(
                f"{self._proxy_url}/key/generate",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._master_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = cast("dict[str, Any]", resp.json())
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Virtual key creation failed: status=%d body=%s",
                exc.response.status_code,
                exc.response.text[:200],
                extra={
                    "event": "virtual_key_create_http_error",
                    "key_name": name,
                    "http_status": exc.response.status_code,
                    "max_budget": max_budget,
                    "max_tokens": max_tokens,
                },
            )
            raise VirtualKeyError(
                f"LiteLLM /key/generate failed: {exc.response.status_code} "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Virtual key creation request failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={
                    "event": "virtual_key_create_request_error",
                    "key_name": name,
                    "error_type": type(exc).__name__,
                },
            )
            raise VirtualKeyError(f"LiteLLM /key/generate request failed: {exc}") from exc

        key = data.get("key")
        if not key:
            raise VirtualKeyError("LiteLLM /key/generate response missing 'key' field")

        logger.info(
            "Virtual key created: name=%s max_budget=%s max_tokens=%s",
            name,
            max_budget,
            max_tokens,
            extra={
                "event": "virtual_key_created",
                "key_name": name,
                "max_budget": max_budget,
                "max_tokens": max_tokens,
            },
        )
        return data

    async def delete_key(self, key: str) -> bool:
        """Delete a virtual key by its key string.

        Args:
            key: The API key string (``sk-...``) to delete.

        Returns:
            ``True`` if deletion succeeded, ``False`` otherwise.
        """
        try:
            client = self._get_client()
            resp = await client.post(
                f"{self._proxy_url}/key/delete",
                json={"keys": [key]},
                headers={
                    "Authorization": f"Bearer {self._master_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Failed to delete virtual key: %s",
                exc,
                exc_info=True,
                extra={
                    "event": "virtual_key_delete_failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
            return False

        logger.info(
            "Virtual key deleted",
            extra={"event": "virtual_key_deleted"},
        )
        return True
