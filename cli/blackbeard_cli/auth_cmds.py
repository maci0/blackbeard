"""CLI auth commands — login, logout, whoami, register."""

from __future__ import annotations

import time

import click
import httpx
from rich.table import Table

from blackbeard_cli.credentials import (
    _ACCESS_TOKEN_LIFETIME_S,
    clear_credentials,
    load_credentials,
    save_credentials,
)
from blackbeard_cli.helpers import (
    console,
    extract_detail,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
)


@click.command(
    epilog="""\b
Examples:
  blackbeard login
  blackbeard login -e user@example.com
  blackbeard -s http://prod:8000 login
"""
)
@click.option("--email", "-e", prompt=True, help="Account email address")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Account password")
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
        console.print(f"[red bold]Error:[/] Login failed: {detail}")
        raise SystemExit(1)

    data = resp.json()
    save_credentials(
        server=server,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        email=email,
        expires_at=time.time() + _ACCESS_TOKEN_LIFETIME_S,
    )

    if ctx.obj["json"]:
        print_json({"status": "logged_in", "email": email, "server": server})
        return

    user = data.get("user", {})
    out.print(
        f"[green]Logged in[/] as [bold]{user.get('display_name', email)}[/] ({email}) on {server}"
    )


@click.command(
    epilog="""\b
Examples:
  blackbeard logout
  blackbeard logout --json
"""
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
    epilog="""\b
Examples:
  blackbeard whoami
  blackbeard whoami --json
"""
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
        detail = extract_detail(resp)
        console.print(f"[red bold]Error:[/] {detail}")
        raise SystemExit(1)

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
    epilog="""\b
Examples:
  blackbeard register
  blackbeard register -e user@example.com -d "Jane Doe"
"""
)
@click.option("--email", "-e", prompt=True, help="Account email address")
@click.option(
    "--password", "-p", prompt=True, hide_input=True, confirmation_prompt=True, help="Password"
)
@click.option("--name", "-d", "display_name", prompt="Display name", help="Display name")
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
        console.print(f"[red bold]Error:[/] Registration failed: {detail}")
        raise SystemExit(1)

    data = resp.json()
    save_credentials(
        server=server,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        email=email,
        expires_at=time.time() + _ACCESS_TOKEN_LIFETIME_S,
    )

    if ctx.obj["json"]:
        print_json(data)
        return

    out.print(f"[green]Account created[/] and logged in as [bold]{display_name}[/] ({email})")
