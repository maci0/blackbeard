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


@pytest.mark.parametrize("role", ["user", "assistant", "system"])
def test_chat_message_explicit_roles(role):
    """All standard chat roles should be accepted."""
    msg = ChatMessage(role=role, content="test")
    assert msg.role == role


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


# ---------------------------------------------------------------------------
# _extract_content unit tests (critical parsing logic — previously untested)
# ---------------------------------------------------------------------------

from blackbeard.api.chat import _extract_content


def test_extract_content_standard_response():
    """Standard OpenAI-format response should extract content and token counts."""
    data = {
        "choices": [{"message": {"content": "Hello!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    content, tokens = _extract_content(data)
    assert content == "Hello!"
    assert tokens == {"prompt": 5, "completion": 2, "total": 7}


def test_extract_content_empty_choices():
    """Empty choices list should return empty content."""
    data = {"choices": [], "usage": {}}
    content, tokens = _extract_content(data)
    assert content == ""
    assert tokens == {"prompt": 0, "completion": 0, "total": 0}


def test_extract_content_missing_choices():
    """Missing choices key should return empty content."""
    data = {"usage": {"total_tokens": 5}}
    content, _tokens = _extract_content(data)
    assert content == ""


def test_extract_content_reasoning_content_fallback():
    """Should fall back to reasoning_content when content is missing."""
    data = {
        "choices": [{"message": {"reasoning_content": "Let me think..."}}],
        "usage": {"total_tokens": 10},
    }
    content, _tokens = _extract_content(data)
    assert content == "Let me think..."


def test_extract_content_missing_usage():
    """Missing usage key should default token counts to 0."""
    data = {"choices": [{"message": {"content": "Hi"}}]}
    content, tokens = _extract_content(data)
    assert content == "Hi"
    assert tokens == {"prompt": 0, "completion": 0, "total": 0}


def test_extract_content_null_content():
    """Null content in message should return empty string."""
    data = {"choices": [{"message": {"content": None}}], "usage": {}}
    content, _tokens = _extract_content(data)
    assert content == ""


# ---------------------------------------------------------------------------
# ChatRequest boundary validation
# ---------------------------------------------------------------------------


def test_chat_request_rejects_oversized_model():
    """Model name exceeding 256 chars should be rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(model="x" * 257, messages=[ChatMessage(content="Hi")])


def test_chat_request_temperature_bounds():
    """Temperature outside 0.0-2.0 should be rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(model="gpt-4o", messages=[ChatMessage(content="Hi")], temperature=3.0)
    with pytest.raises(ValidationError):
        ChatRequest(model="gpt-4o", messages=[ChatMessage(content="Hi")], temperature=-0.1)
