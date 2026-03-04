"""Dependency resolver tests.

Test Spec: TS-02-7 (topological sort), TS-02-E4 (cycle detection)
Requirements: 02-REQ-4.1, 02-REQ-4.2, 02-REQ-3.E2
"""

from __future__ import annotations

import pytest

from agent_fox.core.errors import PlanError
from agent_fox.graph.resolver import resolve_order
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph


class TestTopologicalSort:
    """TS-02-7: Topological sort produces valid order."""

    def test_linear_chain_order(self, simple_acyclic_graph: TaskGraph) -> None:
        """Linear chain A -> B -> C yields [A, B, C]."""
        order = resolve_order(simple_acyclic_graph)

        assert order.index("spec:1") < order.index("spec:2")
        assert order.index("spec:2") < order.index("spec:3")

    def test_all_nodes_in_order(self, simple_acyclic_graph: TaskGraph) -> None:
        """All nodes appear in the ordering."""
        order = resolve_order(simple_acyclic_graph)

        assert len(order) == 3
        assert set(order) == {"spec:1", "spec:2", "spec:3"}

    def test_diamond_order(self, diamond_acyclic_graph: TaskGraph) -> None:
        """Diamond graph respects all edges."""
        order = resolve_order(diamond_acyclic_graph)

        # A before B and C; B and C before D
        assert order.index("spec:1") < order.index("spec:2")
        assert order.index("spec:1") < order.index("spec:3")
        assert order.index("spec:2") < order.index("spec:4")
        assert order.index("spec:3") < order.index("spec:4")

    def test_deterministic_tie_breaking(self) -> None:
        """When nodes have no dependency, order by spec prefix then group number."""
        nodes = [
            Node(
                id="02_beta:1",
                spec_name="02_beta",
                group_number=1,
                title="Beta 1",
                optional=False,
            ),
            Node(
                id="01_alpha:1",
                spec_name="01_alpha",
                group_number=1,
                title="Alpha 1",
                optional=False,
            ),
        ]
        graph = TaskGraph(
            nodes={n.id: n for n in nodes},
            edges=[],
            order=[],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )

        order = resolve_order(graph)

        # alpha (prefix 01) should come before beta (prefix 02)
        assert order.index("01_alpha:1") < order.index("02_beta:1")

    def test_cross_spec_ordering(self, cross_spec_graph: TaskGraph) -> None:
        """Cross-spec edges are respected in ordering."""
        order = resolve_order(cross_spec_graph)

        assert order.index("01_alpha:2") < order.index("02_beta:1")

    def test_empty_graph_produces_empty_order(self) -> None:
        """Empty graph (no nodes) produces empty ordering."""
        graph = TaskGraph(
            nodes={},
            edges=[],
            order=[],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )

        order = resolve_order(graph)

        assert order == []


class TestCycleDetection:
    """TS-02-E4: Cycle in dependency graph raises PlanError."""

    def test_cycle_raises_plan_error(self, cyclic_graph: TaskGraph) -> None:
        """Cyclic graph raises PlanError."""
        with pytest.raises(PlanError):
            resolve_order(cyclic_graph)

    def test_cycle_error_mentions_nodes(self, cyclic_graph: TaskGraph) -> None:
        """PlanError lists at least two node IDs from the cycle."""
        with pytest.raises(PlanError) as exc_info:
            resolve_order(cyclic_graph)

        error_msg = str(exc_info.value)
        # At least two cycle nodes should be mentioned
        node_ids = ["spec:1", "spec:2", "spec:3"]
        mentioned = sum(1 for nid in node_ids if nid in error_msg)
        assert mentioned >= 2, (
            f"Expected at least 2 cycle node IDs in error, got: {error_msg!r}"
        )

    def test_self_loop_raises_plan_error(self) -> None:
        """A self-loop (A -> A) raises PlanError."""
        nodes = [
            Node(
                id="spec:1",
                spec_name="spec",
                group_number=1,
                title="Task A",
                optional=False,
            ),
        ]
        edges = [Edge(source="spec:1", target="spec:1", kind="intra_spec")]
        graph = TaskGraph(
            nodes={n.id: n for n in nodes},
            edges=edges,
            order=[],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )

        with pytest.raises(PlanError):
            resolve_order(graph)
