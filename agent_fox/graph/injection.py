"""Shared archetype injection logic used by both the graph builder and engine.

Centralizes the decision logic for which archetypes to inject (auto_pre,
auto_mid, auto_post), oracle gating, instance resolution, and auditor
configuration.

Also provides ``ensure_graph_archetypes()`` for runtime injection on a
typed ``TaskGraph`` — used by the engine to patch stale cached plans.

Also provides ``build_review_only_graph()`` for constructing a task graph
containing only review archetype nodes (reviewer modes, verifier) for use
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
    """Lightweight tuple of (name, registry_entry, mode) for an enabled archetype.

    The mode field carries the named variant for mode-bearing archetypes (e.g.
    reviewer with pre-review/drift-review modes). None for archetypes without modes.

    Requirements: 98-REQ-4.1
    """

    name: str
    entry: Any
    mode: str | None = None


def resolve_instances(archetypes_config: Any, arch_name: str) -> int:
    """Resolve the instance count for an archetype from config.

    Returns 1 if config is missing or value is not an int.
    """
    instances_cfg = getattr(archetypes_config, "instances", None)
    instances = getattr(instances_cfg, arch_name, 1) if instances_cfg else 1
    return instances if isinstance(instances, int) else 1


def is_archetype_enabled(name: str, archetypes_config: Any | None) -> bool:
    """Check if an archetype is enabled in config.

    For reviewer modes, checks archetypes_config.reviewer (single toggle
    covers all reviewer modes: pre-review, drift-review, audit-review,
    fix-review).

    Requirements: 98-REQ-4.5
    """
    if archetypes_config is None:
        return name == "coder"
    return getattr(archetypes_config, name, False)


def collect_enabled_auto_pre(
    archetypes_config: Any,
    spec_path: Path | None = None,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_pre archetypes, applying drift-review gating.

    For the consolidated reviewer archetype, returns mode-bearing entries:
    - ("reviewer", entry, "pre-review") — always included when reviewer enabled
    - ("reviewer", entry, "drift-review") — gated by spec_has_existing_code

    For other archetypes (non-reviewer), uses the base injection field.

    Args:
        archetypes_config: The archetypes configuration object.
        spec_path: Path to the spec directory (for drift-review gating).
            If None, drift-review gating is skipped.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_pre archetypes.

    Requirements: 98-REQ-4.1, 98-REQ-4.4, 98-REQ-4.5
    """
    from agent_fox.archetypes import ARCHETYPE_REGISTRY

    enabled: list[ArchetypeEntry] = []

    # Handle reviewer archetype modes explicitly
    reviewer_entry = ARCHETYPE_REGISTRY.get("reviewer")
    if reviewer_entry is not None and is_archetype_enabled("reviewer", archetypes_config):
        # pre-review: always injected when reviewer enabled
        enabled.append(ArchetypeEntry("reviewer", reviewer_entry, "pre-review"))

        # drift-review: gated by spec_has_existing_code
        include_drift = True
        if spec_path is not None:
            from agent_fox.graph.spec_helpers import spec_has_existing_code

            if not spec_has_existing_code(spec_path):
                include_drift = False
                logger.info(
                    "Skipping drift-review for %s: no existing code to validate",
                    spec_path.name,
                )
        if include_drift:
            enabled.append(ArchetypeEntry("reviewer", reviewer_entry, "drift-review"))

    # Handle all other auto_pre archetypes (non-reviewer)
    for arch_name, entry in ARCHETYPE_REGISTRY.items():
        if arch_name == "reviewer":
            continue  # handled above
        if entry.injection == "auto_pre" and is_archetype_enabled(arch_name, archetypes_config):
            enabled.append(ArchetypeEntry(arch_name, entry))

    return enabled


def collect_enabled_auto_post(
    archetypes_config: Any,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_post archetypes.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_post archetypes.
    """
    from agent_fox.archetypes import ARCHETYPE_REGISTRY

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
    """Resolve audit-review injection configuration from archetypes config.

    Reads the consolidated reviewer_config for audit settings. Falls back
    to legacy auditor_config if reviewer_config is not present (migration).

    Returns:
        AuditorConfig with enabled flag, minimum TS entries, and instance count.

    Requirements: 98-REQ-4.3
    """
    # New consolidated path: reviewer toggle + reviewer_config
    reviewer_enabled = getattr(archetypes_config, "reviewer", False)
    if reviewer_enabled:
        reviewer_cfg = getattr(archetypes_config, "reviewer_config", None)
        min_ts = getattr(reviewer_cfg, "audit_min_ts_entries", 5) if reviewer_cfg else 5
        instances = resolve_instances(archetypes_config, "reviewer")
        return AuditorConfig(enabled=True, min_ts_entries=min_ts, instances=instances)

    # Legacy path: auditor toggle (for backward compat during migration)
    legacy_enabled = getattr(archetypes_config, "auditor", False)
    if not legacy_enabled:
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

        # Dedup: consider both archetype name and mode for reviewer
        existing_archetype_modes: set[tuple[str, str | None]] = set()
        for nid, n in nodes.items():
            if n.spec_name == spec and n.group_number == 0:
                existing_archetype_modes.add((n.archetype, n.mode))

        needed_pre = [a for a in enabled_auto_pre if (a.name, a.mode) not in existing_archetype_modes]

        for arch in needed_pre:
            # Build a unique node_id incorporating mode when present
            mode_suffix = f":{arch.mode}" if arch.mode else ""
            node_id = f"{spec}:0:{arch.name}{mode_suffix}"
            if node_id in nodes:
                continue
            # For reviewer modes, resolve instances via "reviewer" key
            instance_key = arch.name
            instances = resolve_instances(archetypes_config, instance_key)
            # Human-readable title
            if arch.mode:
                title = f"{arch.name.capitalize()} ({arch.mode})"
            else:
                title = f"{arch.name.capitalize()} Review"
            nodes[node_id] = Node(
                id=node_id,
                spec_name=spec,
                group_number=0,
                title=title,
                optional=False,
                archetype=arch.name,
                mode=arch.mode,
                instances=instances,
            )
            first_id = f"{spec}:{first_group}"
            if first_id in nodes:
                edges.append(Edge(source=node_id, target=first_id, kind="intra_spec"))
            graph.order.insert(0, node_id)
            injected = True
            logger.info(
                "Injected %s (mode=%s) node '%s' at runtime",
                arch.name,
                arch.mode,
                node_id,
            )

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

    # auto_mid injection (reviewer:audit-review after test-writing groups)
    aud_cfg = resolve_auditor_config(archetypes_config)
    if aud_cfg.enabled:
        for spec, groups in spec_groups.items():
            sorted_grps = sorted(groups)

            # Dedup: skip if reviewer:audit-review nodes already exist for this spec
            if any(
                n.spec_name == spec and n.archetype == "reviewer" and n.mode == "audit-review" for n in nodes.values()
            ):
                continue

            # Resolve spec path for TS count
            if specs_dir is None:
                continue
            candidate_path = specs_dir / spec
            if not candidate_path.exists():
                continue
            ts_count = count_ts_entries(candidate_path)
            if ts_count < aud_cfg.min_ts_entries:
                logger.info(
                    "Skipping audit-review injection for spec '%s': %d TS entries < min_ts_entries=%d",
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

                aud_nid = f"{spec}:{grp_num}:reviewer:audit-review"
                if aud_nid in nodes:
                    continue

                nodes[aud_nid] = Node(
                    id=aud_nid,
                    spec_name=spec,
                    group_number=grp_num,
                    title="Reviewer (audit-review)",
                    optional=False,
                    archetype="reviewer",
                    mode="audit-review",
                    instances=aud_cfg.instances,
                )

                grp_idx = sorted_grps.index(grp_num)
                next_grp = sorted_grps[grp_idx + 1] if grp_idx + 1 < len(sorted_grps) else None

                # Rewire edges: test_group → reviewer:audit-review → next_group
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
                logger.info("Injected reviewer:audit-review node '%s' at runtime", aud_nid)

    return injected


# ---------------------------------------------------------------------------
# Review-only mode: graph construction, audit events, and summary output
# ---------------------------------------------------------------------------

#: Source file extensions that trigger Skeptic + Oracle node creation.
_SOURCE_EXTENSIONS = frozenset({".py", ".ts", ".go", ".rs", ".java", ".js"})


def build_review_only_graph(
    specs_dir: Path,
    archetypes_config: Any | None,
    spec_filter: str | None = None,
) -> TaskGraph:
    """Build a task graph containing only review archetype nodes.

    Scans *specs_dir* for spec subdirectories.  For each eligible spec:

    - If the spec directory contains source files (.py, .ts, .go, .rs,
      .java, .js), Skeptic and Oracle nodes are created.
    - If the spec directory contains a ``requirements.md`` file, a
      Verifier node is created.

    When *spec_filter* is provided, only the spec whose directory name
    matches that string is included.

    Returns a :class:`~agent_fox.graph.types.TaskGraph` whose nodes are
    exclusively review archetypes (no coder nodes).

    Requirements: 53-REQ-6.2, 53-REQ-6.E1, 53-REQ-6.E2
    """
    from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

    nodes: dict[str, Node] = {}
    edges: list = []
    order: list[str] = []

    if not specs_dir.exists():
        return TaskGraph(nodes=nodes, edges=edges, order=order)

    # Enumerate spec directories, applying optional filter
    spec_dirs: list[Path] = []
    for item in sorted(specs_dir.iterdir()):
        if item.is_dir():
            if spec_filter is None or item.name == spec_filter:
                spec_dirs.append(item)

    for spec_dir in spec_dirs:
        spec_name = spec_dir.name

        # Check for source files
        has_source = any(f.suffix in _SOURCE_EXTENSIONS for f in spec_dir.iterdir() if f.is_file())

        # Check for requirements.md
        has_reqs = (spec_dir / "requirements.md").exists()

        if has_source:
            pre_id = f"{spec_name}:0:reviewer:pre-review"
            nodes[pre_id] = Node(
                id=pre_id,
                spec_name=spec_name,
                group_number=0,
                title="Reviewer (pre-review)",
                optional=False,
                archetype="reviewer",
                mode="pre-review",
            )
            order.append(pre_id)
            logger.debug("Created reviewer:pre-review node for spec '%s'", spec_name)

            drift_id = f"{spec_name}:0:reviewer:drift-review"
            nodes[drift_id] = Node(
                id=drift_id,
                spec_name=spec_name,
                group_number=0,
                title="Reviewer (drift-review)",
                optional=False,
                archetype="reviewer",
                mode="drift-review",
            )
            order.append(drift_id)
            logger.debug("Created reviewer:drift-review node for spec '%s'", spec_name)

        if has_reqs:
            verifier_id = f"{spec_name}:0:verifier"
            nodes[verifier_id] = Node(
                id=verifier_id,
                spec_name=spec_name,
                group_number=0,
                title="Verifier Review",
                optional=False,
                archetype="verifier",
            )
            order.append(verifier_id)
            logger.debug("Created Verifier node for spec '%s'", spec_name)

    import datetime  # noqa: PLC0415

    metadata = PlanMetadata(created_at=datetime.datetime.now().isoformat())
    return TaskGraph(nodes=nodes, edges=edges, order=order, metadata=metadata)


def print_review_only_summary(conn: Any) -> None:
    """Print a summary of active review findings, verdicts, and drift findings.

    Queries the DuckDB connection for counts of active (non-superseded)
    records across all specs and prints them grouped by severity and status.

    Requirements: 53-REQ-6.5
    """
    # Findings by severity
    finding_rows = conn.execute(
        "SELECT severity, COUNT(*) FROM review_findings WHERE superseded_by IS NULL GROUP BY severity"
    ).fetchall()
    finding_counts: dict[str, int] = {row[0]: row[1] for row in finding_rows}

    # Verdicts by status
    verdict_rows = conn.execute(
        "SELECT verdict, COUNT(*) FROM verification_results WHERE superseded_by IS NULL GROUP BY verdict"
    ).fetchall()
    verdict_counts: dict[str, int] = {row[0]: row[1] for row in verdict_rows}

    # Drift findings by severity
    drift_rows = conn.execute(
        "SELECT severity, COUNT(*) FROM drift_findings WHERE superseded_by IS NULL GROUP BY severity"
    ).fetchall()
    drift_counts: dict[str, int] = {row[0]: row[1] for row in drift_rows}

    print("\nReview-Only Run Summary")
    print("=======================")

    # Findings line
    f_parts = [f"{finding_counts.get(sev, 0)} {sev}" for sev in ("critical", "major", "minor", "observation")]
    print(f"Findings:  {', '.join(f_parts)}")

    # Verdicts line
    pass_count = verdict_counts.get("PASS", 0)
    fail_count = verdict_counts.get("FAIL", 0)
    print(f"Verdicts:  {pass_count} PASS, {fail_count} FAIL")

    # Drift line
    d_parts = [f"{drift_counts.get(sev, 0)} {sev}" for sev in ("critical", "major", "minor", "observation")]
    print(f"Drift:     {', '.join(d_parts)}")
