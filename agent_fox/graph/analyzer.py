"""Plan analysis functions: parallelism phases, critical path, edge grouping.

Pure functions that operate on a resolved TaskGraph to compute
analysis data for the --dry-run flag.

Requirements: 122-REQ-2.1, 122-REQ-3.1, 122-REQ-4.1, 122-REQ-4.3
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from agent_fox.graph.types import Edge, TaskGraph


@dataclass
class Phase:
    """A parallelism phase: a maximal set of nodes at the same topological depth."""

    number: int  # 0-indexed phase number
    node_ids: list[str] = field(default_factory=list)  # sorted lexicographically


@dataclass
class GroupedEdges:
    """Dependency edges partitioned by kind."""

    intra_spec: list[Edge] = field(default_factory=list)
    cross_spec: list[Edge] = field(default_factory=list)


def compute_phases(graph: TaskGraph) -> list[Phase]:
    """Group nodes into parallelism phases by topological depth.

    Topological depth is the length of the longest path from any source
    node to a given node. Nodes at the same depth form a parallelism phase.
    Node IDs within each phase are sorted lexicographically.

    Requirements: 122-REQ-2.1
    """
    if not graph.order:
        return []

    # Build adjacency list
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        adj[edge.source].append(edge.target)

    # Compute topological depth via dynamic programming on topological order.
    # For each node, depth = max(depth of predecessor + 1) over all predecessors.
    # Source nodes (in-degree 0) have depth 0.
    depth: dict[str, int] = {nid: 0 for nid in graph.order}
    for nid in graph.order:
        for successor in adj[nid]:
            candidate = depth[nid] + 1
            if candidate > depth[successor]:
                depth[successor] = candidate

    # Group by depth
    depth_groups: dict[int, list[str]] = defaultdict(list)
    for nid in graph.order:
        depth_groups[depth[nid]].append(nid)

    # Build phases sorted by phase number, node IDs sorted lexicographically
    max_depth = max(depth.values()) if depth else 0
    phases = []
    for d in range(max_depth + 1):
        node_ids = sorted(depth_groups[d])
        phases.append(Phase(number=d, node_ids=node_ids))

    return phases


def critical_path(graph: TaskGraph) -> list[str]:
    """Compute the longest path through the DAG (uniform edge weights).

    Uses dynamic programming on the topological order. At each tie-break
    point, the lexicographically smallest predecessor is chosen to ensure
    determinism.

    Requirements: 122-REQ-4.1, 122-REQ-4.3
    """
    if not graph.order:
        return []

    # Build adjacency list
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in graph.order}
    for edge in graph.edges:
        adj[edge.source].append(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

    # dist[nid] = length of the longest path ending at nid (inclusive)
    dist: dict[str, int] = {nid: 1 for nid in graph.order}
    # predecessor on the longest path (None for source nodes)
    pred: dict[str, str | None] = {nid: None for nid in graph.order}

    # Process in topological order
    for nid in graph.order:
        for successor in adj[nid]:
            candidate = dist[nid] + 1
            if candidate > dist[successor]:
                dist[successor] = candidate
                pred[successor] = nid
            elif candidate == dist[successor]:
                # Tie-break: pick lexicographically smallest predecessor
                if pred[successor] is None or nid < pred[successor]:
                    pred[successor] = nid

    # Find the sink node with the longest path.
    # Among sinks with equal longest path, pick lexicographically smallest.
    out_degree: dict[str, int] = {nid: 0 for nid in graph.order}
    for edge in graph.edges:
        out_degree[edge.source] = out_degree.get(edge.source, 0) + 1

    sinks = [nid for nid in graph.order if out_degree[nid] == 0]

    if not sinks:
        # All nodes have successors — shouldn't happen in a DAG, but handle it
        sinks = list(graph.order)

    # Find max distance among sinks
    max_dist = max(dist[s] for s in sinks)
    # Among sinks with max distance, pick lexicographically smallest
    best_sink = min(s for s in sinks if dist[s] == max_dist)

    # Reconstruct path by following predecessors
    path: list[str] = []
    current: str | None = best_sink
    while current is not None:
        path.append(current)
        current = pred[current]
    path.reverse()

    return path


def group_edges(graph: TaskGraph) -> GroupedEdges:
    """Partition graph edges by kind (intra_spec vs cross_spec).

    Requirements: 122-REQ-3.1
    """
    intra: list[Edge] = []
    cross: list[Edge] = []
    for edge in graph.edges:
        if edge.kind == "cross_spec":
            cross.append(edge)
        else:
            intra.append(edge)
    return GroupedEdges(intra_spec=intra, cross_spec=cross)
