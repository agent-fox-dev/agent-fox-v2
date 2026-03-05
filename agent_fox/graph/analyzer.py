"""Plan analyzer: parallelism analysis, critical path, and float computation.

Stub module -- implementation pending (task groups 2+).

Requirements: 20-REQ-1.*, 20-REQ-2.*
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_fox.graph.types import TaskGraph


@dataclass(frozen=True)
class NodeTiming:
    """Scheduling metadata for a single node."""

    node_id: str
    earliest_start: int
    latest_start: int
    float: int


@dataclass(frozen=True)
class Phase:
    """A set of nodes that can execute concurrently."""

    phase_number: int
    earliest_start: int
    node_ids: list[str]

    @property
    def worker_count(self) -> int:
        return len(self.node_ids)


@dataclass(frozen=True)
class PlanAnalysis:
    """Complete analysis result."""

    phases: list[Phase]
    critical_path: list[str]
    critical_path_length: int
    peak_parallelism: int
    total_nodes: int
    total_phases: int
    timings: dict[str, NodeTiming]
    has_alternative_critical_paths: bool


def analyze_plan(graph: TaskGraph) -> PlanAnalysis:
    """Compute parallelism phases, critical path, and float for all nodes.

    Stub -- raises NotImplementedError until task group 2.
    """
    raise NotImplementedError("analyze_plan not yet implemented")


def format_analysis(analysis: PlanAnalysis, graph: TaskGraph) -> str:
    """Format the analysis result for terminal display.

    Stub -- raises NotImplementedError until task group 2.
    """
    raise NotImplementedError("format_analysis not yet implemented")
