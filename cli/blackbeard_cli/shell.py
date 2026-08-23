"""Interactive TUI shell for the Blackbeard CLI.

Provides a REPL with command autocomplete, resource name completion,
persistent history, and live execution watching.
"""

from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from blackbeard_cli.helpers import (
    TERMINAL_STATUSES,
    build_executions_table,
    console,
    extract_detail,
    extract_items,
    out,
    render_execution_detail,
)
from blackbeard_cli.kinds import ALL_KINDS, KIND_TO_PLURAL

_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "blackbeard"
_HISTORY_FILE = _CONFIG_DIR / "history"

# Shell built-in commands with short descriptions
SHELL_COMMANDS: dict[str, str] = {
    "help": "List available commands",
    "use": "Switch active project: use <project>",
    "ls": "List resources: ls <Kind>",
    "get": "Get resource detail: get <Kind> <name>",
    "cat": "Show resource YAML: cat <Kind> <name>",
    "run": "Kick off a crew: run <crew-name>",
    "watch": "Watch execution status: watch <execution-id>",
    "status": "Show execution status: status <execution-id>",
    "executions": "List recent executions",
    "health": "Check server health",
    "exit": "Exit the shell",
    "quit": "Exit the shell",
}


class ShellState:
    """Mutable state for the interactive session."""

    def __init__(
        self,
        server: str,
        project: str,
        api_key: str | None,
        timeout: float,
    ) -> None:
        self.server = server
        self.project = project
        self.api_key = api_key
        self.timeout = timeout
        self._resource_cache: dict[str, list[str]] = {}
        self._cache_ts: float = 0.0

    def headers(self) -> dict[str, str]:
        """Build auth headers from available credentials."""
        if self.api_key:
            return {"X-API-Key": self.api_key}
        from blackbeard_cli.credentials import get_valid_token

        token = get_valid_token(self.server, self.timeout)
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def fetch_resource_names(self, kind: str) -> list[str]:
        """Fetch resource names for a kind, with a short cache."""
        now = time.monotonic()
        # Cache for 30 seconds to keep tab-completion responsive
        if now - self._cache_ts > 30.0:
            self._resource_cache.clear()
            self._cache_ts = now

        if kind in self._resource_cache:
            return self._resource_cache[kind]

        plural = KIND_TO_PLURAL.get(kind)
        if not plural:
            return []

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(
                    f"{self.server}/api/v1/{plural}",
                    headers=self.headers(),
                    params={"project": self.project, "limit": 200},
                )
            if resp.status_code == 200:
                items = extract_items(resp.json())
                names = [
                    item.get("metadata", {}).get("name", "")
                    for item in items
                    if item.get("metadata", {}).get("name")
                ]
                self._resource_cache[kind] = names
                return names
        except (httpx.RequestError, ValueError):
            pass
        return []


class ShellCompleter(Completer):
    """Context-aware completer for the interactive shell."""

    def __init__(self, state: ShellState) -> None:
        self.state = state

    def get_completions(
        self,
        document: Any,
        complete_event: Any,
    ) -> Any:
        text = document.text_before_cursor
        words = text.split()
        word_count = len(words)

        # If cursor is right after a space, we're starting a new word
        at_new_word = text.endswith(" ") if text else True

        if word_count == 0 or (word_count == 1 and not at_new_word):
            # Completing the command name
            prefix = words[0] if words else ""
            for cmd, desc in SHELL_COMMANDS.items():
                if cmd.startswith(prefix):
                    yield Completion(
                        cmd,
                        start_position=-len(prefix),
                        display_meta=desc,
                    )
            return

        cmd = words[0]

        if cmd in ("ls", "get", "cat"):
            if word_count == 1 and at_new_word:
                # Complete kind (first arg)
                for kind in sorted(ALL_KINDS):
                    yield Completion(kind)
            elif word_count == 2 and not at_new_word:
                # Partial kind
                prefix = words[1]
                for kind in sorted(ALL_KINDS):
                    if kind.lower().startswith(prefix.lower()):
                        yield Completion(kind, start_position=-len(prefix))
            elif cmd in ("get", "cat") and (
                (word_count == 2 and at_new_word) or (word_count == 3 and not at_new_word)
            ):
                # Complete resource name
                kind = words[1]
                prefix = words[2] if word_count == 3 else ""
                if kind in ALL_KINDS:
                    names = self.state.fetch_resource_names(kind)
                    for name in names:
                        if name.startswith(prefix):
                            yield Completion(name, start_position=-len(prefix))

        elif cmd == "run":
            if (word_count == 1 and at_new_word) or (word_count == 2 and not at_new_word):
                prefix = words[1] if word_count == 2 else ""
                names = self.state.fetch_resource_names("Crew")
                for name in names:
                    if name.startswith(prefix):
                        yield Completion(name, start_position=-len(prefix))

        elif cmd == "use" and (
            (word_count == 1 and at_new_word) or (word_count == 2 and not at_new_word)
        ):
            prefix = words[1] if word_count == 2 else ""
            names = self.state.fetch_resource_names("Project")
            for name in names:
                if name.startswith(prefix):
                    yield Completion(name, start_position=-len(prefix))


# ── Command handlers ───────────────────────────────────────────────────────────


def _cmd_help(state: ShellState, args: list[str]) -> None:
    """Print available shell commands."""
    table = Table(title="Shell Commands", show_lines=False, box=None, padding=(0, 2))
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for cmd, desc in SHELL_COMMANDS.items():
        table.add_row(cmd, desc)
    out.print(table)
    out.print()
    out.print("[dim]Kinds:[/]", ", ".join(sorted(ALL_KINDS)))


def _cmd_use(state: ShellState, args: list[str]) -> None:
    """Switch the active project."""
    if not args:
        out.print(f"[bold]Current project:[/] {escape(state.project)}")
        return
    state.project = args[0]
    # Invalidate cache when project changes
    state._resource_cache.clear()
    out.print(f"[green]Switched to project:[/] [bold]{escape(state.project)}[/]")


def _cmd_ls(state: ShellState, args: list[str]) -> None:
    """List resources of a given kind."""
    if not args:
        out.print("[red]Usage:[/] ls <Kind>")
        out.print("[dim]Kinds:[/]", ", ".join(sorted(ALL_KINDS)))
        return

    kind = _resolve_kind(args[0])
    if not kind:
        return

    plural = KIND_TO_PLURAL[kind]
    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.get(
                f"{state.server}/api/v1/{plural}",
                headers=state.headers(),
                params={"project": state.project, "limit": 100},
            )
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
        return

    items = extract_items(resp.json())
    if not items:
        out.print(f"[dim]No {kind} resources in project '{escape(state.project)}'.[/]")
        return

    table = Table(title=f"{kind} Resources")
    table.add_column("Name", style="bold")
    table.add_column("Project", style="dim")
    table.add_column("Version", justify="right")
    table.add_column("Labels")

    for item in items:
        meta = item.get("metadata", {})
        labels = meta.get("labels", {})
        label_str = ", ".join(f"{k}={v}" for k, v in labels.items()) if labels else "—"
        table.add_row(
            meta.get("name", "—"),
            meta.get("project", "—"),
            str(item.get("version", "—")),
            label_str,
        )

    out.print(table)
    out.print(f"[dim]{len(items)} resource(s)[/]")


def _fetch_resource(
    state: ShellState, kind_raw: str, name: str
) -> tuple[str, dict[str, Any]] | None:
    """GET a resource by kind and name; print errors and return None on failure."""
    kind = _resolve_kind(kind_raw)
    if not kind:
        return None

    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.get(
                f"{state.server}/api/v1/{KIND_TO_PLURAL[kind]}/{name}",
                headers=state.headers(),
                params={"project": state.project},
            )
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return None

    if resp.status_code != 200:
        console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
        return None

    return kind, resp.json()


def _cmd_get(state: ShellState, args: list[str]) -> None:
    """Show resource detail."""
    if len(args) < 2:
        out.print("[red]Usage:[/] get <Kind> <name>")
        return

    fetched = _fetch_resource(state, args[0], args[1])
    if fetched is None:
        return
    kind, data = fetched

    meta = data.get("metadata", {})

    header = Table(show_header=False, box=None, padding=(0, 2))
    header.add_column("Key", style="bold dim", width=12)
    header.add_column("Value")
    header.add_row("Kind", kind)
    header.add_row("Name", meta.get("name", args[1]))
    header.add_row("Project", meta.get("project", state.project))
    header.add_row("Version", str(data.get("version", "")))
    labels = meta.get("labels", {})
    if labels:
        header.add_row("Labels", ", ".join(f"{k}={v}" for k, v in labels.items()))
    out.print(header)
    out.print()

    spec_json = json.dumps(data.get("spec", data), indent=2, default=str)
    out.print(Syntax(spec_json, "json", theme="monokai"))


def _cmd_cat(state: ShellState, args: list[str]) -> None:
    """Show resource as YAML."""
    if len(args) < 2:
        out.print("[red]Usage:[/] cat <Kind> <name>")
        return

    fetched = _fetch_resource(state, args[0], args[1])
    if fetched is None:
        return
    kind, data = fetched

    # Build a clean resource document
    resource = {
        "apiVersion": data.get("apiVersion", "blackbeard/v1"),
        "kind": data.get("kind", kind),
        "metadata": data.get("metadata", {}),
        "spec": data.get("spec", {}),
    }
    yaml_str = yaml.dump(resource, default_flow_style=False, sort_keys=False)
    out.print(Syntax(yaml_str, "yaml", theme="monokai"))


def _cmd_run(state: ShellState, args: list[str]) -> None:
    """Kick off a crew execution."""
    if not args:
        out.print("[red]Usage:[/] run <crew-name>")
        return

    crew_name = args[0]
    url = f"{state.server}/api/v1/crews/{crew_name}/kickoff"

    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.post(
                url,
                json={"inputs": {}},
                headers=state.headers(),
                params={"project": state.project},
            )
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    if resp.status_code not in (200, 201, 202):
        console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
        return

    data = resp.json()
    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")

    out.print(
        Panel.fit(
            f"[bold]Crew:[/] {escape(crew_name)}\n"
            f"[bold]Execution ID:[/] {escape(str(execution_id))}\n"
            f"[bold]Status:[/] {escape(status_val)}",
            title="[green]Execution Submitted[/]",
            border_style="green",
        )
    )
    out.print(f"[dim]Watch with: watch {escape(str(execution_id))}[/]")


def _cmd_watch(state: ShellState, args: list[str]) -> None:
    """Watch execution status with live polling."""
    if not args:
        out.print("[red]Usage:[/] watch <execution-id>")
        return

    execution_id = args[0]
    interval = 3

    console.print(
        f"[dim]Watching execution {escape(execution_id)}"
        f" (Ctrl-C to stop, polling every {interval}s)...[/]\n"
    )

    try:
        with httpx.Client(timeout=state.timeout) as client:
            first = True
            while True:
                try:
                    resp = client.get(
                        f"{state.server}/api/v1/executions/{execution_id}",
                        headers=state.headers(),
                    )
                except httpx.RequestError as exc:
                    console.print(f"[red]Error:[/] {exc}")
                    return

                if resp.status_code != 200:
                    console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
                    return

                data = resp.json()
                if not first:
                    console.print("[dim]--- refreshed ---[/]\n")
                render_execution_detail(data, execution_id)
                first = False

                current = data.get("status", "")
                if current in TERMINAL_STATUSES:
                    break

                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/]")


def _cmd_status(state: ShellState, args: list[str]) -> None:
    """Show execution status (single fetch, no polling)."""
    if not args:
        out.print("[red]Usage:[/] status <execution-id>")
        return

    execution_id = args[0]
    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.get(
                f"{state.server}/api/v1/executions/{execution_id}",
                headers=state.headers(),
            )
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
        return

    render_execution_detail(resp.json(), execution_id)


def _cmd_executions(state: ShellState, args: list[str]) -> None:
    """List recent executions."""
    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.get(
                f"{state.server}/api/v1/executions",
                headers=state.headers(),
                params={"project": state.project, "limit": 20},
            )
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error:[/] HTTP {resp.status_code}: {extract_detail(resp)}")
        return

    data = resp.json()
    items = extract_items(data)
    if not items:
        out.print("[dim]No executions found.[/]")
        return

    out.print(build_executions_table(items, title="Recent Executions"))
    out.print(f"[dim]{len(items)} execution(s)[/]")


def _cmd_health(state: ShellState, args: list[str]) -> None:
    """Check server health."""
    try:
        with httpx.Client(timeout=state.timeout) as client:
            resp = client.get(f"{state.server}/api/v1/health")
    except httpx.RequestError as exc:
        console.print(f"[red]Error:[/] Cannot reach {state.server}: {exc}")
        return

    if resp.status_code != 200:
        console.print(f"[red]Error:[/] HTTP {resp.status_code}")
        return

    try:
        data = resp.json()
    except ValueError:
        console.print("[red]Error:[/] Non-JSON response from server")
        return

    status_val = data.get("status", "unknown")
    color = "green" if status_val in ("ok", "healthy") else "red"
    out.print(
        f"[{color} bold]{status_val}[/]  "
        f"[dim]{data.get('service', '')} v{data.get('version', '?')}[/]"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _resolve_kind(raw: str) -> str | None:
    """Case-insensitive kind lookup. Prints error and returns None on miss."""
    for kind in ALL_KINDS:
        if kind.lower() == raw.lower():
            return kind
    console.print(f"[red]Unknown kind:[/] {escape(raw)}")
    console.print("[dim]Valid kinds:[/]", ", ".join(sorted(ALL_KINDS)))
    return None


# ── Command dispatch table ─────────────────────────────────────────────────────

DISPATCH: dict[str, Any] = {
    "help": _cmd_help,
    "use": _cmd_use,
    "ls": _cmd_ls,
    "get": _cmd_get,
    "cat": _cmd_cat,
    "run": _cmd_run,
    "watch": _cmd_watch,
    "status": _cmd_status,
    "executions": _cmd_executions,
    "health": _cmd_health,
}


# ── REPL entry point ──────────────────────────────────────────────────────────


def start_shell(
    server: str = "http://localhost:8000",
    api_key: str | None = None,
    project: str = "default",
    timeout: float = 30.0,
) -> None:
    """Start the interactive Blackbeard shell."""
    state = ShellState(server=server, project=project, api_key=api_key, timeout=timeout)

    # Ensure history directory exists with restricted permissions
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(_CONFIG_DIR, 0o700)

    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(_HISTORY_FILE)),
        completer=ShellCompleter(state),
    )

    # Restrict history file after FileHistory creates it
    if _HISTORY_FILE.exists():
        os.chmod(_HISTORY_FILE, 0o600)

    out.print(
        Panel.fit(
            f"[bold]Server:[/] {escape(state.server)}\n"
            f"[bold]Project:[/] {escape(state.project)}\n\n"
            "[dim]Type 'help' for available commands. Ctrl-D or 'exit' to quit.[/]",
            title="[bold cyan]Blackbeard Shell[/]",
            border_style="cyan",
        )
    )

    while True:
        try:
            prompt_text = HTML(
                f"<b>blackbeard</b> [<style fg='cyan'>{escape(state.project)}</style>]&gt; "
            )
            line = session.prompt(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            out.print("\n[dim]Goodbye.[/]")
            break

        if not line:
            continue

        if line in ("exit", "quit"):
            out.print("[dim]Goodbye.[/]")
            break

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            console.print(f"[red]Parse error:[/] {exc}")
            continue

        cmd = parts[0]
        cmd_args = parts[1:]

        handler = DISPATCH.get(cmd)
        if handler is None:
            console.print(f"[red]Unknown command:[/] {escape(cmd)}")
            console.print("[dim]Type 'help' for available commands.[/]")
            continue

        try:
            handler(state, cmd_args)
        except SystemExit:
            # Don't let click/handler SystemExit kill the shell
            pass
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/]")
        except Exception as exc:
            console.print(f"[red]Error:[/] {exc}")
