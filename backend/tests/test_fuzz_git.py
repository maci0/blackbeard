"""Fuzz / property-based tests for git store validation functions.

The git_store module shells out to ``git`` via subprocess. The validation
functions (_validate_ref, _validate_path_component, _sanitize_author,
add_remote) are the only barrier between attacker-controlled input and
command execution. This file throws adversarial strings at every one.

Invariant: no input ever passes validation if it could cause argument
injection, path traversal, or command execution via the git CLI.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from blackbeard.engine.git_store import (
    _SAFE_BRANCH_RE,
    _SAFE_NAME_RE,
    _SAFE_REF_RE,
    _SAFE_REMOTE_RE,
    _sanitize_author,
    _validate_path_component,
    _validate_ref,
    add_remote,
)

# ---------------------------------------------------------------------------
# 1. _validate_ref fuzzing — guards commit ref args passed to git CLI
# ---------------------------------------------------------------------------


@given(ref=st.text(min_size=0, max_size=500))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_ref(ref):
    """_validate_ref must reject refs starting with '-' (argument injection)
    and anything not matching _SAFE_REF_RE. Must never crash."""
    try:
        result = _validate_ref(ref)
        assert isinstance(result, str)
        assert not result.startswith("-"), f"Ref starting with '-' accepted: {result!r}"
        assert _SAFE_REF_RE.match(result), f"Ref passed but doesn't match safe pattern: {result!r}"
    except ValueError:
        pass


# Explicit argument injection attempts that git interprets as flags
_EVIL_REFS_MUST_REJECT = [
    "-",
    "--",
    "--exec=sh",
    "--upload-pack=evil",
    "-c core.sshCommand=evil",
    "--config=core.sshCommand=evil",
    "--git-dir=/etc",
    "-o ProxyCommand=evil",
    "--work-tree=/",
    "",
    " ",
    "\x00",
    "HEAD; rm -rf /",
    "HEAD\ninjected",
    "HEAD\rinjected",
]


@pytest.mark.parametrize("ref", _EVIL_REFS_MUST_REJECT)
def test_evil_refs_rejected(ref):
    """Argument-injection refs (starting with '-') and refs with shell
    metacharacters or control chars must be rejected."""
    with pytest.raises(ValueError):
        _validate_ref(ref)


def test_path_traversal_ref_is_safe():
    """Path traversal strings like '../../../etc/passwd' match the ref regex
    (dots and slashes are valid in git refs like HEAD~1, origin/main).
    This is safe because refs are passed to git as list args (no shell),
    and git itself rejects unknown revisions. Verify it doesn't crash."""
    result = _validate_ref("../../../etc/passwd")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 2. _validate_path_component fuzzing — guards kind/name in file paths
# ---------------------------------------------------------------------------


@given(value=st.text(min_size=0, max_size=500))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_validate_path_component(value):
    """_validate_path_component must reject path traversal and unsafe chars.
    Must never crash."""
    try:
        result = _validate_path_component(value, "test")
        assert isinstance(result, str)
        assert ".." not in result, f"Path traversal '..'' accepted: {result!r}"
        assert _SAFE_NAME_RE.match(result), f"Accepted but doesn't match safe pattern: {result!r}"
    except ValueError:
        pass


_EVIL_PATHS = [
    "",
    "..",
    "../../../etc/passwd",
    "..\\..\\windows",
    "name\x00injected",
    "-flag",
    " leading-space",
    "/absolute",
    "with spaces",
    "has;semicolons",
    "has|pipe",
    ".hidden",
    "~home",
]


@pytest.mark.parametrize("path", _EVIL_PATHS)
def test_evil_paths_rejected(path):
    """Known path traversal and unsafe names must be rejected."""
    with pytest.raises(ValueError):
        _validate_path_component(path, "test")


# ---------------------------------------------------------------------------
# 3. _sanitize_author fuzzing — guards --author flag for git commit
# ---------------------------------------------------------------------------


@given(author=st.text(min_size=0, max_size=500))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_sanitize_author(author):
    """_sanitize_author must strip dangerous chars and truncate.
    Must never crash, always return a non-empty string."""
    result = _sanitize_author(author)
    assert isinstance(result, str)
    assert len(result) > 0, "sanitize_author returned empty string"
    assert len(result) <= 100, f"sanitize_author returned string longer than 100: {len(result)}"
    assert "<" not in result, f"'<' not stripped from author: {result!r}"
    assert ">" not in result, f"'>' not stripped from author: {result!r}"
    assert "\n" not in result, f"newline not stripped from author: {result!r}"
    assert "\r" not in result, f"carriage return not stripped from author: {result!r}"
    assert "\x00" not in result, f"null byte not stripped from author: {result!r}"


_EVIL_AUTHORS = [
    "",
    "<script>alert(1)</script>",
    "user <evil@hack.com>",
    "user\nnewline-inject",
    "user\rcarriage-return",
    "user\x00null-byte",
    "a" * 200,
    "> /etc/passwd",
    "$(whoami)",
    "`id`",
]


@pytest.mark.parametrize("author", _EVIL_AUTHORS)
def test_evil_authors_sanitized(author):
    """Evil author strings must be sanitized, not passed through."""
    result = _sanitize_author(author)
    assert "<" not in result
    assert ">" not in result
    assert "\n" not in result
    assert "\r" not in result
    assert "\x00" not in result
    assert len(result) <= 100


# ---------------------------------------------------------------------------
# 4. add_remote URL validation fuzzing — prevents SSRF/command execution
# ---------------------------------------------------------------------------


@given(
    name=st.text(min_size=0, max_size=200),
    url=st.text(min_size=0, max_size=500),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_add_remote_validation(name, url):
    """add_remote must reject non-HTTPS URLs and unsafe remote names.
    Must never crash with an unhandled exception."""
    try:
        add_remote(name, url)
    except ValueError:
        pass
    except RuntimeError:
        pass  # "Git store not initialized" is expected in test env


_EVIL_REMOTE_URLS = [
    "file:///etc/passwd",
    "ssh://git@evil.com/repo.git",
    "ext::sh -c evil",
    "ext::curl${IFS}http://evil.com",
    "ftp://evil.com/repo.git",
    "gopher://evil.com:25/",
    "http://169.254.169.254/latest/meta-data/",
    "",
    "-o ProxyCommand=evil",
    "https://evil.com ext::sh -c evil",
]


@pytest.mark.parametrize("url", _EVIL_REMOTE_URLS)
def test_evil_remote_urls_rejected(url):
    """Non-HTTPS and ext:: URLs must be rejected by add_remote."""
    with pytest.raises((ValueError, RuntimeError)):
        add_remote("origin", url)


_EVIL_REMOTE_NAMES = [
    "",
    "-flag",
    "--exec=evil",
    "../traversal",
    "name\x00injected",
    " leading",
    "has spaces",
    ".hidden",
]


@pytest.mark.parametrize("name", _EVIL_REMOTE_NAMES)
def test_evil_remote_names_rejected(name):
    """Remote names that could be interpreted as flags must be rejected."""
    with pytest.raises((ValueError, RuntimeError)):
        add_remote(name, "https://github.com/test/repo.git")


# ---------------------------------------------------------------------------
# 5. Regex pattern consistency — ensure the compiled patterns match docs
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_safe_ref_regex(text):
    """_SAFE_REF_RE must never crash and must reject empty strings."""
    match = _SAFE_REF_RE.match(text)
    if match:
        assert len(text) > 0
        assert not any(c in text for c in " \t\n\r\x00")


@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_safe_name_regex(text):
    """_SAFE_NAME_RE must never crash, must reject strings starting with special chars."""
    match = _SAFE_NAME_RE.match(text)
    if match:
        assert text[0].isalnum(), f"Name starting with non-alnum accepted: {text!r}"


@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_safe_branch_regex(text):
    """_SAFE_BRANCH_RE must never crash and must reject '-' prefix."""
    match = _SAFE_BRANCH_RE.match(text)
    if match:
        assert text[0].isalnum(), f"Branch starting with non-alnum accepted: {text!r}"


@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_safe_remote_regex(text):
    """_SAFE_REMOTE_RE must never crash and must reject '-' prefix."""
    match = _SAFE_REMOTE_RE.match(text)
    if match:
        assert text[0].isalnum(), f"Remote starting with non-alnum accepted: {text!r}"


# ---------------------------------------------------------------------------
# 6. Git API endpoint fuzzing (evil path params and query params)
# ---------------------------------------------------------------------------

from tests.conftest import API_KEY_HEADER

_url_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1,
    max_size=200,
)


@given(
    kind=_url_safe_text,
    name=_url_safe_text,
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_blame_path_params(client, kind, name):
    """GET /api/v1/git/blame/{kind}/{name} with random path params should never 500."""
    resp = await client.get(
        f"/api/v1/git/blame/{kind}/{name}",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on GET /git/blame/{kind!r}/{name!r}: {resp.text[:200]}"


@given(
    commit=_url_safe_text,
    kind=_url_safe_text,
    name=_url_safe_text,
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_show_path_params(client, commit, kind, name):
    """GET /api/v1/git/show/{commit}/{kind}/{name} with random params should never 500."""
    resp = await client.get(
        f"/api/v1/git/show/{commit}/{kind}/{name}",
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, (
        f"500 on GET /git/show/{commit!r}/{kind!r}/{name!r}: {resp.text[:200]}"
    )


_EVIL_COMMIT_REFS = [
    "--exec=evil",
    "-c core.sshCommand=evil",
    "--upload-pack=evil",
    "HEAD; cat /etc/passwd",
    "HEAD$(whoami)",
    "HEAD`id`",
    "../../../etc/passwd",
    "",
    "-",
    "HEAD\ninjected",
    "a" * 10_000,
]


@pytest.mark.parametrize("commit_a", _EVIL_COMMIT_REFS)
async def test_evil_git_diff_commit_refs(client, commit_a):
    """GET /api/v1/git/diff with evil commit_a should not crash."""
    resp = await client.get(
        "/api/v1/git/diff",
        params={"commit_a": commit_a, "commit_b": "HEAD"},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on GET /git/diff commit_a={commit_a!r}"


@given(
    commit_a=st.text(min_size=0, max_size=300),
    commit_b=st.text(min_size=0, max_size=300),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_diff_params(client, commit_a, commit_b):
    """GET /api/v1/git/diff with random commit refs should never 500."""
    resp = await client.get(
        "/api/v1/git/diff",
        params={"commit_a": commit_a, "commit_b": commit_b},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, (
        f"500 on GET /git/diff commit_a={commit_a!r} commit_b={commit_b!r}"
    )


@given(
    remote=st.text(min_size=0, max_size=200),
    url=st.text(min_size=0, max_size=500),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_remote_body(client, remote, url):
    """POST /api/v1/git/remote with random name/url should never 500."""
    resp = await client.post(
        "/api/v1/git/remote",
        json={"name": remote, "url": url},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on POST /git/remote name={remote!r} url={url!r}"


_EVIL_GIT_REMOTE_BODIES = [
    {"name": "--exec=evil", "url": "https://github.com/test.git"},
    {"name": "origin", "url": "ext::sh -c evil"},
    {"name": "origin", "url": "ssh://evil.com/repo"},
    {"name": "origin", "url": "-o ProxyCommand=evil"},
    {"name": "", "url": "https://github.com/test.git"},
    {"name": "origin", "url": ""},
    {"name": "origin", "url": "file:///etc/passwd"},
]


@pytest.mark.parametrize("body", _EVIL_GIT_REMOTE_BODIES)
async def test_evil_git_remote_bodies(client, body):
    """Evil git remote requests should be rejected, never 500."""
    resp = await client.post(
        "/api/v1/git/remote",
        json=body,
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on POST /git/remote body={body!r}"
    assert resp.status_code in (400, 401, 403, 409, 422), (
        f"Expected client error for evil remote, got {resp.status_code}"
    )


@given(
    remote=st.text(min_size=0, max_size=200),
    branch=st.text(min_size=0, max_size=200),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_push_body(client, remote, branch):
    """POST /api/v1/git/push with random remote/branch should never 500."""
    resp = await client.post(
        "/api/v1/git/push",
        json={"remote": remote, "branch": branch},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on POST /git/push remote={remote!r} branch={branch!r}"


@given(
    remote=st.text(min_size=0, max_size=200),
    branch=st.text(min_size=0, max_size=200),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
async def test_fuzz_git_pull_body(client, remote, branch):
    """POST /api/v1/git/pull with random remote/branch should never 500."""
    resp = await client.post(
        "/api/v1/git/pull",
        json={"remote": remote, "branch": branch},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code != 500, f"500 on POST /git/pull remote={remote!r} branch={branch!r}"
