"""CLI auto-improve tests.

Test Spec: TS-31-1 through TS-31-5
Requirements: 31-REQ-1.1, 31-REQ-1.3, 31-REQ-1.4, 31-REQ-1.E1,
              31-REQ-1.E2, 31-REQ-2.1, 31-REQ-10.1, 31-REQ-10.2
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from agent_fox.fix.fix import FixResult, TerminationReason
from agent_fox.fix.improve import ImproveResult, ImproveTermination


def _make_fix_result(
    reason: TerminationReason = TerminationReason.ALL_FIXED,
) -> FixResult:
    return FixResult(
        passes_completed=1,
        clusters_resolved=1,
        clusters_remaining=0,
        sessions_consumed=1,
        termination_reason=reason,
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


class TestAutoFlag:
    """TS-31-1, TS-31-2: --auto flag behavior."""

    def test_auto_enables_phase2_after_all_green(self) -> None:
        """TS-31-1: --auto enables Phase 2 after ALL_FIXED."""
        from agent_fox.cli.fix import fix_cmd

        runner = CliRunner()

        improve_result = _make_improve_result()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[MagicMock()],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=[
                    _make_fix_result(TerminationReason.ALL_FIXED),
                    improve_result,
                ],
            ),
            patch(
                "agent_fox.cli.fix.run_improve_loop",
                new_callable=AsyncMock,
                return_value=improve_result,
            ) as mock_improve,
            patch("agent_fox.cli.fix.render_combined_report"),
        ):
            runner.invoke(
                fix_cmd,
                ["--auto"],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

        assert mock_improve.called

    def test_phase2_skipped_when_not_all_green(self) -> None:
        """TS-31-2: Phase 2 skipped when not ALL_FIXED."""
        from agent_fox.cli.fix import fix_cmd

        runner = CliRunner()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[MagicMock()],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                return_value=_make_fix_result(TerminationReason.MAX_PASSES),
            ),
            patch(
                "agent_fox.cli.fix.run_improve_loop",
                new_callable=AsyncMock,
            ) as mock_improve,
            patch("agent_fox.cli.fix.render_fix_report"),
        ):
            runner.invoke(
                fix_cmd,
                ["--auto"],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

        assert not mock_improve.called


class TestImprovePassesValidation:
    """TS-31-3, TS-31-4: --improve-passes validation."""

    def test_improve_passes_without_auto_is_error(self) -> None:
        """TS-31-3: --improve-passes without --auto is error."""
        from agent_fox.cli.fix import fix_cmd

        runner = CliRunner()

        result = runner.invoke(
            fix_cmd,
            ["--improve-passes", "5"],
            obj={"config": MagicMock(), "json": False},
            catch_exceptions=False,
        )

        assert result.exit_code != 0
        assert "auto" in result.output.lower()

    def test_improve_passes_clamped_to_one(self) -> None:
        """TS-31-4: --improve-passes 0 is clamped to 1."""
        from agent_fox.cli.fix import fix_cmd

        runner = CliRunner()
        improve_result = _make_improve_result()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[MagicMock()],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                side_effect=[
                    _make_fix_result(TerminationReason.ALL_FIXED),
                    improve_result,
                ],
            ),
            patch(
                "agent_fox.cli.fix.run_improve_loop",
                new_callable=AsyncMock,
                return_value=improve_result,
            ) as mock_improve,
            patch("agent_fox.cli.fix.render_combined_report"),
        ):
            runner.invoke(
                fix_cmd,
                ["--auto", "--improve-passes", "0"],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

        call_kw = mock_improve.call_args
        max_p = call_kw.kwargs.get("max_passes", call_kw[1].get("max_passes"))
        assert max_p == 1


class TestDryRunWithAuto:
    """TS-31-5: --dry-run with --auto."""

    def test_dry_run_skips_phase2(self) -> None:
        """TS-31-5: Phase 2 does not run in dry-run mode."""
        from agent_fox.cli.fix import fix_cmd

        runner = CliRunner()

        with (
            patch(
                "agent_fox.cli.fix.detect_checks",
                return_value=[MagicMock()],
            ),
            patch(
                "agent_fox.cli.fix.asyncio.run",
                return_value=_make_fix_result(TerminationReason.ALL_FIXED),
            ),
            patch(
                "agent_fox.cli.fix.run_improve_loop",
                new_callable=AsyncMock,
            ) as mock_improve,
            patch("agent_fox.cli.fix.render_fix_report"),
        ):
            runner.invoke(
                fix_cmd,
                ["--auto", "--dry-run"],
                obj={"config": MagicMock(), "json": False},
                catch_exceptions=False,
            )

        assert not mock_improve.called
