"""Authorization engine using Role and RoleBinding resources."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.kinds import ResourceKind
from blackbeard.models import Resource

logger = logging.getLogger(__name__)

# Simple in-memory cache with TTL for authorization decisions
_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL_S = 30.0
_CACHE_MAX_SIZE = 10_000


def _cache_key(subject_kind: str, subject_name: str, verb: str, resource_kind: str) -> str:
    return f"{subject_kind}:{subject_name}:{verb}:{resource_kind}"


def _get_cached(key: str) -> bool | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _CACHE_TTL_S:
        _cache.pop(key, None)
        return None
    return result


def _set_cached(key: str, result: bool) -> None:
    if len(_cache) >= _CACHE_MAX_SIZE:
        _cache.clear()
    _cache[key] = (result, time.monotonic())


def clear_cache() -> None:
    """Clear the authorization cache (useful for testing)."""
    _cache.clear()


class Authorizer:
    """Check whether a subject is authorized to perform an action on a resource.

    Loads Role and RoleBinding resources from the database, checks if any
    binding grants the requested verb on the resource kind.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check(
        self,
        subject_kind: str,
        subject_name: str,
        verb: str,
        resource_kind: str,
        namespace: str = "default",
    ) -> bool:
        """Check if the subject is authorized for the given verb on resource_kind.

        Returns True if authorized, False otherwise.
        """
        key = _cache_key(subject_kind, subject_name, verb, resource_kind)
        cached = _get_cached(key)
        if cached is not None:
            return cached

        result = await self._check_uncached(subject_kind, subject_name, verb, resource_kind)
        _set_cached(key, result)
        return result

    async def _check_uncached(
        self,
        subject_kind: str,
        subject_name: str,
        verb: str,
        resource_kind: str,
    ) -> bool:
        """Perform the actual authorization check against the database."""
        bindings = await self._find_bindings(subject_kind, subject_name)
        if not bindings:
            logger.warning(
                "Authorization denied: %s/%s verb=%s resource=%s bindings=0",
                subject_kind,
                subject_name,
                verb,
                resource_kind,
                extra={
                    "event": "authz_denied",
                    "subject_kind": subject_kind,
                    "subject_name": subject_name,
                    "verb": verb,
                    "resource_kind": resource_kind,
                    "bindings_checked": 0,
                },
            )
            return False

        role_names: set[str] = set()
        for binding_spec in bindings:
            role_ref = binding_spec.get("role", "")
            if role_ref:
                rn = role_ref.removeprefix("ref:roles/")
                role_names.add(rn)

        roles = await self._load_roles_batch(role_names) if role_names else {}

        for binding_spec in bindings:
            role_ref = binding_spec.get("role", "")
            role_name = role_ref.removeprefix("ref:roles/")
            role_spec = roles.get(role_name)
            if role_spec is None:
                continue

            rules: list[dict[str, Any]] = role_spec.get("rules", [])
            for rule in rules:
                rule_resources: list[str] = rule.get("resources", [])
                rule_verbs: list[str] = rule.get("verbs", [])

                resource_match = "*" in rule_resources or resource_kind in rule_resources
                verb_match = "*" in rule_verbs or verb in rule_verbs

                if resource_match and verb_match:
                    return True

        logger.warning(
            "Authorization denied: %s/%s verb=%s resource=%s bindings=%d",
            subject_kind,
            subject_name,
            verb,
            resource_kind,
            len(bindings),
            extra={
                "event": "authz_denied",
                "subject_kind": subject_kind,
                "subject_name": subject_name,
                "verb": verb,
                "resource_kind": resource_kind,
                "bindings_checked": len(bindings),
            },
        )
        return False

    async def _find_bindings(
        self,
        subject_kind: str,
        subject_name: str,
    ) -> list[dict[str, Any]]:
        """Find all RoleBinding specs where the subject matches."""
        result = await self._session.execute(
            select(Resource.spec).where(
                Resource.kind == ResourceKind.ROLE_BINDING,
            )
        )
        rows = result.scalars().all()
        matching: list[dict[str, Any]] = []
        for spec in rows:
            subjects: list[dict[str, str]] = spec.get("subjects", [])
            for subj in subjects:
                if subj.get("kind") == subject_kind and subj.get("name") == subject_name:
                    matching.append(spec)
                    break
        return matching

    async def _load_roles_batch(self, role_names: set[str]) -> dict[str, dict[str, Any]]:
        """Load multiple Role specs by name in a single query."""
        result = await self._session.execute(
            select(Resource.name, Resource.spec).where(
                Resource.kind == ResourceKind.ROLE,
                Resource.name.in_(role_names),
            )
        )
        return {row.name: row.spec for row in result.all()}
