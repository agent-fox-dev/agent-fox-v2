"""Dependency resolver: topological sort with cycle detection.

Requirements: 02-REQ-4.1, 02-REQ-4.2, 02-REQ-3.E2
"""

from __future__ import annotations

import copy
import heapq
import logging
from collections import defaultdict
from agent_fox.core.errors import PlanError
from agent_fox.core.node_id import parse_node_id
from agent_fox.graph.types import Edge, NodeStatus, PlanMetadata, TaskGraph

logger = logging.getLogger(__name__)


def _sort_key(node_id: str) -> tuple[str, int]:
    """Extract sort key from a node ID for deterministic tie-breaking.

    Breaks ties by spec prefix (ascending), then group number (ascending).
    Node IDs have the format ``{spec_name}:{group_number}[:{role}]``.
    """
    parsed = parse_node_id(node_id)
    return (parsed.spec_name, parsed.group_number)


def resolve_order(graph: TaskGraph) -> list[str]:
    """Compute a topological ordering of the task graph.

    Uses Kahn's algorithm. Ties are broken by spec prefix (ascending)
    then group number (ascending) for deterministic output.

    Args:
        graph: TaskGraph with nodes and edges.

    Returns:
        List of node IDs in execution order.

    Raises:
        PlanError: If the graph contains a cycle, listing involved nodes.
    """
    if not graph.nodes:
        logger.warning("No task groups found; empty execution order.")
        return []

    # Build adjacency list and compute in-degrees
    in_degree: dict[str, int] = {node_id: 0 for node_id in graph.nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in graph.edges:
        in_degree[edge.target] += 1
        adjacency[edge.source].append(edge.target)

    # Initialize min-heap with nodes that have zero in-degree
    # Heap entries are (sort_key, node_id) for deterministic tie-breaking
    heap: list[tuple[tuple[str, int], str]] = []
    for node_id in graph.nodes:
        if in_degree[node_id] == 0:
            heapq.heappush(heap, (_sort_key(node_id), node_id))

    order: list[str] = []

    while heap:
        _, node_id = heapq.heappop(heap)
        order.append(node_id)

        for successor in adjacency[node_id]:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                heapq.heappush(heap, (_sort_key(successor), successor))

    # Cycle detection: if not all nodes are in the order, there's a cycle
    if len(order) != len(graph.nodes):
        cycle_nodes = [node_id for node_id in graph.nodes if node_id not in set(order)]
        raise PlanError(f"Dependency cycle detected involving nodes: {', '.join(sorted(cycle_nodes))}")

    return order


# ---------------------------------------------------------------------------
# Fast-mode filter (merged from fast_mode.py)
# ---------------------------------------------------------------------------


def apply_fast_mode(graph: TaskGraph) -> TaskGraph:
    """Remove optional nodes and rewire dependencies.

    For each optional node B with predecessors {A1, A2} and
    successors {C1, C2}, add edges A_i -> C_j for all combinations,
    then remove B and its edges. B's status is set to SKIPPED.

    Args:
        graph: The full task graph.

    Returns:
        A new TaskGraph with optional nodes removed and dependencies
        rewired. The skipped nodes are retained in the graph with
        SKIPPED status but excluded from the ordering.
    """
    # Deep copy nodes so we don't mutate the original graph
    new_nodes = {nid: copy.copy(node) for nid, node in graph.nodes.items()}

    # Identify optional nodes
    optional_ids = {nid for nid, node in new_nodes.items() if node.optional}

    # If no optional nodes, resolve order and return with fast_mode metadata
    if not optional_ids:
        new_graph = TaskGraph(
            nodes=new_nodes,
            edges=list(graph.edges),
            order=[],
            metadata=PlanMetadata(
                created_at=graph.metadata.created_at,
                fast_mode=True,
                filtered_spec=graph.metadata.filtered_spec,
                version=graph.metadata.version,
            ),
        )
        new_graph.order = resolve_order(new_graph)
        return new_graph

    # Collect existing edges as a set for rewiring
    new_edges: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        new_edges.add((edge.source, edge.target, edge.kind))

    # For each optional node, rewire dependencies and remove its edges
    for opt_id in optional_ids:
        # Find predecessors and successors of this optional node
        preds = [(s, t, k) for s, t, k in new_edges if t == opt_id]
        succs = [(s, t, k) for s, t, k in new_edges if s == opt_id]

        # Add rewired edges: each predecessor -> each successor
        for pred_s, _, _ in preds:
            for _, succ_t, _ in succs:
                new_edges.add((pred_s, succ_t, "intra_spec"))

        # Remove all edges involving this optional node
        new_edges = {(s, t, k) for s, t, k in new_edges if s != opt_id and t != opt_id}

        # Set the optional node's status to SKIPPED
        new_nodes[opt_id].status = NodeStatus.SKIPPED

    # Build edge objects from the remaining edge tuples
    edge_list = [Edge(source=s, target=t, kind=k) for s, t, k in new_edges]

    # Build the new graph; compute order using only non-optional nodes
    order_nodes = {nid: node for nid, node in new_nodes.items() if nid not in optional_ids}
    order_graph = TaskGraph(
        nodes=order_nodes,
        edges=edge_list,
        order=[],
        metadata=PlanMetadata(
            created_at=graph.metadata.created_at,
            fast_mode=True,
            filtered_spec=graph.metadata.filtered_spec,
            version=graph.metadata.version,
        ),
    )
    computed_order = resolve_order(order_graph)

    return TaskGraph(
        nodes=new_nodes,
        edges=edge_list,
        order=computed_order,
        metadata=order_graph.metadata,
    )

