"""Resource CRUD operations for the Blackbeard SDK."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
import yaml

# Canonical kind-to-plural mapping matching backend/blackbeard/kinds.py
KIND_TO_PLURAL: dict[str, str] = {
    "Agent": "agents",
    "Task": "tasks",
    "Crew": "crews",
    "Tool": "tools",
    "LLMConnection": "llm-connections",
    "AgentPolicy": "agent-policies",
    "Guardrail": "guardrails",
    "Flow": "flows",
    "KnowledgeSource": "knowledge-sources",
    "Role": "roles",
    "RoleBinding": "role-bindings",
    "Automation": "automations",
}


def _kind_plural(kind: str) -> str:
    """Resolve a kind name to its URL plural form."""
    plural = KIND_TO_PLURAL.get(kind)
    if plural is None:
        # If already a plural (e.g. user passed "agents"), use as-is
        if kind in KIND_TO_PLURAL.values():
            return kind
        raise ValueError(
            f"Unknown resource kind '{kind}'. "
            f"Valid kinds: {', '.join(sorted(KIND_TO_PLURAL.keys()))}"
        )
    return plural


class ResourceMixin:
    """Resource CRUD methods mixed into BlackbeardClient."""

    _http: httpx.Client

    def list(
        self,
        kind: str,
        namespace: str = "default",
        *,
        label_selector: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List resources of a given kind.

        Args:
            kind: Resource kind (e.g. "Agent", "Task", "Crew") or plural
                  (e.g. "agents").
            namespace: Namespace to filter by.
            label_selector: Comma-separated label filters (e.g. "env=prod,team=ml").
            limit: Maximum number of results (1-1000).
            offset: Number of results to skip.

        Returns:
            List of resource dicts.
        """
        plural = _kind_plural(kind)
        params: dict[str, Any] = {
            "namespace": namespace,
            "limit": limit,
            "offset": offset,
        }
        if label_selector:
            params["label_selector"] = label_selector
        resp = self._http.get(f"/api/v1/{plural}", params=params)
        resp.raise_for_status()
        return resp.json()["items"]

    def get(self, kind: str, name: str, namespace: str = "default") -> dict[str, Any]:
        """Get a single resource by kind and name.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            namespace: Resource namespace.

        Returns:
            Resource dict.
        """
        plural = _kind_plural(kind)
        resp = self._http.get(
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"namespace": namespace},
        )
        resp.raise_for_status()
        return resp.json()

    def create(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Create (or upsert) a resource.

        The resource dict must contain a "kind" key and a "metadata" key
        with at least a "name" field.

        Args:
            resource: Resource definition dict.

        Returns:
            Created/updated resource dict.
        """
        kind = resource.get("kind")
        if not kind:
            raise ValueError("Resource dict must contain a 'kind' key")
        plural = _kind_plural(kind)
        resp = self._http.post(f"/api/v1/{plural}", json=resource)
        resp.raise_for_status()
        return resp.json()

    def update(
        self,
        kind: str,
        name: str,
        resource: dict[str, Any],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Update a resource by kind and name (optimistic locking via version).

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            resource: Updated resource fields (must include version for
                      optimistic locking).
            namespace: Resource namespace.

        Returns:
            Updated resource dict.
        """
        plural = _kind_plural(kind)
        resp = self._http.put(
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"namespace": namespace},
            json=resource,
        )
        resp.raise_for_status()
        return resp.json()

    def delete(self, kind: str, name: str, namespace: str = "default") -> None:
        """Delete a resource by kind and name. Idempotent.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            namespace: Resource namespace.
        """
        plural = _kind_plural(kind)
        resp = self._http.delete(
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"namespace": namespace},
        )
        resp.raise_for_status()

    def apply(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create or update multiple resources (sequential upsert).

        Each resource is sent as a POST (which the API treats as upsert).

        Args:
            resources: List of resource definition dicts.

        Returns:
            List of created/updated resource dicts.
        """
        results: list[dict[str, Any]] = []
        for resource in resources:
            results.append(self.create(resource))
        return results

    def export_all(self, namespace: str = "default") -> str:
        """Export all resources in a namespace as a YAML string.

        Fetches every known resource kind and serializes them into a
        multi-document YAML string suitable for re-import via apply().

        Args:
            namespace: Namespace to export.

        Returns:
            Multi-document YAML string.
        """
        all_resources: list[dict[str, Any]] = []
        for kind in KIND_TO_PLURAL:
            items = self.list(kind, namespace=namespace, limit=1000)
            all_resources.extend(items)
        return yaml.dump_all(all_resources, default_flow_style=False, sort_keys=False)
