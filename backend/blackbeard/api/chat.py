"""Ad-hoc chat and model testing endpoints.

Proxies requests to LiteLLM for:
- Ad-hoc chat completions with any configured model
- Model connectivity testing (verify API keys and provider reachability)
- Model listing from the LiteLLM proxy
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from blackbeard.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_LITELLM_URL = settings.litellm_proxy_url
_LITELLM_KEY = settings.litellm_master_key.get_secret_value()


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    model: str = Field(description="Model name from LiteLLM config")
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None


class ChatResponse(BaseModel):
    model: str
    content: str
    tokens: dict[str, int]
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
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{_LITELLM_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {_LITELLM_KEY}"},
            )
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach LiteLLM proxy at {_LITELLM_URL}: {e}",
        ) from e

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"LiteLLM returned {resp.status_code}: {resp.text[:500]}",
        )

    data = resp.json()
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = data.get("usage", {})

    return ChatResponse(
        model=data.get("model", body.model),
        content=message.get("content", ""),
        tokens={
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        },
        latency_ms=latency_ms,
    )


class ModelTestResult(BaseModel):
    model: str
    status: str  # "ok" | "error"
    latency_ms: int | None = None
    error: str | None = None
    response_preview: str | None = None
    tokens: dict[str, int] | None = None


@router.post(
    "/models/test",
    response_model=ModelTestResult,
)
async def test_model(
    model: str = Body(..., embed=True),  # noqa: PT028
) -> ModelTestResult:
    """Test connectivity and API key validity for a specific model.

    Sends a minimal prompt ("Say hi") and checks if the model responds.
    """
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_LITELLM_URL}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say hi"}],
                    "max_tokens": 10,
                },
                headers={"Authorization": f"Bearer {_LITELLM_KEY}"},
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code != 200:
            error_text = resp.text[:300]
            return ModelTestResult(
                model=model,
                status="error",
                latency_ms=latency_ms,
                error=f"HTTP {resp.status_code}: {error_text}",
            )

        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return ModelTestResult(
            model=model,
            status="ok",
            latency_ms=latency_ms,
            response_preview=content[:100],
            tokens={
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            },
        )

    except httpx.ConnectError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ModelTestResult(
            model=model,
            status="error",
            latency_ms=latency_ms,
            error=f"Connection failed: {e}",
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ModelTestResult(
            model=model,
            status="error",
            latency_ms=latency_ms,
            error=str(e),
        )


class ModelInfo(BaseModel):
    name: str
    provider: str | None = None
    model_id: str | None = None


@router.get(
    "/models/available",
    response_model=list[ModelInfo],
)
async def list_available_models() -> list[ModelInfo]:
    """List all models configured in the LiteLLM proxy."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_LITELLM_URL}/models",
                headers={"Authorization": f"Bearer {_LITELLM_KEY}"},
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"LiteLLM /models returned {resp.status_code}",
            )

        data = resp.json()
        models = data.get("data", [])
        return [
            ModelInfo(
                name=m.get("id", "unknown"),
                provider=m.get("owned_by"),
                model_id=m.get("id"),
            )
            for m in models
        ]

    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach LiteLLM: {e}",
        ) from e
