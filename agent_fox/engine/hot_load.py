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
from typing import TYPE_CHECKING, Any

from agent_fox.core.errors import PlanError
from agent_fox.graph.resolver import resolve_order
from agent_fox.graph.types import Edge, Node, NodeStatus, TaskGraph
from agent_fox.spec.discovery import SpecInfo, discover_specs  # noqa: F401
from agent_fox.spec.parser import parse_cross_deps, parse_tasks
from agent_fox.spec.validators import EXPECTED_FILES, Finding, validate_specs
from agent_fox.workspace.git import run_git

if TYPE_CHECKING:
    import duckdb

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


async def is_spec_tracked_on_develop(
    repo_root: Path,
    spec_name: str,
    specs_dir_rel: str = ".agent-fox/specs",
) -> bool:
    """Check if a spec folder is tracked by git on the develop branch.

    Uses ``git ls-tree develop -- {specs_dir_rel}/{spec_name}`` and returns True
    if any entries are found.

    On failure, returns True (permissive fallback) and logs a warning.

    Requirements: 51-REQ-4.1, 51-REQ-4.2, 51-REQ-4.E1
    """
    try:
        _rc, stdout, _stderr = await run_git(
            ["ls-tree", "develop", "--", f"{specs_dir_rel}/{spec_name}"],
            cwd=repo_root,
            check=False,
        )
        return bool(stdout.strip())
    except Exception:
        logger.warning(
            "git ls-tree failed for spec '%s', falling back to permissive",
            spec_name,
        )
        return True


def is_spec_complete(spec_path: Path) -> tuple[bool, list[str]]:
    """Check if all 5 required files exist and are non-empty.

    Returns:
        Tuple of (passed, list_of_missing_or_empty_filenames).

    Requirements: 51-REQ-5.1, 51-REQ-5.2, 51-REQ-5.E1
    """
    missing_or_empty: list[str] = []
    for filename in EXPECTED_FILES:
        fp = spec_path / filename
        if not fp.is_file() or fp.stat().st_size == 0:
            missing_or_empty.append(filename)
    return (len(missing_or_empty) == 0, missing_or_empty)


def lint_spec_gate(spec_name: str, spec_path: Path) -> tuple[bool, list[str]]:
    """Run the spec validator and check for error-severity findings.

    Returns:
        Tuple of (passed, error_messages).
        Passes if no findings have severity ``"error"``.
        On validator exception, returns ``(False, [error description])``.

    Requirements: 51-REQ-6.1, 51-REQ-6.2, 51-REQ-6.3, 51-REQ-6.E1
    """
    try:
        # Extract numeric prefix; default to 0 if not parseable
        prefix = 0
        parts = spec_name.split("_", 1)
        if parts[0].isdigit():
            prefix = int(parts[0])
        spec_info = SpecInfo(
            name=spec_name,
            prefix=prefix,
            path=spec_path,
            has_tasks=(spec_path / "tasks.md").is_file(),
            has_prd=(spec_path / "prd.md").is_file(),
        )
        findings: list[Finding] = validate_specs(
            specs_dir=spec_path.parent,
            discovered_specs=[spec_info],
        )
        error_findings = [f for f in findings if f.severity == "error"]
        if error_findings:
            error_messages = [f"{f.rule}: {f.message}" for f in error_findings]
            return (False, error_messages)
        return (True, [])
    except Exception as exc:
        return (False, [f"Validator error: {exc}"])


def are_all_tasks_done(spec_path: Path) -> bool:
    """Check if all task groups in tasks.md are marked complete.

    Returns True only when tasks.md exists, contains at least one group,
    and every group has ``completed=True``.

    Args:
        spec_path: Path to the spec folder (e.g., ``.specs/42_feature``).

    Returns:
        True if all task groups are completed, False otherwise.
    """
    tasks_path = spec_path / "tasks.md"
    if not tasks_path.is_file():
        return False
    try:
        groups = parse_tasks(tasks_path)
    except Exception:
        return False
    if not groups:
        return False
    return all(g.completed for g in groups)


def _are_all_plan_nodes_done(
    spec_name: str,
    conn: duckdb.DuckDBPyConnection | None,
) -> bool:
    """Check if all plan_nodes for a spec in the DB are completed.

    Queries the ``plan_nodes`` table directly rather than loading the
    full plan graph.  Returns True only when the DB is available,
    contains nodes for this spec, and every one has status
    ``'completed'``.

    Args:
        spec_name: The spec name to check (e.g., ``"42_feature"``).
        conn: DuckDB connection, or None if unavailable.

    Returns:
        True if all nodes for the spec are completed, False otherwise.
    """
    if conn is None:
        return False
    try:
        row = conn.execute(
            """
            SELECT
                count(*) AS total,
                count(*) FILTER (WHERE status = 'completed') AS done
            FROM plan_nodes
            WHERE spec_name = ?
            """,
            [spec_name],
        ).fetchone()
    except Exception:
        return False
    if row is None:
        return False
    total, done = row[0], row[1]
    return total > 0 and total == done


async def discover_new_specs_gated(
    specs_dir: Path,
    known_specs: set[str],
    repo_root: Path,
    *,
    db_conn: duckdb.DuckDBPyConnection | None = None,
) -> list[SpecInfo]:
    """Discover new specs that pass all four gates.

    Pipeline:
    1. Filesystem discovery (existing ``discover_new_specs``).
    2. Gate 1: git-tracked on develop.
    3. Gate 2: all 5 required files present and non-empty.
    4. Gate 3: no lint errors from validator.
    5. Gate 4: not already fully implemented (tasks.md + plan state).

    Returns only specs that pass all gates.  Skipped specs are
    re-evaluated at the next barrier with a clean slate (51-REQ-7.2).

    Args:
        specs_dir: Path to the .specs/ directory.
        known_specs: Set of spec names already in the current plan.
        repo_root: Path to the repository root (for git checks).
        db_conn: Optional DuckDB connection for querying plan_nodes
            (tasks-complete gate).  When None, the plan node check is
            skipped (gate degrades gracefully — specs are never skipped
            based on plan state alone).

    Requirements: 51-REQ-4.1, 51-REQ-5.1, 51-REQ-6.1, 51-REQ-7.1,
                  51-REQ-7.2, 51-REQ-7.3
    """
    candidates = discover_new_specs(specs_dir, known_specs)
    if not candidates:
        return []

    accepted: list[SpecInfo] = []
    for spec in candidates:
        # Gate 1: git-tracked on develop
        try:
            specs_rel = str(specs_dir.relative_to(repo_root))
        except ValueError:
            specs_rel = str(specs_dir)
        tracked = await is_spec_tracked_on_develop(repo_root, spec.name, specs_dir_rel=specs_rel)
        if not tracked:
            logger.debug("Spec '%s' not tracked on develop, skipping", spec.name)
            continue

        # Gate 2: completeness
        complete, missing = is_spec_complete(spec.path)
        if not complete:
            logger.info(
                "Spec '%s' incomplete (missing/empty: %s), skipping",
                spec.name,
                ", ".join(missing),
            )
            continue

        # Gate 3: lint
        lint_ok, errors = lint_spec_gate(spec.name, spec.path)
        if not lint_ok:
            logger.warning(
                "Spec '%s' has lint errors: %s, skipping",
                spec.name,
                "; ".join(errors),
            )
            continue

        # Gate 4: tasks-complete — skip specs that are fully implemented.
        # Both tasks.md AND plan node state must agree the spec is done.
        if are_all_tasks_done(spec.path) and _are_all_plan_nodes_done(spec.name, db_conn):
            logger.info(
                "Spec '%s' is fully implemented (all tasks complete, all plan nodes done), skipping",
                spec.name,
            )
            continue

        accepted.append(spec)

    return accepted


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


def _validate_and_parse_specs(
    new_spec_infos: list[SpecInfo],
    all_spec_names: set[str],
) -> tuple[list[SpecInfo], dict[str, list], dict[str, list[str]]]:
    """Parse and validate new specs, filtering out invalid ones.

    Returns:
        Tuple of (valid_specs, spec_task_groups, spec_deps).
    """
    valid_specs: list[SpecInfo] = []
    spec_task_groups: dict[str, list] = {}
    spec_deps: dict[str, list[str]] = {}

    for spec_info in new_spec_infos:
        if not spec_info.has_tasks:
            logger.warning(
                "New spec '%s' has no tasks.md, skipping",
                spec_info.name,
            )
            continue

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

        prd_path = spec_info.path / "prd.md"
        dep_names = _parse_dep_specs_from_prd(prd_path)

        if not dep_names:
            cross_deps = parse_cross_deps(prd_path, spec_name=spec_info.name)
            dep_names = [d.to_spec for d in cross_deps]

        # 06-REQ-7.E1: Validate all dependencies exist
        invalid_deps = [d for d in dep_names if d not in all_spec_names]
        if invalid_deps:
            logger.warning(
                "Spec '%s' declares dependency on non-existent spec(s): %s. Skipping this spec.",
                spec_info.name,
                ", ".join(invalid_deps),
            )
            continue

        valid_specs.append(spec_info)
        spec_task_groups[spec_info.name] = task_groups
        spec_deps[spec_info.name] = dep_names

    return valid_specs, spec_task_groups, spec_deps


def _build_nodes_and_edges(
    valid_specs: list[SpecInfo],
    spec_task_groups: dict[str, list],
    spec_deps: dict[str, list[str]],
    existing_nodes: dict[str, Node],
    existing_edges: list[Edge],
) -> tuple[dict[str, Node], list[Edge], list[str]]:
    """Create nodes and edges for validated new specs.

    Returns:
        Tuple of (all_nodes, all_edges, added_spec_names).
    """
    new_nodes: dict[str, Node] = dict(existing_nodes)
    new_edges: list[Edge] = list(existing_edges)
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

            if prev_node_id is not None:
                new_edges.append(
                    Edge(
                        source=prev_node_id,
                        target=node_id,
                        kind="intra_spec",
                    )
                )
            prev_node_id = node_id

        dep_names = spec_deps.get(spec_info.name, [])
        if dep_names:
            first_group = min(g.number for g in sorted_groups)
            target_id = f"{spec_info.name}:{first_group}"

            for dep_name in dep_names:
                dep_groups = [n.group_number for n in new_nodes.values() if n.spec_name == dep_name]
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

    return new_nodes, new_edges, added_spec_names


def hot_load_specs(
    graph: TaskGraph,
    specs_dir: Path,
) -> tuple[TaskGraph, list[str]]:
    """Incorporate newly discovered specs into the task graph.

    1. Discover new spec folders not in graph.nodes.
    2. Parse and validate tasks and dependencies.
    3. Create nodes and edges for the new specs.
    4. Re-compute topological ordering.

    Args:
        graph: The current task graph.
        specs_dir: Path to the .specs/ directory.

    Returns:
        Tuple of (updated TaskGraph, list of newly added spec names).
        If no new specs are found, returns the original graph unchanged
        and an empty list.
    """
    known_specs = {node.spec_name for node in graph.nodes.values()}
    new_spec_infos = discover_new_specs(specs_dir, known_specs)

    if not new_spec_infos:
        # 06-REQ-7.E2: no new specs, return unchanged
        return graph, []

    all_spec_names = known_specs | {s.name for s in new_spec_infos}
    valid_specs, spec_task_groups, spec_deps = _validate_and_parse_specs(
        new_spec_infos,
        all_spec_names,
    )

    if not valid_specs:
        return graph, []

    new_nodes, new_edges, added_spec_names = _build_nodes_and_edges(
        valid_specs,
        spec_task_groups,
        spec_deps,
        graph.nodes,
        graph.edges,
    )

    updated_graph = TaskGraph(
        nodes=new_nodes,
        edges=new_edges,
        order=[],
        metadata=graph.metadata,
    )

    # 06-REQ-7.3: Re-compute topological ordering
    updated_graph.order = resolve_order(updated_graph)

    return updated_graph, added_spec_names


async def hot_load_into_graph(
    *,
    specs_dir: Path,
    graph: TaskGraph,
    graph_sync: Any,
    state: Any,
    repo_root: Path,
    knowledge_db_conn: Any | None = None,
    archetypes_config: Any | None = None,
) -> tuple[TaskGraph, Any]:
    """Discover and incorporate new specs into a running graph.

    Performs gated discovery, parsing, node/edge building, archetype
    injection, and GraphSync rebuild. Returns the updated
    (graph, graph_sync) pair.

    Used by Orchestrator._hot_load_new_specs to keep engine.py thin.
    """
    from agent_fox.engine.graph_sync import GraphSync as _GraphSync
    from agent_fox.engine.state_manager import build_edges_dict, defer_ready_reviews
    from agent_fox.graph.injection import ensure_graph_archetypes

    for nid, node in graph.nodes.items():
        node.status = NodeStatus(state.node_states.get(nid, "pending"))

    known_specs = {n.spec_name for n in graph.nodes.values()}
    gated_specs = await discover_new_specs_gated(specs_dir, known_specs, repo_root, db_conn=knowledge_db_conn)

    if not gated_specs:
        return graph, graph_sync

    all_spec_names = known_specs | {s.name for s in gated_specs}
    valid_specs, spec_task_groups, spec_deps = _validate_and_parse_specs(gated_specs, all_spec_names)

    if not valid_specs:
        return graph, graph_sync

    new_nodes, new_edges, added_spec_names = _build_nodes_and_edges(
        valid_specs,
        spec_task_groups,
        spec_deps,
        graph.nodes,
        graph.edges,
    )

    if not added_spec_names:
        return graph, graph_sync

    logger.info(
        "Hot-loaded %d new spec(s): %s",
        len(added_spec_names),
        ", ".join(added_spec_names),
    )

    for nid, node in new_nodes.items():
        if nid not in graph.nodes:
            graph.nodes[nid] = node
            state.node_states[nid] = "pending"

    existing_edge_set = {(e.source, e.target) for e in graph.edges}
    for edge in new_edges:
        if (edge.source, edge.target) not in existing_edge_set:
            graph.edges.append(edge)

    ensure_graph_archetypes(graph, archetypes_config, specs_dir)
    for nid in graph.nodes:
        if nid not in state.node_states:
            state.node_states[nid] = "pending"

    edges_dict = build_edges_dict(graph)
    node_archetypes = {nid: n.archetype for nid, n in graph.nodes.items()}
    graph_sync = _GraphSync(state.node_states, edges_dict, node_archetypes)
    defer_ready_reviews(graph, graph_sync, knowledge_db_conn)

    return graph, graph_sync


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
    return sync_interval > 0 and completed_count > 0 and completed_count % sync_interval == 0
