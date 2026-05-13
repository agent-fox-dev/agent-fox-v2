"""Unit tests for planner analyze/dry-run features.

Test Spec: TS-122-5, TS-122-6, TS-122-8, TS-122-10 (formatter)
           TS-122-E4 (no cross-spec section)
           TS-122-16, TS-122-17 (run_plan dry_run)
           TS-122-P5 (property: analyze does not persist)
Requirements: 122-REQ-2.2, 122-REQ-2.3, 122-REQ-3.2, 122-REQ-4.2,
              122-REQ-3.E1, 122-REQ-6.1, 122-REQ-6.2
Properties: 5 (analyze does not persist)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_fox.graph.analyzer import (
    GroupedEdges,
    Phase,
    compute_phases,
    critical_path,
    group_edges,
)
from agent_fox.graph.planner import format_plan_analysis, run_plan
from agent_fox.graph.types import Edge, Node, PlanMetadata, TaskGraph
from agent_fox.spec.discovery import SpecInfo

# -- Helpers ----------------------------------------------------------------


def _node(
    node_id: str,
    spec_name: str = "spec",
    group_number: int = 1,
    title: str | None = None,
) -> Node:
    """Create a minimal Node for testing."""
    return Node(
        id=node_id,
        spec_name=spec_name,
        group_number=group_number,
        title=title or f"Task {node_id}",
        optional=False,
    )


def _diamond_graph() -> TaskGraph:
    """Diamond DAG: A -> B, A -> C, B -> D, C -> D."""
    nodes = {
        "A": _node("A", title="Parse specifications"),
        "B": _node("B", title="Build graph"),
        "C": _node("C", title="Resolve ordering"),
        "D": _node("D", title="Final validation"),
    }
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
        Edge(source="A", target="C", kind="intra_spec"),
        Edge(source="B", target="D", kind="intra_spec"),
        Edge(source="C", target="D", kind="intra_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["A", "B", "C", "D"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _intra_only_graph() -> TaskGraph:
    """Graph with only intra-spec edges (no cross-spec)."""
    nodes = {
        "A": _node("A", title="Task A"),
        "B": _node("B", title="Task B"),
    }
    edges = [
        Edge(source="A", target="B", kind="intra_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["A", "B"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _cross_spec_graph() -> TaskGraph:
    """Graph with both intra-spec and cross-spec edges."""
    nodes = {
        "01_core:1": _node(
            "01_core:1", spec_name="01_core", group_number=1, title="Parse specifications"
        ),
        "01_core:2": _node("01_core:2", spec_name="01_core", group_number=2, title="Build graph"),
        "02_planning:1": _node(
            "02_planning:1", spec_name="02_planning", group_number=1, title="Set up deps"
        ),
        "02_planning:2": _node(
            "02_planning:2", spec_name="02_planning", group_number=2, title="Resolve ordering"
        ),
    }
    edges = [
        Edge(source="01_core:1", target="01_core:2", kind="intra_spec"),
        Edge(source="02_planning:1", target="02_planning:2", kind="intra_spec"),
        Edge(source="01_core:2", target="02_planning:2", kind="cross_spec"),
    ]
    return TaskGraph(
        nodes=nodes,
        edges=edges,
        order=["01_core:1", "02_planning:1", "01_core:2", "02_planning:2"],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _make_specs(*names: str) -> list[SpecInfo]:
    """Create minimal SpecInfo objects for testing."""
    return [
        SpecInfo(
            name=name, prefix=i + 1, path=Path(f".specs/{name}"), has_tasks=True, has_prd=True
        )
        for i, name in enumerate(names)
    ]


def _analysis_for_diamond() -> (
    tuple[TaskGraph, list[Phase], list[str], GroupedEdges, list[SpecInfo]]
):
    """Prepare analysis data from the diamond graph for formatter tests."""
    graph = _diamond_graph()
    phases = compute_phases(graph)
    path = critical_path(graph)
    grouped = group_edges(graph)
    specs = _make_specs("spec")
    return graph, phases, path, grouped, specs


# ===========================================================================
# Formatter Tests
# ===========================================================================


class TestFormatPhasesDisplay:
    """TS-122-5: format_plan_analysis includes phase headings and node details.

    Requirement: 122-REQ-2.2
    """

    def test_output_contains_phase_headings(self) -> None:
        """Output contains Phase 0, Phase 1, Phase 2 for a diamond graph."""
        graph, phases, path, grouped, specs = _analysis_for_diamond()
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "Phase 0" in output
        assert "Phase 1" in output
        assert "Phase 2" in output

    def test_output_contains_node_ids_and_titles(self) -> None:
        """Each phase lists node IDs with their titles."""
        graph, phases, path, grouped, specs = _analysis_for_diamond()
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "A" in output
        assert "Parse specifications" in output
        assert "B" in output
        assert "Build graph" in output


class TestFormatPhaseSummary:
    """TS-122-6: Phase summary line.

    Requirement: 122-REQ-2.3
    """

    def test_summary_line_phases_and_peak(self) -> None:
        """Output contains phase count and peak parallelism for diamond (3 phases, peak 2)."""
        graph, phases, path, grouped, specs = _analysis_for_diamond()
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "3 phases" in output
        assert "peak parallelism: 2" in output


class TestEdgeDisplayFormat:
    """TS-122-8: Edge display format.

    Requirement: 122-REQ-3.2
    """

    def test_edges_displayed_as_arrow(self) -> None:
        """Edges are displayed as 'source -> target'."""
        graph, phases, path, grouped, specs = _analysis_for_diamond()
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "A -> B" in output


class TestCriticalPathDisplay:
    """TS-122-10: Critical path display format.

    Requirement: 122-REQ-4.2
    """

    def test_path_rendered_as_chain(self) -> None:
        """Critical path is displayed as A -> B -> D with length."""
        graph = _diamond_graph()
        phases = compute_phases(graph)
        path = critical_path(graph)
        grouped = group_edges(graph)
        specs = _make_specs("spec")
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "A -> B -> D" in output
        assert "Length: 3 nodes" in output


class TestNoCrossSpecEdgesOmitted:
    """TS-122-E4: No cross-spec edges omits section.

    Requirement: 122-REQ-3.E1
    """

    def test_no_cross_spec_section_when_absent(self) -> None:
        """Output does not contain 'Cross-spec' when no cross-spec edges exist."""
        graph = _intra_only_graph()
        phases = compute_phases(graph)
        path = critical_path(graph)
        grouped = group_edges(graph)
        specs = _make_specs("spec")
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "Cross-spec" not in output

    def test_cross_spec_section_present_when_exists(self) -> None:
        """Output contains 'Cross-spec' when cross-spec edges exist."""
        graph = _cross_spec_graph()
        phases = compute_phases(graph)
        path = critical_path(graph)
        grouped = group_edges(graph)
        specs = _make_specs("01_core", "02_planning")
        output = format_plan_analysis(graph, phases, path, grouped, specs)
        assert "Cross-spec" in output


# ===========================================================================
# run_plan dry_run Tests
# ===========================================================================


def _make_config() -> MagicMock:
    """Create a minimal AgentFoxConfig mock."""
    config = MagicMock()
    config.archetypes = {}
    config.knowledge = MagicMock()
    return config


def _setup_temp_specs(tmp_path: Path) -> Path:
    """Create a minimal specs directory for run_plan tests."""
    spec_dir = tmp_path / ".specs" / "01_test"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Write tests\n"
        "  - [ ] 1.1 Unit tests\n"
        "\n"
        "- [ ] 2. Implement feature\n"
        "  - [ ] 2.1 Core logic\n"
    )
    return tmp_path / ".specs"


class TestRunPlanDryRunTrue:
    """TS-122-16: run_plan(dry_run=True) skips persistence.

    Requirement: 122-REQ-6.1
    """

    def test_returns_task_graph(self, tmp_path: Path) -> None:
        """run_plan(dry_run=True) returns a TaskGraph."""
        specs_dir = _setup_temp_specs(tmp_path)
        config = _make_config()

        with (
            patch("agent_fox.graph.persistence.save_plan") as mock_save,
            patch("agent_fox.knowledge.db.open_knowledge_store") as mock_db,
        ):
            graph = run_plan(config, dry_run=True, specs_dir=specs_dir)
            assert isinstance(graph, TaskGraph)
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0


class TestRunPlanDryRunFalse:
    """TS-122-17: run_plan(dry_run=False) persists as before.

    Requirement: 122-REQ-6.2
    """

    def test_persists_plan(self, tmp_path: Path) -> None:
        """run_plan(dry_run=False) calls save_plan exactly once."""
        specs_dir = _setup_temp_specs(tmp_path)
        config = _make_config()

        mock_kb = MagicMock()
        mock_kb.connection = MagicMock()

        with (
            patch("agent_fox.graph.persistence.save_plan") as mock_save,
            patch("agent_fox.knowledge.db.open_knowledge_store", return_value=mock_kb),
        ):
            graph = run_plan(config, dry_run=False, specs_dir=specs_dir)
            assert isinstance(graph, TaskGraph)
            assert mock_save.call_count == 1


# ===========================================================================
# Property Tests
# ===========================================================================


class TestPropertyAnalyzeNoPersist:
    """TS-122-P5: Analyze does not persist.

    Property 5: run_plan with dry_run=True never calls save_plan.
    Validates: 122-REQ-1.1, 122-REQ-6.1
    """

    def test_property_analyze_no_persist(self, tmp_path: Path) -> None:
        """run_plan(dry_run=True) never invokes save_plan or open_knowledge_store."""
        specs_dir = _setup_temp_specs(tmp_path)
        config = _make_config()

        with (
            patch("agent_fox.graph.persistence.save_plan") as mock_save,
            patch("agent_fox.knowledge.db.open_knowledge_store") as mock_db,
        ):
            graph = run_plan(config, dry_run=True, specs_dir=specs_dir)
            assert isinstance(graph, TaskGraph)
            assert mock_save.call_count == 0
            assert mock_db.call_count == 0
