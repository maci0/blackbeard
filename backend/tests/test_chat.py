"""Tests for the chat API endpoints.

Validates request/response schemas and error handling for:
  - POST /chat (ad-hoc completions)
  - POST /models/test (model connectivity test)
  - GET /models/available (model listing)

LiteLLM proxy calls are mocked via httpx_mock or respx.
"""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from blackbeard.api.chat import ChatMessage, ChatRequest, ChatResponse, ModelInfo, ModelTestResult

# ---------------------------------------------------------------------------
# Pydantic model unit tests
# ---------------------------------------------------------------------------


def test_chat_message_defaults():
    msg = ChatMessage(content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_chat_request_validation():
    req = ChatRequest(model="gpt-4o", messages=[ChatMessage(content="Hi")])
    assert req.model == "gpt-4o"
    assert len(req.messages) == 1
    assert req.temperature is None
    assert req.max_tokens is None


def test_chat_request_with_params():
    req = ChatRequest(
        model="gpt-4o",
        messages=[ChatMessage(content="Hi")],
        temperature=0.5,
        max_tokens=100,
    )
    assert req.temperature == 0.5
    assert req.max_tokens == 100


def test_chat_request_empty_messages_rejected():
    with pytest.raises(ValidationError, match="too_short"):
        ChatRequest(model="gpt-4o", messages=[])


def test_chat_response_schema():
    resp = ChatResponse(
        model="gpt-4o",
        content="Hello!",
        tokens={"prompt": 5, "completion": 2, "total": 7},
        latency_ms=150,
    )
    assert resp.model == "gpt-4o"
    assert resp.content == "Hello!"
    assert resp.tokens["total"] == 7


def test_model_test_result_ok():
    result = ModelTestResult(model="gpt-4o", status="ok", latency_ms=200)
    assert result.status == "ok"
    assert result.error is None


def test_model_test_result_error():
    result = ModelTestResult(model="gpt-4o", status="error", error="Connection refused")
    assert result.status == "error"
    assert result.error == "Connection refused"


def test_model_info_schema():
    info = ModelInfo(name="gpt-4o", provider="openai", model_id="gpt-4o")
    assert info.name == "gpt-4o"


def test_model_info_optional_fields():
    info = ModelInfo(name="local-model")
    assert info.provider is None
    assert info.model_id is None


# ---------------------------------------------------------------------------
# API endpoint auth tests
# ---------------------------------------------------------------------------


async def test_chat_requires_auth(client: AsyncClient):
    """POST /chat without API key should return 401."""
    response = await client.post(
        "/api/v1/chat",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert response.status_code == 401


async def test_models_test_requires_auth(client: AsyncClient):
    """POST /models/test without API key should return 401."""
    response = await client.post("/api/v1/models/test", json={"model": "gpt-4o"})
    assert response.status_code == 401


async def test_models_available_requires_auth(client: AsyncClient):
    """GET /models/available without API key should return 401."""
    response = await client.get("/api/v1/models/available")
    assert response.status_code == 401
