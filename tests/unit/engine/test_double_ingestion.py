"""Tests for simplified barrier/cleanup after knowledge decoupling.

Verifies that _barrier_sync and _cleanup_infrastructure no longer perform
any knowledge ingestion (run_background_ingestion was removed by spec 114).
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSimplifiedBarrierAndCleanup:
    """_barrier_sync is a no-op and _cleanup_infrastructure only closes resources."""

    def test_barrier_sync_sets_flag(self) -> None:
        """_barrier_sync sets the _barrier_ingestion_ran flag on infra dict."""
        from agent_fox.engine.run import _barrier_sync

        config = MagicMock()
        infra: dict = {"knowledge_db": MagicMock(), "sink_dispatcher": MagicMock()}

        _barrier_sync(infra, config)
        assert infra.get("_barrier_ingestion_ran") is True

    def test_cleanup_closes_sinks_and_db(self) -> None:
        """_cleanup_infrastructure closes the sink dispatcher and knowledge DB."""
        from agent_fox.engine.run import _cleanup_infrastructure

        config = MagicMock()
        mock_db = MagicMock()
        mock_sink = MagicMock()
        infra: dict = {"knowledge_db": mock_db, "sink_dispatcher": mock_sink}

        _cleanup_infrastructure(infra, config)

        mock_sink.close.assert_called_once()
        mock_db.close.assert_called_once()

    def test_cleanup_survives_close_failures(self) -> None:
        """_cleanup_infrastructure does not raise when close() fails."""
        from agent_fox.engine.run import _cleanup_infrastructure

        config = MagicMock()
        mock_db = MagicMock()
        mock_db.close.side_effect = RuntimeError("close failed")
        mock_sink = MagicMock()
        mock_sink.close.side_effect = RuntimeError("close failed")
        infra: dict = {"knowledge_db": mock_db, "sink_dispatcher": mock_sink}

        # Should not raise
        _cleanup_infrastructure(infra, config)
