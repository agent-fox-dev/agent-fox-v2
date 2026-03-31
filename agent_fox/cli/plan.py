"""Plan CLI command: build and display the execution plan.

Wires together spec discovery, task parsing, graph building,
dependency resolution, fast-mode filtering, and plan persistence
into the ``agent-fox plan`` subcommand.

Requirements: 02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4, 02-REQ-7.5
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import click

from agent_fox import __version__
from agent_fox.core.config import AgentFoxConfig, load_config
from agent_fox.core.errors import PlanError
from agent_fox.graph.builder import build_graph
from agent_fox.graph.persistence import save_plan
from agent_fox.graph.resolver import apply_fast_mode, resolve_order
from agent_fox.graph.types import NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo, discover_specs
from agent_fox.spec.parser import CrossSpecDep, parse_cross_deps, parse_tasks

logger = logging.getLogger(__name__)


def _build_plan(
    specs_dir: Path,
    filter_spec: str | None,
    fast: bool,
    config: AgentFoxConfig,
) -> TaskGraph:
    """Execute the full planning pipeline.

    Discovery → parsing → building → resolving → (fast mode) → graph.

    Args:
        specs_dir: Path to the .specs/ directory.
        filter_spec: If set, restrict to this single spec.
        fast: Whether to apply fast-mode filtering.
        config: Loaded agent-fox config (for archetypes).

    Returns:
        A fully resolved TaskGraph.
    """
    # Step 1: Discover specs
    specs = discover_specs(specs_dir, filter_spec=filter_spec)

    # Step 2: Parse task groups and cross-spec dependencies
    task_groups: dict[str, list] = {}
    cross_deps: list[CrossSpecDep] = []

    for spec in specs:
        if not spec.has_tasks:
            continue
        tasks_path = spec.path / "tasks.md"
        groups = parse_tasks(tasks_path)
        if groups:
            task_groups[spec.name] = groups

        # Parse cross-spec deps from prd.md if present
        if spec.has_prd:
            prd_path = spec.path / "prd.md"
            deps = parse_cross_deps(prd_path, spec_name=spec.name)
            cross_deps.extend(deps)

    # Filter cross-deps to only reference specs present in the discovered set.
    # This prevents dangling references when --spec filters to a single spec.
    discovered_names = {s.name for s in specs}
    cross_deps = [
        dep
        for dep in cross_deps
        if dep.from_spec in discovered_names and dep.to_spec in discovered_names
    ]

    # Step 3: Build graph
    graph = build_graph(
        specs,
        task_groups,
        cross_deps,
        archetypes_config=config.archetypes,
    )

    # Step 4: Resolve ordering or apply fast mode
    if fast:
        graph = apply_fast_mode(graph)
    else:
        graph.order = resolve_order(graph)

    # Step 5: Set metadata
    graph.metadata = PlanMetadata(
        created_at=datetime.now().isoformat(),
        fast_mode=fast,
        filtered_spec=filter_spec,
        version=__version__,
    )

    return graph


def _print_summary(graph: TaskGraph, specs: list[SpecInfo]) -> None:
    """Print a human-readable summary of the execution plan.

    Args:
        graph: The resolved task graph.
        specs: The discovered spec infos.
    """
    total_nodes = len(graph.nodes)
    total_edges = len(graph.edges)
    ordered_count = len(graph.order)
    spec_names = sorted({node.spec_name for node in graph.nodes.values()})

    # Filter to real task nodes (exclude injected archetype nodes)
    task_nodes = {
        nid: node for nid, node in graph.nodes.items() if node.archetype == "coder"
    }
    total_tasks = len(task_nodes)
    completed_tasks = sum(
        1 for node in task_nodes.values() if node.status == NodeStatus.COMPLETED
    )
    review_count = total_nodes - total_tasks

    click.echo("Execution Plan")
    click.echo("=" * 40)
    click.echo(f"Specs:         {', '.join(spec_names)}")
    click.echo(f"Total tasks:   {total_tasks}")
    if review_count:
        click.echo(f"Review nodes:  {review_count}")
    click.echo(f"Dependencies:  {total_edges}")

    if graph.metadata.fast_mode:
        skipped = total_nodes - ordered_count
        click.echo(f"Fast mode:     on ({skipped} optional tasks skipped)")
    else:
        click.echo("Fast mode:     off")

    if completed_tasks:
        click.echo(f"Completed:     {completed_tasks}/{total_tasks}")

    # Separate completed from remaining in execution order
    remaining = [
        nid for nid in graph.order if graph.nodes[nid].status != NodeStatus.COMPLETED
    ]

    click.echo()
    if remaining:
        click.echo("Execution order:")
        for i, node_id in enumerate(remaining, 1):
            node = graph.nodes[node_id]
            click.echo(f"  {i}. {node_id} — {node.title}")
    else:
        click.echo("All tasks completed.")


@click.command("plan")
@click.option("--fast", is_flag=True, help="Exclude optional tasks")
@click.option("--spec", "filter_spec", default=None, help="Plan a single spec")
@click.option("--analyze", is_flag=True, help="Show parallelism analysis")
@click.pass_context
def plan_cmd(
    ctx: click.Context,
    fast: bool,
    filter_spec: str | None,
    analyze: bool,
) -> None:
    """Build an execution plan from specifications."""
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
        graph = _build_plan(specs_dir, filter_spec, fast, config)
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

    _print_summary(graph, specs)

    # 20-REQ-1.1: Show parallelism analysis when --analyze is passed
    if analyze:
        from agent_fox.graph.resolver import analyze_plan, format_analysis

        analysis = analyze_plan(graph)
        click.echo()
        click.echo(format_analysis(analysis, graph))
