"""Graph builder: construct TaskGraph from discovered specs and parsed tasks.

Requirements: 02-REQ-3.1, 02-REQ-3.2, 02-REQ-3.E1,
              26-REQ-5.2, 26-REQ-5.3, 26-REQ-5.4, 26-REQ-5.5
"""

from __future__ import annotations

import logging
from typing import Any

from agent_fox.core.errors import PlanError
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import CrossSpecDep, TaskGroupDef

logger = logging.getLogger(__name__)


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
            initial_status = (
                NodeStatus.COMPLETED if group.completed else NodeStatus.PENDING
            )
            # Carry archetype from tasks.md tag if present (applied later
            # as highest-priority layer in build_graph)
            archetype = "coder"
            if hasattr(group, "archetype") and group.archetype:
                archetype = group.archetype

            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=group.number,
                title=group.title,
                optional=group.optional,
                status=initial_status,
                subtask_count=len(group.subtasks),
                body=group.body,
                archetype=archetype,
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


def _is_archetype_enabled(
    name: str,
    archetypes_config: Any | None,
) -> bool:
    """Check if an archetype is enabled in config."""
    if archetypes_config is None:
        return name == "coder"
    return getattr(archetypes_config, name, False)


def _inject_archetype_nodes(
    nodes: dict[str, Node],
    edges: list[Edge],
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    archetypes_config: Any | None,
) -> None:
    """Inject auto_pre and auto_post archetype nodes into the graph.

    Requirements: 26-REQ-5.3, 26-REQ-5.4
    """
    if archetypes_config is None:
        return

    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    for spec in specs:
        groups = task_groups.get(spec.name, [])
        if not groups:
            continue

        sorted_groups = sorted(groups, key=lambda g: g.number)
        first_group = sorted_groups[0].number
        last_group = sorted_groups[-1].number

        # auto_pre injection (e.g., Skeptic at group 0)
        for arch_name, entry in ARCHETYPE_REGISTRY.items():
            if entry.injection != "auto_pre":
                continue
            if not _is_archetype_enabled(arch_name, archetypes_config):
                continue

            node_id = f"{spec.name}:0"
            instances = getattr(
                getattr(archetypes_config, "instances", None),
                arch_name,
                1,
            )
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=0,
                title=f"{arch_name.capitalize()} Review",
                optional=False,
                archetype=arch_name,
                instances=instances if isinstance(instances, int) else 1,
            )
            # Edge from group 0 to first real group
            first_id = f"{spec.name}:{first_group}"
            if first_id in nodes:
                edges.append(
                    Edge(source=node_id, target=first_id, kind="intra_spec")
                )

        # auto_post injection (e.g., Verifier after last group)
        offset = 1
        for arch_name, entry in ARCHETYPE_REGISTRY.items():
            if entry.injection != "auto_post":
                continue
            if not _is_archetype_enabled(arch_name, archetypes_config):
                continue

            post_group = last_group + offset
            node_id = f"{spec.name}:{post_group}"
            instances = getattr(
                getattr(archetypes_config, "instances", None),
                arch_name,
                1,
            )
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=post_group,
                title=f"{arch_name.capitalize()} Check",
                optional=False,
                archetype=arch_name,
                instances=instances if isinstance(instances, int) else 1,
            )
            # Edge from last Coder group to this post node
            last_id = f"{spec.name}:{last_group}"
            if last_id in nodes:
                edges.append(
                    Edge(source=last_id, target=node_id, kind="intra_spec")
                )
            offset += 1


def _apply_coordinator_overrides(
    nodes: dict[str, Node],
    coordinator_overrides: list[Any] | None,
    archetypes_config: Any | None,
) -> None:
    """Apply coordinator archetype overrides (layer 2 priority).

    Requirements: 26-REQ-5.2, 26-REQ-5.E1
    """
    if not coordinator_overrides:
        return

    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    for override in coordinator_overrides:
        node_id = override.node
        arch_name = override.archetype

        if node_id not in nodes:
            logger.warning(
                "Coordinator override references unknown node '%s'; ignoring",
                node_id,
            )
            continue

        # Check if archetype exists and is enabled
        if arch_name not in ARCHETYPE_REGISTRY:
            logger.warning(
                "Coordinator override references unknown archetype '%s'; ignoring",
                arch_name,
            )
            continue

        if not _is_archetype_enabled(arch_name, archetypes_config):
            logger.warning(
                "Coordinator override references disabled archetype '%s'; ignoring",
                arch_name,
            )
            continue

        entry = ARCHETYPE_REGISTRY[arch_name]
        if not entry.task_assignable:
            logger.warning(
                "Coordinator override references non-assignable archetype '%s'; "
                "falling back to 'coder'",
                arch_name,
            )
            continue

        # Only apply if no tasks.md tag already set (tag has higher priority,
        # but at this point we don't know yet — we apply coordinator first,
        # then tasks.md tag overwrites in the next step)
        nodes[node_id].archetype = arch_name


def _apply_tasks_md_overrides(
    nodes: dict[str, Node],
    task_groups: dict[str, list[TaskGroupDef]],
) -> None:
    """Apply tasks.md [archetype: X] tags as highest-priority overrides.

    Requirements: 26-REQ-5.1, 26-REQ-5.2
    """
    for spec_name, groups in task_groups.items():
        for group in groups:
            if not hasattr(group, "archetype") or group.archetype is None:
                continue
            node_id = f"{spec_name}:{group.number}"
            if node_id in nodes:
                nodes[node_id].archetype = group.archetype


def build_graph(
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    cross_deps: list[CrossSpecDep],
    archetypes_config: Any | None = None,
    coordinator_overrides: list[Any] | None = None,
) -> TaskGraph:
    """Construct a TaskGraph from discovered specs and parsed tasks.

    1. Create nodes and intra-spec edges.
    2. Inject auto_pre/auto_post archetype nodes.
    3. Apply three-layer archetype assignment.
    4. Add cross-spec edges with validation.
    5. Return TaskGraph (ordering computed separately by resolver).

    Args:
        specs: Discovered spec metadata.
        task_groups: Mapping of spec_name -> list of TaskGroupDef.
        cross_deps: Cross-spec dependency declarations.
        archetypes_config: ArchetypesConfig for archetype injection/toggles.
        coordinator_overrides: Coordinator-provided archetype overrides.

    Returns:
        TaskGraph with nodes and edges but no ordering yet.

    Raises:
        PlanError: If dangling cross-spec references found.
    """
    nodes, intra_edges = _create_nodes_and_intra_edges(specs, task_groups)

    # Phase B: Archetype injection
    _inject_archetype_nodes(
        nodes, intra_edges, specs, task_groups, archetypes_config,
    )

    # Three-layer assignment priority (26-REQ-5.2):
    # Layer 1 (lowest): graph builder default — already set to "coder"
    # Layer 2: coordinator overrides
    _apply_coordinator_overrides(nodes, coordinator_overrides, archetypes_config)
    # Layer 3 (highest): tasks.md tags — overwrites coordinator
    _apply_tasks_md_overrides(nodes, task_groups)

    # 26-REQ-5.5: Log final archetype assignment
    for node_id, node in nodes.items():
        logger.info(
            "Node '%s' archetype assignment: %s", node_id, node.archetype,
        )

    cross_edges = _add_cross_spec_edges(cross_deps, task_groups, nodes)

    return TaskGraph(
        nodes=nodes,
        edges=intra_edges + cross_edges,
        order=[],  # ordering is computed by the resolver, not the builder
        metadata=PlanMetadata(
            created_at="",  # set by the plan command when persisting
        ),
    )
