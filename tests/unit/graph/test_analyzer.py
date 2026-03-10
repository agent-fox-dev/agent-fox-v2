"""Unit tests for plan analyzer: phase grouping, critical path, float.

Test Spec: TS-20-1 through TS-20-7, TS-20-E1
Requirements: 20-REQ-1.*, 20-REQ-2.*
"""

from __future__ import annotations

from agent_fox.graph.resolver import analyze_plan
from agent_fox.graph.types import TaskGraph


class TestPhaseGroupingDiamond:
    """TS-20-1: Phase grouping on a diamond graph.

    Requirements: 20-REQ-1.2, 20-REQ-1.3
    Diamond: A -> B, A -> C, B -> D, C -> D
    Expected: Phase 1=[A], Phase 2=[B,C], Phase 3=[D]
    """

    def test_phase_count(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert len(analysis.phases) == 3

    def test_phase_1_contains_A(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert set(analysis.phases[0].node_ids) == {"A"}

    def test_phase_2_contains_B_C(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert set(analysis.phases[1].node_ids) == {"B", "C"}

    def test_phase_2_worker_count(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.phases[1].worker_count == 2

    def test_phase_3_contains_D(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert set(analysis.phases[2].node_ids) == {"D"}


class TestPhaseGroupingChain:
    """TS-20-2: Phase grouping on a linear chain.

    Requirements: 20-REQ-1.2, 20-REQ-1.E2
    Chain: A -> B -> C -> D
    Expected: 4 phases, each with 1 node, peak parallelism 1.
    """

    def test_phase_count(self, analyzer_chain_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_chain_graph)
        assert len(analysis.phases) == 4

    def test_all_phases_have_one_worker(self, analyzer_chain_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_chain_graph)
        assert all(p.worker_count == 1 for p in analysis.phases)

    def test_peak_parallelism_is_one(self, analyzer_chain_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_chain_graph)
        assert analysis.peak_parallelism == 1


class TestPeakParallelismWide:
    """TS-20-3: Peak parallelism on a wide graph.

    Requirements: 20-REQ-1.4
    Wide: A -> {B, C, D, E} -> F
    Expected: peak parallelism 4, total phases 3.
    """

    def test_peak_parallelism(self, analyzer_wide_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_wide_graph)
        assert analysis.peak_parallelism == 4

    def test_total_phases(self, analyzer_wide_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_wide_graph)
        assert analysis.total_phases == 3


class TestCriticalPathDiamond:
    """TS-20-4: Critical path on a diamond graph.

    Requirements: 20-REQ-2.1, 20-REQ-2.2
    Diamond: A -> B -> D, A -> C -> D
    Expected: critical path length 3, starts with A, ends with D.
    """

    def test_critical_path_length(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.critical_path_length == 3

    def test_critical_path_node_count(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert len(analysis.critical_path) == 3

    def test_critical_path_start(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.critical_path[0] == "A"

    def test_critical_path_end(self, analyzer_diamond_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.critical_path[-1] == "D"


class TestFloatOnCriticalPath:
    """TS-20-5: Float computation on all-critical graph.

    Requirements: 20-REQ-2.3
    Graph: A -> B -> C -> D, A -> D (shortcut)
    Critical path: A -> B -> C -> D (length 4). All nodes have float 0.
    """

    def test_all_float_zero(self, analyzer_shortcut_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_shortcut_graph)
        assert analysis.timings["A"].slack == 0
        assert analysis.timings["B"].slack == 0
        assert analysis.timings["C"].slack == 0
        assert analysis.timings["D"].slack == 0


class TestFloatOnNonCriticalNodes:
    """TS-20-6: Float on non-critical nodes.

    Requirements: 20-REQ-2.3, 20-REQ-2.4
    Graph: A -> B -> C -> F, A -> D -> F, A -> E -> F
    Critical path: A -> B -> C -> F (length 4).
    D and E have float > 0.
    """

    def test_non_critical_float_positive(self, analyzer_float_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_float_graph)
        assert analysis.timings["D"].slack > 0
        assert analysis.timings["E"].slack > 0

    def test_critical_float_zero(self, analyzer_float_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_float_graph)
        assert analysis.timings["A"].slack == 0
        assert analysis.timings["B"].slack == 0
        assert analysis.timings["C"].slack == 0
        assert analysis.timings["F"].slack == 0


class TestEmptyGraphAnalysis:
    """TS-20-7: Empty graph analysis.

    Requirements: 20-REQ-1.E1
    Empty graph should produce empty analysis.
    """

    def test_zero_phases(self, analyzer_empty_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_empty_graph)
        assert analysis.total_phases == 0

    def test_zero_critical_path(self, analyzer_empty_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_empty_graph)
        assert analysis.critical_path_length == 0

    def test_zero_peak_parallelism(self, analyzer_empty_graph: TaskGraph) -> None:
        analysis = analyze_plan(analyzer_empty_graph)
        assert analysis.peak_parallelism == 0


class TestTiedCriticalPaths:
    """TS-20-E1: Tied critical paths.

    Requirements: 20-REQ-2.E1
    Diamond graph has two paths of equal length (A->B->D and A->C->D).
    """

    def test_has_alternative_critical_paths(
        self, analyzer_diamond_graph: TaskGraph
    ) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.has_alternative_critical_paths is True

    def test_critical_path_length_still_correct(
        self, analyzer_diamond_graph: TaskGraph
    ) -> None:
        analysis = analyze_plan(analyzer_diamond_graph)
        assert analysis.critical_path_length == 3
