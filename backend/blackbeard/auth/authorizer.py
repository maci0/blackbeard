"""Authorization engine using Role and RoleBinding resources."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.kinds import ResourceKind
from blackbeard.models.resource import Resource

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
        # Evict oldest entries
        cutoff = time.monotonic() - _CACHE_TTL_S
        stale = [k for k, (_, ts) in _cache.items() if ts < cutoff]
        for k in stale:
            _cache.pop(k, None)
        # If still too large, clear entirely
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
        # 1. Find RoleBindings that match the subject
        bindings = await self._find_bindings(subject_kind, subject_name)

        for binding_spec in bindings:
            role_ref = binding_spec.get("role", "")
            # 2. Load the Role referenced by the binding
            role_spec = await self._load_role(role_ref)
            if role_spec is None:
                continue

            # 3. Check if any rule in the role grants the verb on the resource_kind
            rules: list[dict[str, Any]] = role_spec.get("rules", [])
            for rule in rules:
                rule_resources: list[str] = rule.get("resources", [])
                rule_verbs: list[str] = rule.get("verbs", [])

                # Wildcard support
                resource_match = "*" in rule_resources or resource_kind in rule_resources
                verb_match = "*" in rule_verbs or verb in rule_verbs

                if resource_match and verb_match:
                    return True

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

    async def _load_role(self, role_ref: str) -> dict[str, Any] | None:
        """Load a Role spec by ref string (e.g. 'ref:roles/admin') or name."""
        # Handle both ref format and plain name
        role_name = role_ref
        if role_ref.startswith("ref:roles/"):
            role_name = role_ref[len("ref:roles/"):]

        result = await self._session.execute(
            select(Resource.spec).where(
                Resource.kind == ResourceKind.ROLE,
                Resource.name == role_name,
            )
        )
        return result.scalar_one_or_none()
