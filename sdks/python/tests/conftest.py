"""Shared test fixtures for the Blackbeard Python SDK tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from blackbeard_sdk import BlackbeardClient


def _mock_response(
    status_code: int = 200,
    json_data: Any = None,
) -> httpx.Response:
    """Build a mock httpx.Response."""
    content = json.dumps(json_data).encode() if json_data is not None else b""
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


class MockTransport(httpx.BaseTransport):
    """Records requests and returns canned responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        self._response_queue: list[httpx.Response] = []

    def queue(self, resp: httpx.Response) -> None:
        self._response_queue.append(resp)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert self._response_queue, (
            f"MockTransport: no queued response for {request.method} {request.url} "
            f"(request #{len(self.requests)}). Queue a response with transport.queue()."
        )
        resp = self._response_queue.pop(0)
        resp.request = request
        return resp


@pytest.fixture
def transport() -> MockTransport:
    return MockTransport()


@pytest.fixture
def client(transport: MockTransport) -> BlackbeardClient:
    c = BlackbeardClient(base_url="http://test:8000", api_key="test-key")
    c._http = httpx.Client(
        base_url="http://test:8000",
        headers={"X-API-Key": "test-key"},
        transport=transport,
    )
    return c
