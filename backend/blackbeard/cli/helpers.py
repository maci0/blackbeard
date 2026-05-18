"""Shared CLI helpers — output, error handling, auth resolution."""

from __future__ import annotations

import json
from typing import NoReturn

import click
import httpx
from rich.console import Console

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

json_opt = click.option(
    "--json", "output_json", is_flag=True, default=False, help="Output as JSON for scripting"
)


def print_json(data: object, *, compact: bool = False) -> None:
    """Print data as JSON to stdout."""
    if compact:
        out.print(
            json.dumps(data, default=str, ensure_ascii=False, separators=(",", ":")),
            highlight=False,
        )
    else:
        out.print_json(json.dumps(data, default=str, ensure_ascii=False))


def extract_detail(response: httpx.Response) -> str:
    """Safely extract error detail from an HTTP response."""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail", response.text)
            if isinstance(detail, str):
                return detail
            return str(detail)
        return response.text
    except Exception:
        return response.text


def handle_request_error(server: str, exc: httpx.RequestError) -> NoReturn:
    """Handle network-level errors with helpful suggestions."""
    console.print(
        f"[red bold]Error:[/] Cannot reach server at [bold]{server}[/]\n"
        f"  {exc}\n\n"
        f"[dim]Suggestions:\n"
        f"  - Is the server running? Try: curl {server}/api/v1/health\n"
        f"  - Wrong URL? Set --server or BLACKBEARD_SERVER[/]"
    )
    raise SystemExit(1) from exc


def handle_http_error(response: httpx.Response) -> NoReturn:
    """Handle HTTP errors with status-specific hints."""
    detail = extract_detail(response)
    console.print(f"[red bold]Error:[/] HTTP {response.status_code}: {detail}")
    if response.status_code == 401:
        console.print("[dim]Hint: Check your credentials (blackbeard login or --api-key)[/]")
    elif response.status_code == 403:
        console.print("[dim]Hint: Authenticated but lacking permission for this action[/]")
    elif response.status_code == 404:
        console.print("[dim]Hint: Verify the resource name and namespace (-n)[/]")
    elif response.status_code == 409:
        console.print("[dim]Hint: Resource version conflict — re-fetch and retry[/]")
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
    except Exception:
        pass
    raise SystemExit(1)


def require_auth(ctx: click.Context) -> dict[str, str]:
    """Get auth headers from context. Tries API key, then stored JWT.

    Returns dict suitable for httpx headers.
    Exits with code 2 if no auth available.
    """
    from blackbeard.cli.credentials import get_valid_token

    api_key = ctx.obj.get("api_key")
    if api_key:
        return {"X-API-Key": api_key}

    server = ctx.obj["server"]
    timeout = ctx.obj.get("timeout", 30.0)
    token = get_valid_token(server, timeout)
    if token:
        return {"Authorization": f"Bearer {token}"}

    console.print(
        "[red bold]Error:[/] Authentication required.\n"
        "  Use [bold]blackbeard login[/] or set BLACKBEARD_API_KEY."
    )
    raise SystemExit(2)


def auth_headers(ctx: click.Context) -> dict[str, str] | None:
    """Like require_auth but returns None instead of exiting."""
    from blackbeard.cli.credentials import get_valid_token

    api_key = ctx.obj.get("api_key")
    if api_key:
        return {"X-API-Key": api_key}

    server = ctx.obj["server"]
    timeout = ctx.obj.get("timeout", 30.0)
    token = get_valid_token(server, timeout)
    if token:
        return {"Authorization": f"Bearer {token}"}

    return None


def validate_name(name: str) -> None:
    """Exit with code 2 if name doesn't match resource naming rules."""
    import re

    from blackbeard.kinds import NAME_PATTERN

    if not re.fullmatch(NAME_PATTERN, name):
        console.print(
            f"[red bold]Error:[/] Invalid resource name {name!r}.\n"
            "  Names must start with a lowercase letter or digit and"
            " contain only lowercase letters, digits, and hyphens."
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
    from_cli = ctx.get_parameter_source("interval") == click.core.ParameterSource.COMMANDLINE
    if not watch and from_cli:
        console.print(
            f"[yellow]Warning:[/] --interval/-i has no effect without {watch_flag}."
            f" Try: [bold]{cmd_hint} {watch_short} -i {interval}[/]"
        )


def make_client(ctx: click.Context) -> httpx.Client:
    """Create an httpx client with the configured timeout."""
    return httpx.Client(timeout=ctx.obj["timeout"])
