"""Integration tests for the chat API endpoints (api/chat.py).

Tests the chat completion, model listing, and model test endpoints
with mocked LiteLLM proxy calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


async def test_chat_success(client: AsyncClient):
    """POST /chat proxies to LiteLLM and returns response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": "Hello, I am an AI assistant."}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Hello, I am an AI assistant."
    assert data["tokens"]["total"] == 30
    assert "latency_ms" in data


async def test_chat_with_temperature(client: AsyncClient):
    """POST /chat passes temperature to LiteLLM."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Response"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.5,
            },
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200


async def test_chat_litellm_500_error(client: AsyncClient):
    """POST /chat returns 502 when LiteLLM returns 500."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.json.return_value = {"error": "internal error"}
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 502


async def test_chat_litellm_429_rate_limit(client: AsyncClient):
    """POST /chat returns 429 when LiteLLM rate limits."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"
    mock_response.json.return_value = {"error": "rate_limited"}
    mock_response.headers = {"retry-after": "60"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 429


async def test_chat_connection_error(client: AsyncClient):
    """POST /chat returns 502 when LiteLLM is unreachable."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /models/available
# ---------------------------------------------------------------------------


async def test_list_models_success(client: AsyncClient):
    """GET /models/available returns model list from LiteLLM."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "gpt-4o", "owned_by": "openai"},
            {"id": "claude-3-opus", "owned_by": "anthropic"},
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.get("/api/v1/models/available", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "gpt-4o"


async def test_list_models_litellm_error(client: AsyncClient):
    """GET /models/available returns 502 when LiteLLM fails."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.get("/api/v1/models/available", headers=API_KEY_HEADER)
    assert resp.status_code == 502


async def test_list_models_connection_error(client: AsyncClient):
    """GET /models/available returns 502 when LiteLLM is unreachable."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.get("/api/v1/models/available", headers=API_KEY_HEADER)
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /models/test
# ---------------------------------------------------------------------------


async def test_model_test_success(client: AsyncClient):
    """POST /models/test returns success for reachable model."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": "Hi!"}}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/models/test",
            json={"model": "gpt-4o"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["model"] == "gpt-4o"


async def test_model_test_litellm_error(client: AsyncClient):
    """POST /models/test returns error status for LiteLLM failure."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Model error"
    mock_response.json.return_value = {"error": {"message": "Key invalid"}}
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/models/test",
            json={"model": "gpt-4o"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


async def test_model_test_connection_error(client: AsyncClient):
    """POST /models/test returns error status when LiteLLM is unreachable."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("blackbeard.api.chat._get_litellm_client", return_value=mock_client):
        resp = await client.post(
            "/api/v1/models/test",
            json={"model": "gpt-4o"},
            headers=API_KEY_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
