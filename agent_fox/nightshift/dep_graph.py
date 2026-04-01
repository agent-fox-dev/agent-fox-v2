"""Dependency graph: construction, cycle detection, topological sort.

Requirements: 71-REQ-4.1, 71-REQ-4.2, 71-REQ-4.3, 71-REQ-4.E1,
              71-REQ-2.E2, 71-REQ-6.3
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_fox.platform.github import IssueResult


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

    Ties broken by ascending issue number. Cycles broken by removing the
    edge pointing to the oldest issue in the cycle.
    Returns list of issue numbers in processing order.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("build_graph not yet implemented")


def detect_cycles(edges: list[DependencyEdge]) -> list[list[int]]:
    """Find all cycles in the dependency graph.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("detect_cycles not yet implemented")


def merge_edges(
    explicit_edges: list[DependencyEdge],
    ai_edges: list[DependencyEdge],
) -> list[DependencyEdge]:
    """Merge explicit and AI-detected edges, explicit wins on conflict.

    NOT YET IMPLEMENTED — stub for task group 1 tests.
    """
    raise NotImplementedError("merge_edges not yet implemented")
