"""A2A (Agent-to-Agent) Protocol endpoint.

Serves ``/.well-known/agent-card.json`` per the Google A2A specification.
Lists all Crew resources that have ``spec.a2a.enabled: true`` as agent cards.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from blackbeard.kinds import ResourceKind
from blackbeard.models import Resource, get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a2a"])

_cache_entry: tuple[float, dict[str, Any]] | None = None
_cache_lock = asyncio.Lock()
_CACHE_TTL_S = 60.0


def _derive_base_url(request: Request) -> str:
    """Derive the external base URL from the incoming request.

    Uses only the scheme/host that the ASGI server resolved (which honours
    ``X-Forwarded-*`` from trusted proxies via uvicorn's ``forwarded-allow-ips``).
    Raw ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` request headers are NOT
    trusted here: this response is cached globally for 60s, so honouring an
    attacker-supplied forwarded host would let any unauthenticated client
    poison the agent card's URLs for every consumer (CWE-113 / CWE-644),
    redirecting A2A credentials to an attacker-controlled host.
    """
    return f"{request.url.scheme}://{request.url.netloc}"


def _parse_ref_name(ref: str) -> str | None:
    """Extract the resource name from a ``ref:<plural>/<name>`` string.

    Returns ``None`` if the ref format is invalid.
    """
    if not ref.startswith("ref:"):
        return None
    parts = ref[4:].split("/", 1)
    if len(parts) != 2:
        return None
    return parts[1]


def _build_skills(
    task_refs: list[str],
    task_map: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Build A2A skills list from a crew's task refs and resolved task specs."""
    skills: list[dict[str, str]] = []
    for ref in task_refs:
        name = _parse_ref_name(ref)
        if name is None:
            continue
        spec = task_map.get(name)
        if spec is None:
            continue
        description = spec.get("description", "")
        first_line = description.split("\n", 1)[0].strip() if description else name
        skills.append(
            {
                "id": name,
                "name": first_line,
                "description": spec.get("expected_output", ""),
            }
        )
    return skills


_CACHE_HEADERS = {"Cache-Control": f"public, max-age={int(_CACHE_TTL_S)}"}


@router.get("/.well-known/agent-card.json")
async def agent_card(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Return A2A agent cards for all Crew resources with ``a2a.enabled``."""
    global _cache_entry
    now = time.monotonic()

    # Serve from cache if still fresh (fast path, no lock)
    entry = _cache_entry
    if entry is not None and (now - entry[0]) < _CACHE_TTL_S:
        logger.debug(
            "Serving A2A agent card from cache (%d agents)",
            len(entry[1].get("agents", [])),
            extra={"event": "a2a_cache_hit"},
        )
        return JSONResponse(content=entry[1], headers=_CACHE_HEADERS)

    async with _cache_lock:
        # Re-check under lock: another coroutine may have refreshed.
        # Re-read monotonic clock: the original `now` is from before we
        # awaited the lock, so it could be stale enough to miss a fresh entry.
        now = time.monotonic()
        entry = _cache_entry
        if entry is not None and (now - entry[0]) < _CACHE_TTL_S:
            return JSONResponse(content=entry[1], headers=_CACHE_HEADERS)

        base_url = _derive_base_url(request)

        # Fetch all Crew resources (the a2a filter is applied in Python since
        # JSONB operator support varies between PostgreSQL and SQLite tests).
        result = await session.execute(
            select(Resource)
            .where(Resource.kind == ResourceKind.CREW)
            .options(load_only(Resource.name, Resource.project, Resource.spec, Resource.version))
            .order_by(Resource.name)
            .limit(500)
        )
        crews = result.scalars().all()

        a2a_crews = [
            c for c in crews if isinstance(c.spec.get("a2a"), dict) and c.spec["a2a"].get("enabled")
        ]

        if not a2a_crews:
            payload: dict[str, Any] = {"agents": []}
            _cache_entry = (time.monotonic(), payload)
            return JSONResponse(content=payload, headers=_CACHE_HEADERS)

        all_task_names: set[str] = set()
        for crew in a2a_crews:
            for ref in crew.spec.get("tasks", []):
                name = _parse_ref_name(ref)
                if name is not None:
                    all_task_names.add(name)

        task_map: dict[str, dict[str, Any]] = {}
        if all_task_names:
            task_result = await session.execute(
                select(Resource)
                .where(
                    Resource.kind == ResourceKind.TASK,
                    Resource.name.in_(all_task_names),
                )
                .options(load_only(Resource.name, Resource.spec))
                .limit(1000)
            )
            for task in task_result.scalars().all():
                task_map[task.name] = task.spec

        agents: list[dict[str, Any]] = []
        for crew in a2a_crews:
            a2a_spec: dict[str, Any] = crew.spec["a2a"]
            skills = _build_skills(crew.spec.get("tasks", []), task_map)

            card: dict[str, Any] = {
                "name": crew.name,
                "description": crew.spec.get("description", ""),
                "url": f"{base_url}/api/v1/crews/{crew.name}/kickoff?project={crew.project}",
                "provider": {
                    "organization": "Blackbeard",
                    "url": base_url,
                },
                "version": str(crew.version),
                "capabilities": {
                    "streaming": True,
                    "pushNotifications": False,
                },
                "authentication": {
                    "schemes": ["bearer", "apiKey"],
                },
                "defaultInputModes": ["application/json"],
                "defaultOutputModes": ["application/json"],
                "skills": skills,
            }

            # Include optional A2A metadata when present
            if a2a_spec.get("protocol_versions"):
                card["protocolVersions"] = a2a_spec["protocol_versions"]
            if a2a_spec.get("transports"):
                card["supportedTransports"] = a2a_spec["transports"]

            agents.append(card)

        payload = {"agents": agents}
        _cache_entry = (time.monotonic(), payload)

    logger.info(
        "A2A agent card generated: %d agents",
        len(agents),
        extra={
            "event": "a2a_card_generated",
            "agent_count": len(agents),
        },
    )
    return JSONResponse(content=payload, headers=_CACHE_HEADERS)
