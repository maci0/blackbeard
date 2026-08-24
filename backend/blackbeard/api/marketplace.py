"""Marketplace API: import resources from git repos or built-in examples."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from blackbeard.api.mutations import (
    AUTHZ_CACHE_KINDS,
    AUTOMATION_KIND,
    fire_and_forget,
    maybe_reload_scheduler,
    sync_llm_to_litellm,
)
from blackbeard.audit import audit_from_request, log_audit
from blackbeard.auth import require_permission
from blackbeard.auth.authorizer import clear_cache as _clear_authz_cache
from blackbeard.models.resource_schemas import ResourceCreate
from blackbeard.rate_limiter import check_rate_limit, marketplace_limiter
from blackbeard.resources import (
    ResourceService,
    ResourceValidationError,
    check_url_ssrf,
    is_blocked_env_name,
    save_version_snapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from blackbeard.models import User

from blackbeard.models import get_session

logger = logging.getLogger(__name__)

_yaml_loader: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

_APP_DIR = Path(__file__).resolve().parent.parent.parent
_EXAMPLES_DIR = _APP_DIR / "examples"

_MAX_CLONE_TIMEOUT_S = 60
_MAX_YAML_FILES = 200
_MAX_YAML_SIZE_BYTES = 256 * 1024
_MAX_IMPORT_RESOURCES = 500

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


_YAML_SUFFIXES = frozenset({".yaml", ".yml"})


def _find_yaml_files(directory: Path) -> list[Path]:
    """Recursively find YAML files in a directory, respecting safety limits.

    Skips symlinks to prevent symlink-based directory traversal attacks
    where a malicious repo could link to files outside the clone directory.
    """
    resolved_root = directory.resolve()
    files: list[Path] = []
    for f in directory.rglob("*"):
        if f.suffix not in _YAML_SUFFIXES:
            continue
        if f.is_symlink():
            continue
        if not f.resolve().is_relative_to(resolved_root):
            continue
        files.append(f)
        if len(files) >= _MAX_YAML_FILES:
            break
    files.sort()
    return files


_MAX_DOCS_PER_FILE = 100


def _collect_resources(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Find and parse YAML resources in a directory (blocking; run via to_thread)."""
    return _parse_yaml_resources(_find_yaml_files(directory))


def _tree_size(root: Path) -> int:
    """Total size of regular files under *root* (blocking; run via to_thread)."""
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink())


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
            doc_count = 0
            for doc in yaml.load_all(content, Loader=_yaml_loader):
                doc_count += 1
                if doc_count > _MAX_DOCS_PER_FILE:
                    errors.append(
                        f"Skipped remaining docs in {filepath.name}: "
                        f"exceeds {_MAX_DOCS_PER_FILE} documents per file"
                    )
                    break
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


# Maximum total size of cloned repo (100 MB).
_MAX_CLONE_SIZE_BYTES = 100 * 1024 * 1024


async def _clone_repo(url: str, target: Path) -> None:
    """Clone a git repository to a temporary directory (shallow, no checkout of history).

    Uses asyncio.create_subprocess_exec (not shell) to avoid command injection.

    SECURITY hardening:
    - ``-c transfer.fsckObjects=true``: validate objects on transfer
    - ``-c http.followRedirects=initial``: prevent SSRF via git HTTP
      redirects to internal networks (only allows the initial redirect
      from the server, not arbitrary follow-on redirects)
    - ``-c protocol.file.allow=never``: block ``file://`` submodule URLs
    - ``--recurse-submodules=no``: do not clone submodules (could point
      to internal repos or file:// URLs)
    """
    env = {k: v for k, v in os.environ.items() if not is_blocked_env_name(k)}
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_SSH_COMMAND": "",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "",
            "HOME": str(target),
            "XDG_CONFIG_HOME": str(target),
        }
    )
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-c",
        "transfer.fsckObjects=true",
        "-c",
        "http.followRedirects=initial",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--depth=1",
        "--single-branch",
        "--no-tags",
        "--recurse-submodules=no",
        url,
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_MAX_CLONE_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning(
            "Git clone timed out: url=%s timeout=%ds",
            url[:200],
            _MAX_CLONE_TIMEOUT_S,
            extra={
                "event": "marketplace_git_clone_timeout",
                "url": url[:200],
                "timeout_s": _MAX_CLONE_TIMEOUT_S,
            },
        )
        raise HTTPException(
            status_code=504,
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
        422: {"description": "Invalid URL or YAML parse errors"},
        429: {"description": "Too many marketplace import requests"},
        503: {"description": "Built-in examples not available on server"},
        504: {"description": "Git clone timed out"},
    },
)
async def import_from_url(
    body: ImportRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_permission("create", "Resource")),
) -> ImportResponse:
    """Import resources from a git URL or built-in examples."""
    check_rate_limit(
        marketplace_limiter, user, "Too many marketplace import requests. Try again later."
    )
    url = body.url.strip()
    imported_names: list[str] = []
    error_details: list[str] = []

    if url == "built-in":
        # Import from ALL bundled example directories
        if not _EXAMPLES_DIR.is_dir():
            raise HTTPException(
                status_code=503,
                detail="Built-in examples not found on server",
            )
        raw_resources = []
        for example_dir in sorted(_EXAMPLES_DIR.iterdir()):
            if not example_dir.is_dir() or example_dir.name.startswith("."):
                continue
            resources, parse_errors = await asyncio.to_thread(_collect_resources, example_dir)
            raw_resources.extend(resources)
            error_details.extend(parse_errors)
    else:
        # Validate URL scheme and reject embedded credentials
        if not any(url.startswith(scheme) for scheme in _ALLOWED_URL_SCHEMES):
            raise HTTPException(
                status_code=422,
                detail="Only HTTPS git URLs are allowed",
            )
        _parsed = urlparse(url)
        if _parsed.username or _parsed.password:
            raise HTTPException(
                status_code=422,
                detail="Git URL must not contain embedded credentials",
            )

        # Off the event loop: uncached DNS resolution can block up to 2s.
        ssrf_error = await asyncio.to_thread(check_url_ssrf, url)
        if ssrf_error:
            raise HTTPException(status_code=422, detail=ssrf_error)

        tmpdir = Path(tempfile.mkdtemp(prefix="bb-marketplace-"))
        try:
            await _clone_repo(url, tmpdir)

            git_dir = tmpdir / ".git"
            if git_dir.is_dir():
                shutil.rmtree(git_dir, ignore_errors=True)

            # SECURITY: Check total clone size to prevent abuse via
            # large repositories.  This runs after clone because git
            # doesn't support pre-clone size limits.
            total_size = await asyncio.to_thread(_tree_size, tmpdir)
            if total_size > _MAX_CLONE_SIZE_BYTES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Cloned repository is too large ({total_size // (1024 * 1024)}MB, "
                    f"limit: {_MAX_CLONE_SIZE_BYTES // (1024 * 1024)}MB)",
                )

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
            raw_resources, parse_errors = await asyncio.to_thread(_collect_resources, search_dir)
            error_details.extend(parse_errors)
        finally:
            await asyncio.to_thread(shutil.rmtree, tmpdir, ignore_errors=True)

    if len(raw_resources) > _MAX_IMPORT_RESOURCES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many resources in import ({len(raw_resources)}). "
                f"Maximum allowed is {_MAX_IMPORT_RESOURCES} per request."
            ),
        )

    # Import each resource via the ResourceService
    service = ResourceService(session)
    imported_specs: list[tuple[str, str, dict[str, Any]]] = []
    for raw in raw_resources:
        try:
            data = ResourceCreate.model_validate(raw)
        except Exception as exc:
            kind_str = raw.get("kind", "Unknown")
            name_str = raw.get("metadata", {}).get("name", "unknown")
            logger.debug(
                "Marketplace resource validation failed: %s/%s: %s",
                kind_str,
                name_str,
                exc,
                exc_info=True,
                extra={
                    "event": "marketplace_resource_validation_failed",
                    "resource_kind": kind_str,
                    "resource_name": name_str,
                    "error_type": type(exc).__name__,
                },
            )
            error_details.append(
                f"Validation error for {kind_str}/{name_str}: invalid resource structure"
            )
            continue
        try:
            resource, created = await service.create(data)
            await save_version_snapshot(session, resource, user)
            action = "resource_created" if created else "resource_updated"
            label = f"{data.kind}/{data.metadata.name}"
            imported_names.append(label)
            imported_specs.append((data.kind, data.metadata.name, data.spec))
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
        # Same side-effects as the CRUD routes: LiteLLM sync per resource,
        # but scheduler reload and authz cache clear once per batch — firing
        # them per resource makes a 500-resource import do 500 full scheduler
        # rebuilds and cache wipes.
        for kind, name, spec in imported_specs:
            fire_and_forget(sync_llm_to_litellm(kind, name, spec))
        imported_kinds = {kind for kind, _, _ in imported_specs}
        if AUTOMATION_KIND in imported_kinds:
            fire_and_forget(maybe_reload_scheduler(request, AUTOMATION_KIND))
        if imported_kinds & AUTHZ_CACHE_KINDS:
            _clear_authz_cache()

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
