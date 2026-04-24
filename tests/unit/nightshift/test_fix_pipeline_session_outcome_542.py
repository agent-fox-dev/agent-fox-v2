"""Unit tests for fix pipeline session outcome DB logging — issue #542.

AC-4: complete_run failures in NightshiftFixPipeline._try_complete_run are
      logged at WARNING level, not DEBUG.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fix_pipeline() -> object:
    """Build a minimal FixPipeline with a non-None _conn."""
    from unittest.mock import MagicMock

    from agent_fox.nightshift.fix_pipeline import FixPipeline

    config = MagicMock()
    config.orchestrator.max_cost = None
    config.orchestrator.max_sessions = None

    pipeline = FixPipeline(
        config=config,
        platform=MagicMock(),
        conn=MagicMock(),  # non-None so _try_complete_run proceeds
    )
    pipeline._run_id = "test-run-542"
    return pipeline


# ---------------------------------------------------------------------------
# AC-4: complete_run failure → WARNING
# ---------------------------------------------------------------------------


class TestTryCompleteRunLogsWarning:
    """AC-4: _try_complete_run logs at WARNING when complete_run raises."""

    def test_complete_run_failure_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When complete_run raises, a WARNING is emitted (not DEBUG)."""
        pipeline = _make_fix_pipeline()

        with caplog.at_level(logging.WARNING, logger="agent_fox.nightshift.fix_pipeline"):
            with patch(
                "agent_fox.engine.state.complete_run",
                side_effect=RuntimeError("DuckDB connection stale"),
            ):
                pipeline._try_complete_run("completed")  # type: ignore[attr-defined]

        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Failed to complete run record" in m for m in warning_msgs), (
            f"Expected WARNING 'Failed to complete run record'; got: {warning_msgs}"
        )

    def test_complete_run_failure_not_only_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC-4: The failure message must appear at WARNING or above, never only at DEBUG."""
        pipeline = _make_fix_pipeline()

        with caplog.at_level(logging.DEBUG, logger="agent_fox.nightshift.fix_pipeline"):
            with patch(
                "agent_fox.engine.state.complete_run",
                side_effect=RuntimeError("constraint violation"),
            ):
                pipeline._try_complete_run("interrupted")  # type: ignore[attr-defined]

        matching = [
            r for r in caplog.records if "Failed to complete run record" in r.message
        ]
        assert matching, "Expected log entry for 'Failed to complete run record'"
        assert all(r.levelno >= logging.WARNING for r in matching), (
            "All 'Failed to complete run record' entries must be at WARNING or above"
        )

    def test_complete_run_noop_when_conn_is_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No warning emitted when _conn is None (pipeline skips gracefully)."""
        from agent_fox.nightshift.fix_pipeline import FixPipeline

        config = MagicMock()
        config.orchestrator.max_cost = None
        config.orchestrator.max_sessions = None

        pipeline = FixPipeline(config=config, platform=MagicMock(), conn=None)
        pipeline._run_id = "test-run-none"

        with caplog.at_level(logging.WARNING, logger="agent_fox.nightshift.fix_pipeline"):
            pipeline._try_complete_run("completed")

        assert not caplog.records, (
            f"Expected no log output when conn is None; got: {caplog.records}"
        )
