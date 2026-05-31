"""Git version control API for resource history."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from blackbeard.auth.dependencies import require_permission
from blackbeard.engine.git_store import (
    add_remote,
    get_blame,
    get_diff,
    get_log,
    get_show,
    pull,
    push,
)
from blackbeard.models import User

router = APIRouter(prefix="/git", tags=["git"])


class GitLogEntry(BaseModel):
    commit: str
    author: str
    email: str
    timestamp: str
    message: str


class GitLogResponse(BaseModel):
    entries: list[GitLogEntry]
    total: int


class GitDiffResponse(BaseModel):
    diff: str
    commit_a: str
    commit_b: str


class GitBlameResponse(BaseModel):
    blame: str
    kind: str
    name: str


class GitShowResponse(BaseModel):
    content: str
    commit: str
    kind: str
    name: str


class GitRemoteRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._\-]*$")
    url: str = Field(..., min_length=1, max_length=500, pattern=r"^https://")


class GitSyncRequest(BaseModel):
    remote: str = Field(
        default="origin", max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._\-]*$"
    )
    branch: str = Field(
        default="main", max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/\-]*$"
    )


class GitSyncResponse(BaseModel):
    success: bool
    message: str


@router.get("/log", response_model=GitLogResponse)
async def git_log(
    kind: str | None = Query(default=None),
    name: str | None = Query(default=None),
    project: str = Query(default="default"),
    limit: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(require_permission("list", "Agent", require_identity=True)),
) -> GitLogResponse:
    """Get git commit history for a resource or the entire repo."""
    entries = await asyncio.to_thread(get_log, kind=kind, name=name, project=project, limit=limit)
    return GitLogResponse(
        entries=[GitLogEntry(**e) for e in entries],
        total=len(entries),
    )


@router.get("/diff", response_model=GitDiffResponse)
async def git_diff(
    commit_a: str = Query(default="HEAD~1"),
    commit_b: str = Query(default="HEAD"),
    kind: str | None = Query(default=None),
    name: str | None = Query(default=None),
    project: str = Query(default="default"),
    _user: User = Depends(require_permission("list", "Agent", require_identity=True)),
) -> GitDiffResponse:
    """Get diff between two commits."""
    try:
        diff_text = await asyncio.to_thread(
            get_diff, commit_a=commit_a, commit_b=commit_b, kind=kind, name=name, project=project,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitDiffResponse(diff=diff_text, commit_a=commit_a, commit_b=commit_b)


_NAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._\-]*$"


@router.get("/blame/{kind}/{name}", response_model=GitBlameResponse)
async def git_blame(
    kind: str = Path(..., pattern=_NAME_PATTERN, max_length=100),
    name: str = Path(..., pattern=_NAME_PATTERN, max_length=255),
    project: str = Query(default="default", pattern=_NAME_PATTERN, max_length=100),
    _user: User = Depends(require_permission("get", "Agent", require_identity=True)),
) -> GitBlameResponse:
    """Get git blame for a resource file."""
    blame_text = await asyncio.to_thread(get_blame, kind=kind, name=name, project=project)
    if not blame_text:
        raise HTTPException(
            status_code=404, detail=f"Resource {kind}/{name} not found in git store",
        )
    return GitBlameResponse(blame=blame_text, kind=kind, name=name)


@router.get("/show/{commit}/{kind}/{name}", response_model=GitShowResponse)
async def git_show(
    commit: str = Path(..., pattern=r"^[a-zA-Z0-9_./^~\-]+$", max_length=255),
    kind: str = Path(..., pattern=_NAME_PATTERN, max_length=100),
    name: str = Path(..., pattern=_NAME_PATTERN, max_length=255),
    project: str = Query(default="default", pattern=_NAME_PATTERN, max_length=100),
    _user: User = Depends(require_permission("get", "Agent", require_identity=True)),
) -> GitShowResponse:
    """Get resource content at a specific commit."""
    try:
        content = await asyncio.to_thread(
            get_show, commit=commit, kind=kind, name=name, project=project,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not content:
        raise HTTPException(
            status_code=404,
            detail=f"Resource {kind}/{name} not found at commit {commit}",
        )
    return GitShowResponse(content=content, commit=commit, kind=kind, name=name)


@router.post("/remote", response_model=GitSyncResponse)
async def add_git_remote(
    body: GitRemoteRequest,
    _user: User = Depends(require_permission("create", "Agent", require_identity=True)),
) -> GitSyncResponse:
    """Add a git remote to the resource repository."""
    try:
        ok = await asyncio.to_thread(add_remote, body.name, body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=409, detail=f"Remote '{body.name}' already exists")
    return GitSyncResponse(success=True, message=f"Remote '{body.name}' added")


@router.post("/push", response_model=GitSyncResponse)
async def git_push(
    body: GitSyncRequest,
    _user: User = Depends(require_permission("create", "Agent", require_identity=True)),
) -> GitSyncResponse:
    """Push resource commits to a remote."""
    try:
        ok = await asyncio.to_thread(push, remote=body.remote, branch=body.branch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=500, detail="Push failed. Check remote configuration.")
    return GitSyncResponse(success=True, message=f"Pushed to {body.remote}/{body.branch}")


@router.post("/pull", response_model=GitSyncResponse)
async def git_pull(
    body: GitSyncRequest,
    _user: User = Depends(require_permission("create", "Agent", require_identity=True)),
) -> GitSyncResponse:
    """Pull resource changes from a remote."""
    try:
        ok = await asyncio.to_thread(pull, remote=body.remote, branch=body.branch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=500, detail="Pull failed. Check remote configuration.")
    return GitSyncResponse(success=True, message=f"Pulled from {body.remote}/{body.branch}")
