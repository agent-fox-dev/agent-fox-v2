"""Hot-loader: discover and incorporate new specs at sync barriers.

At sync barriers, scans .specs/ for new specification folders not present
in the current task graph, parses them, and incorporates them into the
graph without restart.

Requirements: 06-REQ-6.3, 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3,
              06-REQ-7.E1, 06-REQ-7.E2
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from agent_fox.core.errors import PlanError
from agent_fox.graph.resolver import resolve_order
from agent_fox.graph.types import Edge, Node, NodeStatus, TaskGraph
from agent_fox.spec.discovery import SpecInfo, discover_specs  # noqa: F401
from agent_fox.spec.parser import parse_cross_deps, parse_tasks

logger = logging.getLogger("agent_fox.engine.hot_load")

# Pattern for dependency table header (broader than parser's format)
_DEP_TABLE_HEADER = re.compile(
    r"\|\s*(?:This\s+)?Spec\s*\|\s*Depend(?:s\s+On|ency)\s*\|",
    re.IGNORECASE,
)
_TABLE_SEP = re.compile(r"^\s*\|[\s\-|]+\|\s*$")


def _parse_dep_specs_from_prd(prd_path: Path) -> list[str]:
    """Parse dependency spec names from a prd.md dependency table.

    Handles both the standard ``| This Spec | Depends On |`` format
    and the simpler ``| Spec | Dependency |`` format. Returns just
    the dependency spec names (the second column values), filtering
    out self-references like "this".

    Args:
        prd_path: Path to the spec's prd.md file.

    Returns:
        List of dependency spec names. Empty if no table found.
    """
    if not prd_path.is_file():
        return []

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    dep_names: list[str] = []
    in_table = False
    header_found = False

    for line in lines:
        if not header_found:
            if _DEP_TABLE_HEADER.search(line):
                header_found = True
                in_table = True
            continue

        # Skip separator row
        if in_table and _TABLE_SEP.match(line):
            continue

        if in_table:
            stripped = line.strip()
            if not stripped.startswith("|"):
                break

            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]

            if len(cells) >= 2:
                dep_spec = cells[1].strip()
                if dep_spec and dep_spec.lower() != "this":
                    dep_names.append(dep_spec)

    return dep_names


def discover_new_specs(
    specs_dir: Path,
    known_specs: set[str],
) -> list[SpecInfo]:
    """Find spec folders in .specs/ not already in the task graph.

    Uses the standard spec discovery mechanism and filters out specs
    whose names are already in the known set.

    Args:
        specs_dir: Path to the .specs/ directory.
        known_specs: Set of spec names already in the current plan.

    Returns:
        List of newly discovered SpecInfo records, sorted by prefix.
    """
    try:
        all_specs = discover_specs(specs_dir)
    except PlanError:
        # No specs directory or no specs at all — nothing new to discover
        return []

    new_specs = [s for s in all_specs if s.name not in known_specs]
    return sorted(new_specs, key=lambda s: s.prefix)


def hot_load_specs(
    graph: TaskGraph,
    specs_dir: Path,
) -> tuple[TaskGraph, list[str]]:
    """Incorporate newly discovered specs into the task graph.

    1. Discover new spec folders not in graph.nodes.
    2. Parse tasks.md for each new spec.
    3. Parse cross-spec dependencies from each new spec's prd.md.
    4. Create nodes and edges for the new specs.
    5. Re-compute topological ordering.
    6. Return updated graph and list of new spec names.

    Args:
        graph: The current task graph.
        specs_dir: Path to the .specs/ directory.

    Returns:
        Tuple of (updated TaskGraph, list of newly added spec names).
        If no new specs are found, returns the original graph unchanged
        and an empty list.
    """
    # Step 1: Get known spec names from existing graph nodes
    known_specs: set[str] = set()
    for node in graph.nodes.values():
        known_specs.add(node.spec_name)

    # Step 2: Discover new specs
    new_spec_infos = discover_new_specs(specs_dir, known_specs)

    if not new_spec_infos:
        # 06-REQ-7.E2: no new specs, return unchanged
        return graph, []

    # Step 3: Parse tasks and dependencies for each new spec,
    # validating dependencies before adding
    valid_specs: list[SpecInfo] = []
    spec_task_groups: dict[str, list] = {}
    spec_deps: dict[str, list[str]] = {}

    # All spec names that exist in the system (existing + newly discovered)
    all_spec_names = known_specs | {s.name for s in new_spec_infos}

    for spec_info in new_spec_infos:
        # Skip specs without tasks.md
        if not spec_info.has_tasks:
            logger.warning(
                "New spec '%s' has no tasks.md, skipping",
                spec_info.name,
            )
            continue

        # Parse tasks
        tasks_path = spec_info.path / "tasks.md"
        try:
            task_groups = parse_tasks(tasks_path)
        except Exception:
            logger.warning(
                "Failed to parse tasks.md for spec '%s', skipping",
                spec_info.name,
            )
            continue

        if not task_groups:
            logger.warning(
                "No task groups found in spec '%s', skipping",
                spec_info.name,
            )
            continue

        # Parse cross-spec dependencies from prd.md
        prd_path = spec_info.path / "prd.md"
        dep_names = _parse_dep_specs_from_prd(prd_path)

        # Also try the standard parser for compatibility
        if not dep_names:
            cross_deps = parse_cross_deps(prd_path)
            dep_names = [d.to_spec for d in cross_deps]

        # 06-REQ-7.E1: Validate all dependencies exist
        invalid_deps = [d for d in dep_names if d not in all_spec_names]
        if invalid_deps:
            logger.warning(
                "Spec '%s' declares dependency on non-existent spec(s): %s. "
                "Skipping this spec.",
                spec_info.name,
                ", ".join(invalid_deps),
            )
            continue

        valid_specs.append(spec_info)
        spec_task_groups[spec_info.name] = task_groups
        spec_deps[spec_info.name] = dep_names

    if not valid_specs:
        return graph, []

    # Step 4: Build new nodes and edges
    new_nodes: dict[str, Node] = dict(graph.nodes)
    new_edges: list[Edge] = list(graph.edges)
    added_spec_names: list[str] = []

    for spec_info in valid_specs:
        task_groups = spec_task_groups[spec_info.name]
        sorted_groups = sorted(task_groups, key=lambda g: g.number)

        prev_node_id: str | None = None
        for group in sorted_groups:
            node_id = f"{spec_info.name}:{group.number}"
            new_nodes[node_id] = Node(
                id=node_id,
                spec_name=spec_info.name,
                group_number=group.number,
                title=group.title,
                optional=group.optional,
                status=NodeStatus.PENDING,
                subtask_count=len(group.subtasks),
                body=group.body,
            )

            # Intra-spec sequential edges
            if prev_node_id is not None:
                new_edges.append(
                    Edge(
                        source=prev_node_id,
                        target=node_id,
                        kind="intra_spec",
                    )
                )
            prev_node_id = node_id

        # Cross-spec edges: new spec depends on other specs
        dep_names = spec_deps.get(spec_info.name, [])
        if dep_names:
            # First group of the new spec depends on last group of each dep
            first_group = min(g.number for g in sorted_groups)
            target_id = f"{spec_info.name}:{first_group}"

            for dep_name in dep_names:
                # Find the last group of the dependency spec
                dep_groups = [
                    n.group_number
                    for n in new_nodes.values()
                    if n.spec_name == dep_name
                ]
                if dep_groups:
                    source_id = f"{dep_name}:{max(dep_groups)}"
                    new_edges.append(
                        Edge(
                            source=source_id,
                            target=target_id,
                            kind="cross_spec",
                        )
                    )

        added_spec_names.append(spec_info.name)

    # Step 5: Create updated graph and re-compute topological ordering
    updated_graph = TaskGraph(
        nodes=new_nodes,
        edges=new_edges,
        order=[],  # will be computed by resolver
        metadata=graph.metadata,
    )

    # 06-REQ-7.3: Re-compute topological ordering
    updated_graph.order = resolve_order(updated_graph)

    return updated_graph, added_spec_names


def should_trigger_barrier(
    completed_count: int,
    sync_interval: int,
) -> bool:
    """Check whether a sync barrier should be triggered.

    A sync barrier is triggered when sync_interval > 0 and the number
    of completed sessions is a positive multiple of sync_interval.

    Args:
        completed_count: Number of sessions completed so far.
        sync_interval: Barrier interval (0 = disabled).

    Returns:
        True if a sync barrier should be triggered, False otherwise.
    """
    return (
        sync_interval > 0
        and completed_count > 0
        and completed_count % sync_interval == 0
    )
