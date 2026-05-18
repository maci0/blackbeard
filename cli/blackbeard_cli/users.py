"""CLI user and group management commands."""

from __future__ import annotations

import click
import httpx
from rich.table import Table

from blackbeard_cli.helpers import (
    console,
    extract_detail,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
)

# ── User subgroup ────────────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def user(ctx: click.Context) -> None:
    """Manage platform users."""
    ctx.ensure_object(dict)


@user.command("list")
@click.option(
    "--limit",
    default=100,
    show_default=True,
    type=click.IntRange(1, 1000),
    metavar="N",
    help="Maximum number of results",
)
@json_opt
@click.pass_context
def user_list(ctx: click.Context, limit: int, output_json: bool = False) -> None:
    """List all users."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(f"{server}/api/v1/users", headers=headers, params={"limit": limit})
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = data.get("items", [])
    if not items:
        out.print("[dim]No users found.[/]")
        return

    table = Table(title="Users")
    table.add_column("Email", style="bold")
    table.add_column("Display Name")
    table.add_column("Status")
    table.add_column("Created")

    for u in items:
        active = "[green]active[/]" if u.get("is_active") else "[red]inactive[/]"
        table.add_row(
            u.get("email", "—"),
            u.get("display_name", "—"),
            active,
            str(u.get("created_at", "—"))[:19],
        )

    out.print(table)
    total = data.get("total", len(items))
    out.print(f"[dim]{total} user(s)[/]")


@user.command("invite")
@click.option("--email", "-e", required=True, help="Email address")
@click.option(
    "--password",
    "-p",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Initial password (prompted securely if omitted)",
)
@click.option("--name", "-d", "display_name", required=True, help="Display name")
@json_opt
@click.pass_context
def user_invite(
    ctx: click.Context,
    email: str,
    password: str,
    display_name: str,
    output_json: bool = False,
) -> None:
    """Create a new user account (admin invite)."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.post(
                f"{server}/api/v1/auth/register",
                headers=headers,
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
        console.print(f"[red bold]Error:[/] {detail}")
        raise SystemExit(1)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    out.print(f"[green]Invited[/] [bold]{display_name}[/] ({email})")


# ── Group subgroup ───────────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def group(ctx: click.Context) -> None:
    """Manage groups."""
    ctx.ensure_object(dict)


@group.command("list")
@click.option(
    "--limit",
    default=100,
    show_default=True,
    type=click.IntRange(1, 1000),
    metavar="N",
    help="Maximum number of results",
)
@json_opt
@click.pass_context
def group_list(ctx: click.Context, limit: int, output_json: bool = False) -> None:
    """List all groups."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(f"{server}/api/v1/groups", headers=headers, params={"limit": limit})
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = data.get("items", [])
    if not items:
        out.print("[dim]No groups found.[/]")
        return

    table = Table(title="Groups")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Created")

    for g in items:
        table.add_row(
            g.get("name", "—"),
            g.get("description", "—") or "—",
            str(g.get("created_at", "—"))[:19],
        )

    out.print(table)
    total = data.get("total", len(items))
    out.print(f"[dim]{total} group(s)[/]")


@group.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Group description")
@json_opt
@click.pass_context
def group_create(
    ctx: click.Context, name: str, description: str, output_json: bool = False
) -> None:
    """Create a new group."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    body: dict[str, str] = {"name": name}
    if description:
        body["description"] = description

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.post(f"{server}/api/v1/groups", headers=headers, json=body)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 201):
        detail = extract_detail(resp)
        console.print(f"[red bold]Error:[/] {detail}")
        raise SystemExit(1)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    out.print(f"[green]Created[/] group [bold]{name}[/]")


@group.command("delete")
@click.argument("group_id")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation")
@json_opt
@click.pass_context
def group_delete(ctx: click.Context, group_id: str, yes: bool, output_json: bool = False) -> None:
    """Delete a group by ID."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    if (
        not yes
        and not ctx.obj["json"]
        and not click.confirm(f"Delete group {group_id}?", default=False)
    ):
        console.print("[yellow]Aborted.[/]")
        return

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.delete(f"{server}/api/v1/groups/{group_id}", headers=headers)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 204):
        handle_http_error(resp)

    if ctx.obj["json"]:
        print_json({"deleted": group_id, "status": "deleted"})
        return

    out.print(f"[green]Deleted[/] group [bold]{group_id}[/]")
