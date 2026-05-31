"""Agency Agents import — fetch and convert personas from GitHub."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import require_permission
from blackbeard.engine.agency_import import parse_agency_agent_markdown
from blackbeard.http_client import get_client
from blackbeard.kinds import API_VERSION
from blackbeard.models import User, get_session
from blackbeard.models.resource_schemas import ResourceCreate, ResourceMetadata
from blackbeard.rate_limiter import check_rate_limit, mutation_limiter
from blackbeard.resources import ResourceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"])

_REPO_OWNER = "msitarzewski"
_REPO_NAME = "agency-agents"
_GITHUB_API = "https://api.github.com"

_DIVISIONS = [
    "academic",
    "design",
    "engineering",
    "finance",
    "game-development",
    "marketing",
    "paid-media",
    "product",
    "project-management",
    "sales",
    "spatial-computing",
    "specialized",
    "strategy",
    "support",
    "testing",
]


class AgencyAgentPreview(BaseModel):
    name: str
    slug: str
    role: str
    goal: str
    backstory: str = ""
    division: str = ""
    source_file: str = ""


class AgencyAgentListResponse(BaseModel):
    agents: list[AgencyAgentPreview]
    total: int
    divisions: list[str]


class AgencyAgentImportRequest(BaseModel):
    slugs: list[str] = Field(..., min_length=1, max_length=50, description="Agent slugs to import")


class AgencyAgentImportResponse(BaseModel):
    imported: int
    skipped: int
    errors: list[str]


_file_cache: dict[str, tuple[float, str | None]] = {}
_FILE_CACHE_TTL = 300.0  # 5 minutes
_FILE_CACHE_MAX = 500


async def _fetch_github_file(path: str) -> str | None:
    """Fetch a raw file from the Agency Agents GitHub repo (cached 5min)."""
    now = time.monotonic()
    cached = _file_cache.get(path)
    if cached is not None and (now - cached[0]) < _FILE_CACHE_TTL:
        return cached[1]

    url = f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}/main/{path}"
    client = get_client("agency-import", timeout=15.0)
    t0 = time.monotonic()
    try:
        resp = await client.get(url)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        content = resp.text if resp.status_code == 200 else None
        if len(_file_cache) >= _FILE_CACHE_MAX:
            _file_cache.clear()
        _file_cache[path] = (now, content)
        if resp.status_code != 200:
            logger.warning(
                "GitHub raw file returned %d: path=%s (%.0fms)",
                resp.status_code,
                path,
                latency_ms,
                extra={
                    "event": "agency_fetch_non_200",
                    "path": path,
                    "http_status": resp.status_code,
                    "latency_ms": latency_ms,
                },
            )
        return content
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.warning(
            "Failed to fetch %s: %s (%.0fms)",
            path,
            exc,
            latency_ms,
            extra={
                "event": "agency_fetch_failed",
                "path": path,
                "error_type": type(exc).__name__,
                "latency_ms": latency_ms,
            },
        )
        return None


_division_cache: dict[str, tuple[float, list[str]]] = {}
_DIVISION_CACHE_TTL = 300.0  # 5 minutes
_DIVISION_CACHE_MAX = 100


async def _list_division_files(division: str) -> list[str]:
    """List markdown files in a division directory via GitHub API (cached 5min)."""
    now = time.monotonic()
    cached = _division_cache.get(division)
    if cached is not None and (now - cached[0]) < _DIVISION_CACHE_TTL:
        return cached[1]

    url = f"{_GITHUB_API}/repos/{_REPO_OWNER}/{_REPO_NAME}/contents/{division}"
    client = get_client("agency-import", timeout=15.0)
    t0 = time.monotonic()
    try:
        resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code != 200:
            logger.warning(
                "GitHub API returned %d for division '%s' (%.0fms)",
                resp.status_code,
                division,
                latency_ms,
                extra={
                    "event": "agency_division_list_error",
                    "division": division,
                    "http_status": resp.status_code,
                    "latency_ms": latency_ms,
                },
            )
            return []
        items = resp.json()
        files = [
            item["path"]
            for item in items
            if isinstance(item, dict)
            and item.get("name", "").endswith(".md")
            and item.get("name") != "README.md"
        ]
        if len(_division_cache) >= _DIVISION_CACHE_MAX:
            _division_cache.clear()
        _division_cache[division] = (now, files)
        return files
    except Exception:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.warning(
            "Failed to list division files from GitHub: %s (%.0fms)",
            division,
            latency_ms,
            exc_info=True,
            extra={
                "event": "agency_division_list_failed",
                "division": division,
                "latency_ms": latency_ms,
            },
        )
        return []


@router.get(
    "/agency-agents",
    response_model=AgencyAgentListResponse,
    responses={
        401: {"description": "Authentication required"},
        422: {"description": "Invalid division name"},
    },
)
async def list_agency_agents(
    division: str | None = Query(
        default=None, description="Filter by division (e.g., engineering, design)"
    ),
    _current_user: User = Depends(require_permission("list", "Agent", require_identity=True)),
) -> AgencyAgentListResponse:
    """List available agent personas from the Agency Agents library."""
    if division is not None and division not in _DIVISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid division '{division}'. Valid divisions: {', '.join(_DIVISIONS)}",
        )
    divisions = [division] if division else _DIVISIONS
    agents: list[AgencyAgentPreview] = []

    division_files = await asyncio.gather(
        *[_list_division_files(div) for div in divisions]
    )
    all_files: list[tuple[str, str]] = []
    for div, files in zip(divisions, division_files, strict=True):
        for file_path in files:
            all_files.append((div, file_path))

    contents = await asyncio.gather(
        *[_fetch_github_file(fp) for _, fp in all_files]
    )

    for (div, file_path), content in zip(all_files, contents, strict=True):
        if content is None:
            continue
        parsed = parse_agency_agent_markdown(content, file_path)
        if parsed:
            agents.append(
                AgencyAgentPreview(
                    name=parsed["original_name"],
                    slug=parsed["name"],
                    role=parsed["role"],
                    goal=parsed["goal"],
                    backstory=parsed.get("backstory", ""),
                    division=parsed.get("source_division", div),
                    source_file=file_path,
                )
            )

    return AgencyAgentListResponse(
        agents=agents,
        total=len(agents),
        divisions=_DIVISIONS,
    )


@router.post(
    "/agency-agents",
    response_model=AgencyAgentImportResponse,
    responses={
        401: {"description": "Authentication required"},
        429: {"description": "Too many import requests"},
    },
)
async def import_agency_agents(
    request: Request,
    body: AgencyAgentImportRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_permission("create", "Agent", require_identity=True)),
) -> AgencyAgentImportResponse:
    """Import selected agent personas as Blackbeard Agent resources."""
    check_rate_limit(mutation_limiter, _current_user, "Too many import requests. Try again later.")

    imported = 0
    skipped = 0
    errors: list[str] = []

    service = ResourceService(session)

    division_files = await asyncio.gather(
        *[_list_division_files(div) for div in _DIVISIONS]
    )
    slug_index: dict[str, str] = {}
    for div, files in zip(_DIVISIONS, division_files, strict=True):
        for file_path in files:
            raw_slug = file_path.split("/")[-1].replace(".md", "")
            stripped_slug = raw_slug.replace(f"{div}-", "")
            slug_index.setdefault(stripped_slug, file_path)
            slug_index.setdefault(raw_slug, file_path)

    paths_to_fetch = [slug_index[s] for s in body.slugs if s in slug_index]
    if paths_to_fetch:
        await asyncio.gather(*[_fetch_github_file(fp) for fp in paths_to_fetch])

    for slug in body.slugs:
        file_path = slug_index.get(slug)
        if file_path is None:
            errors.append(f"{slug}: not found in any division")
            continue

        content = await _fetch_github_file(file_path)
        if content is None:
            errors.append(f"Failed to fetch {slug}")
            continue

        parsed = parse_agency_agent_markdown(content, file_path)
        if not parsed:
            errors.append(f"Failed to parse {slug}")
            continue

        try:
            data = ResourceCreate(
                apiVersion=API_VERSION,
                kind="Agent",
                metadata=ResourceMetadata(
                    name=parsed["name"],
                    project="default",
                    labels={
                        "source": "agency-agents",
                        "division": parsed.get("source_division", ""),
                    },
                ),
                spec={
                    "role": parsed["role"],
                    "goal": parsed["goal"],
                    "backstory": parsed["backstory"],
                },
            )
            await service.create(data)
            imported += 1
        except Exception as exc:
            if "already exists" in str(exc).lower():
                skipped += 1
            else:
                logger.warning(
                    "Agency agent import failed: slug=%s error=%s",
                    slug,
                    exc,
                    exc_info=True,
                    extra={
                        "event": "agency_import_resource_failed",
                        "slug": slug,
                        "error_type": type(exc).__name__,
                    },
                )
                errors.append(f"{slug}: {str(exc)[:100]}")

    await log_audit(
        session=session,
        action="import",
        resource_type="Agent",
        resource_id=f"agency-agents:{imported}",
        detail={
            "source": "agency-agents",
            "imported": imported,
            "skipped": skipped,
            "errors": len(errors),
        },
        **audit_from_request(request, _current_user),
    )
    await session.commit()

    return AgencyAgentImportResponse(imported=imported, skipped=skipped, errors=errors)
