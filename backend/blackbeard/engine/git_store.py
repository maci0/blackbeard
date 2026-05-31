"""Git-backed resource version control.

Maintains a local git repository of all resources as YAML files.
Every resource create/update/delete auto-commits the change,
providing full git history with diff, log, and blame.

The repo lives at DATA_DIR/git-resources/ (configurable via
GIT_RESOURCE_DIR env var). Initialize with init_git_store()
during app startup.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_GIT_DIR: Path | None = None
_lock = threading.Lock()


def _git_dir() -> Path:
    if _GIT_DIR is None:
        raise RuntimeError("Git store not initialized. Call init_git_store() first.")
    return _GIT_DIR


def init_git_store(base_dir: str | None = None) -> Path:
    """Initialize the git repository for resource storage.

    Creates the directory and runs `git init` if it doesn't exist.
    Returns the repository path.
    """
    global _GIT_DIR
    repo_dir = Path(base_dir or os.environ.get("GIT_RESOURCE_DIR", "data/git-resources"))
    repo_dir.mkdir(parents=True, exist_ok=True)

    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        _run_git(repo_dir, ["init"])
        _run_git(repo_dir, ["config", "user.name", "Blackbeard"])
        _run_git(repo_dir, ["config", "user.email", "blackbeard@localhost"])
        readme = repo_dir / "README.md"
        readme.write_text("# Blackbeard Resources\n\nGit-backed resource version control.\n")
        _run_git(repo_dir, ["add", "README.md"])
        _run_git(repo_dir, ["commit", "-m", "init resource repository"])
        logger.info("Git resource store initialized at %s", repo_dir)

    _GIT_DIR = repo_dir
    return repo_dir


def _run_git(cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command in the repo directory."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def _resource_path(kind: str, name: str, project: str) -> Path:
    """Build the file path for a resource YAML file."""
    return _git_dir() / project / kind.lower() / f"{name}.yaml"


def _resource_to_yaml(
    kind: str,
    name: str,
    project: str,
    spec: dict[str, Any],
    labels: dict[str, str] | None = None,
) -> str:
    """Convert a resource to YAML string."""
    doc = {
        "apiVersion": "blackbeard/v1",
        "kind": kind,
        "metadata": {
            "name": name,
            "project": project,
        },
        "spec": spec,
    }
    if labels:
        doc["metadata"]["labels"] = labels
    return yaml.dump(doc, default_flow_style=False, sort_keys=False)


def commit_resource(
    kind: str,
    name: str,
    project: str,
    spec: dict[str, Any],
    labels: dict[str, str] | None = None,
    action: str = "update",
    author: str = "system",
) -> str | None:
    """Write a resource to the git store and commit.

    Returns the commit hash, or None if nothing changed.
    """
    with _lock:
        try:
            repo = _git_dir()
            file_path = _resource_path(kind, name, project)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            content = _resource_to_yaml(kind, name, project, spec, labels)
            file_path.write_text(content)

            rel_path = str(file_path.relative_to(repo))
            _run_git(repo, ["add", rel_path])

            status = _run_git(repo, ["status", "--porcelain"], check=False)
            if not status.stdout.strip():
                return None

            msg = f"{action} {kind}/{name}"
            _run_git(repo, [
                "commit",
                "-m", msg,
                "--author", f"{author} <{author}@blackbeard>",
            ])
            commit_hash = _run_git(repo, ["rev-parse", "HEAD"])
            sha = commit_hash.stdout.strip()
            logger.info(
                "Git commit: %s %s/%s (%s)",
                action,
                kind,
                name,
                sha[:8],
                extra={
                    "event": "git_commit",
                    "action": action,
                    "kind": kind,
                    "name": name,
                    "commit": sha,
                },
            )
            return sha
        except Exception:
            logger.warning(
                "Git commit failed for %s/%s",
                kind,
                name,
                exc_info=True,
                extra={"event": "git_commit_failed", "kind": kind, "name": name},
            )
            return None


def delete_resource(
    kind: str,
    name: str,
    project: str,
    author: str = "system",
) -> str | None:
    """Remove a resource file and commit the deletion."""
    with _lock:
        try:
            repo = _git_dir()
            file_path = _resource_path(kind, name, project)
            if not file_path.exists():
                return None

            rel_path = str(file_path.relative_to(repo))
            _run_git(repo, ["rm", rel_path])

            msg = f"delete {kind}/{name}"
            _run_git(repo, [
                "commit",
                "-m", msg,
                "--author", f"{author} <{author}@blackbeard>",
            ])
            commit_hash = _run_git(repo, ["rev-parse", "HEAD"])
            sha = commit_hash.stdout.strip()
            logger.info(
                "Git delete: %s/%s (%s)",
                kind,
                name,
                sha[:8],
                extra={"event": "git_delete", "kind": kind, "name": name, "commit": sha},
            )
            return sha
        except Exception:
            logger.warning(
                "Git delete failed for %s/%s",
                kind,
                name,
                exc_info=True,
                extra={"event": "git_delete_failed", "kind": kind, "name": name},
            )
            return None


def get_log(
    kind: str | None = None,
    name: str | None = None,
    project: str = "default",
    limit: int = 50,
) -> list[dict[str, str]]:
    """Get git log for a resource or the entire repo."""
    repo = _git_dir()
    args = [
        "log",
        f"--max-count={limit}",
        "--format=%H|%an|%ae|%at|%s",
    ]
    if kind and name:
        file_path = _resource_path(kind, name, project)
        rel_path = str(file_path.relative_to(repo))
        args.extend(["--follow", "--", rel_path])

    result = _run_git(repo, args, check=False)
    entries = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            entries.append({
                "commit": parts[0],
                "author": parts[1],
                "email": parts[2],
                "timestamp": parts[3],
                "message": parts[4],
            })
    return entries


def get_diff(
    commit_a: str = "HEAD~1",
    commit_b: str = "HEAD",
    kind: str | None = None,
    name: str | None = None,
    project: str = "default",
) -> str:
    """Get diff between two commits, optionally scoped to a resource."""
    repo = _git_dir()
    args = ["diff", commit_a, commit_b]
    if kind and name:
        file_path = _resource_path(kind, name, project)
        rel_path = str(file_path.relative_to(repo))
        args.extend(["--", rel_path])
    result = _run_git(repo, args, check=False)
    return result.stdout


def get_blame(
    kind: str,
    name: str,
    project: str = "default",
) -> str:
    """Get git blame for a resource file."""
    repo = _git_dir()
    file_path = _resource_path(kind, name, project)
    if not file_path.exists():
        return ""
    rel_path = str(file_path.relative_to(repo))
    result = _run_git(repo, ["blame", rel_path], check=False)
    return result.stdout


def get_show(commit: str, kind: str, name: str, project: str = "default") -> str:
    """Get the content of a resource file at a specific commit."""
    repo = _git_dir()
    file_path = _resource_path(kind, name, project)
    rel_path = str(file_path.relative_to(repo))
    result = _run_git(repo, ["show", f"{commit}:{rel_path}"], check=False)
    return result.stdout


def add_remote(name: str, url: str) -> bool:
    """Add a git remote to the resource repository."""
    repo = _git_dir()
    result = _run_git(repo, ["remote", "add", name, url], check=False)
    return result.returncode == 0


def push(remote: str = "origin", branch: str = "main") -> bool:
    """Push commits to a remote."""
    repo = _git_dir()
    result = _run_git(repo, ["push", remote, branch], check=False)
    return result.returncode == 0


def pull(remote: str = "origin", branch: str = "main") -> bool:
    """Pull from a remote."""
    repo = _git_dir()
    result = _run_git(repo, ["pull", "--rebase", remote, branch], check=False)
    return result.returncode == 0
