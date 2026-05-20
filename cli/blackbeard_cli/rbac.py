"""CLI RBAC commands — role and rolebinding management."""

from __future__ import annotations

from typing import Any

import click
import httpx
from rich.table import Table

from blackbeard_cli.helpers import (
    console,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
    validate_name,
)

ALL_VERBS = ["get", "list", "create", "update", "delete", "run", "invoke", "delegate"]


# ── Role subgroup ────────────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def role(ctx: click.Context) -> None:
    """Manage RBAC roles."""
    ctx.ensure_object(dict)


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
def role_list(ctx: click.Context, limit: int, output_json: bool = False) -> None:
    """List all roles."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(
                f"{server}/api/v1/roles",
                headers=headers,
                params={"limit": limit},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = data if isinstance(data, list) else data.get("items", [])
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
        table.add_row(name, desc[:60], str(len(rules)))

    out.print(table)
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
def role_describe(ctx: click.Context, name: str, output_json: bool = False) -> None:
    """Show role details with resource-verb permission matrix."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(name)
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(f"{server}/api/v1/roles/{name}", headers=headers)
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

    resource_verbs: dict[str, set[str]] = {}
    for rule in rules:
        resources = rule.get("resources", [])
        verbs = rule.get("verbs", [])
        for res in resources:
            if res not in resource_verbs:
                resource_verbs[res] = set()
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
                cells.append("[green]x[/]")
            else:
                cells.append("[dim]·[/]")
        table.add_row(res, *cells)

    out.print(table)


# ── RoleBinding subgroup ─────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def rolebinding(ctx: click.Context) -> None:
    """Manage role bindings."""
    ctx.ensure_object(dict)


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
def rolebinding_list(ctx: click.Context, limit: int, output_json: bool = False) -> None:
    """List all role bindings."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(
                f"{server}/api/v1/role-bindings",
                headers=headers,
                params={"limit": limit},
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = data if isinstance(data, list) else data.get("items", [])
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
        subj_str = ", ".join(f"{s['kind']}:{s['name']}" for s in subjects)
        table.add_row(name, role_name, subj_str or "—")

    out.print(table)
    out.print(f"[dim]{len(items)} binding(s)[/]")


@rolebinding.command(
    "create",
    epilog="""\b
Examples:
  blackbeard rolebinding create dev-binding -r developer -s User:dev@example.com
  blackbeard rolebinding create team-binding -r admin -s Group:backend-team
""",
)
@click.argument("name")
@click.option("--role", "-r", "role_name", required=True, help="Role to bind")
@click.option(
    "--subject",
    "-s",
    "subjects",
    multiple=True,
    required=True,
    metavar="KIND:NAME",
    help="Subject as Kind:Name (repeatable)",
)
@click.option("--namespace", "scope_ns", default=None, help="Scope namespace")
@json_opt
@click.pass_context
def rolebinding_create(
    ctx: click.Context,
    name: str,
    role_name: str,
    subjects: tuple[str, ...],
    scope_ns: str | None,
    output_json: bool = False,
) -> None:
    """Create a role binding."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(name)
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    parsed_subjects = []
    for s in subjects:
        if ":" not in s:
            console.print(f"[red bold]Error:[/] Invalid --subject: expected KIND:NAME, got: {s!r}")
            console.print("[dim]Example: --subject User:admin@blackbeard.sh[/]")
            raise SystemExit(2)
        kind, _, subj_name = s.partition(":")
        if not kind:
            console.print(f"[red bold]Error:[/] Invalid --subject: kind cannot be empty in {s!r}")
            raise SystemExit(2)
        if not subj_name:
            console.print(f"[red bold]Error:[/] Invalid --subject: name cannot be empty in {s!r}")
            raise SystemExit(2)
        parsed_subjects.append({"kind": kind, "name": subj_name})

    spec: dict[str, Any] = {
        "role": role_name,
        "subjects": parsed_subjects,
    }
    if scope_ns:
        spec["scope"] = {"namespace": scope_ns}

    body = {
        "apiVersion": "blackbeard/v1",
        "kind": "RoleBinding",
        "metadata": {"name": name, "namespace": ctx.obj.get("namespace", "default")},
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

    subj_display = ", ".join(f"{s['kind']}:{s['name']}" for s in parsed_subjects)
    out.print(f"[green]Created[/] binding [bold]{name}[/]: {role_name} -> {subj_display}")
