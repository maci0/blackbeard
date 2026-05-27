"""CLI execution commands — list, events, cancel."""

from __future__ import annotations

import time
from typing import Any

import click
import httpx
from rich.markup import escape
from rich.table import Table

from blackbeard_cli.helpers import (
    STATUS_COLORS,
    TERMINAL_STATUSES,
    HelpCommand,
    console,
    handle_http_error,
    handle_request_error,
    json_opt,
    out,
    print_json,
    require_auth,
    warn_unused_interval,
)


@click.command(
    "executions",
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard executions
  blackbeard executions --crew research-crew
  blackbeard executions --status running
  blackbeard executions --crew research-crew --status failed
  blackbeard executions --json
""",
)
@click.option("--crew", "-c", default=None, metavar="NAME", help="Filter by crew name")
@click.option(
    "--status",
    "status_filter",
    default=None,
    type=click.Choice(
        ["queued", "running", "completed", "failed", "cancelled"],
        case_sensitive=False,
    ),
    help="Filter by status",
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
def executions_list(
    ctx: click.Context,
    crew: str | None,
    status_filter: str | None,
    limit: int,
    output_json: bool = False,
) -> None:
    """List executions with optional crew and status filters."""
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
        msg = "No executions found"
        filters = []
        if crew:
            filters.append(f"crew={crew}")
        if status_filter:
            filters.append(f"status={status_filter}")
        if filters:
            msg += f" matching {', '.join(filters)}"
        out.print(f"[dim]{msg}.[/]")
        return

    table = Table(title="Executions")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Crew", style="bold")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")

    for ex in items:
        ex_id = str(ex.get("id", "—"))
        status_val = ex.get("status", "—")
        color = STATUS_COLORS.get(status_val, "dim")
        tokens = ex.get("total_tokens")
        cost = ex.get("cost_usd")
        try:
            cost_str = f"${float(cost):.4f}" if cost else "—"
        except (TypeError, ValueError):
            cost_str = "—"
        table.add_row(
            ex_id,
            ex.get("crew_name", "—"),
            f"[{color}]{status_val}[/]",
            str(ex.get("created_at", "—"))[:19],
            f"{tokens:,}" if tokens else "—",
            cost_str,
        )

    out.print(table)
    total = data.get("total", len(items))
    if total > len(items):
        out.print(f"[dim]Showing {len(items)} of {total} (increase --limit to see more)[/]")
    else:
        out.print(f"[dim]{len(items)} execution(s)[/]")


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard events abc-123
  blackbeard events abc-123 --follow
  blackbeard events abc-123 -f -i 5
  blackbeard events abc-123 --json
  blackbeard events abc-123 --follow --json   # JSONL stream
""",
)
@click.argument("execution_id")
@click.option("--follow", "-f", is_flag=True, default=False, help="Follow events in real-time")
@click.option(
    "--interval",
    "-i",
    default=2,
    show_default=True,
    type=click.IntRange(1, 60),
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
    """Show execution events.

    EXECUTION_ID is the UUID returned by the kickoff command.
    """
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
    event_count = 0
    terminal_status = ""

    if follow and not is_json:
        console.print(
            f"[dim]Following events for {execution_id}"
            f" (Ctrl-C to stop, polling every {interval}s)...[/]\n"
        )

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
                    event_count += 1
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
                        terminal_status = exec_resp.json().get("status", "")
                        if terminal_status in TERMINAL_STATUSES:
                            if not is_json:
                                color = STATUS_COLORS.get(terminal_status, "dim")
                                out.print(f"\n[{color} bold]Execution {terminal_status}[/]")
                            break

                    time.sleep(interval)

    except KeyboardInterrupt:
        if not is_json:
            console.print(f"\n[dim]Stopped following ({event_count} event(s)).[/]")
        raise SystemExit(130) from None

    if not is_json:
        if event_count:
            out.print(f"[dim]{event_count} event(s)[/]")
        elif not follow:
            out.print("[dim]No events found.[/]")

    if terminal_status in ("failed", "cancelled"):
        raise SystemExit(1)


def _event_color(event_type: str) -> str:
    if "error" in event_type or "failed" in event_type:
        return "red"
    if "completed" in event_type or "finished" in event_type:
        return "green"
    if "started" in event_type:
        return "blue"
    return "dim"


def _event_summary(event_type: str, data: dict[str, Any]) -> str:
    parts = []
    if "task_name" in data:
        parts.append(f"task={escape(str(data['task_name']))}")
    if "agent_name" in data:
        parts.append(f"agent={escape(str(data['agent_name']))}")
    if "tool_name" in data:
        parts.append(f"tool={escape(str(data['tool_name']))}")
    if "status" in data:
        parts.append(f"status={escape(str(data['status']))}")
    if "crew_name" in data:
        parts.append(f"crew={escape(str(data['crew_name']))}")
    if "error" in data:
        err = str(data["error"])[:120]
        parts.append(f"error={escape(err)}")
    if "message" in data:
        msg = str(data["message"])[:120]
        parts.append(f"msg={escape(msg)}")
    return " ".join(parts) if parts else ""


@click.command(
    cls=HelpCommand,
    epilog="""\b
Examples:
  blackbeard cancel abc-123
  blackbeard cancel abc-123 -y
  blackbeard cancel abc-123 --json
""",
)
@click.argument("execution_id")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@json_opt
@click.pass_context
def cancel(ctx: click.Context, execution_id: str, yes: bool, output_json: bool = False) -> None:
    """Cancel a running execution.

    EXECUTION_ID is the UUID returned by the kickoff command.
    """
    ctx.obj["json"] = ctx.obj.get("json", False) or output_json
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    if (
        not yes
        and not ctx.obj["json"]
        and not click.confirm(f"Cancel execution {execution_id} on {server}?", default=False)
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
        handle_http_error(resp)

    data = resp.json()

    if ctx.obj["json"]:
        print_json(data)
        return

    out.print(f"[green]✓[/] Cancelled execution [bold]{escape(execution_id)}[/]")
