"""REST API layer: routers, middleware, and request/response handling.

Each module is one router (or middleware). Shared transport constants live
here so list endpoints stay consistent without a separate utils package.

Routers (wired in ``blackbeard.main``): a2a, agency_import, assistant,
asyncapi, audit, auth, automations, chat, collaboration, credentials,
executions, health, marketplace, oidc, plugins, resources, tools_library,
users, webhooks. Cross-cutting: ``middleware`` and ``mutations`` (shared
post-mutation side effects: LiteLLM sync, scheduler reload, RBAC cache
invalidation, background task draining).

Keep domain logic out of this package; call into ``engine``, ``resources``,
``auth``, and ``models`` instead.

This module must never import a sibling router or middleware module: many
routers import these helpers via ``from blackbeard.api import ...``, so any
eager sibling import here creates an import cycle across the whole package.
"""

from __future__ import annotations

from blackbeard.resources.service import smart_total

__all__ = [
    "MUTATION_RATE_MSG",
    "RETRY_HEADERS_30",
    "smart_total",
]

RETRY_HEADERS_30: dict[str, str] = {"Retry-After": "30"}
MUTATION_RATE_MSG = "Too many mutation requests. Try again later."
