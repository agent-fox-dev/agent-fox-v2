"""Tests for critical path computation.

Test Spec: TS-39-23, TS-39-24, TS-39-25
Requirements: 39-REQ-8.1, 39-REQ-8.2, 39-REQ-8.3
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-39-23: Critical Path Computation
# ---------------------------------------------------------------------------


class TestCriticalPath:
    """TS-39-23, TS-39-24, TS-39-25: Critical path computation.

    Requirements: 39-REQ-8.1, 39-REQ-8.2, 39-REQ-8.3
    """

    def test_compute_critical_path(self) -> None:
        """TS-39-23: Critical path uses duration hints as weights.

        Requirement: 39-REQ-8.1
        """
        from agent_fox.graph.critical_path import compute_critical_path

        nodes = {"A": "pending", "B": "pending", "C": "pending"}
        edges = {"B": ["A"], "C": ["B"]}
        hints = {"A": 100, "B": 200, "C": 50}

        result = compute_critical_path(nodes, edges, hints)
        assert result.path == ["A", "B", "C"]
        assert result.total_duration_ms == 350

    def test_parallel_paths_picks_longest(self) -> None:
        """Critical path picks the longest of parallel paths."""
        from agent_fox.graph.critical_path import compute_critical_path

        # A -> B -> D (total 350) and A -> C -> D (total 250)
        nodes = {"A": "pending", "B": "pending", "C": "pending", "D": "pending"}
        edges = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}
        hints = {"A": 100, "B": 200, "C": 100, "D": 50}

        result = compute_critical_path(nodes, edges, hints)
        assert result.total_duration_ms == 350
        assert result.path == ["A", "B", "D"]

    def test_tied_paths(self) -> None:
        """TS-39-25: All tied critical paths reported.

        Requirement: 39-REQ-8.3
        """
        from agent_fox.graph.critical_path import compute_critical_path

        # Diamond graph: A->B->D and A->C->D with equal durations
        nodes = {"A": "pending", "B": "pending", "C": "pending", "D": "pending"}
        edges = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}
        hints = {"A": 100, "B": 200, "C": 200, "D": 50}

        result = compute_critical_path(nodes, edges, hints)
        assert result.total_duration_ms == 350

        all_paths = [result.path] + result.tied_paths
        assert ["A", "B", "D"] in all_paths
        assert ["A", "C", "D"] in all_paths

    def test_single_node(self) -> None:
        """Single node graph returns that node as critical path."""
        from agent_fox.graph.critical_path import compute_critical_path

        nodes = {"A": "pending"}
        edges: dict[str, list[str]] = {}
        hints = {"A": 100}

        result = compute_critical_path(nodes, edges, hints)
        assert result.path == ["A"]
        assert result.total_duration_ms == 100

    def test_status_output(self) -> None:
        """TS-39-24: Critical path available for status output.

        Requirement: 39-REQ-8.2
        """
        from agent_fox.graph.critical_path import (
            CriticalPathResult,
            format_critical_path,
        )

        result = CriticalPathResult(
            path=["A", "B", "C"],
            total_duration_ms=350,
            tied_paths=[],
        )
        output = format_critical_path(result)
        assert "critical path" in output.lower() or "Critical Path" in output
