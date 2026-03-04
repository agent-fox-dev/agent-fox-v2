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
from agent_fox.core.errors import PlanError
from agent_fox.graph.builder import build_graph
from agent_fox.graph.fast_mode import apply_fast_mode
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.resolver import resolve_order
from agent_fox.graph.types import PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo, discover_specs
from agent_fox.spec.parser import CrossSpecDep, parse_cross_deps, parse_tasks

logger = logging.getLogger(__name__)


def _cache_matches_request(
    graph: TaskGraph,
    *,
    fast: bool,
    filter_spec: str | None,
) -> bool:
    """Return True when cached plan metadata matches CLI request flags."""
    return (
        graph.metadata.fast_mode == fast
        and graph.metadata.filtered_spec == filter_spec
    )


def _build_plan(
    specs_dir: Path,
    filter_spec: str | None,
    fast: bool,
) -> TaskGraph:
    """Execute the full planning pipeline.

    Discovery → parsing → building → resolving → (fast mode) → graph.

    Args:
        specs_dir: Path to the .specs/ directory.
        filter_spec: If set, restrict to this single spec.
        fast: Whether to apply fast-mode filtering.

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
    graph = build_graph(specs, task_groups, cross_deps)

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

    click.echo("Execution Plan")
    click.echo("=" * 40)
    click.echo(f"Specs:         {', '.join(spec_names)}")
    click.echo(f"Total tasks:   {total_nodes}")
    click.echo(f"Dependencies:  {total_edges}")

    if graph.metadata.fast_mode:
        skipped = total_nodes - ordered_count
        click.echo(f"Fast mode:     on ({skipped} optional tasks skipped)")
    else:
        click.echo("Fast mode:     off")

    click.echo()
    click.echo("Execution order:")
    for i, node_id in enumerate(graph.order, 1):
        node = graph.nodes[node_id]
        click.echo(f"  {i}. {node_id} — {node.title}")


@click.command("plan")
@click.option("--fast", is_flag=True, help="Exclude optional tasks")
@click.option("--spec", "filter_spec", default=None, help="Plan a single spec")
@click.option("--reanalyze", is_flag=True, help="Discard cached plan")
@click.option("--verify", is_flag=True, help="Verify dependency consistency")
@click.pass_context
def plan_cmd(
    ctx: click.Context,
    fast: bool,
    filter_spec: str | None,
    reanalyze: bool,
    verify: bool,
) -> None:
    """Build an execution plan from specifications."""
    # 02-REQ-7.5: --verify placeholder
    if verify:
        click.echo("Verify: not yet implemented.")
        return

    # Determine project paths
    project_root = Path.cwd()
    specs_dir = project_root / ".specs"
    plan_path = project_root / ".agent-fox" / "plan.json"

    # 02-REQ-6.3: Load existing plan if available (unless --reanalyze)
    if not reanalyze and plan_path.exists():
        existing = load_plan(plan_path)
        if existing is not None:
            if _cache_matches_request(
                existing,
                fast=fast,
                filter_spec=filter_spec,
            ):
                logger.info("Using cached plan from %s", plan_path)
                # Re-discover specs for summary display
                try:
                    specs = discover_specs(specs_dir, filter_spec=filter_spec)
                except PlanError:
                    specs = []
                _print_summary(existing, specs)
                return
            logger.info(
                "Cached plan metadata mismatch; rebuilding "
                "(cached fast=%s spec=%s, requested fast=%s spec=%s)",
                existing.metadata.fast_mode,
                existing.metadata.filtered_spec,
                fast,
                filter_spec,
            )

    # Build fresh plan
    try:
        graph = _build_plan(specs_dir, filter_spec, fast)
    except PlanError as exc:
        click.echo(f"Error: {exc}", err=True)
        ctx.exit(1)
        return

    # Persist the plan (02-REQ-6.1, 02-REQ-6.2)
    save_plan(graph, plan_path)

    # Re-discover specs for summary display
    try:
        specs = discover_specs(specs_dir, filter_spec=filter_spec)
    except PlanError:
        specs = []

    _print_summary(graph, specs)
