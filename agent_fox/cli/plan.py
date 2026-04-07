"""Plan CLI command: build and display the execution plan.

Thin CLI wrapper that delegates to ``graph.planner.build_plan()``
for the planning pipeline, then handles persistence and display.

Requirements: 02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4, 02-REQ-7.5
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from agent_fox.core.config import load_config
from agent_fox.core.errors import PlanError
from agent_fox.graph.persistence import save_plan
from agent_fox.graph.planner import build_plan, format_plan_summary
from agent_fox.spec.discovery import discover_specs


@click.command("plan")
@click.option("--fast", is_flag=True, help="Exclude optional tasks")
@click.option("--spec", "filter_spec", default=None, help="Plan a single spec")
@click.pass_context
def plan_cmd(
    ctx: click.Context,
    fast: bool,
    filter_spec: str | None,
) -> None:
    """Build an execution plan from specifications."""
    # 85-REQ-3.2: Refuse to run when daemon is active.
    from agent_fox.nightshift.pid import PidStatus, check_pid_file

    daemon_pid_path = Path.cwd() / ".agent-fox" / "daemon.pid"
    pid_status, _pid = check_pid_file(daemon_pid_path)
    if pid_status == PidStatus.ALIVE:
        click.echo(
            f"Error: night-shift daemon is running (PID {_pid}). Stop the daemon before running `plan`.",
            err=True,
        )
        sys.exit(1)

    # Determine project paths
    project_root = Path.cwd()
    specs_dir = project_root / ".specs"
    plan_path = project_root / ".agent-fox" / "plan.json"

    # Load config for archetypes
    config_path = project_root / ".agent-fox" / "config.toml"
    config = load_config(config_path if config_path.exists() else None)

    # Always rebuild the plan from .specs/ (63-REQ-1.1)
    json_mode = ctx.obj.get("json", False)
    from agent_fox.ui.progress import PlanSpinner

    spinner = PlanSpinner("Planning...")
    if not json_mode:
        spinner.start()
    try:
        graph = build_plan(specs_dir, filter_spec, fast, config)
    except PlanError as exc:
        spinner.stop()
        if json_mode:
            from agent_fox.cli.json_io import emit_error

            emit_error(str(exc))
            ctx.exit(1)
            return
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return
    finally:
        spinner.stop()

    # Persist the plan (02-REQ-6.1, 02-REQ-6.2, 63-REQ-1.2)
    save_plan(graph, plan_path)

    # Re-discover specs for summary display
    try:
        specs = discover_specs(specs_dir, filter_spec=filter_spec)
    except PlanError:
        specs = []

    # 23-REQ-3.4: JSON output for plan command
    if json_mode:
        from dataclasses import asdict

        from agent_fox.cli.json_io import emit

        emit(
            {
                "nodes": {nid: asdict(node) for nid, node in graph.nodes.items()},
                "edges": [asdict(e) for e in graph.edges],
                "order": graph.order,
                "metadata": asdict(graph.metadata),
            }
        )
        return

    click.echo(format_plan_summary(graph, specs))
