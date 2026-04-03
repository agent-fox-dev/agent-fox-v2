"""Core graph data models: Node, Edge, TaskGraph, NodeStatus.

Requirements: 02-REQ-3.3, 02-REQ-3.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class NodeStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class Node:
    """A task graph node representing a single task group."""

    id: str  # "{spec_name}:{group_number}"
    spec_name: str  # e.g., "02_planning_engine"
    group_number: int  # e.g., 1
    title: str  # human-readable title
    optional: bool  # True if marked optional
    status: NodeStatus = NodeStatus.PENDING
    subtask_count: int = 0  # number of subtasks
    body: str = ""  # raw task body for context
    archetype: str = "coder"  # 26-REQ-4.1
    instances: int = 1  # 26-REQ-4.1


@dataclass(frozen=True)
class Edge:
    """A directed dependency edge: source must complete before target."""

    source: str  # node ID that must complete first
    target: str  # node ID that depends on source
    kind: str  # "intra_spec" or "cross_spec"


@dataclass
class PlanMetadata:
    """Metadata about the generated plan."""

    created_at: str  # ISO 8601 timestamp
    fast_mode: bool = False
    filtered_spec: str | None = None
    version: str = ""  # agent-fox version


@dataclass
class TaskGraph:
    """The complete task graph with nodes, edges, and metadata."""

    nodes: dict[str, Node]  # node_id -> Node
    edges: list[Edge]  # all dependency edges
    order: list[str]  # topologically sorted node IDs
    metadata: PlanMetadata = field(default_factory=lambda: PlanMetadata(created_at=datetime.now().isoformat()))

    def predecessors(self, node_id: str) -> list[str]:
        """Return IDs of all direct predecessors of a node."""
        return [e.source for e in self.edges if e.target == node_id]

    def successors(self, node_id: str) -> list[str]:
        """Return IDs of all direct successors of a node."""
        return [e.target for e in self.edges if e.source == node_id]
