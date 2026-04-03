"""Fixtures for graph builder, resolver, and fast-mode tests.

Builds sample TaskGraph objects: acyclic, cyclic, with optional nodes.
"""

from __future__ import annotations

import pytest

from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

# -- Helper to build graphs from compact definitions -----------------------


def make_graph(
    nodes: list[Node],
    edges: list[Edge],
    order: list[str] | None = None,
) -> TaskGraph:
    """Create a TaskGraph from nodes and edges.

    Args:
        nodes: List of Node objects.
        edges: List of Edge objects.
        order: Pre-computed order; empty list by default.
    """
    node_map = {n.id: n for n in nodes}
    return TaskGraph(
        nodes=node_map,
        edges=edges,
        order=order if order is not None else [],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


# -- Fixtures: simple acyclic graph -----------------------------------------


@pytest.fixture
def simple_acyclic_graph() -> TaskGraph:
    """A -> B -> C, all required (non-optional).

    Used by TS-02-7 (topo sort), TS-02-8 / TS-02-9 (fast mode base).
    """
    nodes = [
        Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Task A",
            optional=False,
        ),
        Node(
            id="spec:2",
            spec_name="spec",
            group_number=2,
            title="Task B",
            optional=False,
        ),
        Node(
            id="spec:3",
            spec_name="spec",
            group_number=3,
            title="Task C",
            optional=False,
        ),
    ]
    edges = [
        Edge(source="spec:1", target="spec:2", kind="intra_spec"),
        Edge(source="spec:2", target="spec:3", kind="intra_spec"),
    ]
    return make_graph(nodes, edges)


@pytest.fixture
def diamond_acyclic_graph() -> TaskGraph:
    """A -> B, A -> C, B -> D, C -> D (diamond shape).

    Used by TS-02-7 (topo sort with multiple valid orderings).
    """
    nodes = [
        Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Task A",
            optional=False,
        ),
        Node(
            id="spec:2",
            spec_name="spec",
            group_number=2,
            title="Task B",
            optional=False,
        ),
        Node(
            id="spec:3",
            spec_name="spec",
            group_number=3,
            title="Task C",
            optional=False,
        ),
        Node(
            id="spec:4",
            spec_name="spec",
            group_number=4,
            title="Task D",
            optional=False,
        ),
    ]
    edges = [
        Edge(source="spec:1", target="spec:2", kind="intra_spec"),
        Edge(source="spec:1", target="spec:3", kind="intra_spec"),
        Edge(source="spec:2", target="spec:4", kind="intra_spec"),
        Edge(source="spec:3", target="spec:4", kind="intra_spec"),
    ]
    return make_graph(nodes, edges)


# -- Fixtures: cyclic graph --------------------------------------------------


@pytest.fixture
def cyclic_graph() -> TaskGraph:
    """A -> B -> C -> A (cycle).

    Used by TS-02-E4 (cycle detection).
    """
    nodes = [
        Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Task A",
            optional=False,
        ),
        Node(
            id="spec:2",
            spec_name="spec",
            group_number=2,
            title="Task B",
            optional=False,
        ),
        Node(
            id="spec:3",
            spec_name="spec",
            group_number=3,
            title="Task C",
            optional=False,
        ),
    ]
    edges = [
        Edge(source="spec:1", target="spec:2", kind="intra_spec"),
        Edge(source="spec:2", target="spec:3", kind="intra_spec"),
        Edge(source="spec:3", target="spec:1", kind="intra_spec"),
    ]
    return make_graph(nodes, edges)


# -- Fixtures: graph with optional nodes ------------------------------------


@pytest.fixture
def graph_with_optional() -> TaskGraph:
    """A (required) -> B (optional) -> C (required).

    Used by TS-02-8 (fast mode removes optional), TS-02-9 (fast mode rewires).
    """
    nodes = [
        Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Task A",
            optional=False,
        ),
        Node(id="spec:2", spec_name="spec", group_number=2, title="Task B", optional=True),
        Node(
            id="spec:3",
            spec_name="spec",
            group_number=3,
            title="Task C",
            optional=False,
        ),
    ]
    edges = [
        Edge(source="spec:1", target="spec:2", kind="intra_spec"),
        Edge(source="spec:2", target="spec:3", kind="intra_spec"),
    ]
    return make_graph(nodes, edges)


# -- Fixtures: multi-spec graph with cross-spec edges -----------------------


# -- Fixtures: plan analyzer graphs (spec 20) --------------------------------


@pytest.fixture
def analyzer_diamond_graph() -> TaskGraph:
    """Diamond DAG: A -> B, A -> C, B -> D, C -> D.

    Used by TS-20-1 (diamond phases), TS-20-4 (critical path),
    TS-20-E1 (tied critical paths).
    """
    nodes = [
        Node(id="A", spec_name="spec", group_number=1, title="Task A", optional=False),
        Node(id="B", spec_name="spec", group_number=2, title="Task B", optional=False),
        Node(id="C", spec_name="spec", group_number=3, title="Task C", optional=False),
        Node(id="D", spec_name="spec", group_number=4, title="Task D", optional=False),
    ]
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="A", target="C", kind="intra_spec"),
        Edge(source="B", target="D", kind="intra_spec"),
        Edge(source="C", target="D", kind="intra_spec"),
    ]
    return make_graph(nodes, edges, order=["A", "B", "C", "D"])


@pytest.fixture
def analyzer_chain_graph() -> TaskGraph:
    """Linear chain: A -> B -> C -> D.

    Used by TS-20-2 (chain phases).
    """
    nodes = [
        Node(id="A", spec_name="spec", group_number=1, title="Task A", optional=False),
        Node(id="B", spec_name="spec", group_number=2, title="Task B", optional=False),
        Node(id="C", spec_name="spec", group_number=3, title="Task C", optional=False),
        Node(id="D", spec_name="spec", group_number=4, title="Task D", optional=False),
    ]
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="B", target="C", kind="intra_spec"),
        Edge(source="C", target="D", kind="intra_spec"),
    ]
    return make_graph(nodes, edges, order=["A", "B", "C", "D"])


@pytest.fixture
def analyzer_wide_graph() -> TaskGraph:
    """Wide fan-out/in: A -> {B, C, D, E} -> F.

    Used by TS-20-3 (peak parallelism).
    """
    nodes = [
        Node(id="A", spec_name="spec", group_number=1, title="Task A", optional=False),
        Node(id="B", spec_name="spec", group_number=2, title="Task B", optional=False),
        Node(id="C", spec_name="spec", group_number=3, title="Task C", optional=False),
        Node(id="D", spec_name="spec", group_number=4, title="Task D", optional=False),
        Node(id="E", spec_name="spec", group_number=5, title="Task E", optional=False),
        Node(id="F", spec_name="spec", group_number=6, title="Task F", optional=False),
    ]
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="A", target="C", kind="intra_spec"),
        Edge(source="A", target="D", kind="intra_spec"),
        Edge(source="A", target="E", kind="intra_spec"),
        Edge(source="B", target="F", kind="intra_spec"),
        Edge(source="C", target="F", kind="intra_spec"),
        Edge(source="D", target="F", kind="intra_spec"),
        Edge(source="E", target="F", kind="intra_spec"),
    ]
    return make_graph(nodes, edges, order=["A", "B", "C", "D", "E", "F"])


@pytest.fixture
def analyzer_empty_graph() -> TaskGraph:
    """Empty graph with no nodes.

    Used by TS-20-7 (empty graph).
    """
    return make_graph([], [], order=[])


@pytest.fixture
def analyzer_float_graph() -> TaskGraph:
    """Graph with non-critical nodes: A -> B -> C -> F, A -> D -> F, A -> E -> F.

    Critical path: A -> B -> C -> F (length 4).
    D and E have float > 0.

    Used by TS-20-6 (float on non-critical nodes).
    """
    nodes = [
        Node(id="A", spec_name="spec", group_number=1, title="Task A", optional=False),
        Node(id="B", spec_name="spec", group_number=2, title="Task B", optional=False),
        Node(id="C", spec_name="spec", group_number=3, title="Task C", optional=False),
        Node(id="D", spec_name="spec", group_number=4, title="Task D", optional=False),
        Node(id="E", spec_name="spec", group_number=5, title="Task E", optional=False),
        Node(id="F", spec_name="spec", group_number=6, title="Task F", optional=False),
    ]
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="B", target="C", kind="intra_spec"),
        Edge(source="C", target="F", kind="intra_spec"),
        Edge(source="A", target="D", kind="intra_spec"),
        Edge(source="D", target="F", kind="intra_spec"),
        Edge(source="A", target="E", kind="intra_spec"),
        Edge(source="E", target="F", kind="intra_spec"),
    ]
    return make_graph(nodes, edges, order=["A", "B", "C", "D", "E", "F"])


@pytest.fixture
def analyzer_shortcut_graph() -> TaskGraph:
    """Graph with shortcut: A -> B -> C -> D, A -> D.

    All nodes on critical path (A -> B -> C -> D is longest).

    Used by TS-20-5 (float on critical path).
    """
    nodes = [
        Node(id="A", spec_name="spec", group_number=1, title="Task A", optional=False),
        Node(id="B", spec_name="spec", group_number=2, title="Task B", optional=False),
        Node(id="C", spec_name="spec", group_number=3, title="Task C", optional=False),
        Node(id="D", spec_name="spec", group_number=4, title="Task D", optional=False),
    ]
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="B", target="C", kind="intra_spec"),
        Edge(source="C", target="D", kind="intra_spec"),
        Edge(source="A", target="D", kind="intra_spec"),
    ]
    return make_graph(nodes, edges, order=["A", "B", "C", "D"])


# -- Fixtures: multi-spec graph with cross-spec edges -----------------------


@pytest.fixture
def cross_spec_graph() -> TaskGraph:
    """Two specs with cross-spec dependency.

    01_alpha: groups 1, 2
    02_beta: groups 1, 2
    Edge: 01_alpha:2 -> 02_beta:1 (cross_spec)
    Plus intra-spec edges.

    Used by TS-02-6 (cross-spec edges).
    """
    nodes = [
        Node(
            id="01_alpha:1",
            spec_name="01_alpha",
            group_number=1,
            title="Alpha Task 1",
            optional=False,
        ),
        Node(
            id="01_alpha:2",
            spec_name="01_alpha",
            group_number=2,
            title="Alpha Task 2",
            optional=False,
        ),
        Node(
            id="02_beta:1",
            spec_name="02_beta",
            group_number=1,
            title="Beta Task 1",
            optional=False,
        ),
        Node(
            id="02_beta:2",
            spec_name="02_beta",
            group_number=2,
            title="Beta Task 2",
            optional=False,
        ),
    ]
    edges = [
        Edge(source="01_alpha:1", target="01_alpha:2", kind="intra_spec"),
        Edge(source="01_alpha:2", target="02_beta:1", kind="cross_spec"),
        Edge(source="02_beta:1", target="02_beta:2", kind="intra_spec"),
    ]
    return make_graph(nodes, edges)
