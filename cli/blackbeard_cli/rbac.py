"""CLI RBAC commands — role and rolebinding management."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import click
import httpx
from rich.markup import escape
from rich.table import Table

from blackbeard_cli.helpers import (
    HelpCommand,
    confirm_destructive,
    console,
    extract_items,
    extract_total,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
    validate_name,
)
from blackbeard_cli.kinds import API_VERSION

ALL_VERBS = ["get", "list", "create", "update", "delete", "run", "invoke", "delegate"]


# ── Role subgroup ────────────────────────────────────────────────────────────


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="""\b
Examples:
  blackbeard role list
  blackbeard role describe admin
""",
)
@json_opt
@click.pass_context
def role(ctx: click.Context) -> None:
    """Manage RBAC roles."""
    ctx.ensure_object(dict)


role.command_class = HelpCommand


@role.command(
    "list",
    epilog="""\b
Examples:
  blackbeard role list
  blackbeard role list --json
""",
)
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
def role_list(ctx: click.Context, limit: int) -> None:
    """List all roles."""
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    project = ctx.obj["project"]

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(
                f"{server}/api/v1/roles",
                headers=headers,
                params={"project": project, "limit": limit},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = extract_items(data)
    if not items:
        out.print("[dim]No roles found.[/]")
        return

    table = Table(title="Roles")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Rules", justify="right")

    for item in items:
        spec = item.get("spec", {})
        name = item.get("metadata", {}).get("name", "—")
        desc = spec.get("description", "—")
        rules = spec.get("rules", [])
        table.add_row(escape(str(name)), escape(str(desc))[:60], str(len(rules)))

    out.print(table)
    total = extract_total(data, items)
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (increase --limit to see more)[/]")
    else:
        out.print(f"[dim]{len(items)} role(s)[/]")


@role.command(
    "describe",
    epilog="""\b
Examples:
  blackbeard role describe admin
  blackbeard role describe viewer --json
""",
)
@click.argument("name")
@json_opt
@click.pass_context
def role_describe(ctx: click.Context, name: str) -> None:
    """Show role details with resource-verb permission matrix."""
    validate_name(name)
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    project = ctx.obj["project"]

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(
                f"{server}/api/v1/roles/{name}",
                headers=headers,
                params={"project": project},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    spec = data.get("spec", {})
    rules: list[dict[str, Any]] = spec.get("rules", [])

    out.print(f"\n[bold]{name}[/]")
    desc = spec.get("description")
    if desc:
        out.print(f"[dim]{desc}[/]\n")

    resource_verbs: dict[str, set[str]] = defaultdict(set)
    for rule in rules:
        resources = rule.get("resources", [])
        verbs = rule.get("verbs", [])
        for res in resources:
            for v in verbs:
                if v == "*":
                    resource_verbs[res].update(ALL_VERBS)
                else:
                    resource_verbs[res].add(v)

    if not resource_verbs:
        out.print("[dim]No rules defined.[/]")
        return

    table = Table(title="Permissions")
    table.add_column("Resource", style="bold")
    for verb in ALL_VERBS:
        table.add_column(verb, justify="center", width=8)

    for res in sorted(resource_verbs):
        verbs_set = resource_verbs[res]
        cells = []
        for verb in ALL_VERBS:
            if verb in verbs_set:
                cells.append("[green]✓[/]")
            else:
                cells.append("[dim]·[/]")
        table.add_row(res, *cells)

    out.print(table)


# ── RoleBinding subgroup ─────────────────────────────────────────────────────


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="""\b
Examples:
  blackbeard rolebinding list
  blackbeard rolebinding create dev-binding -r developer --subject User:dev@example.com
  blackbeard rolebinding delete dev-binding
""",
)
@json_opt
@click.pass_context
def rolebinding(ctx: click.Context) -> None:
    """Manage role bindings."""
    ctx.ensure_object(dict)


rolebinding.command_class = HelpCommand


@rolebinding.command(
    "list",
    epilog="""\b
Examples:
  blackbeard rolebinding list
  blackbeard rolebinding list --json
""",
)
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
def rolebinding_list(ctx: click.Context, limit: int) -> None:
    """List all role bindings."""
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    project = ctx.obj["project"]

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(
                f"{server}/api/v1/role-bindings",
                headers=headers,
                params={"project": project, "limit": limit},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = extract_items(data)
    if not items:
        out.print("[dim]No role bindings found.[/]")
        return

    table = Table(title="Role Bindings")
    table.add_column("Name", style="bold")
    table.add_column("Role")
    table.add_column("Subjects")

    for item in items:
        spec = item.get("spec", {})
        name = item.get("metadata", {}).get("name", "—")
        role_name = spec.get("role", "—")
        subjects = spec.get("subjects", [])
        subj_str = ", ".join(f"{escape(str(s['kind']))}:{escape(str(s['name']))}" for s in subjects)
        table.add_row(escape(str(name)), escape(str(role_name)), subj_str or "—")

    out.print(table)
    total = extract_total(data, items)
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (increase --limit to see more)[/]")
    else:
        out.print(f"[dim]{len(items)} binding(s)[/]")


@rolebinding.command(
    "create",
    epilog="""\b
Examples:
  blackbeard rolebinding create dev-binding -r developer --subject User:dev@example.com
  blackbeard rolebinding create team-binding -r admin --subject Group:backend-team
  blackbeard rolebinding create dev-binding -r developer --subject User:dev@example.com --json
""",
)
@click.argument("name")
@click.option("--role", "-r", "role_name", required=True, metavar="ROLE", help="Role to bind")
@click.option(
    "--subject",
    "subjects",
    multiple=True,
    required=True,
    metavar="KIND:NAME",
    help="Subject as Kind:Name (repeatable)",
)
@click.option(
    "--scope-project",
    "scope_project",
    default=None,
    metavar="PROJECT",
    help="Restrict binding to this project (separate from global -n)",
)
@json_opt
@click.pass_context
def rolebinding_create(
    ctx: click.Context,
    name: str,
    role_name: str,
    subjects: tuple[str, ...],
    scope_project: str | None,
) -> None:
    """Create a role binding."""
    validate_name(name)
    validate_name(role_name)
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    parsed_subjects = []
    for s in subjects:
        if ":" not in s:
            console.print(
                f"[red bold]Error:[/] Invalid --subject: expected KIND:NAME, got: {escape(repr(s))}"
            )
            console.print("[dim]Example: --subject User:admin@blackbeard.sh[/]")
            raise SystemExit(2)
        kind, _, subj_name = s.partition(":")
        if not kind:
            console.print(
                f"[red bold]Error:[/] Invalid --subject: kind cannot be empty in {escape(repr(s))}"
            )
            raise SystemExit(2)
        if not subj_name:
            console.print(
                f"[red bold]Error:[/] Invalid --subject: name cannot be empty in {escape(repr(s))}"
            )
            raise SystemExit(2)
        parsed_subjects.append({"kind": kind, "name": subj_name})

    spec: dict[str, Any] = {
        "role": role_name,
        "subjects": parsed_subjects,
    }
    if scope_project:
        spec["scope"] = {"project": scope_project}

    body = {
        "apiVersion": API_VERSION,
        "kind": "RoleBinding",
        "metadata": {"name": name, "project": ctx.obj["project"]},
        "spec": spec,
    }

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.post(f"{server}/api/v1/role-bindings", headers=headers, json=body)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 201):
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    subj_display = ", ".join(f"{escape(s['kind'])}:{escape(s['name'])}" for s in parsed_subjects)
    out.print(
        f"[green]Created[/] binding [bold]{escape(name)}[/]: {escape(role_name)} -> {subj_display}"
    )


@rolebinding.command(
    "delete",
    epilog="""\b
Examples:
  blackbeard rolebinding delete dev-binding
  blackbeard rolebinding delete dev-binding -y
  blackbeard rolebinding delete dev-binding --json
""",
)
@click.argument("name")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@json_opt
@click.pass_context
def rolebinding_delete(ctx: click.Context, name: str, yes: bool) -> None:
    """Delete a role binding by name."""
    validate_name(name)
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    project = ctx.obj["project"]

    if not confirm_destructive(
        ctx, f"Delete rolebinding {name} in project '{project}' on {server}?", yes=yes
    ):
        return

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.delete(
                f"{server}/api/v1/role-bindings/{name}",
                headers=headers,
                params={"project": project},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 204):
        handle_http_error(resp)

    if ctx.obj["json"]:
        print_json({"deleted": name, "project": project, "status": "deleted"})
        return

    out.print(
        f"[green]✓[/] Deleted rolebinding [bold]{escape(name)}[/] from project '{escape(project)}'"
    )
