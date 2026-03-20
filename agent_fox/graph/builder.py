"""Graph builder: construct TaskGraph from discovered specs and parsed tasks.

Requirements: 02-REQ-3.1, 02-REQ-3.2, 02-REQ-3.E1,
              26-REQ-5.2, 26-REQ-5.3, 26-REQ-5.4, 26-REQ-5.5
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from agent_fox.core.errors import PlanError
from agent_fox.graph.injection import (
    collect_enabled_auto_post,
    collect_enabled_auto_pre,
    is_archetype_enabled,
    resolve_auditor_config,
    resolve_instances,
)
from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import CrossSpecDep, TaskGroupDef

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test-writing group detection (46-REQ-3.1, 46-REQ-3.2)
# ---------------------------------------------------------------------------

_TEST_GROUP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"write failing spec tests", re.IGNORECASE),
    re.compile(r"write failing tests", re.IGNORECASE),
    re.compile(r"create unit test", re.IGNORECASE),
    re.compile(r"create test file", re.IGNORECASE),
    re.compile(r"spec tests", re.IGNORECASE),
]


def is_test_writing_group(title: str) -> bool:
    """Return True if the group title matches a test-writing pattern.

    Requirements: 46-REQ-3.1, 46-REQ-3.2, 46-REQ-3.E1, 46-REQ-3.E2
    """
    return any(p.search(title) for p in _TEST_GROUP_PATTERNS)


def count_ts_entries(spec_dir: Path) -> int:
    """Count TS-NN-N entries in a spec's test_spec.md.

    Returns 0 if the file does not exist.

    Requirements: 46-REQ-4.4
    """
    test_spec = spec_dir / "test_spec.md"
    if not test_spec.exists():
        return 0
    count = 0
    for line in test_spec.read_text().splitlines():
        if line.strip().startswith("### TS-"):
            count += 1
    return count


def _inject_auto_mid_nodes(
    nodes: dict[str, Node],
    edges: list[Edge],
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    archetypes_config: Any,
) -> None:
    """Inject auditor nodes after detected test-writing groups.

    Requirements: 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3, 46-REQ-4.E1,
                  46-REQ-4.E2, 46-REQ-4.E3
    """
    aud_cfg = resolve_auditor_config(archetypes_config)
    if not aud_cfg.enabled:
        return

    min_ts = aud_cfg.min_ts_entries
    instances = aud_cfg.instances

    for spec in specs:
        groups = task_groups.get(spec.name, [])
        if not groups:
            continue

        # Check TS entry threshold
        ts_count = count_ts_entries(spec.path)
        if ts_count < min_ts:
            logger.info(
                "Skipping auditor injection for spec '%s': "
                "%d TS entries < min_ts_entries=%d",
                spec.name,
                ts_count,
                min_ts,
            )
            continue

        sorted_groups = sorted(groups, key=lambda g: g.number)

        for i, group in enumerate(sorted_groups):
            if not is_test_writing_group(group.title):
                continue

            # Fractional group number to place between groups
            group_num = group.number
            # Use a fractional ID: e.g. spec:1:auditor
            node_id = f"{spec.name}:{group_num}:auditor"

            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=group_num,
                title="Auditor Review",
                optional=False,
                archetype="auditor",
                instances=instances if isinstance(instances, int) else 1,
            )

            # Edge from test-writing group to auditor
            test_node_id = f"{spec.name}:{group_num}"
            if test_node_id in nodes:
                # Remove existing edge from test group to next group
                next_group = (
                    sorted_groups[i + 1] if i + 1 < len(sorted_groups) else None
                )
                if next_group is not None:
                    next_node_id = f"{spec.name}:{next_group.number}"
                    edges[:] = [
                        e
                        for e in edges
                        if not (e.source == test_node_id and e.target == next_node_id)
                    ]

                edges.append(
                    Edge(source=test_node_id, target=node_id, kind="intra_spec")
                )

                # Edge from auditor to next group (if exists)
                if next_group is not None:
                    next_node_id = f"{spec.name}:{next_group.number}"
                    if next_node_id in nodes:
                        edges.append(
                            Edge(source=node_id, target=next_node_id, kind="intra_spec")
                        )


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


# ---------------------------------------------------------------------------
# Oracle gating: skip when spec targets only new code
# ---------------------------------------------------------------------------

# Matches file paths in backtick-bold markdown like **`agent_fox/foo.py`** (modified)
_DESIGN_FILE_REF = re.compile(
    r"\*\*`([a-zA-Z0-9_/.\-]+\.\w+)`\*\*\s*\(modified\)",
)


def spec_has_existing_code(spec_path: Path) -> bool:
    """Check whether a spec's design.md references files that already exist.

    Reads design.md, extracts paths marked ``(modified)``, and returns True
    if at least one of those paths exists on disk.  Returns True (safe
    default) when design.md is missing or unreadable so the oracle is not
    accidentally suppressed.
    """
    design_md = spec_path / "design.md"
    try:
        content = design_md.read_text(encoding="utf-8")
    except OSError:
        # No design.md or unreadable — assume code exists (safe default)
        return True

    refs = _DESIGN_FILE_REF.findall(content)
    if not refs:
        # No (modified) references found — nothing for oracle to validate
        return False

    for ref in refs:
        if Path(ref).exists():
            return True

    return False


def _inject_archetype_nodes(
    nodes: dict[str, Node],
    edges: list[Edge],
    specs: list[SpecInfo],
    task_groups: dict[str, list[TaskGroupDef]],
    archetypes_config: Any | None,
) -> None:
    """Inject auto_pre, auto_mid, and auto_post archetype nodes into the graph.

    Requirements: 26-REQ-5.3, 26-REQ-5.4, 46-REQ-4.1
    """
    if archetypes_config is None:
        return

    for spec in specs:
        groups = task_groups.get(spec.name, [])
        if not groups:
            continue

        sorted_groups = sorted(groups, key=lambda g: g.number)
        first_group = sorted_groups[0].number
        last_group = sorted_groups[-1].number

        # auto_pre injection (e.g., Skeptic/Oracle at group 0)
        # 32-REQ-3.1/3.2: Collect enabled auto_pre archetypes first to
        # determine whether to use suffixed IDs (multi) or plain :0 (single).
        enabled_auto_pre = collect_enabled_auto_pre(
            archetypes_config, spec_path=spec.path
        )
        use_suffix = len(enabled_auto_pre) > 1

        for arch in enabled_auto_pre:
            node_id = f"{spec.name}:0:{arch.name}" if use_suffix else f"{spec.name}:0"
            instances = resolve_instances(archetypes_config, arch.name)
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=0,
                title=f"{arch.name.capitalize()} Review",
                optional=False,
                archetype=arch.name,
                instances=instances,
            )
            # Edge from auto_pre node to first real group
            first_id = f"{spec.name}:{first_group}"
            if first_id in nodes:
                edges.append(Edge(source=node_id, target=first_id, kind="intra_spec"))

        # auto_post injection (e.g., Verifier after last group)
        enabled_auto_post = collect_enabled_auto_post(archetypes_config)
        offset = 1
        for arch in enabled_auto_post:
            post_group = last_group + offset
            node_id = f"{spec.name}:{post_group}"
            instances = resolve_instances(archetypes_config, arch.name)
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec.name,
                group_number=post_group,
                title=f"{arch.name.capitalize()} Check",
                optional=False,
                archetype=arch.name,
                instances=instances,
            )
            # Edge from last Coder group to this post node
            last_id = f"{spec.name}:{last_group}"
            if last_id in nodes:
                edges.append(Edge(source=last_id, target=node_id, kind="intra_spec"))
            offset += 1

    # auto_mid injection (e.g., Auditor after test-writing groups)
    _inject_auto_mid_nodes(nodes, edges, specs, task_groups, archetypes_config)


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

        if not is_archetype_enabled(arch_name, archetypes_config):
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


def _propagate_completion_to_archetype_nodes(
    nodes: dict[str, Node],
) -> None:
    """Mark archetype nodes as completed when all coder nodes in their spec are."""
    # Group nodes by spec
    coder_by_spec: dict[str, list[Node]] = defaultdict(list)
    archetype_by_spec: dict[str, list[Node]] = defaultdict(list)
    for node in nodes.values():
        if node.archetype == "coder":
            coder_by_spec[node.spec_name].append(node)
        else:
            archetype_by_spec[node.spec_name].append(node)

    for spec_name, coder_nodes in coder_by_spec.items():
        if all(n.status == NodeStatus.COMPLETED for n in coder_nodes):
            for node in archetype_by_spec.get(spec_name, []):
                node.status = NodeStatus.COMPLETED


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
        nodes,
        intra_edges,
        specs,
        task_groups,
        archetypes_config,
    )

    # Propagate completion: mark archetype nodes as completed when all
    # coder nodes in their spec are completed.
    _propagate_completion_to_archetype_nodes(nodes)

    # Three-layer assignment priority (26-REQ-5.2):
    # Layer 1 (lowest): graph builder default — already set to "coder"
    # Layer 2: coordinator overrides
    _apply_coordinator_overrides(nodes, coordinator_overrides, archetypes_config)
    # Layer 3 (highest): tasks.md tags — overwrites coordinator
    _apply_tasks_md_overrides(nodes, task_groups)

    # 26-REQ-5.5: Log final archetype assignment
    for node_id, node in nodes.items():
        logger.info(
            "Node '%s' archetype assignment: %s",
            node_id,
            node.archetype,
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
