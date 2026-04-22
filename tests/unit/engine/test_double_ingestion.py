"""Regression tests for double git ingestion at end-of-run (issue #505).

Verifies that _cleanup_infrastructure skips run_background_ingestion when
a sync barrier already ran ingestion during the same engine run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _mock_ingestion():
    """Patch run_background_ingestion and return the mock."""
    with patch("agent_fox.engine.run.run_background_ingestion") as mock:
        yield mock


class TestCleanupSkipsIngestionAfterBarrier:
    """_cleanup_infrastructure must not re-ingest when a barrier already did."""

    def test_cleanup_skips_ingestion_after_barrier(self, _mock_ingestion: MagicMock) -> None:
        from agent_fox.engine.run import _barrier_sync, _cleanup_infrastructure

        config = MagicMock()
        infra = {"knowledge_db": MagicMock(), "sink_dispatcher": MagicMock()}

        _barrier_sync(infra, config)
        assert _mock_ingestion.call_count == 1

        _mock_ingestion.reset_mock()
        _cleanup_infrastructure(infra, config)
        _mock_ingestion.assert_not_called()

    def test_cleanup_ingests_when_no_barrier_ran(self, _mock_ingestion: MagicMock) -> None:
        from agent_fox.engine.run import _cleanup_infrastructure

        config = MagicMock()
        infra = {"knowledge_db": MagicMock(), "sink_dispatcher": MagicMock()}

        _cleanup_infrastructure(infra, config)
        _mock_ingestion.assert_called_once()

    def test_barrier_failure_still_sets_flag(self, _mock_ingestion: MagicMock) -> None:
        from agent_fox.engine.run import _barrier_sync, _cleanup_infrastructure

        _mock_ingestion.side_effect = RuntimeError("ingestion failed")

        config = MagicMock()
        infra = {"knowledge_db": MagicMock(), "sink_dispatcher": MagicMock()}

        _barrier_sync(infra, config)

        _mock_ingestion.reset_mock()
        _mock_ingestion.side_effect = None
        _cleanup_infrastructure(infra, config)
        _mock_ingestion.assert_not_called()
