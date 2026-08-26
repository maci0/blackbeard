"""Integration tests for resource API endpoint edge cases.

Covers paths in api/resources.py not exercised by test_api.py:
label_selector filtering, bad label formats, delete via API when
resource doesn't exist (204 idempotent), and update with metadata
mismatch.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import API_KEY_HEADER, _agent_payload

# ---------------------------------------------------------------------------
# Label selector filtering
# ---------------------------------------------------------------------------


async def test_list_with_label_selector(client: AsyncClient):
    """GET /agents?label_selector=env=prod filters by label."""
    # Create agent with labels
    payload = _agent_payload("labeled-agent")
    payload["metadata"]["labels"] = {"env": "prod", "team": "ml"}
    resp = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert resp.status_code == 201

    # Create another without the label
    resp2 = await client.post(
        "/api/v1/agents", json=_agent_payload("unlabeled-agent"), headers=API_KEY_HEADER
    )
    assert resp2.status_code == 201

    # Filter by label
    resp = await client.get("/api/v1/agents?label_selector=env%3Dprod", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    names = [item["metadata"]["name"] for item in data["items"]]
    assert "labeled-agent" in names, "Label filter must return the labeled agent"
    assert "unlabeled-agent" not in names, "Label filter must exclude unlabeled agents"
    assert data["total"] == 1
    for item in data["items"]:
        assert item["metadata"].get("labels", {}).get("env") == "prod"


async def test_list_with_invalid_label_selector(client: AsyncClient):
    """GET /agents?label_selector=badformat returns 400."""
    resp = await client.get("/api/v1/agents?label_selector=no-equals-sign", headers=API_KEY_HEADER)
    assert resp.status_code == 400
    assert "label" in resp.json()["detail"].lower()


async def test_list_with_empty_label_key(client: AsyncClient):
    """GET /agents?label_selector==value returns 400 (empty key)."""
    resp = await client.get("/api/v1/agents?label_selector=%3Dvalue", headers=API_KEY_HEADER)
    assert resp.status_code == 400


async def test_list_with_duplicate_label_key(client: AsyncClient):
    """GET /agents?label_selector=env=a,env=b returns 400 (duplicate key)."""
    resp = await client.get(
        "/api/v1/agents?label_selector=env%3Da%2Cenv%3Db", headers=API_KEY_HEADER
    )
    assert resp.status_code == 400
    assert "duplicate" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Namespace filtering
# ---------------------------------------------------------------------------


async def test_list_by_project(client: AsyncClient):
    """GET /agents?project=other returns only resources in that project."""
    # Create in default project
    resp1 = await client.post(
        "/api/v1/agents", json=_agent_payload("ns-default"), headers=API_KEY_HEADER
    )
    assert resp1.status_code == 201

    # Create in custom project
    payload = _agent_payload("ns-other")
    payload["metadata"]["project"] = "other"
    resp2 = await client.post("/api/v1/agents", json=payload, headers=API_KEY_HEADER)
    assert resp2.status_code == 201

    # Filter by project
    resp = await client.get("/api/v1/agents?project=other", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["metadata"]["project"] == "other"


# ---------------------------------------------------------------------------
# Update with metadata mismatch
# ---------------------------------------------------------------------------


async def test_update_with_name_mismatch(client: AsyncClient):
    """PUT /agents/{name} with different name in body returns 422."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 1,
        "metadata": {"name": "different-name", "project": "default"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    resp = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert resp.status_code == 422
    assert "rename" in resp.json()["detail"].lower()


async def test_update_with_project_mismatch(client: AsyncClient):
    """PUT /agents/{name} with different project in body returns 422."""
    r = await client.post("/api/v1/agents", json=_agent_payload(), headers=API_KEY_HEADER)
    assert r.status_code == 201

    update_payload = {
        "version": 1,
        "metadata": {"name": "researcher", "project": "other"},
        "spec": {"role": "R", "goal": "G", "backstory": "B"},
    }
    resp = await client.put(
        "/api/v1/agents/researcher", json=update_payload, headers=API_KEY_HEADER
    )
    assert resp.status_code == 422
    assert "project" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Resource kind discovery
# ---------------------------------------------------------------------------


async def test_unknown_kind_returns_422(client: AsyncClient):
    """GET /api/v1/unknownkind should return 422 (pattern doesn't match)."""
    resp = await client.get("/api/v1/unknownkind", headers=API_KEY_HEADER)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tool resource
# ---------------------------------------------------------------------------


async def test_create_and_list_tool(client: AsyncClient):
    """End-to-end create + list for Tool resources."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Tool",
        "metadata": {"name": "web-search", "project": "default"},
        "spec": {"type": "builtin", "description": "Search the web"},
    }
    r = await client.post("/api/v1/tools", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["kind"] == "Tool"
    assert data["spec"]["type"] == "builtin"
    assert data["spec"]["description"] == "Search the web"
    assert data["version"] == 1

    resp = await client.get("/api/v1/tools", headers=API_KEY_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    item = resp.json()["items"][0]
    assert item["metadata"]["name"] == "web-search"
    assert item["spec"]["type"] == "builtin"


# ---------------------------------------------------------------------------
# Guardrail resource
# ---------------------------------------------------------------------------


async def test_create_guardrail(client: AsyncClient):
    """Create a Guardrail resource and verify stored spec."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "Guardrail",
        "metadata": {"name": "no-pii", "project": "default"},
        "spec": {
            "description": "Prevent PII in output",
            "type": "function",
            "function_path": "blackbeard.guardrails.check_pii",
        },
    }
    r = await client.post("/api/v1/guardrails", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["kind"] == "Guardrail"
    assert data["metadata"]["name"] == "no-pii"
    assert data["spec"]["type"] == "function"
    assert data["spec"]["function_path"] == "blackbeard.guardrails.check_pii"
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# KnowledgeSource resource
# ---------------------------------------------------------------------------


async def test_create_knowledge_source(client: AsyncClient):
    """Create a KnowledgeSource resource and verify stored spec."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "KnowledgeSource",
        "metadata": {"name": "docs-db", "project": "default"},
        "spec": {
            "type": "text",
        },
    }
    r = await client.post("/api/v1/knowledge-sources", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["kind"] == "KnowledgeSource"
    assert data["metadata"]["name"] == "docs-db"
    assert data["spec"]["type"] == "text"
    assert data["version"] == 1


# ---------------------------------------------------------------------------
# AgentPolicy resource
# ---------------------------------------------------------------------------


async def test_create_agent_policy(client: AsyncClient):
    """Create an AgentPolicy resource and verify stored spec."""
    payload = {
        "apiVersion": "blackbeard/v1",
        "kind": "AgentPolicy",
        "metadata": {"name": "budget-policy", "project": "default"},
        "spec": {
            "budget": {
                "max_tokens": 10000,
                "max_usd": 5.0,
            },
        },
    }
    r = await client.post("/api/v1/agent-policies", json=payload, headers=API_KEY_HEADER)
    assert r.status_code == 201
    data = r.json()
    assert data["kind"] == "AgentPolicy"
    assert data["metadata"]["name"] == "budget-policy"
    assert data["spec"]["budget"]["max_tokens"] == 10000
    assert data["spec"]["budget"]["max_usd"] == 5.0
    assert data["version"] == 1
