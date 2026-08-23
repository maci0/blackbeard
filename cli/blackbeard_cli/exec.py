"""CLI execution commands — list, events, cancel."""

from __future__ import annotations

import time
from typing import Any

import click
import httpx
from rich.markup import escape

from blackbeard_cli.helpers import (
    STATUS_COLORS,
    TERMINAL_STATUSES,
    HelpCommand,
    build_executions_table,
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
  blackbeard -n prod executions --status failed
  blackbeard executions --project staging --type train
  blackbeard executions --json
""",
)
@click.option("--crew", "-c", default=None, metavar="NAME", help="Filter by crew name")
@click.option(
    "--project",
    default=None,
    metavar="NAME",
    help="Filter by project (defaults to global -n/--project)",
)
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
    "--type",
    "exec_type",
    default=None,
    type=click.Choice(["kickoff", "train", "test", "flow"], case_sensitive=False),
    help="Filter by execution type",
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
    project: str | None,
    status_filter: str | None,
    exec_type: str | None,
    limit: int,
) -> None:
    """List executions with optional crew, project, status, and type filters."""
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    effective_project = project if project is not None else ctx.obj.get("project")

    params: dict[str, Any] = {"limit": limit}
    if crew:
        params["crew_name"] = crew
    if effective_project:
        params["project"] = effective_project
    if status_filter:
        params["status"] = status_filter
    if exec_type:
        params["execution_type"] = exec_type

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

    items = extract_items(data)
    if not items:
        msg = "No executions found"
        filters = []
        if crew:
            filters.append(f"crew={escape(crew)}")
        if effective_project:
            filters.append(f"project={escape(effective_project)}")
        if status_filter:
            filters.append(f"status={escape(status_filter)}")
        if exec_type:
            filters.append(f"type={escape(exec_type)}")
        if filters:
            msg += f" matching {', '.join(filters)}"
        out.print(f"[dim]{msg}.[/]")
        return

    out.print(build_executions_table(items, title="Executions"))
    total = extract_total(data, items)
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
@click.argument("execution_id", metavar="UUID")
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
) -> None:
    """Show execution events.

    UUID is the execution ID returned by the kickoff command.
    """
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
            f"[dim]Following events for {escape(execution_id)}"
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
                    # Keep paging until the server reports no more events.
                    if data.get("has_more", False):
                        continue
                    break

                has_more = data.get("has_more", False)
                if not has_more:
                    try:
                        exec_resp = client.get(
                            f"{server}/api/v1/executions/{execution_id}", headers=headers
                        )
                    except httpx.RequestError:
                        time.sleep(interval)
                        continue
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
@click.argument("execution_id", metavar="UUID")
@click.option("-y", "--yes", is_flag=True, default=False, help="Skip confirmation prompt")
@json_opt
@click.pass_context
def cancel(ctx: click.Context, execution_id: str, yes: bool) -> None:
    """Cancel a running execution.

    UUID is the execution ID returned by the kickoff command.
    """
    server = ctx.obj["server"]
    headers = require_auth(ctx)

    if not confirm_destructive(ctx, f"Cancel execution {execution_id} on {server}?", yes=yes):
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
