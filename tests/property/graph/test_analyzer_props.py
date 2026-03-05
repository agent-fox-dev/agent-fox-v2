"""Property tests for plan analyzer.

Test Spec: TS-20-P1 through TS-20-P5
Properties: Properties 1-5 from design.md
Requirements: 20-REQ-1.2, 20-REQ-2.1, 20-REQ-2.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.graph.analyzer import analyze_plan
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph

# -- Hypothesis strategy for generating random DAGs ---------------------------


@st.composite
def random_dags(draw: st.DrawFn) -> TaskGraph:
    """Generate random acyclic task graphs with 1-30 nodes.

    Nodes are numbered 1..N. Edges only go from lower to higher IDs,
    guaranteeing acyclicity.
    """
    n = draw(st.integers(min_value=1, max_value=30))
    spec_name = "test_spec"

    nodes = []
    for i in range(1, n + 1):
        node_id = f"{spec_name}:{i}"
        nodes.append(
            Node(
                id=node_id,
                spec_name=spec_name,
                group_number=i,
                title=f"Task {i}",
                optional=False,
            )
        )

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
    order = [n.id for n in nodes]  # valid topological order (ascending IDs)
    return TaskGraph(
        nodes=node_map,
        edges=edges,
        order=order,
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


# -- TS-20-P1: Phase completeness ---------------------------------------------


class TestPhaseCompleteness:
    """TS-20-P1: Every node appears in exactly one phase.

    Property 1: Union of all phase node_ids equals set of all graph node IDs.
    Validates: 20-REQ-1.2
    """

    @given(dag=random_dags())
    @settings(max_examples=50)
    def test_all_nodes_covered_no_duplicates(self, dag: TaskGraph) -> None:
        analysis = analyze_plan(dag)
        all_phase_nodes: set[str] = set()
        for phase in analysis.phases:
            overlap = all_phase_nodes & set(phase.node_ids)
            assert len(overlap) == 0, f"Duplicate nodes in phases: {overlap}"
            all_phase_nodes |= set(phase.node_ids)
        assert all_phase_nodes == set(dag.nodes.keys())


# -- TS-20-P2: Phase ordering respects dependencies ---------------------------


class TestPhaseOrderingRespectsDependencies:
    """TS-20-P2: For every edge, source phase < target phase.

    Property 2: Dependencies are respected by phase assignment.
    Validates: 20-REQ-1.2
    """

    @given(dag=random_dags())
    @settings(max_examples=50)
    def test_source_phase_before_target_phase(self, dag: TaskGraph) -> None:
        analysis = analyze_plan(dag)
        node_to_phase: dict[str, int] = {}
        for phase in analysis.phases:
            for nid in phase.node_ids:
                node_to_phase[nid] = phase.phase_number
        for edge in dag.edges:
            assert node_to_phase[edge.source] < node_to_phase[edge.target], (
                f"Edge {edge.source} -> {edge.target}: "
                f"phase {node_to_phase[edge.source]} >= {node_to_phase[edge.target]}"
            )


# -- TS-20-P3: Critical path equals makespan ----------------------------------


class TestCriticalPathEqualsMakespan:
    """TS-20-P3: Critical path length equals number of phases.

    Property 3: The critical path determines the makespan.
    Validates: 20-REQ-2.1
    """

    @given(dag=random_dags())
    @settings(max_examples=50)
    def test_critical_path_length_equals_phases(self, dag: TaskGraph) -> None:
        analysis = analyze_plan(dag)
        assert analysis.critical_path_length == analysis.total_phases


# -- TS-20-P4: Zero float implies critical path membership --------------------


class TestZeroFloatImpliesCriticalPath:
    """TS-20-P4: Nodes with float 0 are on the critical path and vice versa.

    Property 4: {n | float(n) == 0} == set(critical_path)
    Validates: 20-REQ-2.3
    """

    @given(dag=random_dags())
    @settings(max_examples=50)
    def test_zero_float_equals_critical_path(self, dag: TaskGraph) -> None:
        analysis = analyze_plan(dag)
        zero_float = {
            nid for nid, t in analysis.timings.items() if t.float == 0
        }
        assert zero_float == set(analysis.critical_path)


# -- TS-20-P5: Float is non-negative ------------------------------------------


class TestFloatNonNegative:
    """TS-20-P5: No node has negative float.

    Property 5: All float values >= 0.
    Validates: 20-REQ-2.3
    """

    @given(dag=random_dags())
    @settings(max_examples=50)
    def test_all_floats_non_negative(self, dag: TaskGraph) -> None:
        analysis = analyze_plan(dag)
        for nid, timing in analysis.timings.items():
            assert timing.float >= 0, f"Node {nid} has negative float: {timing.float}"
