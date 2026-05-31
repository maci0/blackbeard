"""Ad-hoc chat and model testing endpoints.

Proxies requests to LiteLLM for:
- Ad-hoc chat completions with any configured model
- Model connectivity testing (verify API keys and provider reachability)
- Model listing from the LiteLLM proxy
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from blackbeard.api import RETRY_HEADERS_30
from blackbeard.auth import get_current_user
from blackbeard.config import settings
from blackbeard.http_client import get_litellm_client
from blackbeard.logging_config import request_id_var, scrub_pii
from blackbeard.models import User
from blackbeard.rate_limiter import chat_limiter, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_CHAT_RATE_MSG = "Too many chat requests. Try again later."
_MODEL_TEST_RATE_MSG = "Too many model test requests. Try again later."


def _parse_retry_after(resp: httpx.Response) -> str:
    raw = resp.headers.get("retry-after", "30")
    try:
        return str(max(1, min(int(raw), 3600)))
    except (ValueError, OverflowError):
        return "30"


_MODEL_NAME_PATTERN = r"^[a-zA-Z0-9._:/@-]+$"


class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0
    prompt_time_ms: int | None = None
    completion_time_ms: int | None = None


def _get_litellm_client() -> httpx.AsyncClient:
    """Return a shared httpx client for LiteLLM requests."""
    return get_litellm_client("litellm-chat", timeout=120.0)


def _extract_content(data: dict[str, Any]) -> tuple[str, TokenUsage, str | None]:
    """Extract content, usage, and finish_reason from a LiteLLM chat completion response."""
    choices = data.get("choices") or []
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    content = message.get("content") or message.get("reasoning_content") or ""

    prompt_time_ms: int | None = None
    completion_time_ms: int | None = None

    try:
        # Ollama / vLLM: durations in nanoseconds
        if usage.get("prompt_eval_duration"):
            prompt_time_ms = int(float(usage["prompt_eval_duration"]) / 1_000_000)
        if usage.get("eval_duration"):
            completion_time_ms = int(float(usage["eval_duration"]) / 1_000_000)

        # LiteLLM / OpenAI-compatible: _response_ms or prompt_time/completion_time
        if prompt_time_ms is None and usage.get("prompt_time"):
            prompt_time_ms = int(float(usage["prompt_time"]) * 1000)
        if completion_time_ms is None and usage.get("completion_time"):
            completion_time_ms = int(float(usage["completion_time"]) * 1000)
    except (TypeError, ValueError, OverflowError):
        logger.debug(
            "Could not parse timing data from LLM response usage — timing will be omitted",
            exc_info=True,
            extra={"event": "chat_timing_parse_error"},
        )
        prompt_time_ms = None
        completion_time_ms = None

    tokens = TokenUsage(
        prompt=usage.get("prompt_tokens", 0),
        completion=usage.get("completion_tokens", 0),
        total=usage.get("total_tokens", 0),
        prompt_time_ms=prompt_time_ms,
        completion_time_ms=completion_time_ms,
    )
    return content, tokens, finish_reason


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str = Field(max_length=1_000_000)


_MAX_TOTAL_MESSAGE_BYTES = 100 * 1024  # 100KB


class ChatRequest(BaseModel):
    model: str = Field(
        description="Model name from LiteLLM config",
        min_length=1,
        max_length=256,
        pattern=_MODEL_NAME_PATTERN,
    )
    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128_000)

    @model_validator(mode="after")
    def _check_total_message_size(self) -> ChatRequest:
        total = sum(len(m.content.encode("utf-8")) for m in self.messages)
        if total > _MAX_TOTAL_MESSAGE_BYTES:
            msg = (
                f"Total message content size ({total} bytes) exceeds "
                f"the {_MAX_TOTAL_MESSAGE_BYTES // 1024}KB limit"
            )
            raise ValueError(msg)
        return self

    def to_litellm_payload(self, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in self.messages],
            **extra,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        return payload


class ChatResponse(BaseModel):
    model: str
    content: str
    finish_reason: str | None = None
    tokens: TokenUsage
    latency_ms: int


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        429: {"description": "Model rate limit exceeded"},
        502: {"description": "LiteLLM proxy unreachable or model error"},
    },
)
async def chat(
    body: ChatRequest = Body(...),
    _user: User | None = Depends(get_current_user),
) -> ChatResponse:
    """Send an ad-hoc chat completion through LiteLLM."""
    check_rate_limit(chat_limiter, _user, _CHAT_RATE_MSG)
    payload = body.to_litellm_payload()

    t0 = time.monotonic()
    try:
        client = _get_litellm_client()
        resp = await client.post(
            f"{settings.litellm_proxy_url}/chat/completions",
            json=payload,
            headers={"X-Request-Id": request_id_var.get("-")},
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
            headers=RETRY_HEADERS_30,
        ) from e

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        error_body = scrub_pii(resp.text[:500]) if resp.text else ""
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
            },
        )
        if resp.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Model rate limit exceeded. Try again later.",
                headers={"Retry-After": _parse_retry_after(resp)},
            )
        raise HTTPException(
            status_code=502,
            detail=f"Model request failed with status {resp.status_code}.",
            headers=RETRY_HEADERS_30,
        )

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "Unparseable LiteLLM response: model=%s status=%d content_type=%s",
            body.model,
            resp.status_code,
            resp.headers.get("content-type", "unknown"),
            exc_info=True,
            extra={
                "event": "chat_litellm_unparseable",
                "model": body.model,
                "http_status": resp.status_code,
                "latency_ms": latency_ms,
                "content_type": resp.headers.get("content-type", "unknown"),
            },
        )
        raise HTTPException(
            status_code=502,
            detail="Model proxy returned an unparseable response.",
            headers=RETRY_HEADERS_30,
        ) from None
    content, tokens, finish_reason = _extract_content(data)

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
        finish_reason=finish_reason,
        tokens=tokens,
        latency_ms=latency_ms,
    )


class StreamEvent(BaseModel):
    """A single SSE event in the streaming chat response."""

    content: str = ""
    done: bool = False
    error: str | None = None
    tokens: TokenUsage | None = None
    latency_ms: int | None = None
    model: str | None = None


@router.post(
    "/chat/stream",
    responses={
        200: {
            "description": "SSE stream of chat completion tokens",
            "content": {"text/event-stream": {}},
        },
        429: {"description": "Too many chat requests"},
        502: {"description": "LiteLLM proxy unreachable or model error"},
    },
)
async def chat_stream(
    body: ChatRequest = Body(...),
    _user: User | None = Depends(get_current_user),
) -> StreamingResponse:
    """Stream an ad-hoc chat completion through LiteLLM via SSE.

    Each event is ``data: {"content": "...", "done": false}\\n\\n``.
    The final event includes ``"done": true`` plus token usage and latency.
    """
    check_rate_limit(chat_limiter, _user, _CHAT_RATE_MSG)
    payload = body.to_litellm_payload(
        stream=True,
        stream_options={"include_usage": True},
    )

    t0 = time.monotonic()
    request_model = body.model

    async def _event_generator() -> AsyncGenerator[str]:
        try:
            client = _get_litellm_client()
            async with client.stream(
                "POST",
                f"{settings.litellm_proxy_url}/chat/completions",
                json=payload,
                headers={"X-Request-Id": request_id_var.get("-")},
            ) as response:
                if response.status_code != 200:
                    error_text = ""
                    async for chunk in response.aiter_text():
                        error_text += chunk
                        if len(error_text) >= 4096:
                            break
                    logger.warning(
                        "LiteLLM stream error: model=%s status=%d body=%s",
                        request_model,
                        response.status_code,
                        scrub_pii(error_text[:200]),
                        extra={
                            "event": "chat_stream_litellm_error",
                            "model": request_model,
                            "http_status": response.status_code,
                        },
                    )
                    if response.status_code == 429:
                        client_error = "Model rate limit exceeded. Try again later."
                    else:
                        client_error = f"Model request failed with status {response.status_code}."
                    evt = StreamEvent(
                        error=client_error,
                        done=True,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                    )
                    yield f"data: {evt.model_dump_json()}\n\n"
                    return

                usage: dict[str, Any] = {}
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        logger.debug(
                            "Unparseable SSE chunk in stream: model=%s data=%s",
                            request_model,
                            data_str[:200],
                            extra={
                                "event": "chat_stream_unparseable_chunk",
                                "model": request_model,
                            },
                        )
                        continue

                    choices = chunk_data.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content") or delta.get("reasoning_content") or ""
                        if content:
                            yield f'data: {{"content":{json.dumps(content)},"done":false}}\n\n'

                    if chunk_data.get("usage"):
                        usage = chunk_data["usage"]

                latency_ms = int((time.monotonic() - t0) * 1000)
                _, tokens, _ = _extract_content(
                    {
                        "usage": usage,
                        "choices": [{"message": {"content": ""}}],
                    }
                )

                logger.info(
                    "Chat stream completion: model=%s tokens=%d latency_ms=%d",
                    request_model,
                    tokens.total,
                    latency_ms,
                    extra={
                        "event": "chat_stream_completion",
                        "model": request_model,
                        "total_tokens": tokens.total,
                        "prompt_tokens": tokens.prompt,
                        "completion_tokens": tokens.completion,
                        "latency_ms": latency_ms,
                    },
                )
                final_evt = StreamEvent(
                    content="",
                    done=True,
                    tokens=tokens,
                    latency_ms=latency_ms,
                    model=request_model,
                )
                yield f"data: {final_evt.model_dump_json()}\n\n"

        except httpx.TransportError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "LiteLLM stream unreachable: model=%s %s: %s (%.0fms)",
                request_model,
                type(exc).__name__,
                exc,
                latency_ms,
                exc_info=True,
                extra={
                    "event": "chat_stream_litellm_unreachable",
                    "model": request_model,
                    "error_type": type(exc).__name__,
                    "latency_ms": latency_ms,
                },
            )
            evt = StreamEvent(
                error="Model proxy is unreachable. Try again later.",
                done=True,
                latency_ms=latency_ms,
            )
            yield f"data: {evt.model_dump_json()}\n\n"
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "Chat stream unexpected error: model=%s %s: %s",
                request_model,
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={
                    "event": "chat_stream_unexpected_error",
                    "model": request_model,
                    "error_type": type(exc).__name__,
                    "latency_ms": latency_ms,
                },
            )
            evt = StreamEvent(
                error="An unexpected error occurred during streaming.",
                done=True,
                latency_ms=latency_ms,
            )
            yield f"data: {evt.model_dump_json()}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


class ModelTestResult(BaseModel):
    model: str
    status: Literal["ok", "error"]
    latency_ms: int | None = None
    error: str | None = None
    response_preview: str | None = None
    tokens: TokenUsage | None = None


@router.post(
    "/models/test",
    response_model=ModelTestResult,
    responses={
        422: {"description": "Invalid model name"},
        429: {"description": "Too many model test requests"},
    },
)
async def test_model(
    model: str = Body(
        ...,
        embed=True,
        min_length=1,
        max_length=256,
        pattern=_MODEL_NAME_PATTERN,
    ),
    _user: User | None = Depends(get_current_user),
) -> ModelTestResult:
    """Test connectivity and API key validity for a specific model.

    All requests route through the LiteLLM proxy so budget tracking,
    rate limiting, and audit logging apply even during tests.
    """
    check_rate_limit(chat_limiter, _user, _MODEL_TEST_RATE_MSG)
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
            error_body = scrub_pii(resp.text[:500]) if resp.text else ""
            logger.warning(
                "Model test failed: model=%s status=%d body=%s",
                model,
                resp.status_code,
                error_body[:200],
                extra={
                    "event": "model_test_failed",
                    "model": model,
                    "http_status": resp.status_code,
                },
            )
            return ModelTestResult(
                model=model,
                status="error",
                latency_ms=latency_ms,
                error=f"Model request failed with status {resp.status_code}.",
            )

        try:
            data = resp.json()
        except ValueError:
            return ModelTestResult(
                model=model,
                status="error",
                latency_ms=latency_ms,
                error="Model proxy returned an unparseable response.",
            )
        content, tokens, _ = _extract_content(data)

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
        )

    except httpx.TransportError as e:
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


_MODEL_LIST_RATE_MSG = "Too many model list requests. Try again later."


@router.get(
    "/models/available",
    response_model=list[ModelInfo],
    responses={
        429: {"description": "Model proxy rate limit exceeded"},
        502: {"description": "LiteLLM proxy unreachable"},
    },
)
async def list_available_models(
    response: Response,
    _user: User | None = Depends(get_current_user),
) -> list[ModelInfo]:
    """List all models configured in the LiteLLM proxy."""
    check_rate_limit(chat_limiter, _user, _MODEL_LIST_RATE_MSG)
    response.headers["Cache-Control"] = "no-store"
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
            if resp.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="Model proxy rate limit exceeded. Try again later.",
                    headers={"Retry-After": _parse_retry_after(resp)},
                )
            raise HTTPException(
                status_code=502,
                detail="Model proxy returned an error. Try again later.",
                headers=RETRY_HEADERS_30,
            )

        try:
            data = resp.json()
        except ValueError:
            logger.error(
                "Unparseable LiteLLM /models response: status=%d content_type=%s",
                resp.status_code,
                resp.headers.get("content-type", "unknown"),
                exc_info=True,
                extra={
                    "event": "models_litellm_unparseable",
                    "http_status": resp.status_code,
                    "content_type": resp.headers.get("content-type", "unknown"),
                },
            )
            raise HTTPException(
                status_code=502,
                detail="Model proxy returned an unparseable response.",
                headers=RETRY_HEADERS_30,
            ) from None
        return [
            ModelInfo(
                name=m.get("id", "unknown"),
                provider=m.get("owned_by"),
                model_id=m.get("id", "unknown"),
            )
            for m in data.get("data", [])
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
            headers=RETRY_HEADERS_30,
        ) from e
