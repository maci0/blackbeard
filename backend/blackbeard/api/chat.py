"""Ad-hoc chat and model testing endpoints.

Proxies requests to LiteLLM for:
- Ad-hoc chat completions with any configured model
- Model connectivity testing (verify API keys and provider reachability)
- Model listing from the LiteLLM proxy
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from blackbeard.config import settings
from blackbeard.http_client import get_client
from blackbeard.logging_config import request_id_var

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _get_litellm_client() -> httpx.AsyncClient:
    """Return a shared httpx client for LiteLLM requests."""
    key = settings.litellm_master_key.get_secret_value()
    return get_client("litellm-chat", headers={"Authorization": f"Bearer {key}"})


def _extract_content(data: dict[str, Any]) -> tuple[str, TokenUsage]:
    """Extract content and usage from a LiteLLM chat completion response."""
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message", {})
    usage = data.get("usage", {})
    content = message.get("content") or message.get("reasoning_content") or ""
    tokens = TokenUsage(
        prompt=usage.get("prompt_tokens", 0),
        completion=usage.get("completion_tokens", 0),
        total=usage.get("total_tokens", 0),
    )
    return content, tokens


class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str = Field(max_length=1_000_000)


class ChatRequest(BaseModel):
    model: str = Field(description="Model name from LiteLLM config", min_length=1, max_length=256)
    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)


class ChatResponse(BaseModel):
    model: str
    content: str
    tokens: TokenUsage
    latency_ms: int


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        502: {"description": "LiteLLM proxy unreachable or model error"},
    },
)
async def chat(body: ChatRequest = Body(...)) -> ChatResponse:
    """Send an ad-hoc chat completion through LiteLLM."""
    payload: dict[str, Any] = {
        "model": body.model,
        "messages": [m.model_dump() for m in body.messages],
    }
    if body.temperature is not None:
        payload["temperature"] = body.temperature
    if body.max_tokens is not None:
        payload["max_tokens"] = body.max_tokens

    t0 = time.monotonic()
    try:
        client = _get_litellm_client()
        resp = await client.post(
            f"{settings.litellm_proxy_url}/chat/completions",
            json=payload,
            headers={"X-Request-Id": request_id_var.get("-")},
            timeout=120,
        )
    except httpx.TransportError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "LiteLLM unreachable: model=%s %s: %s (%.0fms)",
            body.model,
            type(e).__name__,
            e,
            latency_ms,
            exc_info=True,
            extra={
                "event": "chat_litellm_unreachable",
                "model": body.model,
                "error_type": type(e).__name__,
                "latency_ms": latency_ms,
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Model proxy is unreachable. Try again later.",
            headers={"Retry-After": "30"},
        ) from e

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        error_body = resp.text[:500] if resp.text else ""
        logger.warning(
            "LiteLLM error: model=%s status=%d latency_ms=%d body=%s",
            body.model,
            resp.status_code,
            latency_ms,
            error_body[:200],
            extra={
                "event": "chat_litellm_error",
                "model": body.model,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
                "response_body_preview": error_body,
            },
        )
        raise HTTPException(
            status_code=502,
            detail=f"Model request failed with status {resp.status_code}.",
            headers={"Retry-After": "30"},
        )

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "Unparseable LiteLLM response: model=%s status=%d content_type=%s",
            body.model,
            resp.status_code,
            resp.headers.get("content-type", "unknown"),
            extra={
                "event": "chat_litellm_unparseable",
                "model": body.model,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Model proxy returned an unparseable response.",
            headers={"Retry-After": "30"},
        ) from None
    content, tokens = _extract_content(data)

    logger.info(
        "Chat completion: model=%s tokens=%d latency_ms=%d",
        body.model,
        tokens.total,
        latency_ms,
        extra={
            "event": "chat_completion",
            "model": body.model,
            "total_tokens": tokens.total,
            "prompt_tokens": tokens.prompt,
            "completion_tokens": tokens.completion,
            "latency_ms": latency_ms,
        },
    )
    return ChatResponse(
        model=data.get("model", body.model),
        content=content,
        tokens=tokens,
        latency_ms=latency_ms,
    )


class ModelTestResult(BaseModel):
    model: str
    status: Literal["ok", "error"]
    latency_ms: int | None = None
    error: str | None = None
    response_preview: str | None = None
    tokens: TokenUsage | None = None
    context_length: int | None = None
    parameter_size: str | None = None


@router.post(
    "/models/test",
    response_model=ModelTestResult,
)
async def test_model(
    model: str = Body(..., embed=True, min_length=1, max_length=256),  # noqa: PT028
) -> ModelTestResult:
    """Test connectivity and API key validity for a specific model.

    Sends a minimal prompt ("Say hi") and checks if the model responds.
    """
    t0 = time.monotonic()
    try:
        client = _get_litellm_client()
        resp = await client.post(
            f"{settings.litellm_proxy_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hi"}],
                "max_tokens": 10,
            },
            headers={"X-Request-Id": request_id_var.get("-")},
            timeout=30,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code != 200:
            error_body = resp.text[:500] if resp.text else ""
            logger.warning(
                "Model test failed: model=%s status=%d body=%s",
                model,
                resp.status_code,
                error_body[:200],
                extra={
                    "event": "model_test_failed",
                    "model": model,
                    "http_status": resp.status_code,
                    "response_body_preview": error_body,
                },
            )
            return ModelTestResult(
                model=model,
                status="error",
                latency_ms=latency_ms,
                error=f"Model request failed with status {resp.status_code}.",
            )

        data = resp.json()
        content, tokens = _extract_content(data)

        # Try to get model info (context length, parameter size) from Ollama.
        # Use a separate client without LiteLLM auth headers to avoid leaking
        # the master key to the Ollama endpoint.
        ctx_len = None
        param_size = None
        try:
            ollama_client = get_client("ollama")
            info_resp = await ollama_client.post(
                f"{settings.ollama_url}/api/show",
                json={"model": model},
                timeout=5,
            )
            if info_resp.status_code == 200:
                info = info_resp.json()
                model_info = info.get("model_info", {})
                for k, v in model_info.items():
                    if k.endswith(".context_length"):
                        ctx_len = int(v)
                        break
                param_size = info.get("details", {}).get("parameter_size")
        except Exception:
            logger.debug("Could not fetch Ollama model info for %s", model, exc_info=True)

        logger.info(
            "Model test ok: model=%s tokens=%d latency_ms=%d",
            model,
            tokens.total,
            latency_ms,
            extra={
                "event": "model_test_ok",
                "model": model,
                "total_tokens": tokens.total,
                "latency_ms": latency_ms,
            },
        )
        return ModelTestResult(
            model=model,
            status="ok",
            latency_ms=latency_ms,
            response_preview=content[:100],
            tokens=tokens,
            context_length=ctx_len,
            parameter_size=param_size,
        )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "Model test connection failed: model=%s error=%s latency_ms=%d",
            model,
            e,
            latency_ms,
            extra={
                "event": "model_test_connect_failed",
                "model": model,
                "error_type": type(e).__name__,
                "latency_ms": latency_ms,
            },
        )
        return ModelTestResult(
            model=model,
            status="error",
            latency_ms=latency_ms,
            error="Connection to model proxy failed or timed out.",
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "Model test unexpected error: model=%s error=%s",
            model,
            e,
            exc_info=True,
            extra={
                "event": "model_test_unexpected_error",
                "model": model,
                "error_type": type(e).__name__,
                "latency_ms": latency_ms,
            },
        )
        return ModelTestResult(
            model=model,
            status="error",
            latency_ms=latency_ms,
            error="An unexpected error occurred while testing the model.",
        )


class ModelInfo(BaseModel):
    name: str
    provider: str | None = None
    model_id: str | None = None


@router.get(
    "/models/available",
    response_model=list[ModelInfo],
    responses={
        502: {"description": "LiteLLM proxy unreachable"},
    },
)
async def list_available_models() -> list[ModelInfo]:
    """List all models configured in the LiteLLM proxy."""
    try:
        client = _get_litellm_client()
        resp = await client.get(
            f"{settings.litellm_proxy_url}/models",
            headers={"X-Request-Id": request_id_var.get("-")},
            timeout=10,
        )

        if resp.status_code != 200:
            logger.warning(
                "LiteLLM /models error: status=%d",
                resp.status_code,
                extra={
                    "event": "models_litellm_error",
                    "http_status": resp.status_code,
                },
            )
            raise HTTPException(
                status_code=502,
                detail="Model proxy returned an error. Try again later.",
                headers={"Retry-After": "30"},
            )

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                "Unparseable LiteLLM /models response: status=%d",
                resp.status_code,
                extra={
                    "event": "models_litellm_unparseable",
                    "http_status": resp.status_code,
                },
            )
            raise HTTPException(
                status_code=502,
                detail="Model proxy returned an unparseable response.",
                headers={"Retry-After": "30"},
            ) from None
        models = data.get("data", [])
        return [
            ModelInfo(
                name=m.get("id", "unknown"),
                provider=m.get("owned_by"),
                model_id=m.get("id", "unknown"),
            )
            for m in models
        ]

    except httpx.TransportError as e:
        logger.warning(
            "LiteLLM unreachable for /models: %s: %s",
            type(e).__name__,
            e,
            extra={"event": "models_litellm_unreachable", "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=502,
            detail="Model proxy is unreachable. Try again later.",
            headers={"Retry-After": "30"},
        ) from e
