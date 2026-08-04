"""Hypothesis-based fuzz tests for sandbox command construction.

The sandbox runtimes build ``podman run`` argument vectors from
tool-spec-controlled input (image name, env vars). A crafted image like
``--privileged`` or an env key starting with ``-`` must never be emitted
as a flag. These tests fuzz ``_build_command`` on every runtime tier.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from blackbeard.engine.sandbox.base import BaseSandbox, SandboxRuntimeError
from blackbeard.engine.sandbox.container_runtime import ContainerRuntimeError, ContainerSandbox
from blackbeard.engine.sandbox.gvisor_runtime import GVisorRuntimeError, GVisorSandbox
from blackbeard.engine.sandbox.microvm_runtime import MicroVMRuntimeError, MicroVMSandbox

_STRICT_IMAGE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._/:@\-]*")
_STRICT_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_VALID_IMAGE = "python:3.13-slim"


class _StubSandbox(BaseSandbox):
    def _extra_flags(self) -> list[str]:
        return []


def _make_sandbox(cls):
    with patch("shutil.which", return_value="/usr/bin/podman"):
        return cls()


_SANDBOXES = [
    (_StubSandbox, SandboxRuntimeError),
    (ContainerSandbox, ContainerRuntimeError),
    (GVisorSandbox, GVisorRuntimeError),
    (MicroVMSandbox, MicroVMRuntimeError),
]


@pytest.mark.parametrize(("cls", "error"), _SANDBOXES)
@given(image=st.text(max_size=100))
@settings(max_examples=100)
def test_fuzz_image_name(cls, error, image):
    """Accepted images match the strict allowlist exactly; rest raise."""
    sandbox = _make_sandbox(cls)
    try:
        cmd = sandbox._build_command(image, ["echo", "hi"])
    except error:
        return
    assert _STRICT_IMAGE.fullmatch(image), f"unsafe image accepted: {image!r}"
    assert not image.startswith("-")
    assert "\n" not in image and " " not in image
    assert image in cmd


@pytest.mark.parametrize(("cls", "error"), _SANDBOXES)
@given(env=st.dictionaries(st.text(max_size=50), st.text(max_size=50), max_size=8))
@settings(max_examples=100)
def test_fuzz_env_keys(cls, error, env):
    """Every emitted ``-e`` pair has a strictly valid key; bad keys are skipped."""
    sandbox = _make_sandbox(cls)
    cmd = sandbox._build_command(_VALID_IMAGE, ["echo"], env=env)
    for i, arg in enumerate(cmd):
        if arg == "-e":
            key = cmd[i + 1].split("=", 1)[0]
            assert _STRICT_ENV_KEY.fullmatch(key), f"unsafe env key emitted: {key!r}"


@pytest.mark.parametrize(("cls", "error"), _SANDBOXES)
def test_trailing_newline_image_rejected(cls, error):
    """Regression: ``$``-anchored ``.match()`` accepted a trailing newline."""
    sandbox = _make_sandbox(cls)
    with pytest.raises(error):
        sandbox._build_command("python:3.13\n", ["echo"])
    with pytest.raises(error):
        sandbox._build_command("--privileged", ["echo"])


@pytest.mark.parametrize(("cls", "error"), _SANDBOXES)
def test_trailing_newline_env_key_skipped(cls, error):
    """Regression: env keys with a trailing newline must be dropped."""
    sandbox = _make_sandbox(cls)
    cmd = sandbox._build_command(_VALID_IMAGE, ["echo"], env={"PATH\n": "x", "OK_KEY": "y"})
    assert "OK_KEY=y" in cmd
    assert all("PATH\n" not in arg for arg in cmd)
