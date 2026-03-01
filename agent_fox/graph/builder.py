"""Graph builder: construct TaskGraph from discovered specs and parsed tasks.

Requirements: 02-REQ-3.1, 02-REQ-3.2, 02-REQ-3.E1
"""

from __future__ import annotations

from agent_fox.core.errors import PlanError
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import CrossSpecDep, TaskGroupDef


def build_graph(
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    cross_deps: list[CrossSpecDep],
) -> TaskGraph:
    """Construct a TaskGraph from discovered specs and parsed tasks.

    1. Create a Node for each task group.
    2. Add intra-spec edges (group N depends on N-1).
    3. Add cross-spec edges from dependency declarations.
    4. Validate: no dangling references.

    Args:
        specs: Discovered spec metadata.
        task_groups: Mapping of spec_name -> list of TaskGroupDef.
        cross_deps: Cross-spec dependency declarations.

    Returns:
        TaskGraph with nodes and edges but no ordering yet.

    Raises:
        PlanError: If dangling cross-spec references found.
    """
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    # Step 1 & 2: Create nodes and intra-spec edges for each spec
    for spec in specs:
        groups = task_groups.get(spec.name, [])
        if not groups:
            continue

        # Sort groups by number to ensure correct sequential ordering
        sorted_groups = sorted(groups, key=lambda g: g.number)

        prev_node_id: str | None = None
        for group in sorted_groups:
            # 02-REQ-3.3: unique node ID = {spec_name}:{group_number}
            node_id = f"{spec.name}:{group.number}"
            # 02-REQ-3.4: initialize all nodes with status pending
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

            # 02-REQ-3.1: intra-spec sequential edges (N depends on N-1)
            if prev_node_id is not None:
                edges.append(
                    Edge(
                        source=prev_node_id,
                        target=node_id,
                        kind="intra_spec",
                    )
                )
            prev_node_id = node_id

    # Step 3: Add cross-spec edges
    for dep in cross_deps:
        # Resolve sentinel group numbers (0 = first/last group)
        from_group = dep.from_group
        to_group = dep.to_group

        if from_group == 0:
            # Resolve to first group of from_spec
            from_groups = task_groups.get(dep.from_spec, [])
            if from_groups:
                from_group = min(g.number for g in from_groups)
            else:
                from_group = 1  # fallback

        if to_group == 0:
            # Resolve to last group of to_spec
            to_groups = task_groups.get(dep.to_spec, [])
            if to_groups:
                to_group = max(g.number for g in to_groups)
            else:
                to_group = 1  # fallback

        # Build edge node IDs
        source_id = f"{dep.to_spec}:{to_group}"
        target_id = f"{dep.from_spec}:{from_group}"

        # Step 4: Validate - no dangling references (02-REQ-3.E1)
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

        # CrossSpecDep direction: from_spec declares dependency on to_spec
        # Edge direction: to_spec:to_group -> from_spec:from_group
        edges.append(
            Edge(
                source=source_id,
                target=target_id,
                kind="cross_spec",
            )
        )

    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=[],  # ordering is computed by the resolver, not the builder
        metadata=PlanMetadata(
            created_at="",  # set by the plan command when persisting
        ),
    )
