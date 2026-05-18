"""Authorization engine using Role and RoleBinding resources."""

from __future__ import annotations

import collections
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.kinds import ResourceKind
from blackbeard.models import Resource

logger = logging.getLogger(__name__)

# OrderedDict gives O(1) FIFO eviction vs heapq's O(n log k) scan.
_cache: collections.OrderedDict[str, tuple[bool, float]] = collections.OrderedDict()
_CACHE_TTL_S = 30.0
_CACHE_MAX_SIZE = 10_000


def _cache_key(
    subject_kind: str, subject_name: str, verb: str, resource_kind: str, namespace: str
) -> str:
    return f"{subject_kind}:{subject_name}:{verb}:{resource_kind}:{namespace}"


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
        to_evict = _CACHE_MAX_SIZE // 5
        for _ in range(min(to_evict, len(_cache))):
            _cache.popitem(last=False)
        logger.debug(
            "Authorization cache eviction: evicted=%d remaining=%d",
            to_evict,
            len(_cache),
            extra={
                "event": "authz_cache_eviction",
                "evicted": to_evict,
                "remaining": len(_cache),
                "max_size": _CACHE_MAX_SIZE,
            },
        )
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
        key = _cache_key(subject_kind, subject_name, verb, resource_kind, namespace)
        cached = _get_cached(key)
        if cached is not None:
            return cached

        t0 = time.monotonic()
        result = await self._check_uncached(subject_kind, subject_name, verb, resource_kind)
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        _set_cached(key, result)
        if duration_ms > 100:
            logger.warning(
                "Slow authorization check: %s/%s verb=%s resource=%s (%.0fms)",
                subject_kind,
                subject_name,
                verb,
                resource_kind,
                duration_ms,
                extra={
                    "event": "authz_slow_check",
                    "subject_kind": subject_kind,
                    "subject_name": subject_name,
                    "verb": verb,
                    "resource_kind": resource_kind,
                    "duration_ms": duration_ms,
                    "result": result,
                },
            )
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

        binding_role_names: list[str] = [
            binding.get("role", "").removeprefix("ref:roles/") for binding in bindings
        ]
        role_names = {n for n in binding_role_names if n}

        roles = await self._load_roles_batch(role_names) if role_names else {}

        for role_name in binding_role_names:
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
                    logger.debug(
                        "Authorization granted: %s/%s verb=%s resource=%s via role=%s",
                        subject_kind,
                        subject_name,
                        verb,
                        resource_kind,
                        role_name,
                        extra={
                            "event": "authz_granted",
                            "subject_kind": subject_kind,
                            "subject_name": subject_name,
                            "verb": verb,
                            "resource_kind": resource_kind,
                            "role_name": role_name,
                        },
                    )
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
            select(Resource.spec).where(Resource.kind == ResourceKind.ROLE_BINDING).limit(1000)
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
