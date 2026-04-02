"""Backing module for the ``plan`` CLI command.

Provides ``run_plan()`` and ``build_plan()`` as callable entry points
for building execution plans, usable without the Click framework.

Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox import __version__
from agent_fox.graph.builder import build_graph
from agent_fox.graph.resolver import apply_fast_mode, resolve_order
from agent_fox.graph.types import NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo, discover_specs
from agent_fox.spec.parser import CrossSpecDep, parse_cross_deps, parse_tasks

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)


def build_plan(
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
    cross_deps = [dep for dep in cross_deps if dep.from_spec in discovered_names and dep.to_spec in discovered_names]

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


def format_plan_summary(graph: TaskGraph, specs: list[SpecInfo]) -> str:
    """Format a human-readable summary of the execution plan.

    Args:
        graph: The resolved task graph.
        specs: The discovered spec infos.

    Returns:
        Formatted summary string.
    """
    lines: list[str] = []

    total_nodes = len(graph.nodes)
    total_edges = len(graph.edges)
    ordered_count = len(graph.order)
    spec_names = sorted({node.spec_name for node in graph.nodes.values()})

    # Filter to real task nodes (exclude injected archetype nodes)
    task_nodes = {nid: node for nid, node in graph.nodes.items() if node.archetype == "coder"}
    total_tasks = len(task_nodes)
    completed_tasks = sum(1 for node in task_nodes.values() if node.status == NodeStatus.COMPLETED)
    review_count = total_nodes - total_tasks

    lines.append("Execution Plan")
    lines.append("=" * 40)
    lines.append(f"Specs:         {', '.join(spec_names)}")
    lines.append(f"Total tasks:   {total_tasks}")
    if review_count:
        lines.append(f"Review nodes:  {review_count}")
    lines.append(f"Dependencies:  {total_edges}")

    if graph.metadata.fast_mode:
        skipped = total_nodes - ordered_count
        lines.append(f"Fast mode:     on ({skipped} optional tasks skipped)")
    else:
        lines.append("Fast mode:     off")

    if completed_tasks:
        lines.append(f"Completed:     {completed_tasks}/{total_tasks}")

    # Separate completed from remaining in execution order
    remaining = [nid for nid in graph.order if graph.nodes[nid].status != NodeStatus.COMPLETED]

    lines.append("")
    if remaining:
        lines.append("Execution order:")
        for i, node_id in enumerate(remaining, 1):
            node = graph.nodes[node_id]
            lines.append(f"  {i}. {node_id} — {node.title}")
    else:
        lines.append("All tasks completed.")

    return "\n".join(lines)


def run_plan(
    config: AgentFoxConfig,
    *,
    specs_dir: Path | None = None,
    force: bool = False,
    fast: bool = False,
    filter_spec: str | None = None,
) -> TaskGraph:
    """Build or rebuild the task graph.

    This function can be called without the Click framework.

    Args:
        config: Loaded AgentFoxConfig.
        specs_dir: Path to specs directory (default: .specs).
        force: Discard cached plan and rebuild.
        fast: Exclude optional tasks.
        filter_spec: Plan a single spec only.

    Returns:
        A fully resolved TaskGraph.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.graph.persistence import save_plan

    resolved_specs_dir = specs_dir or Path(".specs")
    plan_path = Path(".agent-fox") / "plan.json"

    # Always rebuild — caching was removed by spec 63
    graph = build_plan(resolved_specs_dir, filter_spec, fast, config)
    save_plan(graph, plan_path)

    return graph
