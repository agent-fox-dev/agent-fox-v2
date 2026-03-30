"""Tests for predecessor escalation in the retry-predecessor path.

Verifies that reviewer-triggered resets correctly record failures on the
predecessor's escalation ladder, trigger tier escalation, and block the
predecessor when all tiers are exhausted.

Test Spec: TS-58-1 through TS-58-8, TS-58-E1, TS-58-E2
Requirements: 58-REQ-1.1 through 58-REQ-3.2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_fox.core.config import OrchestratorConfig
from agent_fox.core.models import ModelTier
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.graph.types import Edge, Node, TaskGraph
from agent_fox.routing.escalation import EscalationLadder

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

#: Default graph: Coder spec:1 -> Verifier spec:2
CODER_VERIFIER_NODES: dict = {
    "spec:1": {"spec_name": "spec", "group_number": 1, "archetype": "coder"},
    "spec:2": {"spec_name": "spec", "group_number": 2, "archetype": "verifier"},
}
CODER_VERIFIER_EDGES: list[dict] = [
    {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
]


def _make_orchestrator(
    plan_nodes: dict,
    edges_list: list[dict],
    node_states: dict[str, str],
    *,
    max_retries: int = 5,
) -> tuple[Orchestrator, ExecutionState, dict[str, int], dict[str, str | None]]:
    """Create a minimal Orchestrator with pre-built graph and routing state.

    Returns (orchestrator, state, attempt_tracker, error_tracker).
    """
    config = OrchestratorConfig(max_retries=max_retries)
    orch = Orchestrator(
        config=config,
        plan_path=MagicMock(),
        state_path=MagicMock(),
        session_runner_factory=MagicMock(),
    )

    # Build typed TaskGraph
    typed_nodes = {
        nid: Node(
            id=nid,
            spec_name=n.get("spec_name", ""),
            group_number=n.get("group_number", 0),
            title=n.get("title", nid),
            optional=n.get("optional", False),
            archetype=n.get("archetype", "coder"),
            instances=n.get("instances", 1),
        )
        for nid, n in plan_nodes.items()
    }
    typed_edges = [
        Edge(source=e["source"], target=e["target"], kind=e.get("kind", "intra_spec"))
        for e in edges_list
    ]
    orch._graph = TaskGraph(
        nodes=typed_nodes,
        edges=typed_edges,
        order=list(plan_nodes.keys()),
    )

    # Build edges dict for GraphSync (target -> list of predecessors)
    edges_dict: dict[str, list[str]] = {nid: [] for nid in node_states}
    for edge in edges_list:
        target = edge["target"]
        source = edge["source"]
        if target in edges_dict:
            edges_dict[target].append(source)

    orch._graph_sync = GraphSync(node_states, edges_dict)
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


def _make_failed_reviewer_record(
    node_id: str = "spec:2",
    attempt: int = 1,
    error_message: str = "Verification failed",
    archetype: str = "verifier",
) -> SessionRecord:
    """Create a failed reviewer (verifier/auditor) session record."""
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status="failed",
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=5000,
        error_message=error_message,
        timestamp="2024-01-01T00:00:00Z",
        archetype=archetype,
    )


# ---------------------------------------------------------------------------
# TS-58-1: Reviewer Failure Records on Predecessor Ladder
# Requirement: 58-REQ-1.1
# ---------------------------------------------------------------------------


class TestReviewerFailureRecordsOnPredLadder:
    """TS-58-1: Reviewer failure records on predecessor ladder."""

    def test_reviewer_failure_records_on_pred_ladder(self) -> None:
        """Verify that a reviewer failure increments the predecessor's attempt count.

        Test Spec: TS-58-1
        Requirement: 58-REQ-1.1
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        orch._routing.ladders["spec:1"] = pred_ladder
        initial_count = pred_ladder.attempt_count  # = 1 before any failures

        orch._process_session_result(
            _make_failed_reviewer_record(),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-1.1: predecessor ladder must record a failure
        assert pred_ladder.attempt_count == initial_count + 1


# ---------------------------------------------------------------------------
# TS-58-2: Predecessor Reset to Pending After Recorded Failure
# Requirement: 58-REQ-1.2
# ---------------------------------------------------------------------------


class TestPredecessorResetToPending:
    """TS-58-2: Predecessor reset to pending after recorded failure."""

    def test_predecessor_reset_to_pending(self) -> None:
        """Verify predecessor and reviewer are pending when ladder is not exhausted.

        Test Spec: TS-58-2
        Requirement: 58-REQ-1.2
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # retries_before_escalation=2: first failure does not exhaust the ladder
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=2,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        orch._process_session_result(
            _make_failed_reviewer_record(),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-1.2: both nodes must be pending (ladder not exhausted)
        assert state.node_states["spec:1"] == "pending"
        assert state.node_states["spec:2"] == "pending"
        # The predecessor's ladder must have recorded the failure
        assert pred_ladder.attempt_count == 2  # 1 initial + 1 failure


# ---------------------------------------------------------------------------
# TS-58-3: Predecessor Escalates After Retries Exhausted at Tier
# Requirement: 58-REQ-1.3
# ---------------------------------------------------------------------------


class TestPredecessorEscalatesAfterRetries:
    """TS-58-3: Predecessor escalates after retries exhausted at tier."""

    def test_predecessor_escalates_after_retries(self) -> None:
        """Verify predecessor ladder escalates from STANDARD to ADVANCED.

        After retries_before_escalation+1 reviewer failures, current_tier
        must advance to ADVANCED while the predecessor remains pending.

        Test Spec: TS-58-3
        Requirement: 58-REQ-1.3
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # retries_before_escalation=1: 2nd failure triggers escalation
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        # First failure — still STANDARD
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.current_tier == ModelTier.STANDARD

        # Reset state for the second call
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:2"] = "in_progress"

        # Second failure — escalates to ADVANCED
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=2),
            2,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.current_tier == ModelTier.ADVANCED
        # Predecessor should still be pending (ladder has ADVANCED left)
        assert state.node_states["spec:1"] == "pending"


# ---------------------------------------------------------------------------
# TS-58-4: Predecessor Blocks on Ladder Exhaustion
# Requirement: 58-REQ-2.1
# ---------------------------------------------------------------------------


class TestPredecessorBlocksOnExhaustion:
    """TS-58-4: Predecessor blocks on ladder exhaustion."""

    def test_predecessor_blocks_on_exhaustion(self) -> None:
        """Verify predecessor status is blocked when ladder is exhausted.

        Test Spec: TS-58-4
        Requirement: 58-REQ-2.1
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # Starting at ADVANCED (ceiling): exhausted after 2 failures
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        # First failure — still retrying
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert not pred_ladder.is_exhausted

        # Reset state for second call
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:2"] = "in_progress"

        # Second failure — exhausts the ladder
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=2),
            2,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-2.1: predecessor must be blocked
        assert pred_ladder.is_exhausted is True
        assert state.node_states["spec:1"] == "blocked"


# ---------------------------------------------------------------------------
# TS-58-5: Outcome Recorded on Predecessor Block
# Requirement: 58-REQ-2.2
# ---------------------------------------------------------------------------


class TestOutcomeRecordedOnBlock:
    """TS-58-5: Outcome recorded on predecessor block."""

    def test_outcome_recorded_on_block(self) -> None:
        """Verify _record_node_outcome is called with 'failed' when pred blocks.

        Test Spec: TS-58-5
        Requirement: 58-REQ-2.2
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # retries_before_escalation=0: exhausted immediately after 1 failure
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=0,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        with patch.object(orch, "_record_node_outcome") as mock_record:
            orch._process_session_result(
                _make_failed_reviewer_record(attempt=1),
                1,
                state,
                attempt_tracker,
                error_tracker,
            )
            # 58-REQ-2.2: must call _record_node_outcome with pred_id and "failed"
            mock_record.assert_called_once_with("spec:1", state, "failed")


# ---------------------------------------------------------------------------
# TS-58-6: Neither Node Reset When Predecessor Blocks
# Requirement: 58-REQ-2.3
# ---------------------------------------------------------------------------


class TestNeitherNodeResetWhenBlocked:
    """TS-58-6: Neither node reset when predecessor blocks."""

    def test_neither_node_reset_when_blocked(self) -> None:
        """Verify that blocking the predecessor does not reset either node.

        Test Spec: TS-58-6
        Requirement: 58-REQ-2.3
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # Immediate exhaustion on first failure
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=0,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        orch._process_session_result(
            _make_failed_reviewer_record(attempt=1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-2.3: predecessor blocked, reviewer NOT reset to pending
        assert state.node_states["spec:1"] == "blocked"
        assert state.node_states["spec:2"] != "pending"


# ---------------------------------------------------------------------------
# TS-58-7: Multiple Reviewers Share Predecessor Ladder
# Requirement: 58-REQ-3.1
# ---------------------------------------------------------------------------


class TestMultipleReviewersShareLadder:
    """TS-58-7: Multiple reviewers share predecessor ladder."""

    def test_multiple_reviewers_share_ladder(self) -> None:
        """Verify verifier and auditor failures accumulate on the same ladder.

        Test Spec: TS-58-7
        Requirement: 58-REQ-3.1
        """
        plan_nodes = {
            "spec:1": {"spec_name": "spec", "group_number": 1, "archetype": "coder"},
            "spec:2": {"spec_name": "spec", "group_number": 2, "archetype": "verifier"},
            "spec:1:auditor": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            {"source": "spec:1", "target": "spec:1:auditor", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:2": "in_progress",
            "spec:1:auditor": "pending",
        }

        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            plan_nodes, edges_list, node_states
        )

        # retries_before_escalation=2: escalation after 3rd failure
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=2,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        # 1st failure (verifier)
        orch._process_session_result(
            _make_failed_reviewer_record("spec:2", 1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.attempt_count == 2  # 1 initial + 1 failure

        # Reset state for auditor
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:1:auditor"] = "in_progress"

        # 2nd failure (auditor)
        orch._process_session_result(
            _make_failed_reviewer_record("spec:1:auditor", 1, archetype="auditor"),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.attempt_count == 3  # 1 initial + 2 failures

        # Reset state for verifier again
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:2"] = "in_progress"

        # 3rd failure (verifier again) — triggers escalation
        orch._process_session_result(
            _make_failed_reviewer_record("spec:2", 2),
            2,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.attempt_count == 4  # 1 initial + 3 failures
        assert pred_ladder.current_tier == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-58-8: Cumulative Escalation Decision
# Requirement: 58-REQ-3.2
# ---------------------------------------------------------------------------


class TestCumulativeEscalationDecision:
    """TS-58-8: Cumulative escalation decision based on all reviewers."""

    def test_cumulative_escalation_decision(self) -> None:
        """Verify escalation decision is based on cumulative count, not per-reviewer.

        After retries_before_escalation+1 total failures (across all reviewers),
        the predecessor ladder must escalate.

        Test Spec: TS-58-8
        Requirement: 58-REQ-3.2
        """
        plan_nodes = {
            "spec:1": {"spec_name": "spec", "group_number": 1, "archetype": "coder"},
            "spec:2": {"spec_name": "spec", "group_number": 2, "archetype": "verifier"},
            "spec:1:auditor": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            {"source": "spec:1", "target": "spec:1:auditor", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:2": "in_progress",
            "spec:1:auditor": "pending",
        }

        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            plan_nodes, edges_list, node_states
        )

        # retries_before_escalation=1: 2nd cumulative failure escalates
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        # 1st failure (verifier): still at STANDARD
        orch._process_session_result(
            _make_failed_reviewer_record("spec:2", 1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.current_tier == ModelTier.STANDARD

        # Reset state for auditor
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:1:auditor"] = "in_progress"

        # 2nd failure (auditor): cumulative count triggers escalation to ADVANCED
        orch._process_session_result(
            _make_failed_reviewer_record("spec:1:auditor", 1, archetype="auditor"),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert pred_ladder.current_tier == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-58-E1: Predecessor Has No Ladder (Defensive Creation)
# Requirement: 58-REQ-1.E1
# ---------------------------------------------------------------------------


class TestNoLadderCreatedDefensively:
    """TS-58-E1: Predecessor has no ladder — defensive creation."""

    def test_no_ladder_created_defensively(self) -> None:
        """Verify a ladder is created with archetype defaults when none exists.

        Test Spec: TS-58-E1
        Requirement: 58-REQ-1.E1
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # Confirm no predecessor ladder exists before the call
        assert "spec:1" not in orch._routing.ladders

        orch._process_session_result(
            _make_failed_reviewer_record(),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-1.E1: a ladder must be created for the predecessor
        assert "spec:1" in orch._routing.ladders
        pred_ladder = orch._routing.ladders["spec:1"]
        assert pred_ladder._tier_ceiling == ModelTier.ADVANCED

    def test_created_ladder_starting_tier_matches_archetype(self) -> None:
        """Verify the created ladder's starting tier matches the coder archetype.

        Test Spec: TS-58-E1
        Requirement: 58-REQ-1.E1
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        orch._process_session_result(
            _make_failed_reviewer_record(),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # Coder archetype default_model_tier is STANDARD
        from agent_fox.session.archetypes import get_archetype

        coder_entry = get_archetype("coder")
        expected_tier = ModelTier(coder_entry.default_model_tier)

        pred_ladder = orch._routing.ladders["spec:1"]
        assert pred_ladder.current_tier == expected_tier


# ---------------------------------------------------------------------------
# TS-58-E2: Predecessor Already at ADVANCED Ceiling Blocks
# Requirement: 58-REQ-2.E1
# ---------------------------------------------------------------------------


class TestAdvancedCeilingBlocks:
    """TS-58-E2: Predecessor already at ADVANCED ceiling eventually blocks."""

    def test_advanced_ceiling_blocks_after_retries(self) -> None:
        """Verify a predecessor at ADVANCED ceiling blocks when retries are done.

        Test Spec: TS-58-E2
        Requirement: 58-REQ-2.E1
        """
        node_states = {"spec:1": "completed", "spec:2": "in_progress"}
        orch, state, attempt_tracker, error_tracker = _make_orchestrator(
            CODER_VERIFIER_NODES, CODER_VERIFIER_EDGES, node_states
        )

        # ADVANCED is the ceiling — no escalation possible, blocks after 2 failures
        pred_ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        orch._routing.ladders["spec:1"] = pred_ladder

        # First failure — still retrying
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=1),
            1,
            state,
            attempt_tracker,
            error_tracker,
        )
        assert not pred_ladder.is_exhausted

        # Reset state for second call
        state.node_states["spec:1"] = "completed"
        state.node_states["spec:2"] = "in_progress"

        # Second failure — no tier to escalate to, ladder exhausted
        orch._process_session_result(
            _make_failed_reviewer_record(attempt=2),
            2,
            state,
            attempt_tracker,
            error_tracker,
        )

        # 58-REQ-2.E1: ladder exhausted, predecessor blocked
        assert pred_ladder.is_exhausted is True
        assert state.node_states["spec:1"] == "blocked"
