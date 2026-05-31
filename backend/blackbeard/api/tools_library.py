"""Tools Library API — browse and install curated tools."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import require_permission
from blackbeard.kinds import API_VERSION
from blackbeard.models import User, get_session
from blackbeard.models.resource_schemas import ResourceCreate, ResourceMetadata
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter
from blackbeard.resources import ResourceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/library", tags=["tools-library"])

_CATALOG_PATH = Path(__file__).parent.parent / "tools_library.yaml"
_catalog: list[dict[str, Any]] | None = None


def _load_catalog() -> list[dict[str, Any]]:
    global _catalog
    if _catalog is not None:
        return _catalog
    if not _CATALOG_PATH.exists():
        logger.warning("Tools library catalog not found: %s", _CATALOG_PATH)
        return []
    try:
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, list):
            logger.error(
                "Tools library catalog root must be a list, got %s: %s",
                type(raw).__name__,
                _CATALOG_PATH,
                extra={"event": "tools_library_invalid_type", "root_type": type(raw).__name__},
            )
            return []
        _catalog = raw
    except yaml.YAMLError:
        logger.exception("Tools library catalog has invalid YAML: %s", _CATALOG_PATH)
        return []
    except OSError:
        logger.exception("Failed to read tools library catalog: %s", _CATALOG_PATH)
        return []
    logger.info(
        "Tools library loaded: %d entries",
        len(_catalog),
        extra={"event": "tools_library_loaded", "count": len(_catalog)},
    )
    return _catalog


class LibraryTool(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    type: str
    class_path: str = ""
    sandbox: str = "none"
    tags: list[str] = []
    config: dict[str, Any] = {}


class LibraryListResponse(BaseModel):
    tools: list[LibraryTool]
    total: int
    categories: list[str]


class InstallRequest(BaseModel):
    slugs: list[str] = Field(..., min_length=1, max_length=20)


class InstallResponse(BaseModel):
    installed: int
    skipped: int
    errors: list[str]


@router.get(
    "",
    response_model=LibraryListResponse,
    responses={401: {"description": "Authentication required"}},
)
async def list_library_tools(
    category: str | None = Query(default=None, description="Filter by category"),
    search: str | None = Query(default=None, max_length=100, description="Search by name or tag"),
    _current_user: User | None = Depends(require_permission("list", "Tool")),
) -> LibraryListResponse:
    """Browse the curated tools library."""
    catalog = _load_catalog()

    tools = []
    categories_set: set[str] = set()
    q = search.lower() if search else ""
    for entry in catalog:
        categories_set.add(entry.get("category", "other"))
        if category and entry.get("category") != category:
            continue
        if q:
            slug_match = q in entry.get("slug", "").lower()
            name_match = q in entry.get("name", "").lower()
            desc_match = q in entry.get("description", "").lower()
            tag_match = any(q in t.lower() for t in entry.get("tags", []))
            if not (slug_match or name_match or desc_match or tag_match):
                continue
        tools.append(
            LibraryTool(
                slug=entry["slug"],
                name=entry["name"],
                description=entry.get("description", ""),
                category=entry.get("category", "other"),
                type=entry.get("type", "python"),
                class_path=entry.get("class_path", ""),
                sandbox=entry.get("sandbox", "none"),
                tags=entry.get("tags", []),
                config=entry.get("config", {}),
            )
        )

    return LibraryListResponse(
        tools=tools,
        total=len(tools),
        categories=sorted(categories_set),
    )


@router.post(
    "/install",
    response_model=InstallResponse,
    responses={
        401: {"description": "Authentication required"},
        429: {"description": "Too many install requests"},
    },
)
async def install_library_tools(
    request: Request,
    body: InstallRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_permission("create", "Tool", require_identity=True)),
) -> InstallResponse:
    """Install tools from the library as Blackbeard Tool resources."""
    check_rate_limit(mutation_limiter, _current_user, "Too many install requests. Try again later.")

    catalog = _load_catalog()
    by_slug = {e["slug"]: e for e in catalog}

    installed = 0
    skipped = 0
    errors: list[str] = []

    service = ResourceService(session)

    for slug in body.slugs:
        entry = by_slug.get(slug)
        if not entry:
            errors.append(f"{slug}: not found in library")
            continue

        spec: dict[str, Any] = {
            "type": entry.get("type", "python"),
            "class_path": entry.get("class_path", ""),
            "description": entry.get("description", ""),
            "sandbox": entry.get("sandbox", "none"),
        }
        if entry.get("config"):
            spec["config"] = entry["config"]

        try:
            data = ResourceCreate(
                apiVersion=API_VERSION,
                kind="Tool",
                metadata=ResourceMetadata(
                    name=slug,
                    project="default",
                    labels={
                        "source": "library",
                        "category": entry.get("category", "other"),
                    },
                ),
                spec=spec,
            )
            await service.create(data)
            installed += 1
        except Exception as exc:
            if "already exists" in str(exc).lower() or "conflict" in str(exc).lower():
                skipped += 1
            else:
                errors.append(f"{slug}: {str(exc)[:100]}")

    await log_audit(
        session=session,
        action="import",
        resource_type="Tool",
        resource_id=f"library:{installed}",
        detail={
            "source": "library",
            "installed": installed,
            "skipped": skipped,
            "errors": len(errors),
        },
        **audit_from_request(request, _current_user),
    )
    await session.commit()

    return InstallResponse(installed=installed, skipped=skipped, errors=errors)
