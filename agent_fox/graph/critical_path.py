"""Critical path computation for task graphs with duration weights.

Computes the longest-duration path through a DAG of task nodes using
a forward pass (topological order). Reports all tied critical paths
when multiple paths share the maximum duration.

Requirements: 39-REQ-8.1, 39-REQ-8.2, 39-REQ-8.3
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class CriticalPathResult:
    """Result of critical path computation.

    Attributes:
        path: The primary critical path as an ordered list of node IDs.
        total_duration_ms: Total duration of the critical path in milliseconds.
        tied_paths: Additional paths with the same total duration (if any).
    """

    path: list[str]
    total_duration_ms: int
    tied_paths: list[list[str]] = field(default_factory=list)


def compute_critical_path(
    nodes: dict[str, str],
    edges: dict[str, list[str]],
    duration_hints: dict[str, int],
) -> CriticalPathResult:
    """Compute the critical path through a task graph.

    Uses a forward pass in topological order to find the longest path.
    Each node's "earliest finish" is its own duration plus the maximum
    earliest finish of all predecessors.

    Args:
        nodes: Mapping of node_id to status (values are not used for
            computation but included for API consistency).
        edges: Mapping of node_id to list of predecessor node_ids.
            Nodes with no predecessors are sources.
        duration_hints: Mapping of node_id to predicted duration in ms.

    Returns:
        A CriticalPathResult with the critical path and total duration.
        If multiple paths tie, they are all reported.

    Requirements: 39-REQ-8.1, 39-REQ-8.3
    """
    if not nodes:
        return CriticalPathResult(path=[], total_duration_ms=0)

    node_ids = list(nodes.keys())

    # Build successor map and in-degree for topological sort
    successors: dict[str, list[str]] = {n: [] for n in node_ids}
    in_degree: dict[str, int] = {n: 0 for n in node_ids}

    for node, preds in edges.items():
        if node not in nodes:
            continue
        for pred in preds:
            if pred in successors:
                successors[pred].append(node)
            in_degree[node] = in_degree.get(node, 0) + 1

    # Ensure all nodes have in_degree entry
    for n in node_ids:
        in_degree.setdefault(n, 0)

    # Topological sort (Kahn's algorithm)
    topo_order: list[str] = []
    queue: deque[str] = deque()
    for n in sorted(node_ids):  # sorted for deterministic ordering
        if in_degree[n] == 0:
            queue.append(n)

    while queue:
        n = queue.popleft()
        topo_order.append(n)
        for succ in sorted(successors[n]):  # sorted for determinism
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Forward pass: compute earliest finish time for each node
    # earliest_finish[n] = duration[n] + max(earliest_finish[pred] for pred in preds)
    earliest_finish: dict[str, int] = {}

    for n in topo_order:
        dur = duration_hints.get(n, 0)
        preds = edges.get(n, [])
        if preds:
            max_pred_finish = max(earliest_finish.get(p, 0) for p in preds)
        else:
            max_pred_finish = 0
        earliest_finish[n] = max_pred_finish + dur

    # Find the maximum finish time (critical path duration)
    max_finish = max(earliest_finish.values()) if earliest_finish else 0

    # Find all sink nodes (no successors) that achieve max_finish
    sinks_at_max = [n for n in node_ids if not successors[n] and earliest_finish.get(n, 0) == max_finish]

    # If no sink achieves max, find any node at max (shouldn't happen in a DAG)
    if not sinks_at_max:
        sinks_at_max = [n for n in node_ids if earliest_finish.get(n, 0) == max_finish]

    # Backtrack to reconstruct all critical paths
    all_critical_paths: list[list[str]] = []
    for sink in sorted(sinks_at_max):
        paths = _backtrack_paths(sink, edges, earliest_finish, duration_hints)
        all_critical_paths.extend(paths)

    # Sort paths for deterministic output
    all_critical_paths.sort()

    if not all_critical_paths:
        # Fallback: single node
        best_node = max(node_ids, key=lambda n: earliest_finish.get(n, 0))
        all_critical_paths = [[best_node]]

    primary = all_critical_paths[0]
    tied = all_critical_paths[1:]

    return CriticalPathResult(
        path=primary,
        total_duration_ms=max_finish,
        tied_paths=tied,
    )


_MAX_BACKTRACK_PATHS = 64


def _backtrack_paths(
    node: str,
    edges: dict[str, list[str]],
    earliest_finish: dict[str, int],
    duration_hints: dict[str, int],
    _count: list[int] | None = None,
) -> list[list[str]]:
    """Backtrack from a node to find all critical paths ending at it.

    A predecessor is on the critical path if its earliest_finish equals
    this node's earliest_finish minus this node's duration.

    Stops after ``_MAX_BACKTRACK_PATHS`` paths to prevent exponential blowup.
    """
    if _count is None:
        _count = [0]

    dur = duration_hints.get(node, 0)
    expected_pred_finish = earliest_finish.get(node, 0) - dur

    preds = edges.get(node, [])
    critical_preds = [p for p in preds if earliest_finish.get(p, 0) == expected_pred_finish]

    if not critical_preds:
        _count[0] += 1
        return [[node]]

    paths: list[list[str]] = []
    for pred in sorted(critical_preds):
        if _count[0] >= _MAX_BACKTRACK_PATHS:
            break
        sub_paths = _backtrack_paths(pred, edges, earliest_finish, duration_hints, _count)
        for sp in sub_paths:
            paths.append(sp + [node])

    return paths


def format_critical_path(result: CriticalPathResult) -> str:
    """Format a critical path result for human-readable status output.

    Args:
        result: A CriticalPathResult instance.

    Returns:
        A formatted string suitable for display.

    Requirement: 39-REQ-8.2
    """
    lines: list[str] = []
    lines.append("== Critical Path ==")
    lines.append("")

    if not result.path:
        lines.append("No tasks in graph.")
        return "\n".join(lines)

    path_str = " -> ".join(result.path)
    lines.append(f"Path: {path_str}")
    lines.append(f"Estimated total duration: {result.total_duration_ms}ms")

    if result.tied_paths:
        lines.append(f"Tied paths ({len(result.tied_paths)} additional):")
        for tp in result.tied_paths:
            lines.append(f"  {' -> '.join(tp)}")

    return "\n".join(lines)
