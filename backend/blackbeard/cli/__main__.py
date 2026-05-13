"""Blackbeard CLI entry point — Rich-powered output."""

import json
import time
from graphlib import TopologicalSorter
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import NoReturn

import click
import httpx
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from blackbeard.kinds import ALL_KINDS, KIND_TO_PLURAL
from blackbeard.models.execution import TERMINAL_STATUSES
from blackbeard.resources.refs import build_adjacency, detect_cycles
from blackbeard.resources.validator import validate_resource

# Rich consoles — stderr for errors/progress, stdout for data
console = Console(stderr=True)
out = Console()

_STATUS_COLORS: dict[str, str] = {
    "completed": "green",
    "failed": "red",
    "cancelled": "yellow",
    "running": "blue",
    "queued": "cyan",
    "pending": "cyan",
}


def _require_api_key(ctx: click.Context) -> str:
    """Get API key from context, raising if not set."""
    key = ctx.obj.get("api_key")
    if not key:
        console.print(
            "[red bold]Error:[/] API key required."
            " Set BLACKBEARD_API_KEY or pass --api-key."
        )
        raise SystemExit(1)
    return key


def _output_json(data: object) -> None:
    out.print_json(json.dumps(data, default=str))


def _extract_detail(response: httpx.Response) -> str:
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text


def _handle_request_error(server: str, exc: httpx.RequestError) -> NoReturn:
    console.print(
        f"[red bold]Error:[/] Cannot reach server at [bold]{server}[/]\n"
        f"  {exc}\n\n"
        f"[dim]Suggestions:\n"
        f"  • Is the server running? Try: curl {server}/api/v1/health\n"
        f"  • Wrong URL? Set --server or BLACKBEARD_SERVER[/]"
    )
    raise SystemExit(1) from exc


def _handle_http_error(response: httpx.Response) -> NoReturn:
    detail = _extract_detail(response)
    console.print(f"[red bold]Error:[/] HTTP {response.status_code}: {detail}")
    if response.status_code == 401:
        console.print("[dim]Hint: Check your API key (--api-key or BLACKBEARD_API_KEY)[/]")
    elif response.status_code == 404:
        console.print("[dim]Hint: Verify the resource name and namespace (-n)[/]")
    raise SystemExit(1)


def load_yaml_resources(path: Path) -> list[dict]:
    """Load all YAML resource files from a file or directory."""
    files: list[Path] = []
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.rglob("*.yaml")) + sorted(path.rglob("*.yml"))
    else:
        console.print(f"[red bold]Error:[/] Path not found: [bold]{path}[/]")
        raise SystemExit(2)

    resources: list[dict] = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
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


def validate_resources(resources: list[dict]) -> tuple[list[tuple[dict, list]], list[list[str]]]:
    """Validate resources and check for cycles."""
    per_errors = []
    for res in resources:
        kind = res.get("kind", "")
        spec = res.get("spec", {})
        errors, _ = validate_resource(kind, spec)
        if errors:
            per_errors.append((res, errors))

    adjacency = build_adjacency(resources)
    cycles = detect_cycles(adjacency)
    return per_errors, cycles


@click.group()
@click.version_option(version=pkg_version("blackbeard"))
@click.option("--server", "-s", default="http://localhost:8000", envvar="BLACKBEARD_SERVER",
              show_default=True, help="Blackbeard API server URL (env: BLACKBEARD_SERVER)")
@click.option("--api-key", "-k", envvar="BLACKBEARD_API_KEY", required=False,
              help="API key (env: BLACKBEARD_API_KEY)")
@click.option("--namespace", "-n", default="default", envvar="BLACKBEARD_NAMESPACE",
              show_default=True, help="Resource namespace (env: BLACKBEARD_NAMESPACE)")
@click.option("--json", "output_json", is_flag=True, default=False,
              help="Output results as JSON (for scripting; skips interactive prompts)")
@click.pass_context
def cli(
    ctx: click.Context, server: str, api_key: str | None,
    namespace: str, output_json: bool,
) -> None:
    """Blackbeard — Agent Management Platform CLI."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    ctx.obj["api_key"] = api_key
    ctx.obj["namespace"] = namespace
    ctx.obj["json"] = output_json


@cli.command(epilog="""\b
Examples:
  blackbeard validate -f crew.yaml
  blackbeard validate -f examples/research-crew/
  blackbeard validate -f crew.yaml --json
""")
@click.option("-f", "--file", "path", required=True, type=click.Path(exists=True),
              help="File or directory of YAML resources")
@click.pass_context
def validate(ctx: click.Context, path: str) -> None:
    """Validate YAML resource files without applying them."""
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
        _output_json(result)
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
        out.print(Panel(
            "\n".join(f"[red]•[/] {' → '.join(c)}" for c in cycles),
            title="[red]Dependency Cycles[/]",
            border_style="red",
        ))

    valid_count = len(resources) - len(per_errors)
    summary = f"[bold]{len(resources)}[/] resources: [green]{valid_count} valid[/]"
    if per_errors:
        summary += f", [red]{len(per_errors)} errors[/]"
    out.print(f"\n{summary}")

    if not all_valid:
        raise SystemExit(1)


@cli.command(epilog="""\b
Examples:
  blackbeard apply -f crew.yaml
  blackbeard apply -f crew.yaml -y
  blackbeard apply -f examples/research-crew/ --dry-run
  blackbeard apply -f examples/research-crew/ --json
""")
@click.option("-f", "--file", "path", required=True, type=click.Path(exists=True),
              help="File or directory of YAML resources")
@click.option("--dry-run", is_flag=True, default=False,
              help="Validate and show what would be applied, without making changes")
@click.option("-y", "--yes", is_flag=True, default=False,
              help="Skip confirmation prompt")
@click.pass_context
def apply(ctx: click.Context, path: str, dry_run: bool, yes: bool) -> None:
    """Apply YAML resource files to the server (create or update)."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)

    resources = load_yaml_resources(Path(path))

    if not resources:
        console.print(f"[red bold]Error:[/] No resource files found in [bold]{path}[/]")
        raise SystemExit(2)

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
        raise SystemExit(1)

    if dry_run:
        if ctx.obj["json"]:
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
        return

    if not yes and not ctx.obj["json"]:
        console.print(
            f"\n[bold]{len(resources)}[/] resource(s) will be applied"
            f" to [bold]{server}[/]."
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
            f"[yellow]Warning:[/] Could not sort by dependencies ({exc}),"
            " applying in file order."
        )

    # Apply resources with progress
    headers = {"X-API-Key": api_key}
    results: list[dict] = []

    try:
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
                        valid = ", ".join(sorted(KIND_TO_PLURAL))
                        results.append({
                            "resource": label, "status": "error",
                            "detail": f"Unknown kind '{kind}'. Valid kinds: {valid}",
                        })
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
                            detail = _extract_detail(response)
                            results.append({
                                "resource": label, "status": "error",
                                "detail": f"HTTP {response.status_code}: {detail}",
                            })
                    except httpx.RequestError as exc:
                        results.append({
                            "resource": label, "status": "error",
                            "detail": f"Connection failed: {exc}",
                        })

                    progress.advance(task)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/]")

    # Output results
    if ctx.obj["json"]:
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

        out.print(table)

        succeeded = sum(1 for r in results if r["status"] in ("created", "updated"))
        failed = sum(1 for r in results if r["status"] == "error")
        out.print(
            f"\n[bold]{len(results)}[/] resources:"
            f" [green]{succeeded} succeeded[/],"
            f" [red]{failed} failed[/]"
        )

    if any(r["status"] == "error" for r in results):
        raise SystemExit(1)


@cli.command(epilog="""\b
Examples:
  blackbeard get Agent my-agent
  blackbeard get Crew research-crew -n prod
  blackbeard get LLMConnection openai --json
""")
@click.argument("kind", type=click.Choice(ALL_KINDS, case_sensitive=True))
@click.argument("name")
@click.pass_context
def get(ctx: click.Context, kind: str, name: str) -> None:
    """Get a single resource by kind and name."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    url = f"{server.rstrip('/')}/api/v1/{plural}/{name}"
    headers = {"X-API-Key": api_key}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params={"namespace": namespace})
    except httpx.RequestError as exc:
        _handle_request_error(server, exc)

    if response.status_code != 200:
        _handle_http_error(response)

    data = response.json()

    if ctx.obj["json"]:
        _output_json(data)
        return

    out.print(Syntax(json.dumps(data, indent=2, default=str), "json", theme="monokai"))


@cli.command("list", epilog="""\b
Examples:
  blackbeard list Agent
  blackbeard list Crew -n prod
  blackbeard list Task --label team=backend
  blackbeard list Agent --json
""")
@click.argument("kind", type=click.Choice(ALL_KINDS, case_sensitive=True))
@click.option("--label", "-l", "labels", multiple=True, metavar="KEY=VALUE",
              help="Filter by label (repeatable)")
@click.option("--limit", default=100, show_default=True, type=click.IntRange(1, 1000),
              help="Maximum number of results")
@click.pass_context
def list_resources_cmd(ctx: click.Context, kind: str, labels: tuple, limit: int) -> None:
    """List resources of a given kind."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    params: dict = {"namespace": namespace, "limit": limit}
    if labels:
        label_parts = []
        for item in labels:
            if "=" not in item:
                console.print(
                    f"[red bold]Error:[/] Invalid --label:"
                    f" expected KEY=VALUE, got: {item!r}"
                )
                raise SystemExit(2)
            label_parts.append(item)
        params["label_selector"] = ",".join(label_parts)

    url = f"{server.rstrip('/')}/api/v1/{plural}"
    headers = {"X-API-Key": api_key}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params=params)
    except httpx.RequestError as exc:
        _handle_request_error(server, exc)

    if response.status_code != 200:
        _handle_http_error(response)

    data = response.json()

    if ctx.obj["json"]:
        _output_json(data)
        return

    items = data.get("items", [])
    if not items:
        console.print(f"[dim]No {kind} resources found in namespace '{namespace}'.[/]")
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
            meta.get("name", "?"),
            meta.get("namespace", "?"),
            str(item.get("version", "?")),
            label_str,
        )

    out.print(table)
    total = data.get("total", len(items))
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (use --limit to see more)[/]")


@cli.command(epilog="""\b
Examples:
  blackbeard delete Agent my-agent
  blackbeard delete Crew research-crew -n prod
  blackbeard delete Agent my-agent -y
""")
@click.argument("kind", type=click.Choice(ALL_KINDS, case_sensitive=True))
@click.argument("name")
@click.option("-y", "--yes", is_flag=True, default=False,
              help="Skip confirmation prompt")
@click.pass_context
def delete(ctx: click.Context, kind: str, name: str, yes: bool) -> None:
    """Delete a resource by kind and name."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    namespace = ctx.obj["namespace"]
    plural = KIND_TO_PLURAL[kind]

    if (
        not yes
        and not ctx.obj["json"]
        and not click.confirm(f"Delete {kind}/{name} in namespace '{namespace}'?", default=False)
    ):
        console.print("[yellow]Aborted.[/]")
        return

    url = f"{server.rstrip('/')}/api/v1/{plural}/{name}"
    headers = {"X-API-Key": api_key}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(url, headers=headers, params={"namespace": namespace})
    except httpx.RequestError as exc:
        _handle_request_error(server, exc)

    if response.status_code not in (200, 204):
        _handle_http_error(response)

    if ctx.obj["json"]:
        _output_json({"deleted": f"{kind}/{name}", "namespace": namespace})
        return

    console.print(f"[green]✓[/] Deleted [bold]{kind}/{name}[/] from namespace '{namespace}'")


@cli.command(epilog="""\b
Examples:
  blackbeard kickoff research-crew
  blackbeard kickoff research-crew --input topic="AI agents"
  blackbeard kickoff research-crew --input topic="AI agents" --input depth=3
  blackbeard kickoff research-crew -s http://prod:8000 -n prod --json
""")
@click.argument("crew_name")
@click.option("--input", "inputs", multiple=True, metavar="KEY=VALUE",
              help="Input key=value pairs; values are parsed as JSON if valid (repeatable)")
@click.pass_context
def kickoff(ctx: click.Context, crew_name: str, inputs: tuple) -> None:
    """Kick off a crew execution.

    CREW_NAME is the name of the crew to run, e.g. research-crew.
    """
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    namespace = ctx.obj["namespace"]

    parsed_inputs: dict = {}
    for item in inputs:
        if "=" not in item:
            console.print(f"[red bold]Error:[/] Invalid --input: expected KEY=VALUE, got: {item!r}")
            console.print("[dim]Example: --input topic=\"AI agents\"[/]")
            raise SystemExit(2)
        key, _, value = item.partition("=")
        if not key:
            console.print(f"[red bold]Error:[/] Invalid --input: key cannot be empty in {item!r}")
            raise SystemExit(2)
        try:
            parsed_inputs[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed_inputs[key] = value

    url = f"{server.rstrip('/')}/api/v1/crews/{crew_name}/kickoff"
    headers = {"X-API-Key": api_key}
    body = {"inputs": parsed_inputs}

    with console.status("Submitting execution..."):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    url, json=body, headers=headers, params={"namespace": namespace},
                )
        except httpx.RequestError as exc:
            _handle_request_error(server, exc)

    if response.status_code not in (200, 201, 202):
        _handle_http_error(response)

    data = response.json()

    if ctx.obj["json"]:
        _output_json(data)
        return

    execution_id = data.get("id", "unknown")
    status_val = data.get("status", "unknown")

    out.print(Panel.fit(
        f"[bold]Execution ID:[/] {execution_id}\n[bold]Status:[/] {status_val}",
        title="[green]Execution Submitted[/]",
        border_style="green",
    ))
    console.print(f"\nTrack with: [bold]blackbeard status {execution_id} --watch[/]")


@cli.command(epilog="""\b
Examples:
  blackbeard status abc-123
  blackbeard status abc-123 -w
  blackbeard status abc-123 -w -i 5
  blackbeard status abc-123 --json
""")
@click.argument("execution_id")
@click.option("--watch", "-w", is_flag=True, default=False,
              help="Poll until execution completes, fails, or is cancelled (Ctrl-C to stop)")
@click.option("--interval", "-i", default=2, show_default=True, type=click.IntRange(1, 60),
              help="Polling interval in seconds (used with --watch)")
@click.pass_context
def status(ctx: click.Context, execution_id: str, watch: bool, interval: int) -> None:
    """Show execution status and details."""
    server = ctx.obj["server"]
    api_key = _require_api_key(ctx)
    is_json = ctx.obj["json"]

    interval_from_cli = (
        ctx.get_parameter_source("interval") == click.core.ParameterSource.COMMANDLINE
    )
    if not watch and interval_from_cli and not is_json:
        console.print("[yellow]Warning:[/] --interval/-i has no effect without --watch (-w)."
                      " Add -w to enable polling.")

    terminal_states = {s.value for s in TERMINAL_STATUSES}
    url = f"{server.rstrip('/')}/api/v1/executions/{execution_id}"
    headers = {"X-API-Key": api_key}

    def _status_color(s: str) -> str:
        return _STATUS_COLORS.get(s, "dim")

    with httpx.Client(timeout=30.0) as client:
        def fetch() -> dict:
            try:
                response = client.get(url, headers=headers)
            except httpx.RequestError as exc:
                _handle_request_error(server, exc)

            if response.status_code != 200:
                _handle_http_error(response)

            return response.json()

        def render(data: dict) -> None:
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

            trace = data.get("langfuse_trace_url")
            if trace:
                table.add_row("Trace", f"[link={trace}]{trace}[/link]")

            out.print(Panel(
                table,
                title=f"Execution [{color}]{status_val}[/]",
                border_style=color,
            ))

            # Error
            error = data.get("error")
            if error:
                out.print(Panel(f"[red]{error}[/]", title="[red]Error[/]", border_style="red"))

            # Outputs
            outputs = data.get("outputs")
            if outputs:
                out.print(Panel(
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

                out.print(task_table)

        if is_json and not watch:
            _output_json(fetch())
            return

        if not watch:
            render(fetch())
            return

        console.print(f"[dim]Watching execution {execution_id} (Ctrl-C to stop)...[/]\n")
        try:
            first = True
            while True:
                data = fetch()

                if is_json:
                    _output_json(data)
                else:
                    if not first:
                        console.print("\n[dim]─── refreshed ───[/]\n")
                    render(data)
                    first = False

                current_status = data.get("status", "")
                if current_status in terminal_states:
                    break

                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped watching.[/]")


if __name__ == "__main__":
    cli()
