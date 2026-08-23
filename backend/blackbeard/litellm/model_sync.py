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
from blackbeard.litellm.helpers import build_litellm_params
from blackbeard.logging_config import scrub_pii

logger = logging.getLogger(__name__)


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
    litellm_params = build_litellm_params(spec)
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
                scrub_pii(resp.text[:300]) if resp.text else "",
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
    synced = 0
    failed = 0
    for (name, _spec), result in zip(tasks, results, strict=True):
        if result is True:
            synced += 1
        else:
            failed += 1
            if isinstance(result, BaseException):
                logger.error(
                    "LiteLLM sync unexpected error for model %s: %s",
                    name,
                    result,
                    exc_info=result,
                    extra={
                        "event": "litellm_sync_model_exception",
                        "model_name": name,
                        "error_type": type(result).__name__,
                    },
                )
    logger.info(
        "LiteLLM full sync: %d models synced, %d failed",
        synced,
        failed,
        extra={"event": "litellm_full_sync", "synced_count": synced, "failed_count": failed},
    )
    return synced
