"""Tests for the git-backed resource version control store."""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from blackbeard.engine import git_store


class _SafeExtraFilter(logging.Filter):
    """Drop the 'name' key from extra dict to avoid LogRecord collision.

    git_store.py passes extra={"name": ...} which conflicts with
    LogRecord's built-in 'name' attribute. This filter renames it so
    the tests can exercise the real code paths without patching
    the production module.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return True


@pytest.fixture(autouse=True)
def _isolate_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reset the module-level _GIT_DIR before each test and point to tmp_path."""
    monkeypatch.setattr(git_store, "_GIT_DIR", None)

    # Patch the logger's makeRecord to rename the conflicting 'name' extra key
    original_logger = git_store.logger

    class SafeLogger(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.get("extra", {})
            if extra and "name" in extra:
                extra["resource_name"] = extra.pop("name")
            kwargs["extra"] = extra
            return msg, kwargs

    safe = SafeLogger(original_logger, {})

    # Replace the module-level logger with one that avoids the conflict
    monkeypatch.setattr(git_store, "logger", safe)
    yield
    monkeypatch.setattr(git_store, "_GIT_DIR", None)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Initialize a git store in a temp directory and return its path."""
    repo_dir = tmp_path / "git-resources"
    result = git_store.init_git_store(str(repo_dir))
    assert result == repo_dir
    return repo_dir


# ---------------------------------------------------------------------------
# init_git_store
# ---------------------------------------------------------------------------


class TestInitGitStore:
    def test_creates_directory_and_git_repo(self, tmp_path: Path):
        repo_dir = tmp_path / "new-repo"
        assert not repo_dir.exists()

        path = git_store.init_git_store(str(repo_dir))

        assert path == repo_dir
        assert (repo_dir / ".git").is_dir()
        assert (repo_dir / "README.md").exists()

    def test_idempotent_on_existing_repo(self, repo: Path):
        # Calling init again should not raise or re-create the repo
        path = git_store.init_git_store(str(repo))
        assert path == repo
        assert (repo / ".git").is_dir()

    def test_initial_commit_exists(self, repo: Path):
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
        assert "init resource repository" in result.stdout


# ---------------------------------------------------------------------------
# commit_resource
# ---------------------------------------------------------------------------


class TestCommitResource:
    def test_creates_yaml_file_and_commits(self, repo: Path):
        sha = git_store.commit_resource(
            kind="Agent",
            name="researcher",
            project="default",
            spec={"role": "Analyst", "goal": "Research things"},
            action="create",
            author="testuser",
        )

        assert sha is not None
        assert len(sha) == 40  # full SHA-1 hash

        yaml_path = repo / "default" / "agent" / "researcher.yaml"
        assert yaml_path.exists()
        content = yaml_path.read_text()
        assert "Analyst" in content
        assert "researcher" in content

    def test_returns_none_when_nothing_changed(self, repo: Path):
        spec = {"role": "Writer", "goal": "Write things"}

        sha1 = git_store.commit_resource(
            kind="Agent", name="writer", project="default", spec=spec,
        )
        assert sha1 is not None

        # Commit the exact same content again
        sha2 = git_store.commit_resource(
            kind="Agent", name="writer", project="default", spec=spec,
        )
        assert sha2 is None

    def test_different_spec_produces_new_commit(self, repo: Path):
        sha1 = git_store.commit_resource(
            kind="Task", name="analyze", project="default",
            spec={"description": "v1"},
        )
        sha2 = git_store.commit_resource(
            kind="Task", name="analyze", project="default",
            spec={"description": "v2"},
        )
        assert sha1 is not None
        assert sha2 is not None
        assert sha1 != sha2

    def test_includes_labels_in_yaml(self, repo: Path):
        git_store.commit_resource(
            kind="Agent", name="labeled", project="default",
            spec={"role": "test"},
            labels={"env": "production", "team": "alpha"},
        )
        yaml_path = repo / "default" / "agent" / "labeled.yaml"
        content = yaml_path.read_text()
        assert "env: production" in content
        assert "team: alpha" in content


# ---------------------------------------------------------------------------
# delete_resource
# ---------------------------------------------------------------------------


class TestDeleteResource:
    def test_removes_file_and_commits(self, repo: Path):
        git_store.commit_resource(
            kind="Agent", name="doomed", project="default",
            spec={"role": "temporary"},
        )
        yaml_path = repo / "default" / "agent" / "doomed.yaml"
        assert yaml_path.exists()

        sha = git_store.delete_resource(
            kind="Agent", name="doomed", project="default", author="admin",
        )
        assert sha is not None
        assert not yaml_path.exists()

    def test_returns_none_for_nonexistent_resource(self, repo: Path):
        sha = git_store.delete_resource(
            kind="Agent", name="ghost", project="default",
        )
        assert sha is None


# ---------------------------------------------------------------------------
# get_log
# ---------------------------------------------------------------------------


class TestGetLog:
    def test_returns_commit_entries(self, repo: Path):
        git_store.commit_resource(
            kind="Crew", name="my-crew", project="default",
            spec={"agents": []}, action="create",
        )
        entries = git_store.get_log()
        assert len(entries) >= 2  # init commit + create commit

        latest = entries[0]
        assert "commit" in latest
        assert "author" in latest
        assert "message" in latest
        assert "my-crew" in latest["message"]

    def test_filters_by_resource(self, repo: Path):
        git_store.commit_resource(
            kind="Agent", name="alpha", project="default",
            spec={"role": "a"},
        )
        git_store.commit_resource(
            kind="Agent", name="beta", project="default",
            spec={"role": "b"},
        )

        entries = git_store.get_log(kind="Agent", name="alpha", project="default")
        assert len(entries) == 1
        assert "alpha" in entries[0]["message"]

    def test_respects_limit(self, repo: Path):
        for i in range(5):
            git_store.commit_resource(
                kind="Task", name=f"task-{i}", project="default",
                spec={"description": f"task {i}"},
            )
        entries = git_store.get_log(limit=3)
        assert len(entries) == 3


# ---------------------------------------------------------------------------
# get_diff
# ---------------------------------------------------------------------------


class TestGetDiff:
    def test_returns_diff_text(self, repo: Path):
        git_store.commit_resource(
            kind="Agent", name="diffme", project="default",
            spec={"role": "version-one"},
        )
        git_store.commit_resource(
            kind="Agent", name="diffme", project="default",
            spec={"role": "version-two"},
        )

        diff = git_store.get_diff()
        assert "version-one" in diff or "version-two" in diff
        assert len(diff) > 0


# ---------------------------------------------------------------------------
# get_blame
# ---------------------------------------------------------------------------


class TestGetBlame:
    def test_returns_blame_output(self, repo: Path):
        git_store.commit_resource(
            kind="Agent", name="blamed", project="default",
            spec={"role": "blameable"},
        )
        blame = git_store.get_blame(kind="Agent", name="blamed", project="default")
        assert len(blame) > 0
        assert "blameable" in blame

    def test_returns_empty_for_nonexistent(self, repo: Path):
        blame = git_store.get_blame(kind="Agent", name="nope", project="default")
        assert blame == ""


# ---------------------------------------------------------------------------
# get_show
# ---------------------------------------------------------------------------


class TestGetShow:
    def test_returns_file_content_at_commit(self, repo: Path):
        sha = git_store.commit_resource(
            kind="Tool", name="search", project="default",
            spec={"description": "search tool"},
        )
        assert sha is not None

        content = git_store.get_show(commit=sha, kind="Tool", name="search", project="default")
        assert "search tool" in content
        assert "apiVersion" in content

    def test_returns_old_version_at_old_commit(self, repo: Path):
        sha1 = git_store.commit_resource(
            kind="Agent", name="evolve", project="default",
            spec={"role": "original"},
        )
        git_store.commit_resource(
            kind="Agent", name="evolve", project="default",
            spec={"role": "updated"},
        )

        assert sha1 is not None
        old_content = git_store.get_show(
            commit=sha1, kind="Agent", name="evolve", project="default",
        )
        assert "original" in old_content
        assert "updated" not in old_content
