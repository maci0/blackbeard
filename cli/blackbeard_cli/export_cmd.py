"""CLI export command — dump resources as YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import httpx
import yaml

from blackbeard_cli.helpers import (
    HelpCommand,
    console,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
    validate_name,
)
from blackbeard_cli.kinds import ALL_KINDS, API_VERSION, KIND_TO_PLURAL


def _strip_server_fields(resource: dict[str, Any]) -> dict[str, Any]:
    """Keep only apiVersion, kind, metadata (name/namespace/labels), and spec."""
    meta = resource.get("metadata", {})
    clean_meta: dict[str, Any] = {"name": meta.get("name", "")}
    ns = meta.get("namespace")
    if ns and ns != "default":
        clean_meta["namespace"] = ns
    labels = meta.get("labels")
    if labels:
        clean_meta["labels"] = labels

    return {
        "apiVersion": resource.get("apiVersion", API_VERSION),
        "kind": resource.get("kind", ""),
        "metadata": clean_meta,
        "spec": resource.get("spec", {}),
    }


def _fetch_resources(
    client: httpx.Client,
    server: str,
    headers: dict[str, str],
    kind: str,
    namespace: str | None,
    *,
    lenient: bool = False,
) -> list[dict[str, Any]]:
    """Fetch all resources of a given kind.

    Args:
        lenient: If True, log warnings and return [] on errors (used by --all).
                 If False, propagate errors to the caller (used for single-kind export).
    """
    plural = KIND_TO_PLURAL.get(kind)
    if not plural:
        if lenient:
            return []
        console.print(f"[red bold]Error:[/] Unknown kind: {kind}")
        raise SystemExit(2)

    params: dict[str, Any] = {"limit": 1000}
    if namespace:
        params["namespace"] = namespace

    try:
        resp = client.get(f"{server}/api/v1/{plural}", headers=headers, params=params)
    except httpx.RequestError as exc:
        if lenient:
            console.print(f"[yellow]Warning:[/] Failed to fetch {kind}: {exc}")
            return []
        handle_request_error(server, exc)

    if resp.status_code != 200:
        if lenient:
            console.print(f"[yellow]Warning:[/] Failed to fetch {kind}: HTTP {resp.status_code}")
            return []
        handle_http_error(resp)

    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", [])
    return [_strip_server_fields(item) for item in items]


def _resources_to_yaml(resources: list[dict[str, Any]]) -> str:
    """Convert resource dicts to multi-document YAML string."""
    docs = []
    for res in resources:
        docs.append(yaml.dump(res, default_flow_style=False, sort_keys=False).rstrip())
    return "\n---\n".join(docs) + "\n" if docs else ""


@click.command(
    "export",
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard export Agent researcher          # single resource
  blackbeard export Agent                     # all agents
  blackbeard export --all                     # everything
  blackbeard export --all -o backup/          # to directory
""",
)
@click.argument(
    "kind",
    required=False,
    type=click.Choice(sorted(ALL_KINDS), case_sensitive=False),
)
@click.argument("name", required=False)
@click.option("--all", "-a", "export_all", is_flag=True, help="Export all resource kinds")
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(),
    metavar="PATH",
    help="Write to file or directory",
)
@json_opt
@click.pass_context
def export_cmd(
    ctx: click.Context,
    kind: str | None,
    name: str | None,
    export_all: bool,
    output_path: str | None,
    output_json: bool = False,
) -> None:
    """Export resources as YAML (or JSON with --json)."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)
    namespace = ctx.obj["namespace"]

    if not export_all and not kind:
        console.print("[red bold]Error:[/] Specify a Kind or use --all.")
        raise SystemExit(2)

    if export_all and kind:
        console.print(
            f"[red bold]Error:[/] --all cannot be combined with Kind argument '{kind}'.\n"
            f"  Use [bold]blackbeard export --all[/] or [bold]blackbeard export {kind}[/]."
        )
        raise SystemExit(2)
    if export_all and name:
        console.print(
            f"[red bold]Error:[/] --all cannot be combined with Name argument '{name}'.\n"
            f"  Use [bold]blackbeard export --all[/] or [bold]blackbeard export <KIND> {name}[/]."
        )
        raise SystemExit(2)

    if name:
        validate_name(name)

    with httpx.Client(timeout=ctx.obj["timeout"]) as client:
        if export_all:
            resources = _export_all(client, server, headers, namespace)
        elif kind and name:
            resources = _export_single(client, server, headers, kind, name, namespace)
        elif kind:
            resources = _fetch_resources(client, server, headers, kind, namespace)
        else:
            resources = []

    if not resources:
        console.print("[dim]No resources to export.[/]")
        return

    if ctx.obj["json"]:
        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(resources, indent=2, default=str, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            console.print(f"[green]Wrote[/] {p} ({len(resources)} resource(s), JSON)")
        else:
            print_json(resources)
        return

    yaml_str = _resources_to_yaml(resources)

    if output_path:
        p = Path(output_path)
        if export_all and p.suffix == "":
            p.mkdir(parents=True, exist_ok=True)
            by_kind: dict[str, list[dict[str, Any]]] = {}
            for res in resources:
                k = res.get("kind", "unknown")
                by_kind.setdefault(k, []).append(res)
            for k, items in sorted(by_kind.items()):
                plural = KIND_TO_PLURAL.get(k, k.lower() + "s")
                file = p / f"{plural}.yaml"
                file.write_text(_resources_to_yaml(items), encoding="utf-8")
                console.print(f"  [green]Wrote[/] {file} ({len(items)} {k})")
            console.print(f"[dim]{len(resources)} resource(s) exported to {p}[/]")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(yaml_str, encoding="utf-8")
            console.print(f"[green]Wrote[/] {p} ({len(resources)} resource(s))")
    else:
        out.print(yaml_str, end="", highlight=False)
        console.print(f"[dim]{len(resources)} resource(s) exported[/]")


def _export_all(
    client: httpx.Client,
    server: str,
    headers: dict[str, str],
    namespace: str | None,
) -> list[dict[str, Any]]:
    """Fetch all resources of all kinds."""
    all_resources: list[dict[str, Any]] = []
    kinds = sorted(ALL_KINDS)
    with console.status("Exporting resources...") as status:
        for i, kind in enumerate(kinds, 1):
            status.update(f"Fetching {kind} ({i}/{len(kinds)})...")
            resources = _fetch_resources(client, server, headers, kind, namespace, lenient=True)
            all_resources.extend(resources)
    return all_resources


def _export_single(
    client: httpx.Client,
    server: str,
    headers: dict[str, str],
    kind: str,
    name: str,
    namespace: str | None,
) -> list[dict[str, Any]]:
    """Fetch a single resource by kind and name."""
    plural = KIND_TO_PLURAL.get(kind)
    if not plural:
        console.print(f"[red bold]Error:[/] Unknown kind: {kind}")
        raise SystemExit(2)

    params: dict[str, Any] = {}
    if namespace:
        params["namespace"] = namespace

    try:
        resp = client.get(f"{server}/api/v1/{plural}/{name}", headers=headers, params=params)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code != 200:
        handle_http_error(resp)

    return [_strip_server_fields(resp.json())]
