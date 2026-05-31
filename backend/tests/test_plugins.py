"""Tests for the plugin SDK: registry, loader, base classes, and API."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from blackbeard.plugins import PluginMeta, PluginRegistry, PluginType
from blackbeard.plugins.base import (
    ExecutionHookPlugin,
    GuardrailPlugin,
    ToolPlugin,
)
from blackbeard.plugins.loader import load_plugin_module, load_plugins

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# PluginType enum
# ---------------------------------------------------------------------------


class TestPluginType:
    def test_values(self):
        assert PluginType.TOOL == "tool"
        assert PluginType.GUARDRAIL == "guardrail"
        assert PluginType.AUTH_PROVIDER == "auth_provider"
        assert PluginType.EXECUTION_HOOK == "execution_hook"

    def test_from_string(self):
        assert PluginType("tool") is PluginType.TOOL
        assert PluginType("guardrail") is PluginType.GUARDRAIL


# ---------------------------------------------------------------------------
# PluginMeta dataclass
# ---------------------------------------------------------------------------


class TestPluginMeta:
    def test_creation(self):
        meta = PluginMeta(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
            plugin_type=PluginType.TOOL,
            entry_point="/some/path.py",
        )
        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.plugin_type is PluginType.TOOL

    def test_frozen(self):
        meta = PluginMeta(name="x", version="0.1", description="", plugin_type=PluginType.TOOL)
        with pytest.raises(AttributeError):
            meta.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        meta = PluginMeta("my-tool", "1.0", "desc", PluginType.TOOL)
        handler = object()
        reg.register(meta, handler)

        assert reg.get(PluginType.TOOL, "my-tool") is handler
        assert reg.get_meta(PluginType.TOOL, "my-tool") == meta

    def test_get_missing(self):
        reg = PluginRegistry()
        assert reg.get(PluginType.TOOL, "nonexistent") is None
        assert reg.get_meta(PluginType.TOOL, "nonexistent") is None

    def test_list_all(self):
        reg = PluginRegistry()
        m1 = PluginMeta("a", "1.0", "", PluginType.TOOL)
        m2 = PluginMeta("b", "2.0", "", PluginType.GUARDRAIL)
        reg.register(m1, object())
        reg.register(m2, object())

        all_plugins = reg.list_plugins()
        assert len(all_plugins) == 2
        names = {m.name for m in all_plugins}
        assert names == {"a", "b"}

    def test_list_filtered(self):
        reg = PluginRegistry()
        m1 = PluginMeta("a", "1.0", "", PluginType.TOOL)
        m2 = PluginMeta("b", "2.0", "", PluginType.GUARDRAIL)
        reg.register(m1, object())
        reg.register(m2, object())

        tools = reg.list_plugins(PluginType.TOOL)
        assert len(tools) == 1
        assert tools[0].name == "a"

    def test_replace_existing(self):
        reg = PluginRegistry()
        meta = PluginMeta("x", "1.0", "", PluginType.TOOL)
        h1 = object()
        h2 = object()
        reg.register(meta, h1)
        reg.register(meta, h2)

        assert reg.get(PluginType.TOOL, "x") is h2

    def test_unregister(self):
        reg = PluginRegistry()
        meta = PluginMeta("x", "1.0", "", PluginType.TOOL)
        reg.register(meta, object())

        assert reg.unregister(PluginType.TOOL, "x") is True
        assert reg.get(PluginType.TOOL, "x") is None
        assert reg.unregister(PluginType.TOOL, "x") is False

    def test_clear(self):
        reg = PluginRegistry()
        reg.register(PluginMeta("a", "1", "", PluginType.TOOL), object())
        reg.register(PluginMeta("b", "1", "", PluginType.GUARDRAIL), object())
        reg.clear()
        assert reg.list_plugins() == []


# ---------------------------------------------------------------------------
# Base classes: concrete subclass instantiation
# ---------------------------------------------------------------------------


class TestBaseClasses:
    def test_tool_plugin_abstract(self):
        with pytest.raises(TypeError):
            ToolPlugin()  # type: ignore[abstract]

    def test_guardrail_plugin_abstract(self):
        with pytest.raises(TypeError):
            GuardrailPlugin()  # type: ignore[abstract]

    def test_execution_hook_plugin_abstract(self):
        with pytest.raises(TypeError):
            ExecutionHookPlugin()  # type: ignore[abstract]

    def test_tool_plugin_concrete(self):
        class MyTool(ToolPlugin):
            name = "my-tool"
            description = "does stuff"

            def execute(self, input: dict[str, Any]) -> dict[str, Any]:
                return {"result": input.get("x", 0) * 2}

        tool = MyTool()
        assert tool.name == "my-tool"
        assert tool.execute({"x": 5}) == {"result": 10}

    def test_guardrail_plugin_concrete(self):
        class MyGuard(GuardrailPlugin):
            name = "my-guard"

            def validate(self, output: str, context: dict[str, Any]) -> tuple[bool, str]:
                if "bad" in output:
                    return False, "contains bad word"
                return True, "ok"

        guard = MyGuard()
        passed, msg = guard.validate("this is bad", {})
        assert not passed
        assert "bad" in msg

        passed, msg = guard.validate("this is fine", {})
        assert passed

    def test_execution_hook_concrete(self):
        calls: list[str] = []

        class MyHook(ExecutionHookPlugin):
            name = "my-hook"

            def before_kickoff(self, crew: Any, inputs: dict[str, Any]) -> None:
                calls.append("before")

            def after_kickoff(self, crew: Any, result: Any) -> None:
                calls.append("after")

        hook = MyHook()
        hook.before_kickoff(None, {})
        hook.after_kickoff(None, None)
        assert calls == ["before", "after"]


# ---------------------------------------------------------------------------
# Plugin loader: filesystem discovery
# ---------------------------------------------------------------------------


class TestPluginLoader:
    def test_load_from_nonexistent_dir(self):
        loaded = load_plugins("/tmp/blackbeard_test_no_such_dir_12345")
        assert loaded == []

    def test_load_valid_plugin(self, tmp_path: Path):
        plugin_file = tmp_path / "greet.py"
        plugin_file.write_text(
            textwrap.dedent("""\
                from blackbeard.plugins.base import ToolPlugin

                class GreetPlugin(ToolPlugin):
                    name = "greet"
                    description = "greets"
                    def execute(self, input):
                        return {"msg": f"hi {input.get('name', 'anon')}"}

                blackbeard_plugin = {
                    "name": "greet",
                    "version": "0.1.0",
                    "description": "greeting plugin",
                    "type": "tool",
                    "handler": GreetPlugin,
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)

        assert len(loaded) == 1
        assert loaded[0].name == "greet"
        assert loaded[0].version == "0.1.0"
        assert loaded[0].plugin_type is PluginType.TOOL

        handler = reg.get(PluginType.TOOL, "greet")
        assert handler is not None
        result = handler.execute({"name": "tester"})
        assert result == {"msg": "hi tester"}

    def test_skip_underscore_files(self, tmp_path: Path):
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "_private.py").write_text("blackbeard_plugin = {}")

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert loaded == []

    def test_skip_module_without_descriptor(self, tmp_path: Path):
        (tmp_path / "plain.py").write_text("x = 42\n")

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert loaded == []

    def test_skip_invalid_descriptor(self, tmp_path: Path):
        # Missing required keys
        (tmp_path / "broken.py").write_text('blackbeard_plugin = {"name": "broken"}\n')

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert loaded == []

    def test_skip_bad_type(self, tmp_path: Path):
        (tmp_path / "badtype.py").write_text(
            textwrap.dedent("""\
                blackbeard_plugin = {
                    "name": "bad",
                    "version": "1.0",
                    "type": "unknown_type",
                    "handler": object,
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert loaded == []

    def test_skip_handler_not_a_class(self, tmp_path: Path):
        (tmp_path / "notclass.py").write_text(
            textwrap.dedent("""\
                blackbeard_plugin = {
                    "name": "nc",
                    "version": "1.0",
                    "type": "tool",
                    "handler": "not_a_class",
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert loaded == []

    def test_load_multiple_plugins(self, tmp_path: Path):
        for i in range(3):
            (tmp_path / f"plugin{i}.py").write_text(
                textwrap.dedent(f"""\
                    from blackbeard.plugins.base import ToolPlugin

                    class Tool{i}(ToolPlugin):
                        name = "tool-{i}"
                        description = "tool {i}"
                        def execute(self, input):
                            return {{"n": {i}}}

                    blackbeard_plugin = {{
                        "name": "tool-{i}",
                        "version": "1.0.0",
                        "type": "tool",
                        "handler": Tool{i},
                    }}
                """)
            )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert len(loaded) == 3
        names = {m.name for m in loaded}
        assert names == {"tool-0", "tool-1", "tool-2"}

    def test_default_plugin_dir_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PLUGIN_DIR", str(tmp_path))
        (tmp_path / "env_plugin.py").write_text(
            textwrap.dedent("""\
                from blackbeard.plugins.base import ToolPlugin

                class EnvTool(ToolPlugin):
                    name = "env-tool"
                    description = "from env"
                    def execute(self, input):
                        return {}

                blackbeard_plugin = {
                    "name": "env-tool",
                    "version": "1.0.0",
                    "type": "tool",
                    "handler": EnvTool,
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(target_registry=reg)
        assert len(loaded) == 1
        assert loaded[0].name == "env-tool"

    def test_load_guardrail_plugin(self, tmp_path: Path):
        (tmp_path / "guard.py").write_text(
            textwrap.dedent("""\
                from blackbeard.plugins.base import GuardrailPlugin

                class LengthGuard(GuardrailPlugin):
                    name = "length-check"
                    def validate(self, output, context):
                        if len(output) > 100:
                            return False, "too long"
                        return True, "ok"

                blackbeard_plugin = {
                    "name": "length-check",
                    "version": "1.0.0",
                    "type": "guardrail",
                    "handler": LengthGuard,
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert len(loaded) == 1
        assert loaded[0].plugin_type is PluginType.GUARDRAIL

        handler = reg.get(PluginType.GUARDRAIL, "length-check")
        passed, _ = handler.validate("short", {})
        assert passed

    def test_load_execution_hook_plugin(self, tmp_path: Path):
        (tmp_path / "hook.py").write_text(
            textwrap.dedent("""\
                from blackbeard.plugins.base import ExecutionHookPlugin

                class LogHook(ExecutionHookPlugin):
                    name = "log-hook"
                    def before_kickoff(self, crew, inputs):
                        pass
                    def after_kickoff(self, crew, result):
                        pass

                blackbeard_plugin = {
                    "name": "log-hook",
                    "version": "1.0.0",
                    "type": "execution_hook",
                    "handler": LogHook,
                }
            """)
        )

        reg = PluginRegistry()
        loaded = load_plugins(str(tmp_path), target_registry=reg)
        assert len(loaded) == 1
        assert loaded[0].plugin_type is PluginType.EXECUTION_HOOK


# ---------------------------------------------------------------------------
# Plugin loader: single module loading
# ---------------------------------------------------------------------------


class TestLoadPluginModule:
    def test_load_single_file(self, tmp_path: Path):
        plugin_file = tmp_path / "single.py"
        plugin_file.write_text(
            textwrap.dedent("""\
                from blackbeard.plugins.base import ToolPlugin

                class SingleTool(ToolPlugin):
                    name = "single"
                    description = "a single tool"
                    def execute(self, input):
                        return {"ok": True}

                blackbeard_plugin = {
                    "name": "single",
                    "version": "2.0.0",
                    "type": "tool",
                    "handler": SingleTool,
                }
            """)
        )

        reg = PluginRegistry()
        meta = load_plugin_module(str(plugin_file), target_registry=reg)

        assert meta is not None
        assert meta.name == "single"
        assert meta.version == "2.0.0"

    def test_returns_none_for_non_python(self, tmp_path: Path):
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("not a plugin")
        assert load_plugin_module(str(txt_file)) is None

    def test_returns_none_for_directory(self, tmp_path: Path):
        subdir = tmp_path / "subpkg"
        subdir.mkdir()
        assert load_plugin_module(str(subdir)) is None

    def test_handles_import_error_gracefully(self, tmp_path: Path):
        bad_file = tmp_path / "badimport.py"
        bad_file.write_text("import nonexistent_module_xyz_123\n")

        meta = load_plugin_module(str(bad_file))
        assert meta is None

    def test_handles_instantiation_error(self, tmp_path: Path):
        (tmp_path / "badinit.py").write_text(
            textwrap.dedent("""\
                class BadTool:
                    def __init__(self):
                        raise RuntimeError("init failed")

                blackbeard_plugin = {
                    "name": "bad-init",
                    "version": "1.0",
                    "type": "tool",
                    "handler": BadTool,
                }
            """)
        )

        reg = PluginRegistry()
        meta = load_plugin_module(str(tmp_path / "badinit.py"), target_registry=reg)
        assert meta is None
        assert reg.get(PluginType.TOOL, "bad-init") is None
