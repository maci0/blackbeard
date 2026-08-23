"""Shared CLI helpers — output, error handling, auth resolution."""

from __future__ import annotations

import json
import re
import sys
from typing import TYPE_CHECKING, Any, NoReturn

import click
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from blackbeard_cli.kinds import ALL_KINDS, NAME_PATTERN

if TYPE_CHECKING:
    import httpx

console = Console(stderr=True)
out = Console()

STATUS_COLORS: dict[str, str] = {
    "completed": "green",
    "failed": "red",
    "cancelled": "yellow",
    "running": "blue",
    "queued": "cyan",
    "pending": "cyan",
}

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

_KIND_LOOKUP: dict[str, str] = {k.lower(): k for k in ALL_KINDS}


class ResourceKindType(click.ParamType):
    """Accept resource kinds case-insensitively; keep TitleCase values and metavar."""

    name = "kind"

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> str:
        if value is None:
            return value  # type: ignore[return-value]
        text = str(value)
        matched = _KIND_LOOKUP.get(text.lower())
        if matched is not None:
            return matched
        choices = ", ".join(sorted(ALL_KINDS))
        self.fail(f"{text!r} is not a valid kind. Choose from: {choices}", param, ctx)

    def get_metavar(self, param: click.Parameter, ctx: click.Context) -> str:
        return "KIND"

    def shell_complete(
        self,
        ctx: click.Context,
        param: click.Parameter,
        incomplete: str,
    ) -> list[click.shell_completion.CompletionItem]:
        from click.shell_completion import CompletionItem

        prefix = incomplete.lower()
        return [
            CompletionItem(kind) for kind in sorted(ALL_KINDS) if kind.lower().startswith(prefix)
        ]


KIND = ResourceKindType()


def configure_output(*, no_color: bool = False, quiet: bool = False) -> None:
    """Apply global output preferences to module-level Rich consoles."""
    if no_color:
        console.no_color = True
        out.no_color = True


def is_interactive(ctx: click.Context) -> bool:
    """True when stdin is a TTY and JSON mode is not active."""
    if ctx.obj.get("json"):
        return False
    return sys.stdin.isatty()


def ensure_interactive_value(
    ctx: click.Context,
    value: str | None,
    flag: str,
    *,
    prompt: str,
    hide_input: bool = False,
    confirmation_prompt: bool = False,
) -> str:
    """Return *value*, or prompt when interactive; exit 2 when not.

    Used so login/register/invite fail clearly under ``--json`` or redirected stdin
    instead of Click's generic ``Aborted!``.
    """
    if value:
        return value
    if not is_interactive(ctx):
        console.print(
            f"[red bold]Error:[/] --{flag} is required in non-interactive mode.\n"
            f"  [dim]Pass --{flag} explicitly, or run without --json on a TTY.[/]"
        )
        raise SystemExit(2)
    return str(
        click.prompt(
            prompt,
            hide_input=hide_input,
            confirmation_prompt=confirmation_prompt,
        )
    )


def _merge_json_flag(ctx: click.Context, _param: click.Parameter, value: bool) -> bool:
    """Auto-merge parent and local ``--json`` into ``ctx.obj["json"]``."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = ctx.obj.get("json", False) or value
    return value


json_opt = click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON for scripting",
    callback=_merge_json_flag,
    expose_value=False,
)


class HelpCommand(click.Command):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        cs = dict(kwargs.pop("context_settings", None) or {})
        cs.setdefault("help_option_names", ["-h", "--help"])
        kwargs["context_settings"] = cs
        super().__init__(*args, **kwargs)


def print_json(data: object, *, compact: bool = False) -> None:
    """Emit machine-readable JSON on stdout with no ANSI/markup (safe for jq/scripts)."""
    if compact:
        text = json.dumps(data, default=str, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(data, default=str, ensure_ascii=False, indent=2)
    # Never syntax-highlight: --json is for machines, not terminals.
    out.print(text, highlight=False, markup=False)


def extract_detail(response: httpx.Response) -> str:
    """Extract error detail from response JSON, falling back to raw text."""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail", response.text)
            if isinstance(detail, str):
                return detail
            if isinstance(detail, list):
                parts = []
                for item in detail:
                    if isinstance(item, dict):
                        loc = ".".join(str(x) for x in item.get("loc", []))
                        msg = item.get("msg", str(item))
                        parts.append(f"{loc}: {msg}" if loc else msg)
                    else:
                        parts.append(str(item))
                return "; ".join(parts) if parts else str(detail)
            return str(detail)
        return response.text
    except (ValueError, KeyError):
        return response.text


def handle_request_error(server: str, exc: httpx.RequestError) -> NoReturn:
    """Print network error with suggestions and exit(1)."""
    console.print(
        f"[red bold]Error:[/] Cannot reach server at [bold]{escape(server)}[/]\n"
        f"  {escape(str(exc))}\n\n"
        f"[dim]Suggestions:\n"
        f"  - Is the server running? Try: curl {escape(server)}/api/v1/health\n"
        f"  - Wrong URL? Set --server or BLACKBEARD_SERVER[/]"
    )
    raise SystemExit(1) from exc


def handle_http_error(response: httpx.Response) -> NoReturn:
    """Print HTTP error with status-specific hints and exit(1)."""
    detail = extract_detail(response)
    method = response.request.method
    path = response.request.url.path
    console.print(
        f"[red bold]Error:[/] HTTP {response.status_code} on {method} {path}: {escape(detail)}"
    )
    if response.status_code == 400:
        console.print("[dim]Hint: Bad request — check the request body and parameters[/]")
    elif response.status_code == 401:
        console.print("[dim]Hint: Check your credentials (blackbeard login or --api-key)[/]")
    elif response.status_code == 403:
        console.print("[dim]Hint: Authenticated but lacking permission for this action[/]")
    elif response.status_code == 404:
        console.print("[dim]Hint: Verify the resource name and project (-n)[/]")
    elif response.status_code == 409:
        console.print("[dim]Hint: Resource version conflict — re-fetch and retry[/]")
    elif response.status_code == 413:
        console.print("[dim]Hint: Payload too large — reduce file size (server limit: 10MB)[/]")
    elif response.status_code == 422:
        console.print("[dim]Hint: Check your input against the expected schema[/]")
    elif response.status_code == 429:
        retry = response.headers.get("Retry-After")
        hint = "Too many requests — wait and retry"
        if retry:
            hint += f" (Retry-After: {retry}s)"
        console.print(f"[dim]Hint: {hint}[/]")
    elif response.status_code >= 500:
        console.print("[dim]Hint: Server error — check server logs for details[/]")
    try:
        body = response.json()
        if isinstance(body, dict) and "request_id" in body:
            console.print(f"[dim]Request ID: {body['request_id']}[/]")
    except (ValueError, KeyError):
        pass
    raise SystemExit(1)


def require_auth(ctx: click.Context) -> dict[str, str]:
    """Get auth headers from context. Tries API key, then stored JWT.

    Returns dict suitable for httpx headers.
    Exits with code 2 if no auth available.
    """
    from blackbeard_cli.credentials import get_valid_token

    api_key = ctx.obj.get("api_key")
    if api_key:
        return {"X-API-Key": api_key}

    server = ctx.obj["server"]
    timeout = ctx.obj.get("timeout", 30.0)
    token = get_valid_token(server, timeout)
    if token:
        return {"Authorization": f"Bearer {token}"}

    from blackbeard_cli.credentials import load_credentials

    creds = load_credentials()
    if creds and creds.server.rstrip("/") != server.rstrip("/"):
        console.print(
            f"[red bold]Error:[/] Authentication required.\n"
            f"  Logged in to [bold]{escape(creds.server)}[/]"
            f" but targeting [bold]{escape(server)}[/].\n"
            f"  Run: [bold]blackbeard -s {escape(server)} login[/]"
        )
    else:
        console.print(
            "[red bold]Error:[/] Authentication required.\n"
            "  Use [bold]blackbeard login[/] or set BLACKBEARD_API_KEY."
        )
    raise SystemExit(2)


def validate_name(name: str) -> None:
    """Exit with code 2 if name doesn't match resource naming rules."""
    if not re.fullmatch(NAME_PATTERN, name):
        console.print(
            f"[red bold]Error:[/] Invalid resource name {escape(repr(name))}.\n"
            "  Names must start with a lowercase letter or digit and"
            " contain only lowercase letters, digits, and hyphens.\n"
            "  [dim]Example: my-agent[/]"
        )
        raise SystemExit(2)


def warn_unused_interval(
    ctx: click.Context,
    watch: bool,
    interval: int,
    cmd_hint: str,
    *,
    watch_flag: str = "--wait/--watch/-w",
    watch_short: str = "-w",
) -> None:
    """Warn when --interval is passed without the streaming/watch flag."""
    if ctx.obj.get("quiet"):
        return
    from_cli = ctx.get_parameter_source("interval") == click.core.ParameterSource.COMMANDLINE
    if not watch and from_cli:
        console.print(
            f"[yellow]Warning:[/] --interval/-i has no effect without {watch_flag}."
            f" Try: [bold]{cmd_hint} {watch_short} -i {interval}[/]"
        )


def parse_key_value_inputs(items: tuple[str, ...], flag_name: str = "--input") -> dict[str, Any]:
    """Parse KEY=VALUE pairs from a repeatable CLI option.

    Values are parsed as JSON when valid, otherwise kept as strings.
    """
    result: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            console.print(
                f"[red bold]Error:[/] Invalid {flag_name}:"
                f" expected KEY=VALUE, got: {escape(repr(item))}"
            )
            console.print(f'[dim]Example: {flag_name} topic="AI agents"[/]')
            raise SystemExit(2)
        key, _, value = item.partition("=")
        if not key:
            console.print(
                f"[red bold]Error:[/] Invalid {flag_name}:"
                f" key cannot be empty in {escape(repr(item))}"
            )
            raise SystemExit(2)
        try:
            result[key] = json.loads(value)
        except (ValueError, json.JSONDecodeError):
            result[key] = value
    return result


def confirm_destructive(ctx: click.Context, prompt_msg: str, *, yes: bool) -> bool:
    """Check destructive-op confirmation; returns True to proceed, False to abort.

    In JSON mode without --yes, prints an error and exits.
    In interactive mode, prompts the user.
    """
    if yes:
        return True
    if ctx.obj["json"]:
        console.print("[red bold]Error:[/] Destructive operation requires -y/--yes with --json.")
        raise SystemExit(2)
    if not click.confirm(prompt_msg, default=False):
        console.print("[yellow]Aborted.[/]")
        return False
    return True


def format_timestamp(value: object, fallback: str = "—") -> str:
    """Format an API timestamp to 'YYYY-MM-DDTHH:MM:SS' (19 chars)."""
    raw = str(value) if value else fallback
    return raw[:19] if raw != fallback else fallback


def extract_items(data: Any) -> list[Any]:
    """Normalise a list-or-paginated API response into a plain list."""
    return data if isinstance(data, list) else data.get("items") or []


def extract_total(data: Any, items: list[Any]) -> int:
    if isinstance(data, list):
        return len(items)
    total = data.get("total")
    return total if isinstance(total, int) else len(items)


def build_executions_table(items: list[Any], *, title: str) -> Table:
    """Build the shared executions list table (rows only; caller adds its footer)."""
    table = Table(title=title)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Crew", style="bold")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")

    for ex in items:
        ex_id = str(ex.get("id", "—"))
        status_val = ex.get("status", "—")
        color = STATUS_COLORS.get(status_val, "dim")
        tokens = ex.get("total_tokens")
        cost = ex.get("cost_usd")
        try:
            cost_str = f"${float(cost):.4f}" if cost else "—"
        except (TypeError, ValueError):
            cost_str = "—"
        table.add_row(
            ex_id,
            escape(str(ex.get("crew_name", "—"))),
            f"[{color}]{status_val}[/]",
            format_timestamp(ex.get("created_at")),
            f"{tokens:,}" if tokens else "—",
            cost_str,
        )
    return table


def render_execution_detail(data: dict[str, Any], execution_id: str) -> None:
    """Render an execution status panel with error and outputs sections."""
    status_val = data.get("status", "unknown")
    color = STATUS_COLORS.get(status_val, "dim")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold dim", width=14)
    table.add_column("Value")

    table.add_row("Execution ID", str(data.get("id", execution_id)))
    table.add_row("Status", f"[{color} bold]{status_val}[/]")
    table.add_row("Crew", str(data.get("crew_name", "—")))

    tokens = data.get("total_tokens")
    if tokens:
        table.add_row("Tokens", f"{tokens:,}")

    cost = data.get("cost_usd")
    try:
        cost_val = float(cost) if cost else 0.0
    except (TypeError, ValueError):
        cost_val = 0.0
    if cost_val > 0:
        table.add_row("Cost", f"${cost_val:.4f}")

    started = data.get("started_at")
    if started:
        table.add_row("Started", str(started))

    completed = data.get("completed_at")
    if completed:
        table.add_row("Completed", str(completed))

    out.print(Panel(table, title=f"Execution [{color}]{status_val}[/]", border_style=color))

    error = data.get("error")
    if error:
        out.print(
            Panel(
                f"[red]{escape(str(error))}[/]",
                title="[red]Error[/]",
                border_style="red",
            )
        )

    outputs = data.get("outputs")
    if outputs:
        out.print(
            Panel(
                Syntax(json.dumps(outputs, indent=2, default=str), "json", theme="monokai"),
                title="Outputs",
                border_style="green",
            )
        )
