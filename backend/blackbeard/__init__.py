"""Blackbeard: Agent Management Platform.

Package layout (where new code goes):

- ``api/``: FastAPI routers, middleware, request/response transport only.
  No business rules beyond orchestration of domain services.
- ``auth/``: JWT, API keys, passwords, RBAC authorizer and FastAPI deps.
- ``engine/``: Crew/flow execution, loader, policy, sandbox, scheduler,
  Temporal adapter, assistant, agency import.
- ``resources/``: Resource kinds CRUD service, JSON Schema validation, refs.
- ``models/``: SQLAlchemy ORM + Pydantic API schemas (``*_schemas.py``).
- ``litellm/``: LiteLLM proxy sync, virtual keys, model config helpers.
- ``plugins/``: Extension registry and discovery (tool, guardrail, auth, hook).
- Root modules: cross-cutting infrastructure colocated at package root:
  ``config``, ``audit``, ``metrics``, ``rate_limiter``, ``retention``,
  ``sse``, ``http_client``, ``logging_config``, ``pii``, ``kinds``, ``main``.

Dependency direction (outer → inner): ``api`` → ``engine`` / ``resources`` /
``auth`` → ``models`` / ``config``. Infrastructure modules must not import
``api`` or ``engine`` (inject at the boundary instead).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("blackbeard")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.0.0.dev0"
