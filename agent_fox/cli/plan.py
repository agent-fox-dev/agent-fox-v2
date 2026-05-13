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


def _node_to_dict(node: object) -> dict:
    """Serialize a Node (or duck-typed object) to a JSON-friendly dict."""
    return {
        "id": node.id,
        "spec_name": node.spec_name,
        "group_number": node.group_number,
        "title": node.title,
        "optional": node.optional,
        "status": str(node.status),
        "archetype": node.archetype,
    }


def _edge_to_dict(edge: object) -> dict:
    """Serialize an Edge (or duck-typed object) to a JSON-friendly dict."""
    return {"source": edge.source, "target": edge.target, "kind": edge.kind}


def _metadata_to_dict(meta: object) -> dict:
    """Serialize PlanMetadata (or duck-typed object) to a JSON-friendly dict."""
    return {
        "created_at": meta.created_at,
        "fast_mode": meta.fast_mode,
        "filtered_spec": meta.filtered_spec,
        "version": meta.version,
    }


@click.command("plan")
@click.option("--dry-run", is_flag=True, help="Show plan analysis without persisting to database")
@click.option("--fast", is_flag=True, help="Exclude optional tasks")
@click.option("--spec", "filter_spec", default=None, help="Plan a single spec")
@click.option(
    "--specs-dir",
    type=click.Path(),
    default=None,
    help="Path to specs directory (default: from config, or .agent-fox/specs)",
)
@click.pass_context
def plan_cmd(
    ctx: click.Context,
    dry_run: bool,
    fast: bool,
    filter_spec: str | None,
    specs_dir: str | None,
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

    # Load config for archetypes
    config_path = project_root / ".agent-fox" / "config.toml"
    config = load_config(config_path if config_path.exists() else None)

    # Resolve spec root from config with backward compatibility
    from agent_fox.core.config import resolve_spec_root

    specs_path: Path = Path(specs_dir) if specs_dir else resolve_spec_root(config, project_root)

    # Always rebuild the plan from specs directory (63-REQ-1.1)
    json_mode = ctx.obj.get("json", False)
    from agent_fox.ui.progress import PlanSpinner

    spinner = PlanSpinner("Planning...")
    if not json_mode:
        spinner.start()
    try:
        graph = build_plan(specs_path, filter_spec, fast, config)
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

    # 122-REQ-1.1: dry-run skips persistence and shows analysis
    if dry_run:
        from agent_fox.graph.analyzer import compute_phases, critical_path, group_edges
        from agent_fox.graph.planner import format_plan_analysis
        from agent_fox.graph.types import NodeStatus

        # 122-REQ-1.4: merge persisted statuses and filter completed nodes
        try:
            from agent_fox.graph.persistence import load_plan
            from agent_fox.knowledge.db import open_knowledge_store

            _db = open_knowledge_store(config.knowledge)
            try:
                persisted = load_plan(_db.connection)
            finally:
                _db.close()
        except Exception:
            persisted = None

        if persisted:
            for nid, node in graph.nodes.items():
                if nid in persisted.nodes:
                    node.status = persisted.nodes[nid].status

        completed_ids = {
            nid for nid, node in graph.nodes.items() if node.status == NodeStatus.COMPLETED
        }
        if completed_ids:
            graph.nodes = {nid: n for nid, n in graph.nodes.items() if nid not in completed_ids}
            graph.edges = [
                e
                for e in graph.edges
                if e.source not in completed_ids and e.target not in completed_ids
            ]
            graph.order = [nid for nid in graph.order if nid not in completed_ids]

        phases = compute_phases(graph)
        path = critical_path(graph)
        grouped = group_edges(graph)

        try:
            specs = discover_specs(specs_path, filter_spec=filter_spec)
        except PlanError:
            specs = []

        if json_mode:
            from agent_fox.cli.json_io import emit

            emit(
                {
                    "nodes": {
                        nid: _node_to_dict(node) for nid, node in graph.nodes.items()
                    },
                    "edges": [_edge_to_dict(e) for e in graph.edges],
                    "order": graph.order,
                    "metadata": _metadata_to_dict(graph.metadata),
                    "phases": [
                        {"number": p.number, "node_ids": p.node_ids} for p in phases
                    ],
                    "critical_path": path,
                    "grouped_edges": {
                        "intra_spec": [
                            _edge_to_dict(e) for e in grouped.intra_spec
                        ],
                        "cross_spec": [
                            _edge_to_dict(e) for e in grouped.cross_spec
                        ],
                    },
                }
            )
            return

        click.echo(format_plan_analysis(graph, phases, path, grouped, specs))
        return

    # Persist the plan to DuckDB (105-REQ-5.2)
    from agent_fox.knowledge.db import open_knowledge_store

    _knowledge_db = open_knowledge_store(config.knowledge)
    try:
        save_plan(graph, _knowledge_db.connection)
    finally:
        _knowledge_db.close()

    # Re-discover specs for summary display
    try:
        specs = discover_specs(specs_path, filter_spec=filter_spec)
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
