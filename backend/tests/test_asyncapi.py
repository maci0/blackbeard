"""Tests for the AsyncAPI 3.0 spec endpoint."""

from __future__ import annotations

from httpx import AsyncClient


async def test_asyncapi_returns_200(client: AsyncClient):
    """GET /api/v1/asyncapi.json returns a valid AsyncAPI 3.0 spec."""
    resp = await client.get("/api/v1/asyncapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["asyncapi"] == "3.0.0"
    assert "info" in spec
    assert spec["info"]["title"] == "Blackbeard Webhook Events"


async def test_asyncapi_no_auth_required(client: AsyncClient):
    """The endpoint is public and does not require authentication."""
    resp = await client.get("/api/v1/asyncapi.json")
    assert resp.status_code == 200


async def test_asyncapi_has_all_event_types(client: AsyncClient):
    """The spec includes messages for every known event type."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    messages = spec["components"]["messages"]
    expected = {
        "crew_started",
        "crew_completed",
        "task_started",
        "task_completed",
        "tool_started",
        "tool_finished",
        "llm_started",
        "llm_completed",
        "cost_alert",
        "hitl_request",
        "hitl_response",
    }
    assert set(messages.keys()) == expected


async def test_asyncapi_has_security_scheme(client: AsyncClient):
    """The spec describes the HMAC-SHA256 signing scheme."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    schemes = spec["components"]["securitySchemes"]
    assert "hmacSignature" in schemes
    assert schemes["hmacSignature"]["name"] == "X-Webhook-Signature"


async def test_asyncapi_message_has_envelope(client: AsyncClient):
    """Each message payload wraps data in the standard envelope."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    msg = spec["components"]["messages"]["crew_started"]
    payload = msg["payload"]
    assert payload["type"] == "object"
    assert "event_type" in payload["properties"]
    assert "execution_id" in payload["properties"]
    assert "data" in payload["properties"]
    assert set(payload["required"]) == {"event_type", "execution_id", "data"}


async def test_asyncapi_has_channel(client: AsyncClient):
    """The spec defines a webhookEndpoint channel."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    assert "webhookEndpoint" in spec["channels"]
    channel = spec["channels"]["webhookEndpoint"]
    assert channel["address"] == "{webhookUrl}"
    assert len(channel["messages"]) == 11


async def test_asyncapi_has_operation(client: AsyncClient):
    """The spec defines a send operation."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    assert "receiveWebhookEvent" in spec["operations"]
    op = spec["operations"]["receiveWebhookEvent"]
    assert op["action"] == "send"


async def test_asyncapi_schemas_exist(client: AsyncClient):
    """The components section includes all data schemas."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    schemas = spec["components"]["schemas"]
    expected = {
        "CrewStartedData",
        "CrewCompletedData",
        "TaskStartedData",
        "TaskCompletedData",
        "ToolStartedData",
        "ToolFinishedData",
        "LLMStartedData",
        "LLMCompletedData",
        "CostAlertData",
        "HITLRequestData",
        "HITLResponseData",
    }
    assert set(schemas.keys()) == expected


async def test_asyncapi_headers_include_signature(client: AsyncClient):
    """Message headers describe the HMAC signature and event type."""
    resp = await client.get("/api/v1/asyncapi.json")
    spec = resp.json()
    msg = spec["components"]["messages"]["task_completed"]
    headers = msg["headers"]
    assert "X-Webhook-Signature" in headers["properties"]
    assert "X-Blackbeard-Event" in headers["properties"]
    assert headers["properties"]["X-Blackbeard-Event"]["const"] == "task_completed"


async def test_asyncapi_is_deterministic(client: AsyncClient):
    """Calling the endpoint twice returns the same spec (cached)."""
    r1 = await client.get("/api/v1/asyncapi.json")
    r2 = await client.get("/api/v1/asyncapi.json")
    assert r1.json() == r2.json()
