"""Agency Agents import — fetch and convert personas from GitHub."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from blackbeard.auth.dependencies import require_permission
from blackbeard.engine.agency_import import parse_agency_agent_markdown
from blackbeard.http_client import get_client
from blackbeard.kinds import API_VERSION
from blackbeard.models import User, get_session
from blackbeard.models.resource_schemas import ResourceCreate, ResourceMetadata
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


async def _fetch_github_file(path: str) -> str | None:
    """Fetch a raw file from the Agency Agents GitHub repo."""
    url = f"https://raw.githubusercontent.com/{_REPO_OWNER}/{_REPO_NAME}/main/{path}"
    client = get_client("agency-import", timeout=15.0)
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception as exc:
        logger.warning(
            "Failed to fetch %s: %s",
            path,
            exc,
            extra={"event": "agency_fetch_failed", "path": path},
        )
        return None


async def _list_division_files(division: str) -> list[str]:
    """List markdown files in a division directory via GitHub API."""
    url = f"{_GITHUB_API}/repos/{_REPO_OWNER}/{_REPO_NAME}/contents/{division}"
    client = get_client("agency-import", timeout=15.0)
    try:
        resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code != 200:
            return []
        items = resp.json()
        return [
            item["path"]
            for item in items
            if isinstance(item, dict)
            and item.get("name", "").endswith(".md")
            and item.get("name") != "README.md"
        ]
    except Exception:
        logger.debug("Failed to list division files from GitHub: %s", division, exc_info=True)
        return []


@router.get(
    "/agency-agents",
    response_model=AgencyAgentListResponse,
)
async def list_agency_agents(
    division: str | None = Query(
        default=None, description="Filter by division (e.g., engineering, design)"
    ),
    _current_user: User = Depends(require_permission("list", "Agent", require_identity=True)),
) -> AgencyAgentListResponse:
    """List available agent personas from the Agency Agents library."""
    divisions = [division] if division else _DIVISIONS
    agents: list[AgencyAgentPreview] = []

    for div in divisions:
        files = await _list_division_files(div)
        for file_path in files:
            content = await _fetch_github_file(file_path)
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
)
async def import_agency_agents(
    body: AgencyAgentImportRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_permission("create", "Agent", require_identity=True)),
) -> AgencyAgentImportResponse:
    """Import selected agent personas as Blackbeard Agent resources."""
    from blackbeard.rate_limiter import check_rate_limit, mutation_limiter

    check_rate_limit(mutation_limiter, _current_user, "Too many import requests. Try again later.")

    imported = 0
    skipped = 0
    errors: list[str] = []

    service = ResourceService(session)

    for slug in body.slugs:
        found = False
        for div in _DIVISIONS:
            files = await _list_division_files(div)
            for file_path in files:
                file_slug = file_path.split("/")[-1].replace(".md", "").replace(f"{div}-", "")
                if file_slug != slug and file_path.split("/")[-1].replace(".md", "") != slug:
                    continue

                content = await _fetch_github_file(file_path)
                if content is None:
                    errors.append(f"Failed to fetch {slug}")
                    found = True
                    break

                parsed = parse_agency_agent_markdown(content, file_path)
                if not parsed:
                    errors.append(f"Failed to parse {slug}")
                    found = True
                    break

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
                        errors.append(f"{slug}: {str(exc)[:100]}")
                found = True
                break
            if found:
                break

        if not found:
            errors.append(f"{slug}: not found in any division")

    if imported > 0:
        await session.commit()

    if imported > 0:
        from blackbeard.audit import log_audit

        await log_audit(
            session=session,
            action="import",
            resource_type="Agent",
            resource_id=f"agency-agents:{imported}",
            actor_type="user",
            actor_id=str(_current_user.id) if _current_user else None,
            detail={"source": "agency-agents", "imported": imported, "skipped": skipped},
        )
        await session.commit()

    return AgencyAgentImportResponse(imported=imported, skipped=skipped, errors=errors)
