"""Unit and property tests for graph analyzer functions.

Test Spec: TS-122-4, TS-122-7, TS-122-9, TS-122-11 (unit)
           TS-122-E3, TS-122-E5, TS-122-E6 (edge cases)
           TS-122-P1 through TS-122-P4, TS-122-P6, TS-122-P7, TS-122-P8 (property)
Requirements: 122-REQ-2.1, 122-REQ-3.1, 122-REQ-4.1, 122-REQ-4.3
Properties: 1 (phase completeness), 2 (phase ordering), 3 (path valid),
            4 (path longest), 6 (edge grouping), 7 (path determinism),
            8 (phase determinism)
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.graph.analyzer import compute_phases, critical_path, group_edges
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

# -- Helpers ----------------------------------------------------------------


def _node(node_id: str, spec_name: str = "spec", group_number: int = 1) -> Node:
    """Create a minimal Node for testing."""
    return Node(
        id=node_id,
        spec_name=spec_name,
        group_number=group_number,
        title=f"Task {node_id}",
        optional=False,
    )


def _graph(
    node_ids: list[str],
    edges: list[tuple[str, str, str]],
    *,
    spec_name: str = "spec",
) -> TaskGraph:
    """Build a TaskGraph from compact definitions.

    Args:
        node_ids: List of node ID strings.
        edges: List of (source, target, kind) tuples.
        spec_name: Default spec name for nodes.
    """
    nodes = {nid: _node(nid, spec_name=spec_name, group_number=i + 1) for i, nid in enumerate(node_ids)}
    edge_objs = [Edge(source=s, target=t, kind=k) for s, t, k in edges]
    return TaskGraph(
        nodes=nodes,
        edges=edge_objs,
        order=node_ids,  # Provide a valid order for the tests
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _diamond_graph() -> TaskGraph:
    """Diamond DAG: A -> B, A -> C, B -> D, C -> D."""
    return _graph(
        ["A", "B", "C", "D"],
        [
            ("A", "B", "intra_spec"),
            ("A", "C", "intra_spec"),
            ("B", "D", "intra_spec"),
            ("C", "D", "intra_spec"),
        ],
    )


def _graph_with_long_branch() -> TaskGraph:
    """Diamond + extra chain: A->B->D, A->C->D, A->B->E->F.

    Critical path: A -> B -> E -> F (length 4).
    """
    nodes = {
        "A": _node("A"),
        "B": _node("B"),
        "C": _node("C"),
        "D": _node("D"),
        "E": _node("E"),
        "F": _node("F"),
    }
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="A", target="C", kind="intra_spec"),
        Edge(source="B", target="D", kind="intra_spec"),
        Edge(source="C", target="D", kind="intra_spec"),
        Edge(source="B", target="E", kind="intra_spec"),
        Edge(source="E", target="F", kind="intra_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["A", "B", "C", "D", "E", "F"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _mixed_edge_graph() -> TaskGraph:
    """Graph with both intra-spec and cross-spec edges.

    01_alpha:1 -> 01_alpha:2 (intra_spec)
    01_alpha:2 -> 01_alpha:3 (intra_spec)
    01_alpha:2 -> 02_beta:1 (cross_spec)
    02_beta:1 -> 02_beta:2 (intra_spec)
    """
    nodes = {
        "01_alpha:1": _node("01_alpha:1", spec_name="01_alpha", group_number=1),
        "01_alpha:2": _node("01_alpha:2", spec_name="01_alpha", group_number=2),
        "01_alpha:3": _node("01_alpha:3", spec_name="01_alpha", group_number=3),
        "02_beta:1": _node("02_beta:1", spec_name="02_beta", group_number=1),
        "02_beta:2": _node("02_beta:2", spec_name="02_beta", group_number=2),
    }
    edges = [
        Edge(source="01_alpha:1", target="01_alpha:2", kind="intra_spec"),
        Edge(source="01_alpha:2", target="01_alpha:3", kind="intra_spec"),
        Edge(source="01_alpha:2", target="02_beta:1", kind="cross_spec"),
        Edge(source="02_beta:1", target="02_beta:2", kind="intra_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["01_alpha:1", "01_alpha:2", "01_alpha:3", "02_beta:1", "02_beta:2"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


# -- Hypothesis strategies for random DAGs ----------------------------------


@st.composite
def random_dags(draw: st.DrawFn, min_nodes: int = 1, max_nodes: int = 50) -> TaskGraph:
    """Generate random acyclic TaskGraphs.

    Nodes are numbered 0..N-1. Edges only go from lower to higher index,
    guaranteeing acyclicity.
    """
    n = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    node_ids = [f"n{i}" for i in range(n)]

    nodes = {nid: _node(nid, group_number=i + 1) for i, nid in enumerate(node_ids)}

    edges: list[Edge] = []
    for i in range(n):
        for j in range(i + 1, n):
            if draw(st.booleans()):
                edges.append(Edge(source=node_ids[i], target=node_ids[j], kind="intra_spec"))

    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=node_ids,  # Index order is a valid topological order
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


@st.composite
def random_dags_with_mixed_edges(draw: st.DrawFn) -> TaskGraph:
    """Generate random DAGs with a mix of intra_spec and cross_spec edges."""
    n = draw(st.integers(min_value=1, max_value=30))
    node_ids = [f"n{i}" for i in range(n)]
    spec_names = ["spec_a", "spec_b"]

    nodes = {}
    for i, nid in enumerate(node_ids):
        spec = draw(st.sampled_from(spec_names))
        nodes[nid] = _node(nid, spec_name=spec, group_number=i + 1)

    edges: list[Edge] = []
    for i in range(n):
        for j in range(i + 1, n):
            if draw(st.booleans()):
                src_spec = nodes[node_ids[i]].spec_name
                tgt_spec = nodes[node_ids[j]].spec_name
                kind = "intra_spec" if src_spec == tgt_spec else "cross_spec"
                edges.append(Edge(source=node_ids[i], target=node_ids[j], kind=kind))

    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=node_ids,
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


# ===========================================================================
# Unit Tests
# ===========================================================================


class TestComputePhasesDiamond:
    """TS-122-4: compute_phases with diamond graph.

    Requirement: 122-REQ-2.1
    """

    def test_diamond_produces_three_phases(self) -> None:
        """Diamond A->B, A->C, B->D, C->D gives 3 phases."""
        graph = _diamond_graph()
        phases = compute_phases(graph)
        assert len(phases) == 3

    def test_diamond_phase_zero_contains_source(self) -> None:
        """Phase 0 contains only the source node A."""
        graph = _diamond_graph()
        phases = compute_phases(graph)
        assert phases[0].number == 0
        assert phases[0].node_ids == ["A"]

    def test_diamond_phase_one_contains_middle_sorted(self) -> None:
        """Phase 1 contains B and C, sorted lexicographically."""
        graph = _diamond_graph()
        phases = compute_phases(graph)
        assert phases[1].number == 1
        assert phases[1].node_ids == ["B", "C"]

    def test_diamond_phase_two_contains_sink(self) -> None:
        """Phase 2 contains only the sink node D."""
        graph = _diamond_graph()
        phases = compute_phases(graph)
        assert phases[2].number == 2
        assert phases[2].node_ids == ["D"]


class TestGroupEdges:
    """TS-122-7: group_edges partitions edges by kind.

    Requirement: 122-REQ-3.1
    """

    def test_mixed_edges_partitioned(self) -> None:
        """Graph with 3 intra-spec + 1 cross-spec edge is split correctly."""
        graph = _mixed_edge_graph()
        grouped = group_edges(graph)
        assert len(grouped.intra_spec) == 3
        assert len(grouped.cross_spec) == 1

    def test_all_intra_spec(self) -> None:
        """Graph with only intra-spec edges has empty cross-spec list."""
        graph = _diamond_graph()
        grouped = group_edges(graph)
        assert len(grouped.intra_spec) == 4
        assert len(grouped.cross_spec) == 0

    def test_grouped_edges_preserve_all(self) -> None:
        """Total of grouped edges equals total edges in graph."""
        graph = _mixed_edge_graph()
        grouped = group_edges(graph)
        assert len(grouped.intra_spec) + len(grouped.cross_spec) == len(graph.edges)


class TestCriticalPathLongest:
    """TS-122-9: critical_path finds the longest path.

    Requirement: 122-REQ-4.1
    """

    def test_longest_path_in_branching_graph(self) -> None:
        """Graph with A->B->E->F (len 4) vs A->B->D (len 3): picks length 4."""
        graph = _graph_with_long_branch()
        path = critical_path(graph)
        assert path == ["A", "B", "E", "F"]
        assert len(path) == 4

    def test_linear_chain_is_critical_path(self) -> None:
        """Linear chain A->B->C has critical path [A, B, C]."""
        graph = _graph(
            ["A", "B", "C"],
            [("A", "B", "intra_spec"), ("B", "C", "intra_spec")],
        )
        path = critical_path(graph)
        assert path == ["A", "B", "C"]


class TestCriticalPathDeterministic:
    """TS-122-11: critical_path deterministic tie-break.

    Requirement: 122-REQ-4.3
    """

    def test_diamond_picks_lexicographic_path(self) -> None:
        """Diamond A->B->D and A->C->D, both length 3: picks A->B->D (B < C)."""
        graph = _diamond_graph()
        path1 = critical_path(graph)
        path2 = critical_path(graph)
        assert path1 == path2
        assert path1 == ["A", "B", "D"]

    def test_repeated_calls_same_result(self) -> None:
        """Multiple calls on same graph always produce identical path."""
        graph = _graph_with_long_branch()
        results = [critical_path(graph) for _ in range(5)]
        assert all(r == results[0] for r in results)


# ===========================================================================
# Edge Case Tests
# ===========================================================================


class TestSingleNodePhases:
    """TS-122-E3: Single node graph produces one phase.

    Requirement: 122-REQ-2.E1
    """

    def test_single_node_one_phase(self) -> None:
        """Graph with one node gives one phase containing that node."""
        graph = _graph(["A"], [])
        phases = compute_phases(graph)
        assert len(phases) == 1
        assert phases[0].node_ids == ["A"]
        assert phases[0].number == 0


class TestSingleNodeCriticalPath:
    """TS-122-E5: Single node critical path.

    Requirement: 122-REQ-4.E1
    """

    def test_single_node_path_length_one(self) -> None:
        """Single-node graph has critical path of length 1."""
        graph = _graph(["A"], [])
        path = critical_path(graph)
        assert path == ["A"]


class TestEmptyGraphCriticalPath:
    """TS-122-E6: Empty graph critical path.

    Requirement: 122-REQ-4.E2
    """

    def test_empty_graph_returns_empty_path(self) -> None:
        """Empty graph (no nodes) returns empty critical path."""
        graph = TaskGraph(
            nodes={},
            edges=[],
            order=[],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )
        path = critical_path(graph)
        assert path == []


# ===========================================================================
# Property Tests
# ===========================================================================


class TestPropertyPhaseCompleteness:
    """TS-122-P1: Phase completeness.

    Property 1: All nodes appear in exactly one phase.
    Validates: 122-REQ-2.1
    """

    @given(graph=random_dags())
    @settings(max_examples=50)
    def test_property_phase_completeness(self, graph: TaskGraph) -> None:
        """Union of all phase node_ids equals set of graph.order, no duplicates."""
        phases = compute_phases(graph)
        all_ids = [nid for p in phases for nid in p.node_ids]
        assert set(all_ids) == set(graph.order)
        assert len(all_ids) == len(set(all_ids))  # no duplicates


class TestPropertyPhaseOrdering:
    """TS-122-P2: Phase ordering respects dependencies.

    Property 2: For every edge (A->B), A is in an earlier phase than B.
    Validates: 122-REQ-2.1
    """

    @given(graph=random_dags(min_nodes=2))
    @settings(max_examples=50)
    def test_property_phase_ordering(self, graph: TaskGraph) -> None:
        """Source of every edge is in a strictly earlier phase than target."""
        phases = compute_phases(graph)
        phase_of = {nid: p.number for p in phases for nid in p.node_ids}
        for edge in graph.edges:
            assert phase_of[edge.source] < phase_of[edge.target], (
                f"Edge {edge.source} -> {edge.target}: "
                f"phase {phase_of[edge.source]} not < phase {phase_of[edge.target]}"
            )


class TestPropertyPathValid:
    """TS-122-P3: Critical path is valid path.

    Property 3: Every consecutive pair in the critical path is connected by an edge.
    Validates: 122-REQ-4.1
    """

    @given(graph=random_dags())
    @settings(max_examples=50)
    def test_property_path_valid(self, graph: TaskGraph) -> None:
        """Each consecutive pair in critical path has an edge in the graph."""
        path = critical_path(graph)
        edge_set = {(e.source, e.target) for e in graph.edges}
        for i in range(len(path) - 1):
            assert (path[i], path[i + 1]) in edge_set, f"No edge from {path[i]} to {path[i + 1]}"


class TestPropertyPathLongest:
    """TS-122-P4: Critical path is longest.

    Property 4: No source-to-sink path is longer than the critical path.
    Validates: 122-REQ-4.1, 122-REQ-4.3
    """

    @given(graph=random_dags(min_nodes=1, max_nodes=30))
    @settings(max_examples=30)
    def test_property_path_longest(self, graph: TaskGraph) -> None:
        """Critical path length >= every other source-to-sink path."""
        cp = critical_path(graph)
        cp_len = len(cp)

        # Build adjacency list
        adj: dict[str, list[str]] = {nid: [] for nid in graph.order}
        in_degree: dict[str, int] = {nid: 0 for nid in graph.order}
        for e in graph.edges:
            adj[e.source].append(e.target)
            in_degree[e.target] = in_degree.get(e.target, 0) + 1

        sources = [nid for nid in graph.order if in_degree.get(nid, 0) == 0]
        sinks = {nid for nid in graph.order if not adj[nid]}

        # DFS to find all source-to-sink paths (feasible for small graphs)
        def all_paths_from(node: str, current: list[str]) -> list[list[str]]:
            if node in sinks:
                return [current[:]]
            paths: list[list[str]] = []
            for nxt in adj[node]:
                current.append(nxt)
                paths.extend(all_paths_from(nxt, current))
                current.pop()
            return paths

        for src in sources:
            for p in all_paths_from(src, [src]):
                assert cp_len >= len(p), (
                    f"Found path {p} (len {len(p)}) longer than critical path {cp} (len {cp_len})"
                )


class TestPropertyEdgeGrouping:
    """TS-122-P6: Edge grouping exhaustive.

    Property 6: len(intra_spec) + len(cross_spec) == len(graph.edges).
    Validates: 122-REQ-3.1
    """

    @given(graph=random_dags_with_mixed_edges())
    @settings(max_examples=50)
    def test_property_edge_grouping(self, graph: TaskGraph) -> None:
        """All edges are accounted for in exactly one group."""
        grouped = group_edges(graph)
        assert len(grouped.intra_spec) + len(grouped.cross_spec) == len(graph.edges)


class TestPropertyPathDeterminism:
    """TS-122-P7: Critical path determinism.

    Property 7: Two calls on same graph return identical results.
    Validates: 122-REQ-4.3
    """

    @given(graph=random_dags())
    @settings(max_examples=50)
    def test_property_path_determinism(self, graph: TaskGraph) -> None:
        """critical_path(g) == critical_path(g) for the same g."""
        assert critical_path(graph) == critical_path(graph)


class TestPropertyPhaseDeterminism:
    """TS-122-P8: Phase determinism.

    Property 8: Two calls on same graph return identical results.
    Validates: 122-REQ-2.1
    """

    @given(graph=random_dags())
    @settings(max_examples=50)
    def test_property_phase_determinism(self, graph: TaskGraph) -> None:
        """compute_phases(g) == compute_phases(g) for the same g."""
        p1 = compute_phases(graph)
        p2 = compute_phases(graph)
        assert len(p1) == len(p2)
        for phase_a, phase_b in zip(p1, p2):
            assert phase_a.number == phase_b.number
            assert phase_a.node_ids == phase_b.node_ids
