"""LiteLLM virtual key lifecycle management.

Creates per-execution virtual keys with model restrictions and budget limits.
"""

from __future__ import annotations

import logging
import threading

import httpx

from blackbeard.config import settings

logger = logging.getLogger(__name__)

# Shared HTTP client for LiteLLM Proxy API calls — created once, reused across calls
_client: httpx.AsyncClient | None = None
_client_lock = threading.Lock()


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    base_url=settings.litellm_proxy_url,
                    timeout=30.0,
                )
    return _client


async def shutdown_key_manager() -> None:
    """Close the HTTP client."""
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def create_execution_key(
    execution_id: str,
    models: list[str] | None = None,
    max_budget: float | None = None,
) -> str | None:
    """Create a scoped virtual key via the LiteLLM Proxy API.

    Returns the generated API key string, or None if the proxy is unreachable.
    """
    try:
        client = _get_client()
        payload: dict = {
            "metadata": {"execution_id": execution_id},
        }
        if models:
            payload["models"] = models
        if max_budget:
            payload["max_budget"] = max_budget

        response = await client.post(
            "/key/generate",
            json=payload,
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            timeout=10.0,
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("key")
        else:
            logger.warning(
                "Failed to create LiteLLM key: %d %s", response.status_code, response.text
            )
            return None

    except Exception as e:
        logger.warning("LiteLLM key creation failed, using master key: %s", e)
        return None


async def delete_execution_key(key: str) -> bool:
    """Delete a LiteLLM virtual key after execution completes."""
    try:
        client = _get_client()
        response = await client.post(
            "/key/delete",
            json={"keys": [key]},
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            timeout=10.0,
        )
        return response.status_code == 200
    except Exception as e:
        logger.warning("Failed to delete LiteLLM key: %s", e)
        return False


async def get_key_spend(key: str) -> dict | None:
    """Get spend data for a LiteLLM virtual key."""
    try:
        client = _get_client()
        response = await client.get(
            "/key/info",
            params={"key": key},
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.warning("Failed to get key spend: %s", e)
        return None
