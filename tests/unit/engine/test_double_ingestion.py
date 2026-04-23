"""Tests for simplified barrier/cleanup after knowledge decoupling.

Verifies that _cleanup_infrastructure only closes resources.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSimplifiedBarrierAndCleanup:
    """_cleanup_infrastructure only closes resources."""

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
