"""Plan analysis functions: parallelism phases, critical path, edge grouping.

Pure functions that operate on a resolved TaskGraph to compute
analysis data for the --dry-run flag.

Requirements: 122-REQ-2.1, 122-REQ-3.1, 122-REQ-4.1, 122-REQ-4.3
"""

from __future__ import annotations

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

    Requirements: 122-REQ-2.1
    """
    raise NotImplementedError("compute_phases not yet implemented")


def critical_path(graph: TaskGraph) -> list[str]:
    """Compute the longest path through the DAG (uniform edge weights).

    Requirements: 122-REQ-4.1, 122-REQ-4.3
    """
    raise NotImplementedError("critical_path not yet implemented")


def group_edges(graph: TaskGraph) -> GroupedEdges:
    """Partition graph edges by kind (intra_spec vs cross_spec).

    Requirements: 122-REQ-3.1
    """
    raise NotImplementedError("group_edges not yet implemented")
