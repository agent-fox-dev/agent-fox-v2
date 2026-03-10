"""Improve report tests.

Test Spec: TS-31-26, TS-31-27, TS-31-28
Requirements: 31-REQ-9.1, 31-REQ-9.2, 31-REQ-9.3, 31-REQ-9.E1
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from agent_fox.fix.fix import FixResult, TerminationReason
from agent_fox.fix.improve import ImproveResult, ImproveTermination
from agent_fox.fix.improve_report import build_combined_json, render_combined_report


def _make_fix_result(
    termination_reason: TerminationReason = TerminationReason.ALL_FIXED,
    passes_completed: int = 1,
) -> FixResult:
    return FixResult(
        passes_completed=passes_completed,
        clusters_resolved=1,
        clusters_remaining=0,
        sessions_consumed=1,
        termination_reason=termination_reason,
        remaining_failures=[],
    )


def _make_improve_result() -> ImproveResult:
    return ImproveResult(
        passes_completed=2,
        max_passes=3,
        total_improvements=5,
        improvements_by_tier={"quick_win": 3, "structural": 2},
        verifier_pass_count=2,
        verifier_fail_count=0,
        sessions_consumed=6,
        total_cost=2.50,
        termination_reason=ImproveTermination.CONVERGED,
        pass_results=[],
    )


class TestRenderCombinedReport:
    """TS-31-26, TS-31-27: Combined report rendering."""

    def test_combined_report_renders_both_phases(self) -> None:
        """TS-31-26: Combined report includes Phase 1 and Phase 2."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)

        render_combined_report(
            _make_fix_result(),
            _make_improve_result(),
            total_cost=3.50,
            console=console,
        )

        output = buf.getvalue()
        assert "Phase 1" in output
        assert "Phase 2" in output
        assert "5" in output
        assert "3.50" in output

    def test_report_omits_phase2_when_not_run(self) -> None:
        """TS-31-27: Report omits Phase 2 when improve_result is None."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)

        render_combined_report(
            _make_fix_result(TerminationReason.MAX_PASSES),
            None,
            total_cost=1.20,
            console=console,
        )

        output = buf.getvalue()
        assert "Phase 2" not in output


class TestBuildCombinedJson:
    """TS-31-28: JSON mode combined report."""

    def test_json_combined_report(self) -> None:
        """TS-31-28: JSON mode produces valid structure with both phases."""
        data = build_combined_json(
            _make_fix_result(),
            _make_improve_result(),
            total_cost=4.82,
        )

        assert data["event"] == "complete"
        assert "phase1" in data["summary"]
        assert "phase2" in data["summary"]
        assert data["summary"]["total_cost"] == 4.82
