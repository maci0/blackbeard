"""Marketplace API: import resources from git repos or built-in examples."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth.dependencies import get_current_user
from blackbeard.models.resource_schemas import ResourceCreate
from blackbeard.resources import ResourceService, ResourceValidationError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from blackbeard.models.user import User

from blackbeard.models import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

# Path to the bundled examples directory, relative to the repo root.
# In Docker the working directory is /app/backend so the examples sit one level up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "examples"

# Limit the size of cloned repositories to prevent abuse.
_MAX_CLONE_TIMEOUT_S = 60
_MAX_YAML_FILES = 200
_MAX_YAML_SIZE_BYTES = 256 * 1024  # 256 KB per file

# Only allow HTTPS URLs (no file://, ssh://, etc.)
_ALLOWED_URL_SCHEMES = ("https://",)


class ImportRequest(BaseModel):
    """Request body for the marketplace import endpoint."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Git HTTPS URL or 'built-in' for bundled examples",
    )
    path: str = Field(
        default="",
        max_length=512,
        description="Subdirectory within the repo to import from (optional)",
    )


class ImportResponse(BaseModel):
    """Response from the marketplace import endpoint."""

    imported: int
    errors: int
    resources: list[str]
    error_details: list[str] = Field(default_factory=list)


def _find_yaml_files(directory: Path) -> list[Path]:
    """Recursively find YAML files in a directory, respecting safety limits.

    Skips symlinks to prevent symlink-based directory traversal attacks
    where a malicious repo could link to files outside the clone directory.
    """
    resolved_root = directory.resolve()
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        for f in directory.rglob(ext):
            if f.is_symlink():
                continue
            if not f.resolve().is_relative_to(resolved_root):
                continue
            files.append(f)
    files.sort()
    return files[:_MAX_YAML_FILES]


def _parse_yaml_resources(yaml_files: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse YAML files into resource dicts. Returns (resources, errors)."""
    resources: list[dict[str, Any]] = []
    errors: list[str] = []
    for filepath in yaml_files:
        if filepath.stat().st_size > _MAX_YAML_SIZE_BYTES:
            errors.append(f"Skipped {filepath.name}: exceeds {_MAX_YAML_SIZE_BYTES} byte limit")
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
            # Support multi-document YAML files
            for doc in yaml.safe_load_all(content):
                if not isinstance(doc, dict):
                    continue
                if "kind" not in doc or "metadata" not in doc:
                    continue
                resources.append(doc)
        except yaml.YAMLError as exc:
            errors.append(f"YAML parse error in {filepath.name}: {exc}")
        except OSError as exc:
            errors.append(f"Read error for {filepath.name}: {exc}")
    return resources, errors


async def _clone_repo(url: str, target: Path) -> None:
    """Clone a git repository to a temporary directory (shallow, no checkout of history).

    Uses asyncio.create_subprocess_exec (not shell) to avoid command injection.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth=1",
        "--single-branch",
        "--no-tags",
        url,
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_MAX_CLONE_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(
            status_code=408,
            detail=f"Git clone timed out after {_MAX_CLONE_TIMEOUT_S}s",
        ) from None
    if proc.returncode != 0:
        raw_msg = stderr.decode(errors="replace").strip()[:500]
        logger.warning(
            "Git clone failed for URL %s: %s",
            url[:200],
            raw_msg,
            extra={
                "event": "marketplace_git_clone_failed",
                "url": url[:200],
                "exit_code": proc.returncode,
                "stderr_preview": raw_msg[:200],
            },
        )
        raise HTTPException(
            status_code=422,
            detail="Git clone failed. Verify the URL is a valid, accessible HTTPS git repository.",
        )


@router.post(
    "/import",
    response_model=ImportResponse,
    responses={
        408: {"description": "Git clone timed out"},
        422: {"description": "Invalid URL or YAML parse errors"},
    },
)
async def import_from_url(
    body: ImportRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> ImportResponse:
    """Import resources from a git URL or built-in examples."""
    url = body.url.strip()
    imported_names: list[str] = []
    error_details: list[str] = []

    if url == "built-in":
        # Import from bundled examples directory
        example_dir = _EXAMPLES_DIR / "research-crew"
        if not example_dir.is_dir():
            raise HTTPException(
                status_code=500,
                detail="Built-in examples not found on server",
            )
        yaml_files = _find_yaml_files(example_dir)
        raw_resources, parse_errors = _parse_yaml_resources(yaml_files)
        error_details.extend(parse_errors)
    else:
        # Validate URL scheme
        if not any(url.startswith(scheme) for scheme in _ALLOWED_URL_SCHEMES):
            raise HTTPException(
                status_code=422,
                detail="Only HTTPS git URLs are allowed",
            )

        # Clone to temp dir
        tmpdir = Path(tempfile.mkdtemp(prefix="bb-marketplace-"))
        try:
            await _clone_repo(url, tmpdir)
            git_dir = tmpdir / ".git"
            if git_dir.is_dir():
                shutil.rmtree(git_dir, ignore_errors=True)
            search_dir = tmpdir / body.path if body.path else tmpdir
            # Prevent path traversal: ensure resolved search_dir stays inside tmpdir
            if not search_dir.resolve().is_relative_to(tmpdir.resolve()):
                raise HTTPException(
                    status_code=422,
                    detail="Path must not escape the repository root (path traversal detected)",
                )
            if not search_dir.is_dir():
                raise HTTPException(
                    status_code=422,
                    detail=f"Path '{body.path}' not found in repository",
                )
            yaml_files = _find_yaml_files(search_dir)
            raw_resources, parse_errors = _parse_yaml_resources(yaml_files)
            error_details.extend(parse_errors)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # Import each resource via the ResourceService
    service = ResourceService(session)
    for raw in raw_resources:
        try:
            data = ResourceCreate.model_validate(raw)
        except Exception as exc:
            kind_str = raw.get("kind", "Unknown")
            name_str = raw.get("metadata", {}).get("name", "unknown")
            error_details.append(
                f"Validation error for {kind_str}/{name_str}: {type(exc).__name__}"
            )
            continue
        try:
            _resource, created = await service.create(data)
            action = "resource_created" if created else "resource_updated"
            label = f"{data.kind}/{data.metadata.name}"
            imported_names.append(label)
            await log_audit(
                session,
                action=action,
                resource_type=data.kind,
                resource_id=data.metadata.name,
                **audit_from_request(request, user),
                detail={"source": "marketplace", "url": url},
            )
        except ResourceValidationError as exc:
            label = f"{data.kind}/{data.metadata.name}"
            msgs = "; ".join(e.message for e in exc.errors)
            error_details.append(f"Resource validation failed for {label}: {msgs}")
        except Exception as exc:
            label = f"{data.kind}/{data.metadata.name}"
            logger.warning(
                "Marketplace import failed for %s: %s",
                label,
                exc,
                exc_info=True,
                extra={
                    "event": "marketplace_import_resource_failed",
                    "resource_label": label,
                    "error_type": type(exc).__name__,
                },
            )
            error_details.append(f"Import failed for {label}")

    if imported_names:
        await session.commit()

    logger.info(
        "Marketplace import: url=%s imported=%d errors=%d",
        url,
        len(imported_names),
        len(error_details),
        extra={
            "event": "marketplace_import",
            "url": url,
            "imported_count": len(imported_names),
            "error_count": len(error_details),
        },
    )

    return ImportResponse(
        imported=len(imported_names),
        errors=len(error_details),
        resources=imported_names,
        error_details=error_details,
    )
