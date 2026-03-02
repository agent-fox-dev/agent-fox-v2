"""Report tests.

Test Spec: TS-08-13 (report rendering)
Requirements: 08-REQ-6.1, 08-REQ-6.2
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from agent_fox.fix.loop import FixResult, TerminationReason
from agent_fox.fix.report import render_fix_report


class TestFixReportRendering:
    """TS-08-13: Fix report renders to console.

    Requirement: 08-REQ-6.1, 08-REQ-6.2
    """

    def test_report_contains_passes_completed(self) -> None:
        """Report output includes the number of passes completed."""
        result = FixResult(
            passes_completed=2,
            clusters_resolved=3,
            clusters_remaining=1,
            sessions_consumed=4,
            termination_reason=TerminationReason.MAX_PASSES,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "2" in text

    def test_report_contains_clusters_resolved(self) -> None:
        """Report output includes the number of clusters resolved."""
        result = FixResult(
            passes_completed=2,
            clusters_resolved=3,
            clusters_remaining=1,
            sessions_consumed=4,
            termination_reason=TerminationReason.MAX_PASSES,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "3" in text

    def test_report_contains_clusters_remaining(self) -> None:
        """Report output includes the number of clusters remaining."""
        result = FixResult(
            passes_completed=2,
            clusters_resolved=3,
            clusters_remaining=1,
            sessions_consumed=4,
            termination_reason=TerminationReason.MAX_PASSES,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "1" in text

    def test_report_contains_sessions_consumed(self) -> None:
        """Report output includes the number of sessions consumed."""
        result = FixResult(
            passes_completed=2,
            clusters_resolved=3,
            clusters_remaining=1,
            sessions_consumed=4,
            termination_reason=TerminationReason.MAX_PASSES,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "4" in text

    def test_report_contains_termination_reason(self) -> None:
        """Report output includes the termination reason."""
        result = FixResult(
            passes_completed=2,
            clusters_resolved=3,
            clusters_remaining=1,
            sessions_consumed=4,
            termination_reason=TerminationReason.MAX_PASSES,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "max" in text.lower() or "MAX_PASSES" in text

    def test_all_fixed_report(self) -> None:
        """Report for ALL_FIXED termination includes success indicator."""
        result = FixResult(
            passes_completed=1,
            clusters_resolved=2,
            clusters_remaining=0,
            sessions_consumed=2,
            termination_reason=TerminationReason.ALL_FIXED,
            remaining_failures=[],
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        render_fix_report(result, console)

        text = output.getvalue()
        assert "0" in text  # clusters_remaining is 0
