"""CLI auth commands — login, logout, whoami, register."""

from __future__ import annotations

import time

import click
import httpx
from rich.markup import escape
from rich.table import Table

from blackbeard_cli.credentials import (
    ACCESS_TOKEN_LIFETIME_S,
    clear_credentials,
    load_credentials,
    save_credentials,
)
from blackbeard_cli.helpers import (
    HelpCommand,
    console,
    extract_detail,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
)


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard login
  blackbeard login -e user@example.com
  blackbeard -s http://prod:8000 login
""",
)
@click.option(
    "--email",
    "-e",
    prompt=True,
    metavar="EMAIL",
    help="Account email address",
)
@click.option(
    "--password",
    "-p",
    prompt=True,
    hide_input=True,
    metavar="PASS",
    help="Account password",
)
@json_opt
@click.pass_context
def login(ctx: click.Context, email: str, password: str, output_json: bool = False) -> None:
    """Log in and store credentials locally."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.post(
                f"{server}/api/v1/auth/login",
                json={"email": email, "password": password},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        detail = extract_detail(resp)
        console.print(f"[red bold]Error:[/] Login failed: {escape(detail)}")
        if resp.status_code == 401:
            console.print(
                "[dim]Hint: Check your email and password. New user? Try: blackbeard register[/]"
            )
        raise SystemExit(1)

    data = resp.json()
    save_credentials(
        server=server,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        email=email,
        expires_at=time.time() + ACCESS_TOKEN_LIFETIME_S,
    )

    if ctx.obj["json"]:
        print_json({"status": "logged_in", "email": email, "server": server})
        return

    user = data.get("user", {})
    out.print(
        f"[green]Logged in[/] as [bold]{escape(user.get('display_name', email))}[/]"
        f" ({escape(email)}) on {escape(server)}"
    )


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard logout
  blackbeard logout --json
""",
)
@json_opt
@click.pass_context
def logout(ctx: click.Context, output_json: bool = False) -> None:
    """Clear stored credentials."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    existed = clear_credentials()

    if ctx.obj["json"]:
        print_json({"status": "logged_out" if existed else "no_credentials"})
        return

    if existed:
        out.print("[green]Logged out.[/] Credentials cleared.")
    else:
        out.print("[dim]No stored credentials found.[/]")


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard whoami
  blackbeard whoami --json
""",
)
@json_opt
@click.pass_context
def whoami(ctx: click.Context, output_json: bool = False) -> None:
    """Show the currently authenticated user."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(f"{server}/api/v1/auth/me", headers=headers)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    creds = load_credentials()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold dim", width=14)
    table.add_column("Value")
    table.add_row("Email", data.get("email", "—"))
    table.add_row("Display Name", data.get("display_name", "—"))
    table.add_row("User ID", str(data.get("id", "—")))
    table.add_row("Active", "[green]yes[/]" if data.get("is_active") else "[red]no[/]")
    table.add_row("Server", server)
    if creds and "X-API-Key" not in headers:
        table.add_row("Auth", "JWT (stored)")
    else:
        table.add_row("Auth", "API Key")
    out.print(table)


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard register
  blackbeard register -e user@example.com --display-name "Jane Doe"
""",
)
@click.option(
    "--email",
    "-e",
    prompt=True,
    metavar="EMAIL",
    help="Account email address",
)
@click.option(
    "--password",
    "-p",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    metavar="PASS",
    help="Password",
)
@click.option(
    "--display-name",
    "display_name",
    prompt="Display name",
    metavar="NAME",
    help="Display name shown in the UI",
)
@json_opt
@click.pass_context
def register(
    ctx: click.Context,
    email: str,
    password: str,
    display_name: str,
    output_json: bool = False,
) -> None:
    """Register a new user account."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.post(
                f"{server}/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": display_name,
                },
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 201):
        detail = extract_detail(resp)
        console.print(f"[red bold]Error:[/] Registration failed: {escape(detail)}")
        if resp.status_code == 409:
            console.print(
                "[dim]Hint: This email may already be registered. Try: blackbeard login[/]"
            )
        raise SystemExit(1)

    data = resp.json()
    save_credentials(
        server=server,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        email=email,
        expires_at=time.time() + ACCESS_TOKEN_LIFETIME_S,
    )

    if ctx.obj["json"]:
        print_json(data)
        return

    out.print(
        f"[green]Account created[/] and logged in as"
        f" [bold]{escape(display_name)}[/] ({escape(email)})"
    )
