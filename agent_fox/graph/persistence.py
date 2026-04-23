"""Plan persistence: serialize/deserialize TaskGraph to/from DuckDB.

Requirements: 105-REQ-1.1, 105-REQ-1.2, 105-REQ-1.3, 105-REQ-1.4,
              105-REQ-1.E1, 105-REQ-1.E2, 105-REQ-5.E1
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import fields as dc_fields
from enum import Enum
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
    if _count_row is None:
        raise RuntimeError("COUNT(*) query returned no rows")
    meta_count = _count_row[0]
    if meta_count == 0:
        return None

    # Load metadata
    meta_row = conn.sql(
        "SELECT content_hash, created_at, fast_mode, filtered_spec, version FROM plan_meta WHERE id = 1"
    ).fetchone()
    if meta_row is None:
        raise RuntimeError("plan_meta row missing despite non-zero count")

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
# Public API — DuckDB only (plan.json removed per issue #446)
# ---------------------------------------------------------------------------


def save_plan(graph: TaskGraph, conn: duckdb.DuckDBPyConnection) -> None:
    """Persist a TaskGraph to DuckDB tables.

    Args:
        graph: The task graph to persist.
        conn: A DuckDB connection.

    Requirements: 105-REQ-1.1
    """
    _save_plan_to_db(graph, conn)


def load_plan(
    conn: duckdb.DuckDBPyConnection,
) -> TaskGraph | None:
    """Load a TaskGraph from DuckDB tables.

    Args:
        conn: A DuckDB connection.

    Returns:
        The deserialized TaskGraph, or None if no plan exists.

    Requirements: 105-REQ-1.2, 105-REQ-1.E1, 105-REQ-5.E1
    """
    return _load_plan_from_db(conn)


def load_plan_or_raise(conn: duckdb.DuckDBPyConnection) -> TaskGraph:
    """Load the task graph from DuckDB, raising on failure.

    Convenience wrapper around :func:`load_plan` that raises
    :class:`AgentFoxError` instead of returning ``None``.

    Args:
        conn: A DuckDB connection.

    Raises:
        AgentFoxError: If no plan exists in the database.
    """
    from agent_fox.core.errors import AgentFoxError

    graph = load_plan(conn)
    if graph is None:
        raise AgentFoxError(
            "No plan found. Run `agent-fox plan` first.",
        )
    return graph
