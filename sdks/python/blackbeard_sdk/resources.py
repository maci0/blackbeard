"""Resource CRUD operations for the Blackbeard SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from blackbeard_sdk.errors import BlackbeardApiError

if TYPE_CHECKING:
    import httpx

_DictList = list[dict[str, Any]]

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
    "Project": "projects",
    "ServiceAccount": "service-accounts",
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

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        raise NotImplementedError

    def list(
        self,
        kind: str,
        project: str = "default",
        *,
        label_selector: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List resources of a given kind.

        Args:
            kind: Resource kind (e.g. "Agent", "Task", "Crew") or plural
                  (e.g. "agents").
            project: Project to filter by.
            label_selector: Comma-separated label filters (e.g. "env=prod,team=ml").
            limit: Maximum number of results (1-1000).
            offset: Number of results to skip.

        Returns:
            List of resource dicts.
        """
        plural = _kind_plural(kind)
        params: dict[str, Any] = {
            "project": project,
            "limit": limit,
            "offset": offset,
        }
        if label_selector:
            params["label_selector"] = label_selector
        return self._send("GET", f"/api/v1/{plural}", params=params).json()["items"]

    def get(self, kind: str, name: str, project: str = "default") -> dict[str, Any]:
        """Get a single resource by kind and name.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            project: Resource project.

        Returns:
            Resource dict.
        """
        plural = _kind_plural(kind)
        return self._send(
            "GET",
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"project": project},
        ).json()

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
        return self._send("POST", f"/api/v1/{plural}", json=resource).json()

    def update(
        self,
        kind: str,
        name: str,
        resource: dict[str, Any],
        project: str = "default",
    ) -> dict[str, Any]:
        """Update a resource by kind and name (optimistic locking via version).

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            resource: Updated resource fields (must include version for
                      optimistic locking).
            project: Resource project.

        Returns:
            Updated resource dict.
        """
        plural = _kind_plural(kind)
        return self._send(
            "PUT",
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"project": project},
            json=resource,
        ).json()

    def delete(self, kind: str, name: str, project: str = "default") -> None:
        """Delete a resource by kind and name. Idempotent.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            project: Resource project.
        """
        plural = _kind_plural(kind)
        self._send(
            "DELETE",
            f"/api/v1/{plural}/{quote(name, safe='')}",
            params={"project": project},
        )

    def apply(self, resources: _DictList) -> _DictList:
        """Create or update multiple resources (sequential upsert).

        Each resource is sent as a POST (which the API treats as upsert).
        On failure, the error detail includes the kind/name of the resource
        that failed and its position in the list.

        Args:
            resources: List of resource definition dicts.

        Returns:
            List of created/updated resource dicts.
        """
        results: list[dict[str, Any]] = []
        for i, resource in enumerate(resources):
            try:
                results.append(self.create(resource))
            except BlackbeardApiError as exc:
                kind = resource.get("kind", "?")
                name = resource.get("metadata", {}).get("name", "?")
                raise BlackbeardApiError(
                    exc.status_code,
                    f"[{i}] {kind}/{name}: {exc.detail}",
                    exc.body,
                ) from exc
        return results

    def list_versions(
        self,
        kind: str,
        name: str,
        project: str = "default",
    ) -> list[dict[str, Any]]:
        """List version snapshots for a resource.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            project: Resource project.

        Returns:
            List of version summary dicts (version, changed_by, created_at, changed_keys).
        """
        plural = _kind_plural(kind)
        return self._send(
            "GET",
            f"/api/v1/{plural}/{quote(name, safe='')}/versions",
            params={"project": project},
        ).json()["versions"]

    def get_version(
        self,
        kind: str,
        name: str,
        version: int,
        project: str = "default",
    ) -> dict[str, Any]:
        """Get the full snapshot of a resource at a specific version.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            version: Version number (1-based).
            project: Resource project.

        Returns:
            Version detail dict with spec, labels, changed_by, created_at.
        """
        plural = _kind_plural(kind)
        return self._send(
            "GET",
            f"/api/v1/{plural}/{quote(name, safe='')}/versions/{version}",
            params={"project": project},
        ).json()

    def rollback(
        self,
        kind: str,
        name: str,
        to_version: int,
        project: str = "default",
    ) -> dict[str, Any]:
        """Rollback a resource to a previous version.

        Args:
            kind: Resource kind or plural.
            name: Resource name.
            to_version: Version number to restore.
            project: Resource project.

        Returns:
            Updated resource dict.
        """
        plural = _kind_plural(kind)
        return self._send(
            "POST",
            f"/api/v1/{plural}/{quote(name, safe='')}/rollback",
            params={"project": project},
            json={"to_version": to_version},
        ).json()

    def export_all(self, project: str = "default") -> str:
        """Export all resources in a project as a YAML string.

        Uses the server's bulk export endpoint (single request) and returns
        a multi-document YAML string.  To re-import, parse with
        ``yaml.safe_load_all()`` and pass the resulting list to ``apply()``.

        Args:
            project: Project to export.

        Returns:
            Multi-document YAML string.
        """
        return self._send(
            "GET",
            "/api/v1/resources/export",
            params={"project": project},
        ).text
