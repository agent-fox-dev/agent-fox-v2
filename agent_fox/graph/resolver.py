"""Dependency resolver: topological sort with cycle detection.

Requirements: 02-REQ-4.1, 02-REQ-4.2, 02-REQ-3.E2
"""

from __future__ import annotations

import heapq
from collections import defaultdict

from agent_fox.core.errors import PlanError
from agent_fox.graph.types import TaskGraph


def _sort_key(node_id: str) -> tuple[str, int]:
    """Extract sort key from a node ID for deterministic tie-breaking.

    Breaks ties by spec prefix (ascending), then group number (ascending).
    Node IDs have the format ``{spec_name}:{group_number}``.
    """
    parts = node_id.rsplit(":", 1)
    spec_name = parts[0]
    group_number = int(parts[1]) if len(parts) > 1 else 0
    return (spec_name, group_number)


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
        cycle_nodes = [
            node_id for node_id in graph.nodes if node_id not in set(order)
        ]
        raise PlanError(
            f"Dependency cycle detected involving nodes: "
            f"{', '.join(sorted(cycle_nodes))}"
        )

    return order
