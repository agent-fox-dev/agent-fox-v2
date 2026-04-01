"""Dependency graph: construction, cycle detection, topological sort.

Requirements: 71-REQ-4.1, 71-REQ-4.2, 71-REQ-4.3, 71-REQ-4.E1,
              71-REQ-2.E2, 71-REQ-6.3
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from agent_fox.platform.github import IssueResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DependencyEdge:
    """A directed dependency: `from_issue` must be fixed before `to_issue`."""

    from_issue: int  # prerequisite
    to_issue: int  # dependent
    source: str  # "explicit", "github", or "ai"
    rationale: str  # why this edge exists


def build_graph(
    issues: list[IssueResult],
    edges: list[DependencyEdge],
) -> list[int]:
    """Build dependency graph, detect/break cycles, return topological order.

    Uses Kahn's algorithm. Ties broken by ascending issue number.
    Cycles broken by removing the edge pointing to the oldest (lowest-
    numbered) issue in the cycle, with a WARNING log.

    Returns list of issue numbers in processing order.

    Requirements: 71-REQ-4.1, 71-REQ-4.2, 71-REQ-4.3, 71-REQ-4.E1
    """
    issue_numbers = {i.number for i in issues}

    # Filter edges to only include those between issues in the batch
    valid_edges = [
        e
        for e in edges
        if e.from_issue in issue_numbers and e.to_issue in issue_numbers
    ]

    # Break cycles before running topological sort
    valid_edges = _break_all_cycles(valid_edges, issue_numbers)

    return _kahn_sort(issue_numbers, valid_edges)


def _kahn_sort(
    nodes: set[int],
    edges: list[DependencyEdge],
) -> list[int]:
    """Kahn's algorithm with tie-breaking by ascending issue number.

    Requirements: 71-REQ-4.1, 71-REQ-4.2
    """
    # Build adjacency list and in-degree map
    in_degree: dict[int, int] = {n: 0 for n in nodes}
    successors: dict[int, list[int]] = defaultdict(list)

    for edge in edges:
        in_degree[edge.to_issue] += 1
        successors[edge.from_issue].append(edge.to_issue)

    # Initialize with zero in-degree nodes, sorted by issue number (tie-break)
    ready = sorted(n for n, deg in in_degree.items() if deg == 0)
    result: list[int] = []

    while ready:
        # Pick the lowest-numbered node (tie-breaking: 71-REQ-4.2)
        node = ready.pop(0)
        result.append(node)

        for succ in successors[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                # Insert in sorted position to maintain order
                _insert_sorted(ready, succ)

    return result


def _insert_sorted(lst: list[int], val: int) -> None:
    """Insert val into a sorted list maintaining sorted order."""
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if lst[mid] < val:
            lo = mid + 1
        else:
            hi = mid
    lst.insert(lo, val)


def _break_all_cycles(
    edges: list[DependencyEdge],
    nodes: set[int],
) -> list[DependencyEdge]:
    """Repeatedly detect and break cycles until the graph is acyclic.

    Each cycle is broken by removing the edge pointing to the oldest
    (lowest-numbered) issue in the cycle.

    Requirements: 71-REQ-4.3, 71-REQ-2.E2, 71-REQ-6.3
    """
    working_edges = list(edges)

    while True:
        cycles = detect_cycles(working_edges)
        if not cycles:
            break

        for cycle in cycles:
            oldest = min(cycle)
            # Remove the edge pointing TO the oldest issue in this cycle
            edge_to_remove = None
            for e in working_edges:
                if e.to_issue == oldest and e.from_issue in cycle:
                    edge_to_remove = e
                    break

            if edge_to_remove is not None:
                logger.warning(
                    "Dependency cycle detected among issues %s; "
                    "breaking cycle by removing edge #%d -> #%d",
                    cycle,
                    edge_to_remove.from_issue,
                    edge_to_remove.to_issue,
                )
                working_edges.remove(edge_to_remove)
            # Only break one cycle per iteration, then re-detect
            break

    return working_edges


def detect_cycles(edges: list[DependencyEdge]) -> list[list[int]]:
    """Find all cycles in the dependency graph using DFS.

    Returns a list of cycles, where each cycle is a list of issue numbers.
    """
    # Build adjacency list
    adj: dict[int, list[int]] = defaultdict(list)
    all_nodes: set[int] = set()
    for e in edges:
        adj[e.from_issue].append(e.to_issue)
        all_nodes.add(e.from_issue)
        all_nodes.add(e.to_issue)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {n: WHITE for n in all_nodes}
    path: list[int] = []
    cycles: list[list[int]] = []

    def dfs(node: int) -> None:
        color[node] = GRAY
        path.append(node)

        for neighbor in adj[node]:
            if color[neighbor] == GRAY:
                # Found a cycle: extract it from path
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor)

        path.pop()
        color[node] = BLACK

    for node in sorted(all_nodes):
        if color[node] == WHITE:
            dfs(node)

    return cycles


def merge_edges(
    explicit_edges: list[DependencyEdge],
    ai_edges: list[DependencyEdge],
) -> list[DependencyEdge]:
    """Merge explicit and AI-detected edges, explicit wins on conflict.

    A conflict exists when an explicit edge says A->B but an AI edge
    says B->A. In that case, the AI edge is discarded.

    Requirements: 71-REQ-3.4
    """
    # Collect all explicit edge pairs for conflict detection
    explicit_pairs = {(e.from_issue, e.to_issue) for e in explicit_edges}

    result = list(explicit_edges)

    for ai_edge in ai_edges:
        # Check if the reverse direction exists as an explicit edge
        reverse = (ai_edge.to_issue, ai_edge.from_issue)
        if reverse in explicit_pairs:
            # Conflict: explicit wins, discard AI edge
            logger.debug(
                "Discarding AI edge #%d -> #%d (conflicts with explicit #%d -> #%d)",
                ai_edge.from_issue,
                ai_edge.to_issue,
                reverse[0],
                reverse[1],
            )
            continue

        # No conflict: also skip duplicates
        pair = (ai_edge.from_issue, ai_edge.to_issue)
        if pair not in explicit_pairs:
            result.append(ai_edge)

    return result
