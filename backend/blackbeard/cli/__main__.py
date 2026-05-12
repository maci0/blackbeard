"""Blackbeard CLI entry point — Rich-powered output."""

import json
import sys
import time
from graphlib import TopologicalSorter
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import httpx
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from blackbeard.resources.validator import validate_resource
from blackbeard.resources.refs import build_adjacency, detect_cycles
from blackbeard.kinds import KIND_TO_PLURAL

# Rich consoles — stderr for errors/progress, stdout for data
console = Console(stderr=True)
out = Console()


def _require_api_key(ctx: click.Context) -> str:
    """Get API key from context, raising if not set."""
    key = ctx.obj.get("api_key")
    if not key:
        console.print("[red bold]Error:[/] API key required. Set BLACKBEARD_API_KEY or pass --api-key.")
        raise SystemExit(1)
    return key


def _output_json(data: object) -> None:
    """Print data as formatted JSON to stdout."""
    out.print_json(json.dumps(data, default=str))


def load_yaml_resources(path: Path) -> list[dict]:
    """Load all YAML resource files from a file or directory."""
    files: list[Path] = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.rglob("*.yaml")) + sorted(path.rglob("*.yml"))
    else:
        console.print(f"[red]Path not found:[/] {path}")
        raise SystemExit(1)

    resources: list[dict] = []
    for f in files:
        with open(f) as fh:
            for doc in yaml.safe_load_all(fh):
                if doc and isinstance(doc, dict) and "kind" in doc:
                    doc["_source_file"] = str(f)
                    resources.append(doc)
    return resources


def validate_resources(resources: list[dict]) -> tuple[list[tuple[dict, list]], list[list[str]]]:
    """Validate resources and check for cycles."""
    per_errors = []
    for res in resources:
        kind = res.get("kind", "")
        spec = res.get("spec", {})
        errors = validate_resource(kind, spec)
        if errors:
            per_errors.append((res, errors))

    adjacency = build_adjacency(resources)
    cycles = detect_cycles(adjacency)
    return per_errors, cycles


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version=pkg_version("blackbeard"))
@click.option("--server", default="http://localhost:8000", envvar="BLACKBEARD_SERVER",
              show_default=True, help="Blackbeard API server URL (env: BLACKBEARD_SERVER)")
@click.option("--api-key", envvar="BLACKBEARD_API_KEY", required=False,
              help="API key (env: BLACKBEARD_API_KEY)")
@click.option("--namespace", "-n", default="default", envvar="BLACKBEARD_NAMESPACE",
              show_default=True, help="Resource namespace (env: BLACKBEARD_NAMESPACE)")
@click.option("--json", "output_json", is_flag=True, default=False,
              help="Output results as JSON (for scripting)")
@click.pass_context
def cli(ctx: click.Context, server: str, api_key: str | None, namespace: str, output_json: bool) -> None:
    """Blackbeard — Agent Management Platform CLI."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    ctx.obj["api_key"] = api_key
    ctx.obj["namespace"] = namespace
    ctx.obj["json"] = output_json


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command()
@click.option("-f", "--file", "path", required=True, type=click.Path(exists=True),
              help="File or directory of YAML resources")
@click.pass_context
def validate(ctx: click.Context, path: str) -> None:
    """Validate YAML resource files."""
    resources = load_yaml_resources(Path(path))

    if not resources:
        console.print("[yellow]No resource files found.[/]")
        sys.exit(1)

    per_errors, cycles = validate_resources(resources)
    all_valid = not per_errors and not cycles

    if ctx.obj.get("json"):
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
        _output_json(result)
        sys.exit(0 if all_valid else 1)

    # Rich table output
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

    console.print(table)

    if cycles:
        console.print(Panel(
            "\n".join(f"[red]•[/] {' → '.join(c)}" for c in cycles),
            title="[red]Dependency Cycles[/]",
            border_style="red",
        ))

    valid_count = len(resources) - len(per_errors)
    summary = f"[bold]{len(resources)}[/] resources: [green]{valid_count} valid[/]"
    if per_errors:
        summary += f", [red]{len(per_errors)} errors[/]"
    console.print(f"\n{summary}")

    sys.exit(0 if all_valid else 1)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

@cli.command()
@click.option("-f", "--file", "path", required=True, type=click.Path(exists=True),
              help="File or directory of YAML resources")
@click.option("--dry-run", is_flag=True, default=False, help="Validate without applying")
@click.pass_context
def apply(ctx: click.Context, path: str, dry_run: bool) -> None:
    """Apply YAML resource files to the server."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)

    resources = load_yaml_resources(Path(path))

    if not resources:
        console.print("[yellow]No resource files found.[/]")
        sys.exit(1)

    # Local validation first
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
        sys.exit(1)

    if dry_run:
        if ctx.obj.get("json"):
            _output_json({"dry_run": True, "resources": [
                {"kind": r.get("kind"), "name": r.get("metadata", {}).get("name")}
                for r in resources
            ]})
        else:
            console.print(Panel("[cyan]Dry run — no changes applied[/]", border_style="cyan"))
            for res in resources:
                kind = res.get("kind", "")
                name = res.get("metadata", {}).get("name", "?")
                console.print(f"  [cyan]→[/] {kind}/{name}: would apply")
        sys.exit(0)

    # Topologically sort resources by dependency order
    adjacency = build_adjacency(resources)
    try:
        order = list(TopologicalSorter(adjacency).static_order())
        resources_by_key = {f"{r['kind']}/{r['metadata']['name']}": r for r in resources}
        sorted_resources = [resources_by_key[k] for k in order if k in resources_by_key]
        sorted_keys = set(k for k in order if k in resources_by_key)
        for r in resources:
            key = f"{r['kind']}/{r['metadata']['name']}"
            if key not in sorted_keys:
                sorted_resources.append(r)
        resources = sorted_resources
    except (KeyError, ValueError) as exc:
        console.print(f"[yellow]⚠ Could not sort by dependencies ({exc}), applying in file order.[/]")

    # Apply resources with progress
    headers = {"X-API-Key": api_key}
    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Applying resources...", total=len(resources))

        with httpx.Client(timeout=30.0) as client:
            for res in resources:
                kind = res.get("kind", "")
                name = res.get("metadata", {}).get("name", "?")
                label = f"{kind}/{name}"
                progress.update(task, description=f"Applying {label}...")

                plural = KIND_TO_PLURAL.get(kind)
                if not plural:
                    results.append({"resource": label, "status": "error", "detail": f"Unknown kind '{kind}'"})
                    progress.advance(task)
                    continue

                body = {k: v for k, v in res.items() if k != "_source_file"}
                url = f"{server.rstrip('/')}/api/v1/{plural}"

                try:
                    response = client.post(url, json=body, headers=headers)
                    if response.status_code in (200, 201):
                        action = "created" if response.status_code == 201 else "updated"
                        results.append({"resource": label, "status": action})
                    else:
                        try:
                            detail = response.json().get("detail", response.text)
                        except Exception:
                            detail = response.text
                        results.append({"resource": label, "status": "error", "detail": f"HTTP {response.status_code}: {detail}"})
                except httpx.RequestError as exc:
                    results.append({"resource": label, "status": "error", "detail": f"Connection failed: {exc}"})

                progress.advance(task)

    # Output results
    if ctx.obj.get("json"):
        _output_json({"results": results})
    else:
        table = Table(title="Apply Results")
        table.add_column("Status", width=3)
        table.add_column("Resource", style="bold")
        table.add_column("Detail")

        for r in results:
            if r["status"] == "error":
                table.add_row("[red]✗[/]", r["resource"], f"[red]{r.get('detail', '')}[/]")
            elif r["status"] == "created":
                table.add_row("[green]✓[/]", r["resource"], "[green]created[/]")
            else:
                table.add_row("[blue]↻[/]", r["resource"], "[blue]updated[/]")

        console.print(table)

        created = sum(1 for r in results if r["status"] in ("created", "updated"))
        failed = sum(1 for r in results if r["status"] == "error")
        console.print(f"\n[bold]{len(results)}[/] resources: [green]{created} succeeded[/], [red]{failed} failed[/]")

    if any(r["status"] == "error" for r in results):
        sys.exit(1)


# ---------------------------------------------------------------------------
# kickoff
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("crew_name")
@click.option("--input", "inputs", multiple=True, metavar="KEY=VALUE",
              help="Input key=value pairs; values are parsed as JSON if valid (repeatable)")
@click.pass_context
def kickoff(ctx: click.Context, crew_name: str, inputs: tuple) -> None:
    """Kick off a crew execution.

    CREW_NAME is the crew name, e.g. research-crew
    """
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    namespace = ctx.obj["namespace"]

    # Parse key=value inputs
    parsed_inputs: dict = {}
    for item in inputs:
        if "=" not in item:
            console.print(f"[red]Error:[/] Input must be in key=value format, got: {item!r}")
            raise SystemExit(1)
        key, _, value = item.partition("=")
        try:
            parsed_inputs[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_inputs[key] = value

    url = f"{server.rstrip('/')}/api/v1/crews/{crew_name}/kickoff?namespace={namespace}"
    headers = {"X-API-Key": api_key}
    body = {"inputs": parsed_inputs}

    with console.status("Submitting execution..."):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            console.print(f"[red]Cannot reach server at {server}.[/] Check --server or BLACKBEARD_SERVER.\n{exc}")
            raise SystemExit(1) from exc

    if response.status_code not in (200, 201, 202):
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        console.print(f"[red]HTTP {response.status_code}:[/] {detail}")
        raise SystemExit(1)

    data = response.json()

    if ctx.obj.get("json"):
        _output_json(data)
        return

    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")

    console.print(Panel.fit(
        f"[bold]Execution ID:[/] {execution_id}\n[bold]Status:[/] {status_val}",
        title="[green]Execution Submitted[/]",
        border_style="green",
    ))
    console.print(f"\nTrack with: [bold]blackbeard status {execution_id} --watch[/]")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("execution_id")
@click.option("--watch", is_flag=True, default=False, help="Poll until execution reaches a terminal state")
@click.pass_context
def status(ctx: click.Context, execution_id: str, watch: bool) -> None:
    """Check execution status."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    is_json = ctx.obj.get("json")

    terminal_states = {"completed", "failed", "cancelled"}
    url = f"{server.rstrip('/')}/api/v1/executions/{execution_id}"
    headers = {"X-API-Key": api_key}

    def _status_color(s: str) -> str:
        return {"completed": "green", "failed": "red", "cancelled": "yellow"}.get(s, "blue")

    with httpx.Client(timeout=30.0) as client:
        def fetch() -> dict:
            try:
                response = client.get(url, headers=headers)
            except httpx.RequestError as exc:
                console.print(f"[red]Cannot reach server at {server}.[/] Check --server or BLACKBEARD_SERVER.\n{exc}")
                raise SystemExit(1) from exc

            if response.status_code != 200:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                console.print(f"[red]HTTP {response.status_code}:[/] {detail}")
                raise SystemExit(1)

            return response.json()

        def render(data: dict) -> None:
            status_val = data.get("status", "unknown")
            color = _status_color(status_val)

            # Build info table
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

            trace = data.get("langfuse_trace_url")
            if trace:
                table.add_row("Trace", f"[link={trace}]{trace}[/link]")

            console.print(Panel(table, title=f"Execution [{color}]{status_val}[/]", border_style=color))

            # Error
            error = data.get("error")
            if error:
                console.print(Panel(f"[red]{error}[/]", title="[red]Error[/]", border_style="red"))

            # Outputs
            outputs = data.get("outputs")
            if outputs:
                console.print(Panel(
                    Syntax(json.dumps(outputs, indent=2, default=str), "json", theme="monokai"),
                    title="Outputs",
                    border_style="green",
                ))

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
                    task_table.add_row(
                        str(t.get("order", "—")),
                        t.get("task_name", "—"),
                        t.get("agent_name") or "—",
                        f"[{t_color}]{t_status}[/]",
                        str(t.get("tokens_used", 0)),
                    )

                console.print(task_table)

        if is_json and not watch:
            _output_json(fetch())
            return

        if not watch:
            render(fetch())
            return

        # Watch mode with live updates
        console.print(f"[dim]Watching execution {execution_id} (Ctrl-C to stop)...[/]\n")
        while True:
            data = fetch()

            if is_json:
                _output_json(data)
            else:
                console.clear()
                console.print(f"[dim]Watching execution {execution_id} (Ctrl-C to stop)...[/]\n")
                render(data)

            current_status = data.get("status", "")
            if current_status in terminal_states:
                break

            time.sleep(2)


if __name__ == "__main__":
    cli()
