"""Tests for review retry-predecessor on blocking (issue #519).

Validates that when a reviewer with retry_predecessor=True finds blocking-level
critical findings, the coder is not permanently blocked but instead allowed to
proceed (or retried) with findings as context. Also tests the threshold change
from > to >= and the group-0 coder_node_id fix.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb

from agent_fox.engine.blocking import BlockDecision, evaluate_review_blocking
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord
from agent_fox.graph.types import Edge, Node, TaskGraph
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings


def _make_finding(
    *,
    severity: str = "critical",
    description: str = "Test finding",
    spec_name: str = "test_spec",
    task_group: str = "1",
    session_id: str = "test_spec:1:1",
    category: str | None = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=description,
        requirement_ref=None,
        spec_name=spec_name,
        task_group=task_group,
        session_id=session_id,
        category=category,
    )


def _make_session_record(
    node_id: str = "test_spec:1",
    archetype: str = "skeptic",
    attempt: int = 1,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        archetype=archetype,
        attempt=attempt,
        status="completed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=None,
        timestamp="2026-01-01T00:00:00",
    )


def _make_archetypes_config(block_threshold: int = 1):
    config = MagicMock()
    config.reviewer_config.pre_review_block_threshold = block_threshold
    config.reviewer_config.drift_review_block_threshold = block_threshold
    return config


class TestThresholdGteComparison:
    """Threshold comparison uses >= so threshold=1 blocks on 1 critical."""

    def test_single_critical_blocks_at_threshold_1(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        finding = _make_finding(
            severity="critical",
            description="Missing error handling",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=1)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True

    def test_single_critical_does_not_block_at_threshold_2(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        finding = _make_finding(
            severity="critical",
            description="Missing error handling",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=2)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is False

    def test_two_criticals_block_at_threshold_2(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        findings = [
            _make_finding(description=f"Critical issue {i}", session_id="test_spec:1:1")
            for i in range(2)
        ]
        insert_findings(knowledge_conn, findings)

        record = _make_session_record()
        config = _make_archetypes_config(block_threshold=2)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True


class TestGroup0CoderNodeId:
    """Group-0 reviewers target coder group 1, not group 0."""

    def test_group_0_reviewer_targets_group_1(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        finding = _make_finding(
            severity="critical",
            description="Command injection",
            spec_name="spec_07",
            task_group="1",
            session_id="spec_07:0:reviewer:pre-review:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record(
            node_id="spec_07:0:reviewer:pre-review",
            archetype="reviewer",
        )
        config = _make_archetypes_config(block_threshold=1)

        decision = evaluate_review_blocking(
            record, config, knowledge_conn, mode="pre-review"
        )

        assert decision.should_block is True
        assert decision.coder_node_id == "spec_07:1"

    def test_non_group_0_reviewer_keeps_own_group(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        finding = _make_finding(
            severity="critical",
            description="Missing validation",
            spec_name="spec_07",
            task_group="3",
            session_id="spec_07:3:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        record = _make_session_record(
            node_id="spec_07:3",
            archetype="skeptic",
        )
        config = _make_archetypes_config(block_threshold=1)

        decision = evaluate_review_blocking(record, config, knowledge_conn)

        assert decision.should_block is True
        assert decision.coder_node_id == "spec_07:3"


class TestPreReviewRetryPredecessor:
    """Pre-review with retry_predecessor=True converts block to retry."""

    def test_pre_review_has_retry_predecessor(self) -> None:
        from agent_fox.archetypes import get_archetype, resolve_effective_config

        entry = get_archetype("reviewer")
        resolved = resolve_effective_config(entry, "pre-review")
        assert resolved.retry_predecessor is True

    def test_audit_review_has_retry_predecessor(self) -> None:
        from agent_fox.archetypes import get_archetype, resolve_effective_config

        entry = get_archetype("reviewer")
        resolved = resolve_effective_config(entry, "audit-review")
        assert resolved.retry_predecessor is True

    def test_drift_review_does_not_have_retry_predecessor(self) -> None:
        from agent_fox.archetypes import get_archetype, resolve_effective_config

        entry = get_archetype("reviewer")
        resolved = resolve_effective_config(entry, "drift-review")
        assert resolved.retry_predecessor is False


class TestRetryOnReviewBlock:
    """Result handler converts block to retry when retry_predecessor is set."""

    def _make_handler_with_graph(
        self,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> tuple[SessionResultHandler, ExecutionState, MagicMock]:
        node_states = {
            "test_spec:0:reviewer:pre-review": "completed",
            "test_spec:1": "pending",
        }
        edges_dict = {
            "test_spec:0:reviewer:pre-review": [],
            "test_spec:1": ["test_spec:0:reviewer:pre-review"],
        }
        graph_sync = MagicMock()
        graph_sync.node_states = node_states
        graph_sync.predecessors = lambda nid: edges_dict.get(nid, [])

        graph = TaskGraph(
            nodes={
                "test_spec:0:reviewer:pre-review": Node(
                    id="test_spec:0:reviewer:pre-review",
                    spec_name="test_spec",
                    group_number=0,
                    title="Pre-review",
                    optional=False,
                    archetype="reviewer",
                    mode="pre-review",
                ),
                "test_spec:1": Node(
                    id="test_spec:1",
                    spec_name="test_spec",
                    group_number=1,
                    title="Coder",
                    optional=False,
                    archetype="coder",
                ),
            },
            edges=[
                Edge(
                    source="test_spec:0:reviewer:pre-review",
                    target="test_spec:1",
                    kind="intra_spec",
                )
            ],
            order=["test_spec:0:reviewer:pre-review", "test_spec:1"],
        )

        block_task_fn = MagicMock()

        archetypes_config = _make_archetypes_config(block_threshold=1)

        handler = SessionResultHandler(
            graph_sync=graph_sync,
            routing_ladders={},
            retries_before_escalation=2,
            max_retries=3,
            task_callback=None,
            sink=None,
            run_id="test-run",
            graph=graph,
            archetypes_config=archetypes_config,
            knowledge_db_conn=knowledge_conn,
            block_task_fn=block_task_fn,
            check_block_budget_fn=MagicMock(),
        )

        state = ExecutionState(
            plan_hash="test",
            node_states=node_states,
            started_at="2026-01-01",
            updated_at="2026-01-01",
        )

        return handler, state, block_task_fn

    def test_pre_review_block_converts_to_retry(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Pre-review blocking with retry_predecessor does NOT permanently block."""
        finding = _make_finding(
            severity="critical",
            description="Command injection vulnerability",
            session_id="test_spec:0:reviewer:pre-review:1",
            category="security",
        )
        insert_findings(knowledge_conn, [finding])

        handler, state, block_task_fn = self._make_handler_with_graph(knowledge_conn)

        record = _make_session_record(
            node_id="test_spec:0:reviewer:pre-review",
            archetype="reviewer",
        )

        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is False
        block_task_fn.assert_not_called()

    def test_drift_review_block_is_permanent(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """Drift-review blocking without retry_predecessor permanently blocks."""
        finding = _make_finding(
            severity="critical",
            description="Missing validation",
            session_id="test_spec:1:1",
        )
        insert_findings(knowledge_conn, [finding])

        node_states = {
            "test_spec:1": "completed",
        }
        graph_sync = MagicMock()
        graph_sync.node_states = node_states

        graph = TaskGraph(
            nodes={
                "test_spec:1": Node(
                    id="test_spec:1",
                    spec_name="test_spec",
                    group_number=1,
                    title="Coder",
                    optional=False,
                    archetype="reviewer",
                    mode="drift-review",
                ),
            },
            edges=[],
            order=["test_spec:1"],
        )

        block_task_fn = MagicMock()
        archetypes_config = _make_archetypes_config(block_threshold=1)

        handler = SessionResultHandler(
            graph_sync=graph_sync,
            routing_ladders={},
            retries_before_escalation=2,
            max_retries=3,
            task_callback=None,
            sink=None,
            run_id="test-run",
            graph=graph,
            archetypes_config=archetypes_config,
            knowledge_db_conn=knowledge_conn,
            block_task_fn=block_task_fn,
            check_block_budget_fn=MagicMock(),
        )

        state = ExecutionState(
            plan_hash="test",
            node_states=node_states,
            started_at="2026-01-01",
            updated_at="2026-01-01",
        )

        record = _make_session_record(
            node_id="test_spec:1",
            archetype="skeptic",
        )

        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is True
        block_task_fn.assert_called_once()


class TestDefaultThreshold:
    """Default pre_review_block_threshold is 1."""

    def test_default_threshold_is_1(self) -> None:
        from agent_fox.core.config import ReviewerConfig

        rc = ReviewerConfig()
        assert rc.pre_review_block_threshold == 1
