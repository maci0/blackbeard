"""Blackbeard CLI entry point — Rich-powered output."""

from __future__ import annotations

import json
import re
import time
from graphlib import TopologicalSorter
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any, cast

import click
import httpx
import yaml
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from blackbeard_cli.helpers import (
    STATUS_COLORS,
    console,
    extract_detail,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
    validate_name,
    warn_unused_interval,
)
from blackbeard_cli.kinds import ALL_KINDS, KIND_TO_PLURAL, NAME_PATTERN
from blackbeard_cli.resources import (
    ValidationError,
    build_adjacency,
    detect_cycles,
    validate_resource,
)

# Terminal execution statuses — inlined to avoid pulling in SQLAlchemy.
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


def load_yaml_resources(path: Path) -> list[dict[str, Any]]:
    """Load all YAML resource files from a file or directory."""
    files: list[Path] = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.rglob("*.yaml")) + sorted(path.rglob("*.yml"))
    else:
        console.print(f"[red bold]Error:[/] Path not found: [bold]{path}[/]")
        raise SystemExit(2)

    resources: list[dict[str, Any]] = []
    for f in files:
        try:
            with f.open(encoding="utf-8") as fh:
                for doc in yaml.safe_load_all(fh):
                    if not doc or not isinstance(doc, dict):
                        continue
                    if "kind" in doc:
                        doc["_source_file"] = str(f)
                        resources.append(doc)
                    elif "metadata" in doc or "spec" in doc:
                        console.print(
                            f"[yellow]Warning:[/] {f}: document has"
                            " 'metadata'/'spec' but no 'kind' — skipped"
                        )
        except yaml.YAMLError as exc:
            console.print(f"[red bold]Error:[/] Invalid YAML in [bold]{f}[/]: {exc}")
            raise SystemExit(2) from exc
    return resources


def validate_resources(
    resources: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], list[ValidationError]]], list[list[str]]]:
    """Validate resources and check for cycles."""
    per_errors = []
    for res in resources:
        kind = res.get("kind", "")
        spec = res.get("spec", {})
        errors: list[ValidationError] = []

        meta = res.get("metadata")
        if not isinstance(meta, dict) or not meta.get("name"):
            errors.append(ValidationError("metadata.name", "Required field missing"))
        else:
            name = meta["name"]
            if not re.fullmatch(NAME_PATTERN, name):
                errors.append(
                    ValidationError(
                        "metadata.name",
                        f"Invalid name '{name}':"
                        " must match [a-z0-9][a-z0-9-]* (lowercase, hyphens only)",
                    )
                )

        schema_errors, _ = validate_resource(kind, spec)
        errors.extend(schema_errors)
        if errors:
            per_errors.append((res, errors))

    adjacency = build_adjacency(resources)
    cycles = detect_cycles(adjacency)
    return per_errors, cycles


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="""\b
Common workflows:
  blackbeard health                           # liveness check (no auth)
  blackbeard health --ready                   # full readiness check
  blackbeard validate -f crew.yaml            # check resources offline
  blackbeard apply -f crew.yaml               # create/update resources
  blackbeard list Agent                       # list all agents
  blackbeard get Crew research-crew           # inspect a resource
  blackbeard kickoff research-crew --wait     # run a crew and wait
  blackbeard status <execution-id> -w         # watch execution progress
  blackbeard delete Agent my-agent            # remove a resource
""",
)
@click.version_option(version=pkg_version("blackbeard-cli"))
@click.option(
    "--server",
    "-s",
    default="http://localhost:8000",
    envvar="BLACKBEARD_SERVER",
    show_default=True,
    metavar="URL",
    help="Blackbeard API server URL (env: BLACKBEARD_SERVER)",
)
@click.option(
    "--api-key",
    "-k",
    envvar="BLACKBEARD_API_KEY",
    required=False,
    metavar="KEY",
    help="API key (env: BLACKBEARD_API_KEY)",
)
@click.option(
    "--namespace",
    "-n",
    default="default",
    envvar="BLACKBEARD_NAMESPACE",
    show_default=True,
    metavar="NAME",
    help="Resource namespace (env: BLACKBEARD_NAMESPACE)",
)
@click.option(
    "--timeout",
    "-t",
    default=30,
    show_default=True,
    type=click.IntRange(1, 300),
    envvar="BLACKBEARD_TIMEOUT",
    metavar="SECONDS",
    help="HTTP request timeout in seconds (env: BLACKBEARD_TIMEOUT)",
)
@json_opt
@click.pass_context
def cli(
    ctx: click.Context,
    server: str,
    api_key: str | None,
    namespace: str,
    timeout: int,
    output_json: bool,
) -> None:
    """Blackbeard — Agent Management Platform CLI."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server.rstrip("/")
    ctx.obj["api_key"] = api_key
    ctx.obj["namespace"] = namespace
    ctx.obj["timeout"] = float(timeout)
    ctx.obj["json"] = output_json


@cli.command(
    epilog="""\b
Examples:
  blackbeard health
  blackbeard health --ready
  blackbeard health --json
"""
)
@click.option(
    "--ready",
    "-r",
    is_flag=True,
    default=False,
    help="Run full readiness check (database, cache, LiteLLM) instead of liveness",
)
@json_opt
@click.pass_context
def health(ctx: click.Context, ready: bool, output_json: bool) -> None:
    """Check server health and component readiness (no API key required)."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    endpoint = "/api/v1/health/ready" if ready else "/api/v1/health"
    url = f"{server}{endpoint}"

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            response = client.get(url)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    try:
        data = response.json()
    except Exception:
        body_preview = response.text[:200] if response.text else "(empty body)"
        console.print(
            f"[red bold]Error:[/] Server returned non-JSON response"
            f" (HTTP {response.status_code})\n  [dim]{body_preview}[/]"
        )
        raise SystemExit(1) from None

    if ctx.obj["json"]:
        print_json(data)
        if response.status_code != 200:
            raise SystemExit(1)
        return

    status_val = data.get("status", "unknown")
    color = "green" if status_val in ("ok", "healthy") else "red"

    if not ready:
        out.print(
            f"[{color} bold]{status_val}[/]  "
            f"[dim]{data.get('service', '')} v{data.get('version', '?')}[/]"
        )
    else:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Component", style="bold", width=12)
        table.add_column("Status")
        table.add_column("Latency", justify="right", style="dim")

        checks = data.get("checks", {})
        for name, check in checks.items():
            c_status = check.get("status", "?")
            c_color = {"up": "green", "degraded": "yellow"}.get(c_status, "red")
            latency = check.get("latency_ms")
            lat_str = f"{latency}ms" if latency is not None else "—"
            table.add_row(name, f"[{c_color}]{c_status}[/]", lat_str)

        out.print(Panel(table, title=f"[{color}]{status_val}[/]", border_style=color))

    if response.status_code != 200:
        raise SystemExit(1)


@cli.command(
    epilog="""\b
Examples:
  blackbeard validate -f crew.yaml
  blackbeard validate -f examples/research-crew/
  blackbeard validate -f crew.yaml --json
"""
)
@click.option(
    "-f",
    "--file",
    "path",
    required=True,
    type=click.Path(exists=True),
    help="File or directory of YAML resources",
)
@json_opt
@click.pass_context
def validate(ctx: click.Context, path: str, output_json: bool) -> None:
    """Validate YAML resource files offline (no server connection needed)."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    resources = load_yaml_resources(Path(path))

    if not resources:
        console.print(f"[red bold]Error:[/] No resource files found in [bold]{path}[/]")
        raise SystemExit(2)

    per_errors, cycles = validate_resources(resources)
    all_valid = not per_errors and not cycles

    if ctx.obj["json"]:
        result = {
            "valid": all_valid,
            "total": len(resources),
            "errors": [
                {
                    "kind": res.get("kind"),
                    "name": res.get("metadata", {}).get("name"),
                    "source": res.get("_source_file"),
                    "issues": [{"field": e.field, "message": e.message} for e in errs],
                }
                for res, errs in per_errors
            ],
            "cycles": cycles,
        }
        print_json(result)
        if not all_valid:
            raise SystemExit(1)
        return

    table = Table(title="Validation Results", show_lines=False)
    table.add_column("Status", width=3)
    table.add_column("Kind/Name", style="bold")
    table.add_column("Source", style="dim")
    table.add_column("Issues")

    for res in resources:
        source = res.get("_source_file", "unknown")
        kind = res.get("kind", "?")
        name = res.get("metadata", {}).get("name", "?")
        res_errors = next((errs for r, errs in per_errors if r is res), [])

        if res_errors:
            issues = "\n".join(f"[red]•[/] {e.field}: {e.message}" for e in res_errors)
            table.add_row("[red]✗[/]", f"{kind}/{name}", source, issues)
        else:
            table.add_row("[green]✓[/]", f"{kind}/{name}", source, "[green]OK[/]")

    out.print(table)

    if cycles:
        out.print(
            Panel(
                "\n".join(f"[red]•[/] {' → '.join(c)}" for c in cycles),
                title="[red]Dependency Cycles[/]",
                border_style="red",
            )
        )

    valid_count = len(resources) - len(per_errors)
    summary = f"[bold]{len(resources)}[/] resources: [green]{valid_count} valid[/]"
    if per_errors:
        summary += f", [red]{len(per_errors)} errors[/]"
    out.print(f"\n{summary}")

    if not all_valid:
        raise SystemExit(1)


@cli.command(
    epilog="""\b
Examples:
  blackbeard apply -f crew.yaml
  blackbeard apply -f crew.yaml -y
  blackbeard apply -f examples/research-crew/ --dry-run
  blackbeard apply -f examples/research-crew/ --json
"""
)
@click.option(
    "-f",
    "--file",
    "path",
    required=True,
    type=click.Path(exists=True),
    help="File or directory of YAML resources",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate and show what would be applied, without making changes",
)
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON for scripting (skips confirmation prompt)",
)
@click.pass_context
def apply(ctx: click.Context, path: str, dry_run: bool, yes: bool, output_json: bool) -> None:
    """Apply YAML resource files to the server (create or update)."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]

    resources = load_yaml_resources(Path(path))

    if not resources:
        console.print(f"[red bold]Error:[/] No resource files found in [bold]{path}[/]")
        raise SystemExit(2)

    per_errors, cycles = validate_resources(resources)
    if per_errors or cycles:
        if per_errors:
            console.print("[red bold]Validation errors:[/]")
            for res, errs in per_errors:
                kind = res.get("kind", "?")
                name = res.get("metadata", {}).get("name", "?")
                console.print(f"  [red]✗[/] {kind}/{name}")
                for err in errs:
                    console.print(f"    [dim]•[/] {err.field}: {err.message}")
        if cycles:
            console.print("[red bold]Dependency cycles:[/]")
            for cycle in cycles:
                console.print(f"  [red]•[/] {' → '.join(cycle)}")
        console.print("\n[red]Aborting apply due to validation errors.[/]")
        raise SystemExit(1)

    if dry_run:
        ns = ctx.obj["namespace"]
        if ctx.obj["json"]:
            print_json(
                {
                    "dry_run": True,
                    "server": server,
                    "namespace": ns,
                    "resources": [
                        {"kind": r.get("kind"), "name": r.get("metadata", {}).get("name")}
                        for r in resources
                    ],
                }
            )
        else:
            out.print(
                Panel(
                    f"[cyan]Dry run — no changes applied[/]\n"
                    f"[dim]Server: {server}  Namespace: {ns}[/]",
                    border_style="cyan",
                )
            )
            for res in resources:
                kind = res.get("kind", "")
                name = res.get("metadata", {}).get("name", "?")
                out.print(f"  [cyan]→[/] {kind}/{name}: would apply")
        return

    if not yes and not ctx.obj["json"]:
        console.print(
            f"\n[bold]{len(resources)}[/] resource(s) will be applied to"
            f" [bold]{server}[/] (namespace: [bold]{ctx.obj['namespace']}[/])."
        )
        if not click.confirm("Proceed?", default=True):
            console.print("[yellow]Aborted.[/]")
            return

    # Topologically sort resources by dependency order
    adjacency = build_adjacency(resources)
    try:
        order = list(TopologicalSorter(adjacency).static_order())
        resources_by_key = {f"{r['kind']}/{r['metadata']['name']}": r for r in resources}
        sorted_resources = [resources_by_key[k] for k in order if k in resources_by_key]
        sorted_keys = {k for k in order if k in resources_by_key}
        for r in resources:
            key = f"{r['kind']}/{r['metadata']['name']}"
            if key not in sorted_keys:
                sorted_resources.append(r)
        resources = sorted_resources
    except (KeyError, ValueError) as exc:
        console.print(
            f"[yellow]Warning:[/] Could not sort by dependencies ({exc}), applying in file order."
        )

    # Inject CLI namespace into resources that lack one
    namespace = ctx.obj["namespace"]
    for res in resources:
        meta = res.setdefault("metadata", {})
        if "namespace" not in meta:
            meta["namespace"] = namespace

    headers = require_auth(ctx)
    results: list[dict[str, Any]] = []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Applying resources...", total=len(resources))

            total = len(resources)
            with httpx.Client(timeout=ctx.obj["timeout"]) as client:
                for idx, res in enumerate(resources, 1):
                    kind = res.get("kind", "")
                    name = res.get("metadata", {}).get("name", "?")
                    label = f"{kind}/{name}"
                    progress.update(task, description=f"Applying {label} [{idx}/{total}]...")

                    plural = KIND_TO_PLURAL.get(kind)
                    if not plural:
                        valid = ", ".join(sorted(KIND_TO_PLURAL))
                        results.append(
                            {
                                "resource": label,
                                "status": "error",
                                "detail": f"Unknown kind '{kind}'. Valid kinds: {valid}",
                            }
                        )
                        progress.advance(task)
                        continue

                    source = res.get("_source_file")
                    body = {k: v for k, v in res.items() if k != "_source_file"}
                    url = f"{server}/api/v1/{plural}"

                    try:
                        response = client.post(url, json=body, headers=headers)
                        if response.status_code in (200, 201):
                            action = "created" if response.status_code == 201 else "updated"
                            results.append({"resource": label, "status": action})
                        else:
                            detail = extract_detail(response)
                            results.append(
                                {
                                    "resource": label,
                                    "status": "error",
                                    "source": source,
                                    "detail": f"HTTP {response.status_code}: {detail}",
                                }
                            )
                    except httpx.RequestError as exc:
                        results.append(
                            {
                                "resource": label,
                                "status": "error",
                                "source": source,
                                "detail": f"Connection failed: {exc}",
                            }
                        )

                    progress.advance(task)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")

    interrupted = len(results) < len(resources)

    if ctx.obj["json"]:
        print_json({"results": results, "total": len(resources), "interrupted": interrupted})
    else:
        table = Table(title="Apply Results")
        table.add_column("Status", width=3)
        table.add_column("Resource", style="bold")
        table.add_column("Detail")

        for r in results:
            detail = r.get("detail", "")
            source = r.get("source")
            if r["status"] == "error":
                if source:
                    detail = f"{detail} [dim]({source})[/]"
                table.add_row("[red]✗[/]", r["resource"], f"[red]{detail}[/]")
            elif r["status"] == "created":
                table.add_row("[green]✓[/]", r["resource"], "[green]created[/]")
            else:
                table.add_row("[blue]↻[/]", r["resource"], "[blue]updated[/]")

        out.print(table)

        succeeded = sum(1 for r in results if r["status"] in ("created", "updated"))
        failed = sum(1 for r in results if r["status"] == "error")
        skipped = len(resources) - len(results)
        summary = (
            f"\n[bold]{len(resources)}[/] resources:"
            f" [green]{succeeded} succeeded[/],"
            f" [red]{failed} failed[/]"
        )
        if skipped:
            summary += f", [yellow]{skipped} skipped[/]"
        out.print(summary)

    if interrupted:
        raise SystemExit(130)
    if any(r["status"] == "error" for r in results):
        raise SystemExit(1)


@cli.command(
    epilog="""\b
Examples:
  blackbeard get Agent my-agent
  blackbeard -n prod get Crew research-crew
  blackbeard get LLMConnection openai --json
"""
)
@click.argument("kind", type=click.Choice(sorted(ALL_KINDS), case_sensitive=False))
@click.argument("name")
@json_opt
@click.pass_context
def get(ctx: click.Context, kind: str, name: str, output_json: bool) -> None:
    """Get a single resource by kind and name.

    KIND is the resource type (e.g. Agent, Crew, Task).
    NAME is the resource name (e.g. my-agent).
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(name)
    server = ctx.obj["server"]

    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    url = f"{server}/api/v1/{plural}/{name}"
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            response = client.get(url, headers=headers, params={"namespace": namespace})
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if response.status_code != 200:
        handle_http_error(response)

    data = response.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    meta = data.get("metadata", {})
    header = Table(show_header=False, box=None, padding=(0, 2))
    header.add_column("Key", style="bold dim", width=12)
    header.add_column("Value")
    header.add_row("Kind", kind)
    header.add_row("Name", meta.get("name", name))
    header.add_row("Namespace", meta.get("namespace", namespace))
    header.add_row("Version", str(data.get("version", "—")))
    item_labels = meta.get("labels", {})
    if item_labels:
        header.add_row(
            "Labels",
            ", ".join(f"{k}={v}" for k, v in item_labels.items()),
        )
    out.print(header)
    out.print()
    spec_json = json.dumps(data.get("spec", data), indent=2, default=str)
    out.print(Syntax(spec_json, "json", theme="monokai"))


@cli.command(
    "list",
    epilog="""\b
Examples:
  blackbeard list Agent
  blackbeard -n prod list Crew
  blackbeard list Task --label team=backend
  blackbeard list Agent --json
""",
)
@click.argument("kind", type=click.Choice(sorted(ALL_KINDS), case_sensitive=False))
@click.option(
    "--label",
    "-l",
    "labels",
    multiple=True,
    metavar="KEY=VALUE",
    help="Filter by label (repeatable)",
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
def list_resources_cmd(
    ctx: click.Context, kind: str, labels: tuple[str, ...], limit: int, output_json: bool
) -> None:
    """List resources of a given kind.

    KIND is the resource type (e.g. Agent, Crew, Task).
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]

    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    params: dict[str, Any] = {"namespace": namespace, "limit": limit}
    if labels:
        label_parts = []
        for item in labels:
            if "=" not in item:
                console.print(
                    f"[red bold]Error:[/] Invalid --label: expected KEY=VALUE, got: {item!r}"
                )
                console.print("[dim]Example: --label team=backend[/]")
                raise SystemExit(2)
            key, _, _ = item.partition("=")
            if not key:
                console.print(
                    f"[red bold]Error:[/] Invalid --label: key cannot be empty in {item!r}"
                )
                raise SystemExit(2)
            label_parts.append(item)
        params["label_selector"] = ",".join(label_parts)

    url = f"{server}/api/v1/{plural}"
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            response = client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if response.status_code != 200:
        handle_http_error(response)

    data = response.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    items = data.get("items", [])
    if not items:
        msg = f"No {kind} resources found in namespace '{namespace}'"
        if labels:
            msg += f" with labels: {', '.join(labels)}"
        out.print(f"[dim]{msg}.[/]")
        return

    table = Table(title=f"{kind} Resources")
    table.add_column("Name", style="bold")
    table.add_column("Namespace", style="dim")
    table.add_column("Version", justify="right")
    table.add_column("Labels")

    for item in items:
        meta = item.get("metadata", {})
        item_labels = meta.get("labels", {})
        label_str = ", ".join(f"{k}={v}" for k, v in item_labels.items()) if item_labels else "—"
        table.add_row(
            meta.get("name", "—"),
            meta.get("namespace", "—"),
            str(item.get("version", "—")),
            label_str,
        )

    out.print(table)
    total = data.get("total", len(items))
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (increase --limit to see more)[/]")
    else:
        out.print(f"[dim]{len(items)} resource(s)[/]")


@cli.command(
    epilog="""\b
Examples:
  blackbeard delete Agent my-agent
  blackbeard -n prod delete Crew research-crew
  blackbeard delete Agent my-agent -y
  blackbeard delete Agent my-agent --json
"""
)
@click.argument("kind", type=click.Choice(sorted(ALL_KINDS), case_sensitive=False))
@click.argument("name")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON for scripting (skips confirmation prompt)",
)
@click.pass_context
def delete(ctx: click.Context, kind: str, name: str, yes: bool, output_json: bool) -> None:
    """Delete a resource by kind and name.

    KIND is the resource type (e.g. Agent, Crew, Task).
    NAME is the resource name (e.g. my-agent).
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(name)
    server = ctx.obj["server"]

    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    if (
        not yes
        and not ctx.obj["json"]
        and not click.confirm(
            f"Delete {kind}/{name} in namespace '{namespace}' on {server}?", default=False
        )
    ):
        console.print("[yellow]Aborted.[/]")
        return

    url = f"{server}/api/v1/{plural}/{name}"
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            response = client.delete(url, headers=headers, params={"namespace": namespace})
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if response.status_code not in (200, 204):
        handle_http_error(response)

    if ctx.obj["json"]:
        print_json({"deleted": f"{kind}/{name}", "namespace": namespace, "status": "deleted"})
        return

    out.print(f"[green]✓[/] Deleted [bold]{kind}/{name}[/] from namespace '{namespace}'")


@cli.command(
    epilog="""\b
Examples:
  blackbeard kickoff research-crew
  blackbeard kickoff research-crew --input topic="AI agents"
  blackbeard kickoff research-crew --input topic="AI agents" --input depth=3
  blackbeard kickoff research-crew --wait
  blackbeard kickoff research-crew -w -i 5
  blackbeard -s http://prod:8000 -n prod kickoff research-crew --json
"""
)
@click.argument("crew_name")
@click.option(
    "--input",
    "inputs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Input key=value pairs; values are parsed as JSON if valid (repeatable)",
)
@click.option(
    "--wait",
    "--watch",
    "-w",
    "watch",
    is_flag=True,
    default=False,
    help="Poll until execution completes, fails, or is cancelled (Ctrl-C to stop)",
)
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 60),
    metavar="SECONDS",
    help="Polling interval in seconds (used with --wait)",
)
@json_opt
@click.pass_context
def kickoff(
    ctx: click.Context,
    crew_name: str,
    inputs: tuple[str, ...],
    watch: bool,
    interval: int,
    output_json: bool,
) -> None:
    """Kick off a crew execution.

    CREW_NAME is the name of the crew to run, e.g. research-crew.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(crew_name)

    parsed_inputs: dict[str, Any] = {}
    for item in inputs:
        if "=" not in item:
            console.print(f"[red bold]Error:[/] Invalid --input: expected KEY=VALUE, got: {item!r}")
            console.print('[dim]Example: --input topic="AI agents"[/]')
            raise SystemExit(2)
        key, _, value = item.partition("=")
        if not key:
            console.print(f"[red bold]Error:[/] Invalid --input: key cannot be empty in {item!r}")
            raise SystemExit(2)
        try:
            parsed_inputs[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_inputs[key] = value

    server = ctx.obj["server"]

    namespace = ctx.obj["namespace"]
    prog = ctx.find_root().info_name or "blackbeard"

    warn_unused_interval(ctx, watch, interval, f"{prog} kickoff {crew_name}")

    url = f"{server}/api/v1/crews/{crew_name}/kickoff"
    headers = require_auth(ctx)
    body = {"inputs": parsed_inputs}

    with console.status("Submitting execution..."):
        try:
            with httpx.Client(timeout=ctx.obj["timeout"]) as client:
                response = client.post(
                    url,
                    json=body,
                    headers=headers,
                    params={"namespace": namespace},
                )
        except httpx.RequestError as exc:
            handle_request_error(server, exc)

    if response.status_code not in (200, 201, 202):
        handle_http_error(response)

    data = response.json()
    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")
    is_json = ctx.obj["json"]

    if is_json and not watch:
        print_json(data)
        return

    if not is_json:
        out.print(
            Panel.fit(
                f"[bold]Crew:[/] {crew_name}\n"
                f"[bold]Namespace:[/] {namespace}\n"
                f"[bold]Execution ID:[/] {execution_id}\n"
                f"[bold]Status:[/] {status_val}",
                title="[green]Execution Submitted[/]",
                border_style="green",
            )
        )

    if watch:
        ctx.invoke(
            status,
            execution_id=execution_id,
            watch=True,
            interval=interval,
            output_json=is_json,
        )
    else:
        console.print(f"\nTrack with: [bold]{prog} status {execution_id} -w[/]")


@cli.command(
    epilog="""\b
Examples:
  blackbeard train research-crew --input topic="AI agents" --iterations 3
  blackbeard train research-crew -w --filename my-training.pkl
  blackbeard train research-crew --json
"""
)
@click.argument("crew_name")
@click.option(
    "--input",
    "inputs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Input key=value pairs; values are parsed as JSON if valid (repeatable)",
)
@click.option(
    "--iterations",
    default=3,
    show_default=True,
    type=click.IntRange(1, 100),
    metavar="N",
    help="Number of training iterations",
)
@click.option(
    "--filename",
    default="training_data.pkl",
    show_default=True,
    metavar="FILE",
    help="Filename for training data output (must end with .pkl)",
)
@click.option(
    "--wait",
    "--watch",
    "-w",
    "watch",
    is_flag=True,
    default=False,
    help="Poll until execution completes, fails, or is cancelled (Ctrl-C to stop)",
)
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 60),
    metavar="SECONDS",
    help="Polling interval in seconds (used with --wait)",
)
@json_opt
@click.pass_context
def train(
    ctx: click.Context,
    crew_name: str,
    inputs: tuple[str, ...],
    iterations: int,
    filename: str,
    watch: bool,
    interval: int,
    output_json: bool,
) -> None:
    """Train a crew with iterative learning.

    CREW_NAME is the name of the crew to train, e.g. research-crew.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(crew_name)

    parsed_inputs: dict[str, Any] = {}
    for item in inputs:
        if "=" not in item:
            console.print(f"[red bold]Error:[/] Invalid --input: expected KEY=VALUE, got: {item!r}")
            console.print('[dim]Example: --input topic="AI agents"[/]')
            raise SystemExit(2)
        key, _, value = item.partition("=")
        if not key:
            console.print(f"[red bold]Error:[/] Invalid --input: key cannot be empty in {item!r}")
            raise SystemExit(2)
        try:
            parsed_inputs[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_inputs[key] = value

    server = ctx.obj["server"]
    namespace = ctx.obj["namespace"]
    prog = ctx.find_root().info_name or "blackbeard"

    warn_unused_interval(ctx, watch, interval, f"{prog} train {crew_name}")

    url = f"{server}/api/v1/crews/{crew_name}/train"
    headers = require_auth(ctx)
    body = {"inputs": parsed_inputs, "n_iterations": iterations, "filename": filename}

    with console.status("Submitting training execution..."):
        try:
            with httpx.Client(timeout=ctx.obj["timeout"]) as client:
                response = client.post(
                    url,
                    json=body,
                    headers=headers,
                    params={"namespace": namespace},
                )
        except httpx.RequestError as exc:
            handle_request_error(server, exc)

    if response.status_code not in (200, 201, 202):
        handle_http_error(response)

    data = response.json()
    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")
    is_json = ctx.obj["json"]

    if is_json and not watch:
        print_json(data)
        return

    if not is_json:
        out.print(
            Panel.fit(
                f"[bold]Crew:[/] {crew_name}\n"
                f"[bold]Namespace:[/] {namespace}\n"
                f"[bold]Mode:[/] train\n"
                f"[bold]Iterations:[/] {iterations}\n"
                f"[bold]Filename:[/] {filename}\n"
                f"[bold]Execution ID:[/] {execution_id}\n"
                f"[bold]Status:[/] {status_val}",
                title="[green]Training Submitted[/]",
                border_style="green",
            )
        )

    if watch:
        ctx.invoke(
            status,
            execution_id=execution_id,
            watch=True,
            interval=interval,
            output_json=is_json,
        )
    else:
        console.print(f"\nTrack with: [bold]{prog} status {execution_id} -w[/]")


@cli.command(
    "test-crew",
    epilog="""\b
Examples:
  blackbeard test-crew research-crew --input topic="AI agents" --iterations 3
  blackbeard test-crew research-crew -w
  blackbeard test-crew research-crew --json
""",
)
@click.argument("crew_name")
@click.option(
    "--input",
    "inputs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Input key=value pairs; values are parsed as JSON if valid (repeatable)",
)
@click.option(
    "--iterations",
    default=3,
    show_default=True,
    type=click.IntRange(1, 100),
    metavar="N",
    help="Number of test iterations",
)
@click.option(
    "--wait",
    "--watch",
    "-w",
    "watch",
    is_flag=True,
    default=False,
    help="Poll until execution completes, fails, or is cancelled (Ctrl-C to stop)",
)
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 60),
    metavar="SECONDS",
    help="Polling interval in seconds (used with --wait)",
)
@json_opt
@click.pass_context
def test_crew_cmd(
    ctx: click.Context,
    crew_name: str,
    inputs: tuple[str, ...],
    iterations: int,
    watch: bool,
    interval: int,
    output_json: bool,
) -> None:
    """Test a crew and collect performance metrics.

    CREW_NAME is the name of the crew to test, e.g. research-crew.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    validate_name(crew_name)

    parsed_inputs: dict[str, Any] = {}
    for item in inputs:
        if "=" not in item:
            console.print(f"[red bold]Error:[/] Invalid --input: expected KEY=VALUE, got: {item!r}")
            console.print('[dim]Example: --input topic="AI agents"[/]')
            raise SystemExit(2)
        key, _, value = item.partition("=")
        if not key:
            console.print(f"[red bold]Error:[/] Invalid --input: key cannot be empty in {item!r}")
            raise SystemExit(2)
        try:
            parsed_inputs[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_inputs[key] = value

    server = ctx.obj["server"]
    namespace = ctx.obj["namespace"]
    prog = ctx.find_root().info_name or "blackbeard"

    warn_unused_interval(ctx, watch, interval, f"{prog} test-crew {crew_name}")

    url = f"{server}/api/v1/crews/{crew_name}/test"
    headers = require_auth(ctx)
    body = {"inputs": parsed_inputs, "n_iterations": iterations}

    with console.status("Submitting test execution..."):
        try:
            with httpx.Client(timeout=ctx.obj["timeout"]) as client:
                response = client.post(
                    url,
                    json=body,
                    headers=headers,
                    params={"namespace": namespace},
                )
        except httpx.RequestError as exc:
            handle_request_error(server, exc)

    if response.status_code not in (200, 201, 202):
        handle_http_error(response)

    data = response.json()
    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")
    is_json = ctx.obj["json"]

    if is_json and not watch:
        print_json(data)
        return

    if not is_json:
        out.print(
            Panel.fit(
                f"[bold]Crew:[/] {crew_name}\n"
                f"[bold]Namespace:[/] {namespace}\n"
                f"[bold]Mode:[/] test\n"
                f"[bold]Iterations:[/] {iterations}\n"
                f"[bold]Execution ID:[/] {execution_id}\n"
                f"[bold]Status:[/] {status_val}",
                title="[green]Test Submitted[/]",
                border_style="green",
            )
        )

    if watch:
        ctx.invoke(
            status,
            execution_id=execution_id,
            watch=True,
            interval=interval,
            output_json=is_json,
        )
    else:
        console.print(f"\nTrack with: [bold]{prog} status {execution_id} -w[/]")


@cli.command(
    epilog="""\b
Examples:
  blackbeard status abc-123
  blackbeard status abc-123 --wait
  blackbeard status abc-123 -w -i 5
  blackbeard status abc-123 --json
  blackbeard status abc-123 --json --wait  # one JSON object per poll (JSONL)
"""
)
@click.argument("execution_id")
@click.option(
    "--wait",
    "--watch",
    "-w",
    "watch",
    is_flag=True,
    default=False,
    help="Poll until execution completes, fails, or is cancelled (Ctrl-C to stop)",
)
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 60),
    metavar="SECONDS",
    help="Polling interval in seconds (used with --wait)",
)
@json_opt
@click.pass_context
def status(
    ctx: click.Context, execution_id: str, watch: bool, interval: int, output_json: bool
) -> None:
    """Show execution status and details.

    EXECUTION_ID is the UUID returned by the kickoff command.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]

    is_json = ctx.obj["json"]

    prog = ctx.find_root().info_name or "blackbeard"
    warn_unused_interval(ctx, watch, interval, f"{prog} status {execution_id}")

    terminal_states = TERMINAL_STATUSES
    url = f"{server}/api/v1/executions/{execution_id}"
    headers = require_auth(ctx)

    def _status_color(s: str) -> str:
        return STATUS_COLORS.get(s, "dim")

    with httpx.Client(timeout=ctx.obj["timeout"]) as client:

        def fetch() -> dict[str, Any]:
            try:
                response = client.get(url, headers=headers)
            except httpx.RequestError as exc:
                handle_request_error(server, exc)

            if response.status_code != 200:
                handle_http_error(response)

            return cast("dict[str, Any]", response.json())

        def render(data: dict[str, Any]) -> None:
            status_val = data.get("status", "unknown")
            color = _status_color(status_val)

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
            if cost and isinstance(cost, (int, float)) and cost > 0:
                table.add_row("Cost", f"${cost:.4f}")

            started = data.get("started_at")
            if started:
                table.add_row("Started", str(started))

            completed = data.get("completed_at")
            if completed:
                table.add_row("Completed", str(completed))

            out.print(
                Panel(
                    table,
                    title=f"Execution [{color}]{status_val}[/]",
                    border_style=color,
                )
            )

            # Error
            error = data.get("error")
            if error:
                out.print(Panel(f"[red]{error}[/]", title="[red]Error[/]", border_style="red"))

            # Outputs
            outputs = data.get("outputs")
            if outputs:
                out.print(
                    Panel(
                        Syntax(json.dumps(outputs, indent=2, default=str), "json", theme="monokai"),
                        title="Outputs",
                        border_style="green",
                    )
                )

            # Tasks
            tasks = data.get("tasks", [])
            if tasks:
                task_table = Table(title="Tasks")
                task_table.add_column("#", width=3)
                task_table.add_column("Task", style="bold")
                task_table.add_column("Agent")
                task_table.add_column("Status")
                task_table.add_column("Tokens", justify="right")

                for t in tasks:
                    t_status = t.get("status", "—")
                    t_color = _status_color(t_status)
                    t_tokens = t.get("tokens_used")
                    task_table.add_row(
                        str(t.get("order", "—")),
                        t.get("task_name", "—"),
                        t.get("agent_name") or "—",
                        f"[{t_color}]{t_status}[/]",
                        f"{t_tokens:,}" if t_tokens else "—",
                    )

                out.print(task_table)

        if is_json and not watch:
            data = fetch()
            print_json(data)
            if data.get("status") in ("failed", "cancelled"):
                raise SystemExit(1)
            return

        if not watch:
            data = fetch()
            render(data)
            current = data.get("status", "")
            if current and current not in terminal_states:
                console.print(f"\n[dim]Still running. Watch: {prog} status {execution_id} -w[/]")
            elif current in ("failed", "cancelled"):
                raise SystemExit(1)
            return

        console.print(
            f"[dim]Watching execution {execution_id}"
            f" (Ctrl-C to stop, polling every {interval}s)...[/]\n"
        )
        current_status = ""
        try:
            first = True
            while True:
                data = fetch()

                if is_json:
                    print_json(data, compact=True)
                else:
                    if not first:
                        console.print("\n[dim]─── refreshed ───[/]\n")
                    render(data)
                    first = False

                current_status = data.get("status", "")
                if current_status in terminal_states:
                    break

                with console.status(f"[dim]Polling in {interval}s…[/]"):
                    time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped watching.[/]")
            raise SystemExit(130) from None

        if current_status in ("failed", "cancelled"):
            raise SystemExit(1)


@cli.command(
    epilog="""\b
Examples:
  blackbeard pull https://github.com/org/crew-repo.git
  blackbeard pull ./local-crew-dir
  blackbeard pull https://github.com/org/crew-repo.git -n prod
""",
)
@click.argument("source")
@json_opt
@click.pass_context
def pull(ctx: click.Context, source: str, output_json: bool) -> None:
    """Import resources from a git URL or local directory.

    SOURCE is a git HTTPS URL or local directory path containing YAML resource files.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{server}/api/v1/marketplace/import",
                json={"url": source},
                headers=headers,
            )
    except httpx.RequestError as exc:
        handle_request_error(server, exc)

    if resp.status_code not in (200, 201):
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    imported = data.get("imported", 0)
    errors = data.get("errors", 0)
    resources = data.get("resources", [])

    if imported:
        out.print(f"[green]Imported {imported} resource(s)[/]")
        for r in resources:
            out.print(f"  [green]✓[/] {r}")
    if errors:
        out.print(f"[red]{errors} error(s)[/]")
    if not imported and not errors:
        out.print("[dim]No resources found.[/]")


# ── Register subcommands from CLI modules ────────────────────────────────────

from blackbeard_cli.auth_cmds import login, logout, register, whoami  # noqa: E402
from blackbeard_cli.exec import cancel, events, executions_list  # noqa: E402
from blackbeard_cli.export_cmd import export_cmd  # noqa: E402
from blackbeard_cli.rbac import role, rolebinding  # noqa: E402
from blackbeard_cli.users import group, user  # noqa: E402

cli.add_command(login)
cli.add_command(logout)
cli.add_command(whoami)
cli.add_command(register)
cli.add_command(executions_list)
cli.add_command(events)
cli.add_command(cancel)
cli.add_command(export_cmd)
cli.add_command(user)
cli.add_command(group)
cli.add_command(role)
cli.add_command(rolebinding)


if __name__ == "__main__":
    cli()
