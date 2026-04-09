"""Tests for auditor circuit breaker and retry logic.

Test Spec: TS-46-23 through TS-46-28, TS-46-P6
Requirements: 46-REQ-7.1 through 46-REQ-7.E2
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager
from agent_fox.graph.types import Edge, Node, TaskGraph


def _make_auditor_orchestrator(
    plan_nodes: dict,
    edges_list: list[dict],
    node_states: dict[str, str],
    *,
    max_retries: int = 2,
    auditor_max_retries: int = 2,
) -> tuple[Orchestrator, ExecutionState, dict[str, int], dict[str, str | None]]:
    """Create a minimal Orchestrator for auditor circuit breaker tests.

    Returns (orchestrator, state, attempt_tracker, error_tracker).
    """
    config = OrchestratorConfig(max_retries=max_retries)
    orch = Orchestrator(
        config=config,
        plan_path=MagicMock(),
        state_path=MagicMock(),
        session_runner_factory=MagicMock(),
    )

    # Build typed TaskGraph from dict-based plan data
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
    typed_edges = [Edge(source=e["source"], target=e["target"], kind=e.get("kind", "intra_spec")) for e in edges_list]
    orch._graph = TaskGraph(
        nodes=typed_nodes,
        edges=typed_edges,
        order=list(plan_nodes.keys()),
    )

    # Build edges dict for GraphSync
    edges_dict: dict[str, list[str]] = {nid: [] for nid in node_states}
    for edge in edges_list:
        target = edge["target"]
        source = edge["source"]
        if target in edges_dict:
            edges_dict[target].append(source)

    orch._graph_sync = GraphSync(node_states, edges_dict)
    orch._state_manager = MagicMock(spec=StateManager)

    # Initialize result handler (normally done in run())
    orch._result_handler = SessionResultHandler(
        graph_sync=orch._graph_sync,
        state_manager=orch._state_manager,
        routing_ladders=orch._routing.ladders,
        retries_before_escalation=orch._routing.retries_before_escalation,
        max_retries=config.max_retries,
        task_callback=None,
        sink=None,
        run_id="test-run",
        graph=orch._graph,
        archetypes_config=None,
        knowledge_db_conn=None,
        block_task_fn=orch._block_task,
        check_block_budget_fn=orch._check_block_budget,
    )

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
# TS-46-23: Retry Triggered On FAIL
# Requirement: 46-REQ-7.1
# ---------------------------------------------------------------------------


class TestRetryOnFail:
    """Verify auditor FAIL resets predecessor coder to pending."""

    def test_retry_on_fail(self) -> None:
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:1.5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(plan_nodes, edges_list, node_states)

        failed_record = SessionRecord(
            node_id="spec:1.5",
            attempt=1,
            status="failed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=5000,
            error_message="Audit FAIL: TS-1 MISSING, TS-2 WEAK",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._result_handler.process(  # type: ignore[union-attr]
            failed_record,
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # Predecessor should be reset to pending
        assert state.node_states["spec:1"] == "pending"
        # Error tracker should contain audit findings
        assert error_tracker.get("spec:1") is not None


# ---------------------------------------------------------------------------
# TS-46-24: Auditor Re-runs After Retry
# Requirement: 46-REQ-7.2
# ---------------------------------------------------------------------------


class TestAuditorReruns:
    """Verify auditor node is also reset to pending after triggering retry."""

    def test_auditor_reruns(self) -> None:
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:1.5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(plan_nodes, edges_list, node_states)

        failed_record = SessionRecord(
            node_id="spec:1.5",
            attempt=1,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="Audit FAIL",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._result_handler.process(  # type: ignore[union-attr]
            failed_record,
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # Auditor itself should be reset to pending
        assert state.node_states["spec:1.5"] == "pending"


# ---------------------------------------------------------------------------
# TS-46-25: Circuit Breaker Blocks After Max Retries
# Requirements: 46-REQ-7.4, 46-REQ-7.5
# ---------------------------------------------------------------------------


class TestCircuitBreakerBlocks:
    """Verify circuit breaker blocks auditor and prevents retries."""

    def test_circuit_breaker_blocks(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:1.5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(
            plan_nodes,
            edges_list,
            node_states,
            max_retries=2,
        )

        # Attempt 3 = max_retries(2) + 1 — circuit breaker should trip
        failed_record = SessionRecord(
            node_id="spec:1.5",
            attempt=3,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="Still failing",
            timestamp="2024-01-01T00:00:00Z",
        )

        with caplog.at_level(logging.WARNING):
            orch._result_handler.process(  # type: ignore[union-attr]
                failed_record,
                3,
                state,
                attempt_tracker,
                error_tracker,
            )

        # Auditor should be blocked
        assert state.node_states["spec:1.5"] == "blocked"
        # Predecessor should NOT be reset
        assert state.node_states["spec:1"] != "pending"


# ---------------------------------------------------------------------------
# TS-46-26: Circuit Breaker Files GitHub Issue
# Requirement: 46-REQ-7.6
# ---------------------------------------------------------------------------


class TestCircuitBreakerFilesIssue:
    """Verify circuit breaker files a GitHub issue."""

    def test_circuit_breaker_files_issue(self) -> None:
        from agent_fox.session.auditor_output import (
            create_circuit_breaker_issue_title,
        )

        title = create_circuit_breaker_issue_title("my_spec")
        assert "circuit breaker" in title.lower()
        assert "[Auditor]" in title


# ---------------------------------------------------------------------------
# TS-46-27: Max Retries Zero Blocks On First FAIL
# Requirement: 46-REQ-7.E1
# ---------------------------------------------------------------------------


class TestMaxRetriesZeroBlocks:
    """Verify max_retries=0 means auditor blocks on first FAIL."""

    def test_max_retries_zero_blocks(self) -> None:
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:1.5": "in_progress",
        }

        # max_retries=0 means no retries at all
        orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(
            plan_nodes,
            edges_list,
            node_states,
            max_retries=0,
        )

        failed_record = SessionRecord(
            node_id="spec:1.5",
            attempt=1,
            status="failed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message="Audit FAIL",
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._result_handler.process(  # type: ignore[union-attr]
            failed_record,
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # Should be blocked immediately
        assert state.node_states["spec:1.5"] == "blocked"


# ---------------------------------------------------------------------------
# TS-46-28: PASS On First Run No Retry
# Requirement: 46-REQ-7.E2
# ---------------------------------------------------------------------------


class TestPassNoRetry:
    """Verify PASS verdict does not trigger retry."""

    def test_pass_no_retry(self) -> None:
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]
        node_states = {
            "spec:1": "completed",
            "spec:1.5": "in_progress",
        }

        orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(plan_nodes, edges_list, node_states)

        pass_record = SessionRecord(
            node_id="spec:1.5",
            attempt=1,
            status="completed",
            input_tokens=100,
            output_tokens=50,
            cost=0.01,
            duration_ms=5000,
            error_message=None,
            timestamp="2024-01-01T00:00:00Z",
        )

        orch._result_handler.process(  # type: ignore[union-attr]
            pass_record,
            1,
            state,
            attempt_tracker,
            error_tracker,
        )

        # Predecessor should not be reset
        pred_state = state.node_states["spec:1"]
        assert pred_state != "pending" or pred_state == "completed"
        # Auditor should be completed
        assert state.node_states["spec:1.5"] == "completed"


# ---------------------------------------------------------------------------
# TS-46-P6: Circuit Breaker Bound (Property)
# Property 6: Retry count never exceeds max_retries.
# Validates: 46-REQ-7.3, 46-REQ-7.4
# ---------------------------------------------------------------------------


class TestPropertyCircuitBreakerBound:
    """Retry count never exceeds max_retries."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS,
        reason="hypothesis not installed",
    )
    @given(max_retries=st.integers(min_value=0, max_value=10))
    @settings(max_examples=20)
    def test_prop_circuit_breaker_bound(self, max_retries: int) -> None:
        """Simulate a retry loop: count how many predecessor resets happen."""
        plan_nodes = {
            "spec:1": {
                "spec_name": "spec",
                "group_number": 1,
                "archetype": "coder",
            },
            "spec:1.5": {
                "spec_name": "spec",
                "group_number": 1.5,
                "archetype": "auditor",
            },
        }
        edges_list = [
            {"source": "spec:1", "target": "spec:1.5", "kind": "intra_spec"},
        ]

        reset_count = 0
        for attempt in range(1, max_retries + 5):
            node_states = {
                "spec:1": "completed",
                "spec:1.5": "in_progress",
            }

            orch, state, attempt_tracker, error_tracker = _make_auditor_orchestrator(
                plan_nodes,
                edges_list,
                node_states,
                max_retries=max_retries,
            )

            failed_record = SessionRecord(
                node_id="spec:1.5",
                attempt=attempt,
                status="failed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message="Still failing",
                timestamp="2024-01-01T00:00:00Z",
            )

            orch._result_handler.process(  # type: ignore[union-attr]
                failed_record,
                attempt,
                state,
                attempt_tracker,
                error_tracker,
            )

            if state.node_states.get("spec:1") == "pending":
                reset_count += 1

            if state.node_states.get("spec:1.5") == "blocked":
                break

        assert reset_count <= max_retries
