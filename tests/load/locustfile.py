"""Load tests for Blackbeard API using Locust.

Run: locust -f tests/load/locustfile.py --host http://localhost:8000
Web UI opens at http://localhost:8089

Or headless:
  locust -f tests/load/locustfile.py --host http://localhost:8000 \
    --headless -u 50 -r 5 --run-time 60s
"""

from __future__ import annotations

import json
import random
import string

from locust import HttpUser, between, task


def _random_name() -> str:
    return "load-" + "".join(random.choices(string.ascii_lowercase, k=8))


class BlackbeardUser(HttpUser):
    wait_time = between(0.5, 2.0)
    api_key = "change-me-in-production"

    def on_start(self) -> None:
        self.headers = {"X-API-Key": self.api_key}

    # -- Health --

    @task(10)
    def health(self) -> None:
        self.client.get("/api/v1/health", headers=self.headers)

    @task(5)
    def readiness(self) -> None:
        self.client.get("/api/v1/health/ready", headers=self.headers)

    # -- Resource CRUD --

    @task(8)
    def list_agents(self) -> None:
        self.client.get("/api/v1/agents", headers=self.headers)

    @task(8)
    def list_tasks(self) -> None:
        self.client.get("/api/v1/tasks", headers=self.headers)

    @task(8)
    def list_crews(self) -> None:
        self.client.get("/api/v1/crews", headers=self.headers)

    @task(5)
    def list_tools(self) -> None:
        self.client.get("/api/v1/tools", headers=self.headers)

    @task(3)
    def list_llm_connections(self) -> None:
        self.client.get("/api/v1/llm-connections", headers=self.headers)

    @task(2)
    def list_executions(self) -> None:
        self.client.get("/api/v1/executions", headers=self.headers)

    @task(2)
    def list_audit_logs(self) -> None:
        self.client.get("/api/v1/audit-logs", headers=self.headers)

    @task(1)
    def export_resources(self) -> None:
        self.client.get("/api/v1/resources/export", headers=self.headers)

    # -- Create and delete agent (write path) --

    @task(3)
    def create_and_delete_agent(self) -> None:
        name = _random_name()
        payload = {
            "apiVersion": "blackbeard/v1",
            "kind": "Agent",
            "metadata": {"name": name, "project": "default"},
            "spec": {
                "role": "Load Test Agent",
                "goal": "Verify API performance under load",
                "backstory": "Created by load test",
            },
        }
        with self.client.post(
            "/api/v1/agents",
            json=payload,
            headers={**self.headers, "Content-Type": "application/json"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                resp.success()
                self.client.delete(
                    f"/api/v1/agents/{name}",
                    headers=self.headers,
                    name="/api/v1/agents/[name]",
                )
            elif resp.status_code == 409:
                resp.success()
            else:
                resp.failure(f"Create agent failed: {resp.status_code}")

    # -- A2A endpoint --

    @task(2)
    def agent_card(self) -> None:
        self.client.get("/.well-known/agent-card.json")

    # -- Tools library --

    @task(2)
    def tools_library(self) -> None:
        self.client.get("/api/v1/tools/library", headers=self.headers)

    # -- Auth --

    @task(1)
    def whoami(self) -> None:
        self.client.get("/api/v1/auth/me", headers=self.headers)


class AdminUser(HttpUser):
    """Simulates admin-heavy operations at lower frequency."""

    wait_time = between(2.0, 5.0)
    api_key = "change-me-in-production"
    weight = 1  # 1/10th the traffic of regular users

    def on_start(self) -> None:
        self.headers = {"X-API-Key": self.api_key}

    @task(5)
    def list_users(self) -> None:
        self.client.get("/api/v1/users", headers=self.headers)

    @task(3)
    def list_roles(self) -> None:
        self.client.get("/api/v1/roles", headers=self.headers)

    @task(3)
    def list_groups(self) -> None:
        self.client.get("/api/v1/groups", headers=self.headers)

    @task(2)
    def list_webhooks(self) -> None:
        self.client.get("/api/v1/webhooks", headers=self.headers)

    @task(2)
    def list_credentials(self) -> None:
        self.client.get("/api/v1/credentials", headers=self.headers)

    @task(1)
    def list_projects(self) -> None:
        self.client.get("/api/v1/projects", headers=self.headers)
