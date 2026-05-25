"""Sync LLMConnection resources to LiteLLM proxy via its management API.

When a user creates, updates, or deletes an LLMConnection resource through
Blackbeard, this module pushes the change to LiteLLM so the model becomes
available immediately — no proxy restart required.

LiteLLM management API:
  POST /model/new    — add a model
  POST /model/update — update a model
  POST /model/delete — delete a model
  GET  /model/info   — list configured models
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from blackbeard.config import settings
from blackbeard.http_client import get_client
from blackbeard.litellm.helpers import apply_model_params, apply_vertex_params, build_model_string

logger = logging.getLogger(__name__)


class LiteLLMSyncError(Exception):
    """Raised when a LiteLLM model sync operation fails."""


def _build_litellm_params(spec: dict[str, Any]) -> dict[str, Any]:
    """Build litellm_params dict from an LLMConnection spec."""
    provider = spec.get("provider", "")
    model = spec.get("model", "")
    params = spec.get("parameters", {})
    vertex = spec.get("vertex", {})

    litellm_params: dict[str, Any] = {
        "model": build_model_string(provider, model),
    }

    if provider == "vertex_ai":
        apply_vertex_params(litellm_params, vertex)

    api_key_env = spec.get("api_key_env")
    if api_key_env:
        litellm_params["api_key"] = f"os.environ/{api_key_env}"

    base_url = spec.get("base_url")
    if base_url:
        litellm_params["api_base"] = base_url

    apply_model_params(litellm_params, params)
    return litellm_params


def _build_model_info(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Build model_info dict with fallback configuration from an LLMConnection spec.

    Returns ``None`` when no model_info fields are needed.
    """
    fallbacks = spec.get("fallbacks")
    if not fallbacks:
        return None

    return {
        "fallbacks": [{"model_name": fb} for fb in fallbacks],
    }


def _proxy_url() -> str:
    return settings.litellm_proxy_url.rstrip("/")


def _get_client() -> httpx.AsyncClient:
    master_key = settings.litellm_master_key.get_secret_value()
    return get_client(
        "litellm-model-sync",
        timeout=10.0,
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
    )


async def add_model(name: str, spec: dict[str, Any]) -> bool:
    """Add a model to LiteLLM proxy. Returns True on success."""
    litellm_params = _build_litellm_params(spec)
    body: dict[str, Any] = {
        "model_name": name,
        "litellm_params": litellm_params,
    }
    model_info = _build_model_info(spec)
    if model_info is not None:
        body["model_info"] = model_info
    client = _get_client()
    proxy = _proxy_url()
    try:
        resp = await client.post(f"{proxy}/model/new", json=body)
        if resp.status_code not in (200, 201):
            logger.warning(
                "LiteLLM add_model failed: %s status=%d body=%s",
                name,
                resp.status_code,
                resp.text[:300],
                extra={
                    "event": "litellm_add_model_failed",
                    "model_name": name,
                    "http_status": resp.status_code,
                },
            )
            return False
        logger.info(
            "LiteLLM model added: %s",
            name,
            extra={"event": "litellm_model_added", "model_name": name},
        )
        return True
    except httpx.HTTPError as exc:
        logger.error(
            "LiteLLM add_model error: %s %s",
            name,
            exc,
            exc_info=True,
            extra={"event": "litellm_add_model_error", "model_name": name},
        )
        return False


async def update_model(name: str, spec: dict[str, Any]) -> None:
    """Update a model on LiteLLM proxy (delete + re-add)."""
    await delete_model(name)
    await add_model(name, spec)


async def delete_model(name: str) -> bool:
    """Delete a model from LiteLLM proxy. Returns True on success."""
    client = _get_client()
    proxy = _proxy_url()
    try:
        resp = await client.post(f"{proxy}/model/delete", json={"id": name})
        if resp.status_code not in (200, 204):
            logger.debug(
                "LiteLLM delete_model: %s status=%d (may not exist)",
                name,
                resp.status_code,
                extra={
                    "event": "litellm_delete_model_status",
                    "model_name": name,
                    "http_status": resp.status_code,
                },
            )
            return False
        logger.info(
            "LiteLLM model deleted: %s",
            name,
            extra={"event": "litellm_model_deleted", "model_name": name},
        )
        return True
    except httpx.HTTPError as exc:
        logger.error(
            "LiteLLM delete_model error: %s %s",
            name,
            exc,
            exc_info=True,
            extra={"event": "litellm_delete_model_error", "model_name": name},
        )
        return False


async def sync_all(llm_connections: list[dict[str, Any]]) -> int:
    """Sync all LLMConnection resources to LiteLLM. Returns count synced."""
    import asyncio

    tasks: list[tuple[str, dict[str, Any]]] = []
    for conn in llm_connections:
        name = conn.get("name", "")
        spec = conn.get("spec", {})
        if not spec.get("model"):
            continue
        tasks.append((name, spec))
    if not tasks:
        return 0
    results = await asyncio.gather(
        *(add_model(name, spec) for name, spec in tasks), return_exceptions=True
    )
    synced = sum(1 for r in results if r is True)
    failed = len(results) - synced
    logger.info(
        "LiteLLM full sync: %d models synced, %d failed",
        synced,
        failed,
        extra={"event": "litellm_full_sync", "synced_count": synced, "failed_count": failed},
    )
    return synced
