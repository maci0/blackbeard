"""CLI execution commands — list, events, cancel."""

from __future__ import annotations

import time
from typing import Any

import click
import httpx
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
    warn_unused_interval,
)


@click.command("executions")
@click.option("--crew", "-c", default=None, help="Filter by crew name")
@click.option(
    "--status",
    "status_filter",
    default=None,
    type=click.Choice(["queued", "running", "completed", "failed", "cancelled"]),
    help="Filter by status",
)
@click.option(
    "--limit",
    default=20,
    show_default=True,
    type=click.IntRange(1, 1000),
    metavar="N",
    help="Maximum number of results",
)
@json_opt
@click.pass_context
def executions_list(
    ctx: click.Context,
    crew: str | None,
    status_filter: str | None,
    limit: int,
    output_json: bool = False,
) -> None:
    """List all executions."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    params: dict[str, Any] = {"limit": limit}
    if crew:
        params["crew_name"] = crew
    if status_filter:
        params["status"] = status_filter

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.get(f"{server}/api/v1/executions", headers=headers, params=params)
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
        out.print("[dim]No executions found.[/]")
        return

    table = Table(title="Executions")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Crew", style="bold")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")

    for ex in items:
        ex_id = str(ex.get("id", "—"))[:8]
        status_val = ex.get("status", "—")
        color = STATUS_COLORS.get(status_val, "dim")
        tokens = ex.get("total_tokens")
        cost = ex.get("cost_usd")
        table.add_row(
            ex_id,
            ex.get("crew_name", "—"),
            f"[{color}]{status_val}[/]",
            str(ex.get("created_at", "—"))[:19],
            f"{tokens:,}" if tokens else "—",
            f"${float(cost):.4f}" if cost else "—",
        )

    out.print(table)
    total = data.get("total", len(items))
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (increase --limit)[/]")
    else:
        out.print(f"[dim]{len(items)} execution(s)[/]")


@click.command()
@click.argument("execution_id")
@click.option("--follow", "-f", is_flag=True, default=False, help="Follow events in real-time")
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 30),
    metavar="SECONDS",
    help="Polling interval in seconds (used with --follow)",
)
@json_opt
@click.pass_context
def events(
    ctx: click.Context,
    execution_id: str,
    follow: bool,
    interval: int,
    output_json: bool = False,
) -> None:
    """Show execution events."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)
    is_json = ctx.obj["json"]

    prog = ctx.find_root().info_name or "blackbeard"
    warn_unused_interval(
        ctx,
        follow,
        interval,
        f"{prog} events {execution_id}",
        watch_flag="--follow/-f",
        watch_short="-f",
    )

    url = f"{server}/api/v1/executions/{execution_id}/events"
    after = -1

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            while True:
                try:
                    resp = client.get(url, headers=headers, params={"after": after})
                except httpx.RequestError as exc:
                    handle_request_error(server, exc)

                if resp.status_code != 200:
                    handle_http_error(resp)

                data = resp.json()
                event_list = data.get("events", [])

                for ev in event_list:
                    seq = ev.get("sequence", 0)
                    if seq > after:
                        after = seq

                    if is_json:
                        print_json(ev, compact=True)
                    else:
                        ts = str(ev.get("timestamp", ""))[:23]
                        etype = ev.get("event_type", "unknown")
                        ev_data = ev.get("data", {})

                        color = _event_color(etype)
                        summary = _event_summary(etype, ev_data)
                        out.print(f"[dim]{ts}[/]  [{color}]{etype}[/]  {summary}")

                if not follow:
                    break

                has_more = data.get("has_more", False)
                if not has_more:
                    exec_resp = client.get(
                        f"{server}/api/v1/executions/{execution_id}", headers=headers
                    )
                    if exec_resp.status_code == 200:
                        status = exec_resp.json().get("status", "")
                        if status in ("completed", "failed", "cancelled"):
                            if not is_json:
                                color = STATUS_COLORS.get(status, "dim")
                                out.print(f"\n[{color} bold]Execution {status}[/]")
                            break

                    time.sleep(interval)

    except KeyboardInterrupt:
        if not is_json:
            console.print("\n[dim]Stopped following.[/]")
        raise SystemExit(130) from None


def _event_color(event_type: str) -> str:
    if "started" in event_type:
        return "blue"
    if "completed" in event_type or "finished" in event_type:
        return "green"
    if "error" in event_type or "failed" in event_type:
        return "red"
    return "dim"


def _event_summary(event_type: str, data: dict[str, Any]) -> str:
    parts = []
    if "task_name" in data:
        parts.append(f"task={data['task_name']}")
    if "agent_name" in data:
        parts.append(f"agent={data['agent_name']}")
    if "tool_name" in data:
        parts.append(f"tool={data['tool_name']}")
    if "status" in data:
        parts.append(f"status={data['status']}")
    if "crew_name" in data:
        parts.append(f"crew={data['crew_name']}")
    return " ".join(parts) if parts else ""


@click.command()
@click.argument("execution_id")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation")
@json_opt
@click.pass_context
def cancel(ctx: click.Context, execution_id: str, yes: bool, output_json: bool = False) -> None:
    """Cancel a running execution."""
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    if (
        not yes
        and not ctx.obj["json"]
        and not click.confirm(f"Cancel execution {execution_id[:8]}...?", default=False)
    ):
        console.print("[yellow]Aborted.[/]")
        return

    try:
        with httpx.Client(timeout=ctx.obj["timeout"]) as client:
            resp = client.patch(
                f"{server}/api/v1/executions/{execution_id}/cancel", headers=headers
            )
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

    out.print(f"[green]Cancelled[/] execution [bold]{execution_id[:8]}...[/]")
