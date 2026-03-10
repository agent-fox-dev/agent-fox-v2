"""Tests for retry-predecessor orchestrator logic.

Test Spec: TS-26-39 through TS-26-40, TS-26-E12, TS-26-P12
Requirements: 26-REQ-9.3, 26-REQ-9.4, 26-REQ-9.E1
"""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.engine import GraphSync, Orchestrator
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager


def _make_orchestrator_with_graph(
    plan_nodes: dict,
    edges_list: list[dict],
    node_states: dict[str, str],
    *,
    max_retries: int = 2,
) -> tuple[Orchestrator, ExecutionState, dict[str, int], dict[str, str | None]]:
    """Create a minimal Orchestrator with pre-built graph state.

    Returns (orchestrator, state, attempt_tracker, error_tracker).
    """
    config = OrchestratorConfig(max_retries=max_retries)
    orch = Orchestrator(
        config=config,
        plan_path=MagicMock(),
        state_path=MagicMock(),
        session_runner_factory=MagicMock(),
    )

    # Inject plan nodes and edges
    orch._plan_nodes = plan_nodes
    orch._edges_list = edges_list

    # Build edges dict for GraphSync
    edges_dict: dict[str, list[str]] = {nid: [] for nid in node_states}
    for edge in edges_list:
        target = edge["target"]
        source = edge["source"]
        if target in edges_dict:
            edges_dict[target].append(source)

    orch._graph_sync = GraphSync(node_states, edges_dict)

    # Mock state manager
    orch._state_manager = MagicMock(spec=StateManager)

    state = ExecutionState(
        plan_hash="test",
        node_states=node_states,
        started_at="2024-01-01",
        updated_at="2024-01-01",
    )

    attempt_tracker: dict[str, int] = {}
    error_tracker: dict[str, str | None] = {}

    return orch, state, attempt_tracker, error_tracker


# ---------------------------------------------------------------------------
# TS-26-39: Retry-predecessor on Verifier failure
# Requirement: 26-REQ-9.3
# ---------------------------------------------------------------------------


class TestPredecessorReset:
    """Verify orchestrator resets predecessor when Verifier fails."""

    def test_predecessor_reset_concept(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("verifier")
        assert entry.retry_predecessor is True

    def test_coder_no_retry_predecessor(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("coder")
        assert entry.retry_predecessor is False

    def test_verifier_failure_resets_predecessor(self) -> None:
        """Integration: Verifier failure resets predecessor coder node."""
        plan_nodes = {
            "spec:4": {
                "spec_name": "spec",
                "group_number": 4,
                "archetype": "coder",
            },
            "spec:5": {
                "spec_name": "spec",
                "group_number": 5,
                "archetype": "verifier",
            },
        }
        edges_list = [
            {"source": "spec:4", "target": "spec:5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:4": "completed",
            "spec:5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = (
            _make_orchestrator_with_graph(plan_nodes, edges_list, node_states)
        )

        failed_record = SessionRecord(
            node_id="spec:5",
            attempt=1,
            status="failed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=5000,
            error_message="Verification failed: 2 requirements not met",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._process_session_result(
            failed_record, 1, state, attempt_tracker, error_tracker,
        )

        # Predecessor should be reset to pending
        assert state.node_states["spec:4"] == "pending"
        # Verifier should also be reset to pending
        assert state.node_states["spec:5"] == "pending"
        # Error tracker should have the predecessor error
        assert error_tracker["spec:4"] == "Verification failed: 2 requirements not met"


# ---------------------------------------------------------------------------
# TS-26-40: Retry-predecessor cycle limit
# Requirement: 26-REQ-9.4
# ---------------------------------------------------------------------------


class TestRetryCycleLimit:
    """Verify retry-predecessor does not exceed max_retries."""

    def test_retry_concept(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        assert ARCHETYPE_REGISTRY["verifier"].retry_predecessor is True
        assert ARCHETYPE_REGISTRY["coder"].retry_predecessor is False
        assert ARCHETYPE_REGISTRY["skeptic"].retry_predecessor is False

    def test_verifier_blocked_after_max_retries(self) -> None:
        """After max_retries+1 failures, verifier is blocked."""
        plan_nodes = {
            "spec:4": {
                "spec_name": "spec",
                "group_number": 4,
                "archetype": "coder",
            },
            "spec:5": {
                "spec_name": "spec",
                "group_number": 5,
                "archetype": "verifier",
            },
        }
        edges_list = [
            {"source": "spec:4", "target": "spec:5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:4": "completed",
            "spec:5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = (
            _make_orchestrator_with_graph(
                plan_nodes, edges_list, node_states, max_retries=2,
            )
        )

        failed_record = SessionRecord(
            node_id="spec:5",
            attempt=3,  # attempt >= max_retries + 1 (2+1=3)
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="Still failing",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._process_session_result(
            failed_record, 3, state, attempt_tracker, error_tracker,
        )

        # Should be blocked, not reset
        assert state.node_states["spec:5"] == "blocked"


# ---------------------------------------------------------------------------
# TS-26-E12: Retry-predecessor with non-coder predecessor
# Requirement: 26-REQ-9.E1
# ---------------------------------------------------------------------------


class TestNonCoderPredecessor:
    """Verify retry-predecessor works for any predecessor archetype."""

    def test_retry_works_for_any_predecessor(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("verifier")
        assert entry.retry_predecessor is True

    def test_librarian_predecessor_reset(self) -> None:
        """Retry-predecessor works when predecessor is librarian, not coder."""
        plan_nodes = {
            "spec:3": {
                "spec_name": "spec",
                "group_number": 3,
                "archetype": "librarian",
            },
            "spec:4": {
                "spec_name": "spec",
                "group_number": 4,
                "archetype": "verifier",
            },
        }
        edges_list = [
            {"source": "spec:3", "target": "spec:4", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:3": "completed",
            "spec:4": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = (
            _make_orchestrator_with_graph(plan_nodes, edges_list, node_states)
        )

        failed_record = SessionRecord(
            node_id="spec:4",
            attempt=1,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="Verification failed",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._process_session_result(
            failed_record, 1, state, attempt_tracker, error_tracker,
        )

        # Librarian predecessor should be reset
        assert state.node_states["spec:3"] == "pending"
        assert state.node_states["spec:4"] == "pending"


# ---------------------------------------------------------------------------
# TS-26-P12: Retry-Predecessor Correctness (Property)
# Property 12: Retry resets correct predecessor and respects max_retries
# Validates: 26-REQ-9.3, 26-REQ-9.4
# ---------------------------------------------------------------------------


class TestPropertyRetryPredecessor:
    """Retry-predecessor resets the correct predecessor."""

    def test_prop_retry_flag_only_on_verifier(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        for name, entry in ARCHETYPE_REGISTRY.items():
            if name == "verifier":
                assert entry.retry_predecessor is True
            else:
                assert entry.retry_predecessor is False, (
                    f"{name} should not have retry_predecessor"
                )
