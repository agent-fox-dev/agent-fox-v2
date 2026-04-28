"""Graph sync cascade blocking idempotency tests.

Test Spec: TS-118-15 (idempotent cascade blocking on blocked node),
           TS-118-16 (cascade blocking skips completed nodes),
           TS-118-E9 (cascade skip on in-progress node)
Requirements: 118-REQ-7.1, 118-REQ-7.2, 118-REQ-7.E1
"""

from __future__ import annotations

import logging

import pytest

from agent_fox.engine.graph_sync import GraphSync


class TestIdempotentCascadeBlockingOnBlocked:
    """TS-118-15: cascade-blocking an already-blocked node is a no-op.

    Requirements: 118-REQ-7.1
    """

    def test_reblocking_blocked_node_is_noop(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Re-blocking an already-blocked node produces no state change
        and no WARNING log emission."""
        # Set up a graph: B depends on A
        node_states = {"A": "pending", "B": "pending"}
        edges = {"A": [], "B": ["A"]}  # B depends on A
        graph_sync = GraphSync(node_states, edges)

        # Block B initially
        graph_sync.mark_blocked("B", "original reason")
        assert node_states["B"] == "blocked"

        # Now try to re-block B (as from a cascade)
        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.graph_sync"):
            graph_sync.mark_blocked("B", "cascade from A")

        # B should remain blocked (no state change)
        assert node_states["B"] == "blocked"

        # No WARNING should have been emitted
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert not warning_messages, (
            f"Expected no WARNING logs when re-blocking already-blocked node; "
            f"got: {warning_messages}"
        )


class TestCascadeBlockingSkipsCompleted:
    """TS-118-16: cascade-blocking a completed node is silently skipped.

    Requirements: 118-REQ-7.2
    """

    def test_completed_node_not_blocked_by_cascade(self) -> None:
        """Cascade-blocking does not change a completed node's state."""
        # Set up: A -> B (B depends on A), B is completed
        node_states = {"A": "pending", "B": "completed"}
        edges = {"A": [], "B": ["A"]}  # B depends on A
        graph_sync = GraphSync(node_states, edges)

        # Block A — cascade should NOT affect B (completed is terminal)
        graph_sync.mark_blocked("A", "test reason")

        assert node_states["A"] == "blocked"
        assert node_states["B"] == "completed"


class TestCascadeSkipInProgress:
    """TS-118-E9: cascade-blocking skips in-progress nodes with DEBUG log.

    Requirements: 118-REQ-7.E1
    """

    def test_in_progress_node_not_blocked(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """In-progress nodes are skipped during cascade blocking, with a
        DEBUG log emitted."""
        # Set up: A -> B -> C, B is in_progress, C is pending
        node_states = {"A": "pending", "B": "in_progress", "C": "pending"}
        edges = {"A": [], "B": ["A"], "C": ["B"]}
        graph_sync = GraphSync(node_states, edges)

        with caplog.at_level(logging.DEBUG, logger="agent_fox.engine.graph_sync"):
            graph_sync.mark_blocked("A", "test reason")

        # A should be blocked
        assert node_states["A"] == "blocked"
        # B should remain in_progress (not blocked)
        assert node_states["B"] == "in_progress"
        # C should be blocked (cascaded through B)
        assert node_states["C"] == "blocked"

        # DEBUG log should have been emitted for the skipped in-progress node
        debug_messages = [
            r.message for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("in-progress" in m and "B" in m for m in debug_messages), (
            f"Expected DEBUG log about skipping in-progress node B; got: {debug_messages}"
        )
