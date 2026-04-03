"""Shared archetype injection logic used by both the graph builder and engine.

Centralizes the decision logic for which archetypes to inject (auto_pre,
auto_mid, auto_post), oracle gating, instance resolution, and auditor
configuration.

Also provides ``ensure_graph_archetypes()`` for runtime injection on a
typed ``TaskGraph`` — used by the engine to patch stale cached plans.

Also provides ``build_review_only_graph()`` for constructing a task graph
containing only review archetype nodes (Skeptic, Oracle, Verifier) for use
in review-only mode.

Requirements: 26-REQ-5.3, 26-REQ-5.4, 32-REQ-3.1, 32-REQ-3.2,
              46-REQ-3.1, 46-REQ-4.1, 46-REQ-4.4,
              53-REQ-6.1, 53-REQ-6.2, 53-REQ-6.3, 53-REQ-6.4, 53-REQ-6.5
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from agent_fox.graph.types import TaskGraph

logger = logging.getLogger(__name__)


class ArchetypeEntry(NamedTuple):
    """Lightweight tuple of (name, registry_entry) for an enabled archetype."""

    name: str
    entry: Any


def resolve_instances(archetypes_config: Any, arch_name: str) -> int:
    """Resolve the instance count for an archetype from config.

    Returns 1 if config is missing or value is not an int.
    """
    instances_cfg = getattr(archetypes_config, "instances", None)
    instances = getattr(instances_cfg, arch_name, 1) if instances_cfg else 1
    return instances if isinstance(instances, int) else 1


def is_archetype_enabled(name: str, archetypes_config: Any | None) -> bool:
    """Check if an archetype is enabled in config."""
    if archetypes_config is None:
        return name == "coder"
    return getattr(archetypes_config, name, False)


def collect_enabled_auto_pre(
    archetypes_config: Any,
    spec_path: Path | None = None,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_pre archetypes, applying oracle gating.

    Args:
        archetypes_config: The archetypes configuration object.
        spec_path: Path to the spec directory (for oracle gating).
            If None, oracle gating is skipped.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_pre archetypes.
    """
    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    enabled: list[ArchetypeEntry] = [
        ArchetypeEntry(arch_name, entry)
        for arch_name, entry in ARCHETYPE_REGISTRY.items()
        if entry.injection == "auto_pre" and is_archetype_enabled(arch_name, archetypes_config)
    ]

    # Gate oracle: skip when spec has no existing code to validate against
    if any(a.name == "oracle" for a in enabled) and spec_path is not None:
        from agent_fox.graph.spec_helpers import spec_has_existing_code

        if not spec_has_existing_code(spec_path):
            enabled = [a for a in enabled if a.name != "oracle"]
            logger.info(
                "Skipping oracle for %s: no existing code to validate",
                spec_path.name,
            )

    return enabled


def collect_enabled_auto_post(
    archetypes_config: Any,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_post archetypes.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_post archetypes.
    """
    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    return [
        ArchetypeEntry(arch_name, entry)
        for arch_name, entry in ARCHETYPE_REGISTRY.items()
        if entry.injection == "auto_post" and is_archetype_enabled(arch_name, archetypes_config)
    ]


class AuditorConfig(NamedTuple):
    """Resolved auditor injection configuration."""

    enabled: bool
    min_ts_entries: int
    instances: int


def resolve_auditor_config(archetypes_config: Any) -> AuditorConfig:
    """Resolve auditor injection configuration from archetypes config.

    Returns:
        AuditorConfig with enabled flag, minimum TS entries, and instance count.
    """
    enabled = getattr(archetypes_config, "auditor", False)
    if not enabled:
        return AuditorConfig(enabled=False, min_ts_entries=5, instances=1)

    auditor_cfg = getattr(archetypes_config, "auditor_config", None)
    min_ts = getattr(auditor_cfg, "min_ts_entries", 5) if auditor_cfg else 5
    instances = resolve_instances(archetypes_config, "auditor")

    return AuditorConfig(enabled=True, min_ts_entries=min_ts, instances=instances)


def ensure_graph_archetypes(
    graph: TaskGraph,
    archetypes_config: Any | None,
    specs_dir: Path | None = None,
) -> bool:
    """Inject missing archetype nodes into a TaskGraph at runtime.

    Examines each spec in the graph and adds auto_pre, auto_post, and
    auto_mid nodes if they're enabled in config but absent from the
    graph. This ensures archetypes activate even with a stale cached plan.

    Mutates *graph* in place. Returns True if any nodes were injected.
    """
    if archetypes_config is None:
        return False

    from agent_fox.graph.spec_helpers import count_ts_entries, is_test_writing_group
    from agent_fox.graph.types import Edge, Node

    nodes = graph.nodes
    edges = graph.edges
    injected = False

    # Group existing coder nodes by spec
    spec_groups: dict[str, list[int]] = {}
    for nid, node in nodes.items():
        if node.archetype == "coder":
            spec_groups.setdefault(node.spec_name, []).append(node.group_number)

    for spec, groups in spec_groups.items():
        sorted_groups = sorted(groups)
        first_group = sorted_groups[0]
        last_group = sorted_groups[-1]

        # auto_pre injection
        spec_path = (specs_dir / spec) if specs_dir is not None else None
        enabled_auto_pre = collect_enabled_auto_pre(archetypes_config, spec_path=spec_path)

        # Dedup: find existing auto_pre archetypes for this spec
        existing_archetypes: set[str] = set()
        for nid, n in nodes.items():
            if n.spec_name == spec and n.group_number == 0:
                existing_archetypes.add(n.archetype)

        needed_pre = [a for a in enabled_auto_pre if a.name not in existing_archetypes]

        for arch in needed_pre:
            node_id = f"{spec}:0:{arch.name}"
            if node_id in nodes:
                continue
            instances = resolve_instances(archetypes_config, arch.name)
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec,
                group_number=0,
                title=f"{arch.name.capitalize()} Review",
                optional=False,
                archetype=arch.name,
                instances=instances,
            )
            first_id = f"{spec}:{first_group}"
            if first_id in nodes:
                edges.append(Edge(source=node_id, target=first_id, kind="intra_spec"))
            graph.order.insert(0, node_id)
            injected = True
            logger.info("Injected %s node '%s' at runtime", arch.name, node_id)

        # auto_post injection
        enabled_auto_post = collect_enabled_auto_post(archetypes_config)
        offset = 1
        for arch in enabled_auto_post:
            post_group = last_group + offset
            node_id = f"{spec}:{post_group}"
            if node_id in nodes:
                offset += 1
                continue
            instances = resolve_instances(archetypes_config, arch.name)
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec,
                group_number=post_group,
                title=f"{arch.name.capitalize()} Check",
                optional=False,
                archetype=arch.name,
                instances=instances,
            )
            last_id = f"{spec}:{last_group}"
            if last_id in nodes:
                edges.append(Edge(source=last_id, target=node_id, kind="intra_spec"))
            graph.order.append(node_id)
            offset += 1
            injected = True
            logger.info("Injected %s node '%s' at runtime", arch.name, node_id)

    # auto_mid injection (auditor after test-writing groups)
    aud_cfg = resolve_auditor_config(archetypes_config)
    if aud_cfg.enabled:
        for spec, groups in spec_groups.items():
            sorted_grps = sorted(groups)

            # Dedup: skip if auditor nodes already exist for this spec
            if any(n.spec_name == spec and n.archetype == "auditor" for n in nodes.values()):
                continue

            # Resolve spec path for TS count
            candidate_path = Path(f".specs/{spec}")
            if not candidate_path.exists():
                continue
            ts_count = count_ts_entries(candidate_path)
            if ts_count < aud_cfg.min_ts_entries:
                logger.info(
                    "Skipping auditor injection for spec '%s': %d TS entries < min_ts_entries=%d",
                    spec,
                    ts_count,
                    aud_cfg.min_ts_entries,
                )
                continue

            for grp_num in sorted_grps:
                grp_nid = f"{spec}:{grp_num}"
                grp_node = nodes.get(grp_nid)
                if grp_node is None or not is_test_writing_group(grp_node.title):
                    continue

                aud_nid = f"{spec}:{grp_num}:auditor"
                if aud_nid in nodes:
                    continue

                nodes[aud_nid] = Node(
                    id=aud_nid,
                    spec_name=spec,
                    group_number=grp_num,
                    title="Auditor Review",
                    optional=False,
                    archetype="auditor",
                    instances=aud_cfg.instances,
                )

                grp_idx = sorted_grps.index(grp_num)
                next_grp = sorted_grps[grp_idx + 1] if grp_idx + 1 < len(sorted_grps) else None

                # Rewire edges: test_group → auditor → next_group
                if next_grp is not None:
                    next_nid = f"{spec}:{next_grp}"
                    graph.edges[:] = [e for e in graph.edges if not (e.source == grp_nid and e.target == next_nid)]

                edges.append(Edge(source=grp_nid, target=aud_nid, kind="intra_spec"))

                if next_grp is not None:
                    next_nid = f"{spec}:{next_grp}"
                    if next_nid in nodes:
                        edges.append(Edge(source=aud_nid, target=next_nid, kind="intra_spec"))

                if grp_nid in graph.order:
                    idx = graph.order.index(grp_nid)
                    graph.order.insert(idx + 1, aud_nid)
                else:
                    graph.order.append(aud_nid)

                injected = True
                logger.info("Injected auditor node '%s' at runtime", aud_nid)

    return injected

