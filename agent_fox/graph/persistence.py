"""Plan persistence: serialize/deserialize TaskGraph to/from JSON or DuckDB.

Requirements: 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3, 02-REQ-6.4, 02-REQ-6.E1,
              105-REQ-1.1, 105-REQ-1.2, 105-REQ-1.3, 105-REQ-1.4,
              105-REQ-1.E1, 105-REQ-1.E2, 105-REQ-5.E1
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from dataclasses import fields as dc_fields
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_fox.graph.types import Edge, Node, NodeStatus, PlanMetadata, TaskGraph

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


def compute_plan_hash(graph: TaskGraph) -> str:
    """Compute SHA-256 content hash from plan structure, excluding runtime state.

    Hashes only structural fields (nodes without status, edges, topological
    order). Mutable runtime fields (status, blocked_reason) are excluded so
    that status transitions do not invalidate the hash.

    Requirements: 105-REQ-1.4
    """
    # Build canonical node dicts, excluding mutable runtime fields
    _EXCLUDE = frozenset({"status"})

    canonical_nodes: dict[str, Any] = {}
    for nid, node in sorted(graph.nodes.items()):
        node_dict: dict[str, Any] = {}
        for f in dc_fields(node):
            if f.name in _EXCLUDE:
                continue
            val = getattr(node, f.name)
            # Enums become their string value
            if isinstance(val, Enum):
                val = str(val)
            node_dict[f.name] = val
        canonical_nodes[nid] = node_dict

    canonical: dict[str, Any] = {
        "nodes": canonical_nodes,
        "edges": sorted(
            [{"source": e.source, "target": e.target, "kind": e.kind} for e in graph.edges],
            key=lambda e: (e["source"], e["target"]),
        ),
        "order": graph.order,
    }
    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# DB-based persistence (new API — accepts duckdb.DuckDBPyConnection)
# ---------------------------------------------------------------------------


def _save_plan_to_db(graph: TaskGraph, conn: duckdb.DuckDBPyConnection) -> None:
    """Persist a TaskGraph to DuckDB plan tables in a single transaction.

    Clears any existing plan data before inserting, so save_plan is idempotent.

    Requirements: 105-REQ-1.1, 105-REQ-1.4
    """
    plan_hash = compute_plan_hash(graph)

    # Build order index for sort_position (topological order, not dict order)
    order_index: dict[str, int] = {nid: i for i, nid in enumerate(graph.order)}

    conn.execute("BEGIN")
    try:
        # Clear existing plan data (DELETE order respects no FK constraints in DuckDB)
        conn.execute("DELETE FROM plan_meta")
        conn.execute("DELETE FROM plan_edges")
        conn.execute("DELETE FROM plan_nodes")

        # Insert nodes
        for nid, node in graph.nodes.items():
            sort_pos = order_index.get(nid, len(graph.nodes))
            conn.execute(
                """
                INSERT INTO plan_nodes (
                    id, spec_name, group_number, title, body,
                    archetype, mode, model_tier, status,
                    subtask_count, optional, instances, sort_position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    node.id,
                    node.spec_name,
                    node.group_number,
                    node.title,
                    node.body,
                    node.archetype,
                    node.mode,
                    None,  # model_tier: not stored on Node
                    str(node.status),
                    node.subtask_count,
                    node.optional,
                    node.instances,
                    sort_pos,
                ],
            )

        # Insert edges
        for edge in graph.edges:
            conn.execute(
                "INSERT INTO plan_edges (from_node, to_node, edge_type) VALUES (?, ?, ?)",
                [edge.source, edge.target, edge.kind],
            )

        # Insert metadata (single row, id = 1 enforced by CHECK constraint)
        conn.execute(
            """
            INSERT INTO plan_meta (id, content_hash, fast_mode, filtered_spec, version)
            VALUES (1, ?, ?, ?, ?)
            """,
            [
                plan_hash,
                graph.metadata.fast_mode,
                graph.metadata.filtered_spec,
                graph.metadata.version,
            ],
        )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _load_plan_from_db(conn: duckdb.DuckDBPyConnection) -> TaskGraph | None:
    """Load a TaskGraph from DuckDB plan tables.

    Returns None if no plan exists (plan_meta has no rows).

    Requirements: 105-REQ-1.2, 105-REQ-1.E1, 105-REQ-1.E2, 105-REQ-5.E1
    """
    # Check whether a plan has been saved
    _count_row = conn.sql("SELECT count(*) FROM plan_meta").fetchone()
    assert _count_row is not None  # COUNT(*) always returns exactly one row
    meta_count = _count_row[0]
    if meta_count == 0:
        return None

    # Load metadata
    meta_row = conn.sql(
        "SELECT content_hash, created_at, fast_mode, filtered_spec, version FROM plan_meta WHERE id = 1"
    ).fetchone()
    assert meta_row is not None  # guaranteed: meta_count > 0 confirmed above

    created_at_val = meta_row[1]
    if hasattr(created_at_val, "isoformat"):
        created_at_str = created_at_val.isoformat()
    else:
        created_at_str = str(created_at_val) if created_at_val is not None else ""

    metadata = PlanMetadata(
        created_at=created_at_str,
        fast_mode=bool(meta_row[2]),
        filtered_spec=meta_row[3],
        version=meta_row[4] or "",
    )

    # Load nodes ordered by sort_position (restores topological order)
    node_rows = conn.sql(
        """
        SELECT id, spec_name, group_number, title, body,
               archetype, mode, status, subtask_count, optional,
               instances, sort_position
        FROM plan_nodes
        ORDER BY sort_position
        """
    ).fetchall()

    nodes: dict[str, Node] = {}
    for row in node_rows:
        node = Node(
            id=row[0],
            spec_name=row[1],
            group_number=row[2],
            title=row[3],
            body=row[4] or "",
            archetype=row[5] or "coder",
            mode=row[6],
            status=NodeStatus(row[7]) if row[7] else NodeStatus.PENDING,
            subtask_count=row[8] if row[8] is not None else 0,
            optional=bool(row[9]) if row[9] is not None else False,
            instances=row[10] if row[10] is not None else 1,
        )
        nodes[row[0]] = node

    # Topological order is the node IDs in sort_position order
    order = [row[0] for row in node_rows]

    # Load edges
    edge_rows = conn.sql("SELECT from_node, to_node, edge_type FROM plan_edges").fetchall()
    edges = [Edge(source=row[0], target=row[1], kind=row[2]) for row in edge_rows]

    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=order,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# File-based persistence (legacy API — accepts Path)
# ---------------------------------------------------------------------------


def _serialize(obj: object) -> dict[str, Any]:
    """Convert a dataclass to a JSON-safe dict (stringifies enums)."""
    raw = asdict(obj)  # type: ignore[call-overload]

    def _fixup(value: object) -> object:
        if isinstance(value, Enum):
            return str(value)
        if isinstance(value, dict):
            return {k: _fixup(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_fixup(v) for v in value]
        return value

    return _fixup(raw)  # type: ignore[return-value]


def _node_from_dict(data: dict[str, Any]) -> Node:
    """Deserialize a Node from a dictionary (handles defaults for older plans)."""
    return Node(
        id=data["id"],
        spec_name=data["spec_name"],
        group_number=data["group_number"],
        title=data["title"],
        optional=data["optional"],
        status=NodeStatus(data["status"]),
        subtask_count=data.get("subtask_count", 0),
        body=data.get("body", ""),
        archetype=data.get("archetype", "coder"),
        mode=data.get("mode", None),
        instances=data.get("instances", 1),
    )


def _metadata_from_dict(data: dict[str, Any]) -> PlanMetadata:
    """Deserialize PlanMetadata from a dictionary (handles defaults for older plans).

    Old plan.json files may contain legacy fields (specs_hash, config_hash) which
    are silently ignored for backward compatibility (63-REQ-3.E1).
    """
    return PlanMetadata(
        created_at=data.get("created_at", ""),
        fast_mode=data.get("fast_mode", False),
        filtered_spec=data.get("filtered_spec"),
        version=data.get("version", ""),
    )


def _save_plan_to_file(graph: TaskGraph, plan_path: Path) -> None:
    """Serialize a TaskGraph to JSON and write to disk."""
    data = _serialize(graph)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_plan_from_file(plan_path: Path) -> TaskGraph | None:
    """Load a TaskGraph from a JSON plan file."""
    if not plan_path.exists():
        logger.warning("Plan file not found: %s", plan_path)
        return None

    try:
        raw = plan_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupted plan file %s: %s", plan_path, exc)
        return None

    try:
        metadata = _metadata_from_dict(data.get("metadata", {}))
        nodes = {nid: _node_from_dict(node_data) for nid, node_data in data.get("nodes", {}).items()}
        edges = [Edge(**e) for e in data.get("edges", [])]
        order = data.get("order", [])

        return TaskGraph(
            nodes=nodes,
            edges=edges,
            order=order,
            metadata=metadata,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Invalid plan file structure %s: %s", plan_path, exc)
        return None


# ---------------------------------------------------------------------------
# Public API — dispatches on argument type
# ---------------------------------------------------------------------------


def save_plan(graph: TaskGraph, dest: Path | duckdb.DuckDBPyConnection) -> None:
    """Persist a TaskGraph to either DuckDB tables or a JSON file.

    Args:
        graph: The task graph to persist.
        dest: Either a ``duckdb.DuckDBPyConnection`` (writes to DB tables) or
              a ``Path`` (writes to ``plan.json``). The DB path is the new
              default; the file path is kept for backward compatibility.

    Requirements: 105-REQ-1.1 (DB path), 02-REQ-6.1 (file path)
    """
    if isinstance(dest, Path):
        _save_plan_to_file(graph, dest)
    else:
        # Assume DuckDB connection
        _save_plan_to_db(graph, dest)


def load_plan(
    src: Path | duckdb.DuckDBPyConnection,
) -> TaskGraph | None:
    """Load a TaskGraph from DuckDB tables or a JSON plan file.

    Args:
        src: Either a ``duckdb.DuckDBPyConnection`` (reads from DB tables) or
             a ``Path`` (reads from ``plan.json``).

    Returns:
        The deserialized TaskGraph, or None if no plan exists / corrupted.

    Requirements: 105-REQ-1.2, 105-REQ-1.E1, 105-REQ-5.E1 (DB path),
                  02-REQ-6.2 (file path)
    """
    if isinstance(src, Path):
        return _load_plan_from_file(src)
    else:
        return _load_plan_from_db(src)


def load_plan_or_raise(plan_path: Path) -> TaskGraph:
    """Load the task graph from plan.json, raising on failure.

    Convenience wrapper around :func:`load_plan` that raises
    :class:`AgentFoxError` instead of returning ``None``.

    Args:
        plan_path: Path to .agent-fox/plan.json.

    Raises:
        AgentFoxError: If the plan file cannot be read.
    """
    from agent_fox.core.errors import AgentFoxError

    graph = load_plan(plan_path)
    if graph is None:
        raise AgentFoxError(
            "No plan file found. Run `agent-fox plan` first.",
            path=str(plan_path),
        )
    return graph
