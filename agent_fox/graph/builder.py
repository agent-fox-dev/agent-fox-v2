"""Graph builder: construct TaskGraph from discovered specs and parsed tasks.

Requirements: 02-REQ-3.1, 02-REQ-3.2, 02-REQ-3.E1
"""

from __future__ import annotations

from agent_fox.core.errors import PlanError
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import CrossSpecDep, TaskGroupDef


def _create_nodes_and_intra_edges(
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
) -> tuple[dict[str, Node], list[Edge]]:
    """Create nodes and intra-spec sequential edges.

    02-REQ-3.3: node ID = {spec_name}:{group_number}
    02-REQ-3.4: all nodes start PENDING
    02-REQ-3.1: group N depends on group N-1 within the same spec
    """
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    for spec in specs:
        groups = task_groups.get(spec.name, [])
        if not groups:
            continue

        sorted_groups = sorted(groups, key=lambda g: g.number)

        prev_node_id: str | None = None
        for group in sorted_groups:
            node_id = f"{spec.name}:{group.number}"
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=group.number,
                title=group.title,
                optional=group.optional,
                status=NodeStatus.PENDING,
                subtask_count=len(group.subtasks),
                body=group.body,
            )

            if prev_node_id is not None:
                edges.append(
                    Edge(source=prev_node_id, target=node_id, kind="intra_spec")
                )
            prev_node_id = node_id

    return nodes, edges


def _resolve_sentinel_group(
    group_num: int,
    spec_name: str,
    task_groups: dict[str, list[TaskGroupDef]],
    *,
    use_max: bool,
) -> int:
    """Resolve sentinel group number 0 to the actual first or last group."""
    if group_num != 0:
        return group_num
    groups = task_groups.get(spec_name, [])
    if groups:
        nums = [g.number for g in groups]
        return max(nums) if use_max else min(nums)
    return 1  # fallback


def _add_cross_spec_edges(
    cross_deps: list[CrossSpecDep],
    task_groups: dict[str, list[TaskGroupDef]],
    nodes: dict[str, Node],
) -> list[Edge]:
    """Add cross-spec dependency edges, validating no dangling refs.

    02-REQ-3.E1: raises PlanError on dangling references.
    """
    edges: list[Edge] = []

    for dep in cross_deps:
        from_group = _resolve_sentinel_group(
            dep.from_group,
            dep.from_spec,
            task_groups,
            use_max=False,
        )
        to_group = _resolve_sentinel_group(
            dep.to_group,
            dep.to_spec,
            task_groups,
            use_max=True,
        )

        # CrossSpecDep direction: from_spec declares dependency on to_spec
        # Edge direction: to_spec:to_group -> from_spec:from_group
        source_id = f"{dep.to_spec}:{to_group}"
        target_id = f"{dep.from_spec}:{from_group}"

        if source_id not in nodes:
            raise PlanError(
                f"Dangling cross-spec dependency: "
                f"'{source_id}' (from spec '{dep.to_spec}') "
                f"does not exist in the task graph"
            )
        if target_id not in nodes:
            raise PlanError(
                f"Dangling cross-spec dependency: "
                f"'{target_id}' (from spec '{dep.from_spec}') "
                f"does not exist in the task graph"
            )

        edges.append(Edge(source=source_id, target=target_id, kind="cross_spec"))

    return edges


def build_graph(
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    cross_deps: list[CrossSpecDep],
) -> TaskGraph:
    """Construct a TaskGraph from discovered specs and parsed tasks.

    1. Create nodes and intra-spec edges.
    2. Add cross-spec edges with validation.
    3. Return TaskGraph (ordering computed separately by resolver).

    Args:
        specs: Discovered spec metadata.
        task_groups: Mapping of spec_name -> list of TaskGroupDef.
        cross_deps: Cross-spec dependency declarations.

    Returns:
        TaskGraph with nodes and edges but no ordering yet.

    Raises:
        PlanError: If dangling cross-spec references found.
    """
    nodes, intra_edges = _create_nodes_and_intra_edges(specs, task_groups)
    cross_edges = _add_cross_spec_edges(cross_deps, task_groups, nodes)

    return TaskGraph(
        nodes=nodes,
        edges=intra_edges + cross_edges,
        order=[],  # ordering is computed by the resolver, not the builder
        metadata=PlanMetadata(
            created_at="",  # set by the plan command when persisting
        ),
    )
