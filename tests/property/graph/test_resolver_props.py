"""Property tests for dependency resolver.

Test Spec: TS-02-P1 (topological order validity), TS-02-P4 (cycle detection)
Properties: Property 1 (topo order), Property 4 (cycle detection) from design.md
Requirements: 02-REQ-4.1, 02-REQ-3.E2
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.errors import PlanError
from agent_fox.graph.resolver import resolve_order
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

# -- Hypothesis strategies for generating DAGs --------------------------------


def _node_strategy(node_id: str, spec_name: str, group_number: int) -> Node:
    """Create a node with given parameters."""
    return Node(
        id=node_id,
        spec_name=spec_name,
        group_number=group_number,
        title=f"Task {node_id}",
        optional=False,
    )


@st.composite
def acyclic_graphs(draw: st.DrawFn) -> TaskGraph:
    """Generate random acyclic task graphs with 1-20 nodes.

    Nodes are numbered 1..N in a single spec. Edges only go from
    lower to higher IDs, guaranteeing acyclicity.
    """
    n = draw(st.integers(min_value=1, max_value=20))
    spec_name = "test_spec"

    nodes = []
    for i in range(1, n + 1):
        node_id = f"{spec_name}:{i}"
        nodes.append(_node_strategy(node_id, spec_name, i))

    # Generate edges only from lower to higher (acyclic guarantee)
    edges: list[Edge] = []
    for i in range(1, n + 1):
        for j in range(i + 1, n + 1):
            if draw(st.booleans()):
                edges.append(
                    Edge(
                        source=f"{spec_name}:{i}",
                        target=f"{spec_name}:{j}",
                        kind="intra_spec",
                    )
                )

    node_map = {n.id: n for n in nodes}
    return TaskGraph(
        nodes=node_map,
        edges=edges,
        order=[],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


@st.composite
def cyclic_graphs(draw: st.DrawFn) -> TaskGraph:
    """Generate graphs that always contain a cycle.

    Creates a ring of 2-5 nodes: 1 -> 2 -> ... -> N -> 1.
    """
    n = draw(st.integers(min_value=2, max_value=5))
    spec_name = "cycle_spec"

    nodes = []
    edges: list[Edge] = []
    for i in range(1, n + 1):
        node_id = f"{spec_name}:{i}"
        nodes.append(_node_strategy(node_id, spec_name, i))

        # Edge to next node (wrapping around to create cycle)
        next_id = f"{spec_name}:{(i % n) + 1}"
        edges.append(Edge(source=node_id, target=next_id, kind="intra_spec"))

    node_map = {n.id: n for n in nodes}
    return TaskGraph(
        nodes=node_map,
        edges=edges,
        order=[],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


class TestTopologicalOrderValidity:
    """TS-02-P1: For any acyclic graph, topo order respects all edges.

    Property 1: For any valid task graph (no cycles), the resolve_order()
    function returns an ordering where for every edge (A -> B), A appears
    before B.
    """

    @given(graph=acyclic_graphs())
    @settings(max_examples=50)
    def test_edges_respected_in_order(self, graph: TaskGraph) -> None:
        """For every edge (A -> B), A appears before B in the ordering."""
        order = resolve_order(graph)

        for edge in graph.edges:
            src_idx = order.index(edge.source)
            tgt_idx = order.index(edge.target)
            assert src_idx < tgt_idx, f"Edge {edge.source} -> {edge.target}: source at {src_idx}, target at {tgt_idx}"

    @given(graph=acyclic_graphs())
    @settings(max_examples=50)
    def test_all_nodes_present_in_order(self, graph: TaskGraph) -> None:
        """All nodes appear exactly once in the ordering."""
        order = resolve_order(graph)

        assert set(order) == set(graph.nodes.keys())
        assert len(order) == len(graph.nodes)


class TestCycleDetectionCompleteness:
    """TS-02-P4: Any graph with a cycle raises PlanError.

    Property 4: For any task graph containing a cycle, resolve_order()
    raises a PlanError rather than returning a partial ordering.
    """

    @given(graph=cyclic_graphs())
    @settings(max_examples=50)
    def test_cycle_always_detected(self, graph: TaskGraph) -> None:
        """Cyclic graphs always raise PlanError."""
        with pytest.raises(PlanError):
            resolve_order(graph)
