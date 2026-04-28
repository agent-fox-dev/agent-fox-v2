"""Result handler non-retryable error classification tests.

Test Spec: TS-118-8 (result handler blocks immediately on non-retryable)
Requirements: 118-REQ-3.2, 118-REQ-3.3
"""

from __future__ import annotations

from agent_fox.core.models import ModelTier
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord
from agent_fox.routing.escalation import EscalationLadder


class TestNonRetryableImmediateBlock:
    """TS-118-8: result handler blocks immediately on non-retryable error.

    Requirements: 118-REQ-3.2, 118-REQ-3.3
    """

    def _make_handler(
        self,
        graph_sync: GraphSync,
        routing_ladders: dict,
        block_calls: list,
    ) -> SessionResultHandler:
        """Create a SessionResultHandler with mocked dependencies."""

        def _block_task(node_id: str, state: ExecutionState, reason: str) -> None:
            block_calls.append((node_id, reason))
            graph_sync.mark_blocked(node_id, reason)
            state.blocked_reasons[node_id] = reason

        return SessionResultHandler(
            graph_sync=graph_sync,
            routing_ladders=routing_ladders,
            retries_before_escalation=2,
            max_retries=3,
            task_callback=None,
            sink=None,
            run_id="test-run",
            graph=None,
            archetypes_config=None,
            knowledge_db_conn=None,
            block_task_fn=_block_task,
            check_block_budget_fn=lambda _state: False,
        )

    def test_nonretryable_blocks_immediately(self) -> None:
        """Non-retryable errors block the node immediately without consuming
        escalation ladder retries, with 'workspace-state' in reason."""
        node_states = {"spec:1": "in_progress"}
        edges: dict[str, list[str]] = {"spec:1": []}
        graph_sync = GraphSync(node_states, edges)

        # Set up an escalation ladder with remaining retries
        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=2,
        )
        routing_ladders = {"spec:1": ladder}

        block_calls: list[tuple[str, str]] = []
        handler = self._make_handler(graph_sync, routing_ladders, block_calls)

        record = SessionRecord(
            node_id="spec:1",
            attempt=1,
            status="failed",
            input_tokens=100,
            output_tokens=200,
            cost=0.10,
            duration_ms=5000,
            error_message="Divergent untracked files",
            timestamp="2026-01-01T00:00:00",
            is_non_retryable=True,
        )

        state = ExecutionState(
            plan_hash="abc123",
            node_states=node_states,
        )

        attempt_tracker: dict[str, int] = {"spec:1": 1}
        error_tracker: dict[str, str | None] = {}

        handler.process(record, 1, state, attempt_tracker, error_tracker)

        # Node must be blocked
        assert node_states["spec:1"] == "blocked"

        # Blocked reason must contain "workspace-state"
        assert len(block_calls) == 1
        assert "workspace-state" in block_calls[0][1]

        # Ladder must NOT have consumed an additional failure
        # (the record_failure in _handle_failure should be skipped)
        assert ladder.attempt_count == 1  # no additional failures recorded
