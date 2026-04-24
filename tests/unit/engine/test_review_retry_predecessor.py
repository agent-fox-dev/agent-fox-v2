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

from agent_fox.engine.blocking import evaluate_review_blocking
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


# ---------------------------------------------------------------------------
# AC-1: evaluate_review_blocking filters session findings to the coder's
# task_group before counting critical findings.
# ---------------------------------------------------------------------------


class TestEvaluateReviewBlockingTaskGroupFilter:
    """AC-1: only findings matching the coder's task_group count toward blocking."""

    def test_cross_group_finding_excluded_from_critical_count(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A finding tagged task_group='1' does NOT block a coder for group 2."""
        # Reviewer runs for group 2; its session has one finding for group 1 (cross-group)
        session_id = "test_spec:2:reviewer:pre-review:1"
        cross_finding = _make_finding(
            severity="critical",
            description="Cross-group finding",
            spec_name="test_spec",
            task_group="1",  # <-- belongs to group 1, not group 2
            session_id=session_id,
        )
        insert_findings(knowledge_conn, [cross_finding])

        record = _make_session_record(
            node_id="test_spec:2:reviewer:pre-review",
            archetype="reviewer",
            attempt=1,
        )
        config = _make_archetypes_config(block_threshold=1)

        decision = evaluate_review_blocking(
            record, config, knowledge_conn, mode="pre-review"
        )

        assert decision.should_block is False, (
            "Cross-group finding (task_group='1') must not block coder for group 2"
        )

    def test_same_group_finding_counts_toward_block(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """A finding tagged task_group='2' DOES block a coder for group 2."""
        session_id = "test_spec:2:reviewer:pre-review:1"
        own_finding = _make_finding(
            severity="critical",
            description="Own-group finding",
            spec_name="test_spec",
            task_group="2",
            session_id=session_id,
        )
        insert_findings(knowledge_conn, [own_finding])

        record = _make_session_record(
            node_id="test_spec:2:reviewer:pre-review",
            archetype="reviewer",
            attempt=1,
        )
        config = _make_archetypes_config(block_threshold=1)

        decision = evaluate_review_blocking(
            record, config, knowledge_conn, mode="pre-review"
        )

        assert decision.should_block is True

    def test_mixed_groups_only_own_group_counts(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """When session has findings for groups 1 and 2, only group-2 counts for group-2 coder."""
        session_id = "test_spec:2:reviewer:pre-review:1"
        findings = [
            _make_finding(
                severity="critical",
                description="Finding for group 2",
                spec_name="test_spec",
                task_group="2",
                session_id=session_id,
            ),
            _make_finding(
                severity="critical",
                description="Finding for group 1",
                spec_name="test_spec",
                task_group="1",
                session_id=session_id,
            ),
        ]
        # Insert group-2 finding first so supersession doesn't erase it
        insert_findings(knowledge_conn, [findings[0]])
        # Insert group-1 finding with different task_group (no supersession conflict)
        knowledge_conn.execute(
            """
            INSERT INTO review_findings (id, severity, description, spec_name, task_group, session_id)
            VALUES (gen_random_uuid(), 'critical', 'Finding for group 1', 'test_spec', '1', ?)
            """,
            [session_id],
        )

        record = _make_session_record(
            node_id="test_spec:2:reviewer:pre-review",
            archetype="reviewer",
            attempt=1,
        )
        config = _make_archetypes_config(block_threshold=2)

        # threshold=2, but only 1 finding for group 2 → should NOT block
        decision = evaluate_review_blocking(
            record, config, knowledge_conn, mode="pre-review"
        )

        assert decision.should_block is False, (
            "Only the group-2 finding should count; cross-group finding should be excluded"
        )


# ---------------------------------------------------------------------------
# AC-2: _retry_on_review_block does not reset coder when no findings match
# the coder's task_group.
# ---------------------------------------------------------------------------


class TestRetryOnReviewBlockTaskGroupFilter:
    """AC-2: review block with only cross-group findings does not reset the coder."""

    def test_cross_group_only_findings_do_not_trigger_retry(
        self, knowledge_conn: duckdb.DuckDBPyConnection
    ) -> None:
        """All session findings for group 0 → block decision is False → coder not reset."""
        session_id = "test_spec:0:reviewer:pre-review:1"
        # Only task_group='0' findings exist
        finding = _make_finding(
            severity="critical",
            description="Spec-wide finding",
            spec_name="test_spec",
            task_group="0",
            session_id=session_id,
        )
        insert_findings(knowledge_conn, [finding])

        node_states = {
            "test_spec:0:reviewer:pre-review": "completed",
            "test_spec:1": "completed",
        }
        graph_sync = MagicMock()
        graph_sync.node_states = node_states

        graph = MagicMock()
        graph.nodes = {
            "test_spec:0:reviewer:pre-review": MagicMock(
                archetype="reviewer", mode="pre-review"
            ),
            "test_spec:1": MagicMock(archetype="coder", mode=None),
        }

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
            node_id="test_spec:0:reviewer:pre-review",
            archetype="reviewer",
            attempt=1,
        )

        # The reviewer runs for group 0, so task_group is mapped to '1' (group-0 targets group-1).
        # But the finding is tagged task_group='0', which != '1'. So no block.
        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is False
        block_task_fn.assert_not_called()
        graph_sync._transition.assert_not_called()
