"""Tests for audit-review blocking remediation (issue #554).

Verifies that ``reviewer:audit-review`` findings trigger a retry of the
test-group coder rather than being silently ignored.

Acceptance Criteria:
  AC-1: evaluate_review_blocking() returns blocking when critical/major audit
        findings exist for the (spec, task_group).
  AC-2: evaluate_review_blocking() does NOT block when no critical/major audit
        findings exist (empty table, superseded rows, or non-audit rows).
  AC-3: check_skeptic_blocking() triggers _retry_on_review_block for audit-review
        blocking decisions, resetting the test_group coder to pending.
  AC-4: build_retry_context() includes audit findings in the re-run coder's
        prompt when task_group matches.
  AC-5: Repeated audit failures exhaust the predecessor escalation ladder and
        permanently block the coder rather than looping infinitely.

Requirements: 554-REQ-1
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import duckdb
import pytest

from agent_fox.engine.blocking import evaluate_review_blocking
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord
from agent_fox.graph.types import Edge, Node, TaskGraph
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.knowledge.review_store import ReviewFinding, insert_findings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audit_finding(
    *,
    severity: str = "critical",
    description: str = "Missing assertion after DB write",
    spec_name: str = "foo",
    task_group: str = "2",
    session_id: str = "foo:audit:1",
    category: str = "audit",
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


def _make_audit_review_record(
    node_id: str = "foo:2:reviewer:audit-review",
    attempt: int = 1,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        archetype="reviewer",
        attempt=attempt,
        status="completed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=None,
        timestamp="2026-01-01T00:00:00",
    )


@pytest.fixture
def audit_conn() -> duckdb.DuckDBPyConnection:
    """Fresh in-memory DuckDB with full schema for audit-review tests."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# AC-1: evaluate_review_blocking() returns blocking when critical/major
#        audit findings exist.
# ---------------------------------------------------------------------------


class TestAC1EvaluateReviewBlockingReturnsBlock:
    """AC-1: evaluate_review_blocking with mode='audit-review' blocks on
    critical/major findings with category='audit'."""

    def test_critical_audit_finding_triggers_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Single critical audit finding → should_block=True, coder_node_id='foo:2'."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is True
        assert decision.coder_node_id == "foo:2"
        assert decision.reason  # non-empty

    def test_major_audit_finding_triggers_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Major-severity audit finding also triggers blocking (not critical-only)."""
        finding = _make_audit_finding(
            severity="major",
            description="Tests lack DB-state assertions",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is True
        assert decision.coder_node_id == "foo:2"

    def test_reason_includes_finding_count_and_description(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Blocking reason includes finding count and truncated description."""
        finding = _make_audit_finding(
            description="Tests do not assert HTTP status code after POST",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is True
        assert "1" in decision.reason
        assert "foo:2" in decision.reason

    def test_multiple_audit_findings_all_count(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Multiple audit findings all contribute to the reason summary."""
        findings = [
            _make_audit_finding(
                description=f"Audit gap {i}",
                spec_name="foo",
                task_group="2",
                session_id=f"foo:audit:{i}",
            )
            for i in range(5)
        ]
        # Insert individually to avoid supersession of earlier rows
        for f in findings:
            audit_conn.execute(
                """
                INSERT INTO review_findings
                    (id, severity, description, spec_name, task_group, session_id, category)
                VALUES (gen_random_uuid(), 'critical', ?, 'foo', '2', ?, 'audit')
                """,
                [f.description, f.session_id],
            )

        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is True
        assert "and" in decision.reason  # "and N more" present when >3


# ---------------------------------------------------------------------------
# AC-2: evaluate_review_blocking() does NOT block when no critical/major
#        audit findings exist.
# ---------------------------------------------------------------------------


class TestAC2EvaluateReviewBlockingNoBlock:
    """AC-2: evaluate_review_blocking with mode='audit-review' does not block
    when no critical/major audit findings exist."""

    def test_empty_db_returns_no_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Empty review_findings table → should_block=False."""
        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is False

    def test_superseded_finding_does_not_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Superseded audit finding is excluded → should_block=False."""
        # Insert a critical audit finding, then supersede it
        old_id = str(uuid.uuid4())
        new_id = str(uuid.uuid4())
        audit_conn.execute(
            """
            INSERT INTO review_findings
                (id, severity, description, spec_name, task_group, session_id, category)
            VALUES (?, 'critical', 'Old gap', 'foo', '2', 'foo:audit:1', 'audit')
            """,
            [old_id],
        )
        # Mark the old finding as superseded
        audit_conn.execute(
            "UPDATE review_findings SET superseded_by = ? WHERE id = ?",
            [new_id, old_id],
        )

        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is False

    def test_non_audit_category_does_not_trigger_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Critical finding with category='security' (not 'audit') is ignored."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
            category="security",  # not 'audit'
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is False

    def test_wrong_task_group_does_not_block(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Audit finding for task_group='3' does not block coder for group 2."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="3",  # different group
            session_id="foo:audit:1",
            category="audit",
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        decision = evaluate_review_blocking(record, None, audit_conn, mode="audit-review")

        assert decision.should_block is False

    def test_fix_review_mode_never_blocks(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """fix-review mode is excluded from blocking even with audit findings."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, audit_conn, mode="fix-review")

        assert decision.should_block is False

    def test_null_knowledge_db_returns_no_block(self) -> None:
        """None knowledge_db_conn → should_block=False without crash."""
        record = _make_audit_review_record()
        decision = evaluate_review_blocking(record, None, None, mode="audit-review")

        assert decision.should_block is False


# ---------------------------------------------------------------------------
# AC-3: check_skeptic_blocking() triggers _retry_on_review_block for
#        audit-review, resetting the test_group coder to pending.
# ---------------------------------------------------------------------------


def _make_audit_review_handler(
    audit_conn: duckdb.DuckDBPyConnection,
) -> tuple[SessionResultHandler, ExecutionState, MagicMock]:
    """Build a minimal SessionResultHandler wired to an audit-review scenario.

    Graph: foo:2 (coder) → foo:2:reviewer:audit-review (reviewer)
    """
    node_states: dict[str, str] = {
        "foo:2": "completed",
        "foo:2:reviewer:audit-review": "completed",
    }
    edges_dict: dict[str, list[str]] = {
        "foo:2": [],
        "foo:2:reviewer:audit-review": ["foo:2"],
    }

    graph_sync = MagicMock()
    graph_sync.node_states = node_states
    graph_sync.predecessors = lambda nid: edges_dict.get(nid, [])

    # Configure _transition to actually update node_states so assertions on
    # state transitions work correctly after check_skeptic_blocking() runs.
    def _transition(nid: str, new_status: str, *, reason: str = "") -> None:
        node_states[nid] = new_status

    graph_sync._transition.side_effect = _transition

    graph = TaskGraph(
        nodes={
            "foo:2": Node(
                id="foo:2",
                spec_name="foo",
                group_number=2,
                title="Write tests",
                optional=False,
                archetype="coder",
            ),
            "foo:2:reviewer:audit-review": Node(
                id="foo:2:reviewer:audit-review",
                spec_name="foo",
                group_number=2,
                title="Reviewer (audit-review)",
                optional=False,
                archetype="reviewer",
                mode="audit-review",
            ),
        },
        edges=[
            Edge(
                source="foo:2",
                target="foo:2:reviewer:audit-review",
                kind="intra_spec",
            )
        ],
        order=["foo:2", "foo:2:reviewer:audit-review"],
    )

    block_task_fn = MagicMock()
    archetypes_config = MagicMock()
    archetypes_config.reviewer_config.pre_review_block_threshold = 1
    archetypes_config.reviewer_config.audit_max_retries = 2

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
        knowledge_db_conn=audit_conn,
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


class TestAC3CheckSkepticBlockingForAuditReview:
    """AC-3: check_skeptic_blocking triggers retry_predecessor for audit-review."""

    def test_audit_review_blocking_resets_coder_to_pending(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """When audit findings block, the coder is reset to pending (not permanently blocked)."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_review_handler(audit_conn)
        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")

        # check_skeptic_blocking returns False when coder is reset (not permanently blocked)
        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is False, "retry_predecessor=True should not permanently block the coder"
        block_task_fn.assert_not_called()
        # Both coder and audit-review nodes should be pending for retry
        assert handler._graph_sync.node_states.get("foo:2") == "pending"
        assert handler._graph_sync.node_states.get("foo:2:reviewer:audit-review") == "pending"

    def test_no_audit_findings_does_not_trigger_retry(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Empty audit findings → no blocking, coder stays completed."""
        handler, state, block_task_fn = _make_audit_review_handler(audit_conn)
        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")

        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is False
        block_task_fn.assert_not_called()
        assert state.node_states["foo:2"] == "completed"

    def test_audit_review_has_retry_predecessor_flag(self) -> None:
        """audit-review mode has retry_predecessor=True in archetypes."""
        from agent_fox.archetypes import get_archetype, resolve_effective_config

        entry = get_archetype("reviewer")
        resolved = resolve_effective_config(entry, "audit-review")
        assert resolved.retry_predecessor is True


# ---------------------------------------------------------------------------
# AC-4: build_retry_context() includes audit findings in re-run coder prompt.
# ---------------------------------------------------------------------------


class TestAC4BuildRetryContextIncludesAuditFindings:
    """AC-4: build_retry_context() includes active audit findings for the
    matching (spec_name, task_group)."""

    def test_critical_audit_finding_included_in_retry_context(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """build_retry_context returns non-empty string with the audit finding."""
        from agent_fox.engine.session_lifecycle import build_retry_context

        finding = _make_audit_finding(
            severity="critical",
            description="Test does not assert DB state after insert",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        # Wrap the raw connection in a KnowledgeDB-compatible shim
        class _MockKnowledgeDB:
            connection = audit_conn

        ctx = build_retry_context(_MockKnowledgeDB(), "foo", task_group="2")  # type: ignore[arg-type]

        assert ctx, "build_retry_context must return non-empty string when audit findings exist"
        assert "Test does not assert DB state after insert" in ctx

    def test_major_audit_finding_included(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Major-severity audit findings are also included in the retry context."""
        from agent_fox.engine.session_lifecycle import build_retry_context

        finding = _make_audit_finding(
            severity="major",
            description="Assertions are too shallow",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        class _MockKnowledgeDB:
            connection = audit_conn

        ctx = build_retry_context(_MockKnowledgeDB(), "foo", task_group="2")  # type: ignore[arg-type]

        assert ctx
        assert "Assertions are too shallow" in ctx

    def test_wrong_task_group_finding_excluded(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Audit finding for task_group='3' is excluded when querying for group 2."""
        from agent_fox.engine.session_lifecycle import build_retry_context

        finding = _make_audit_finding(
            severity="critical",
            description="Finding for group 3",
            spec_name="foo",
            task_group="3",
            session_id="foo:audit:1",
        )
        insert_findings(audit_conn, [finding])

        class _MockKnowledgeDB:
            connection = audit_conn

        ctx = build_retry_context(_MockKnowledgeDB(), "foo", task_group="2")  # type: ignore[arg-type]

        assert ctx == "", (
            "Findings for task_group='3' must not appear when build_retry_context is called with task_group='2'"
        )

    def test_no_findings_returns_empty_string(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Empty finding table → build_retry_context returns empty string."""
        from agent_fox.engine.session_lifecycle import build_retry_context

        class _MockKnowledgeDB:
            connection = audit_conn

        ctx = build_retry_context(_MockKnowledgeDB(), "foo", task_group="2")  # type: ignore[arg-type]

        assert ctx == ""


# ---------------------------------------------------------------------------
# AC-5: Exhausted escalation ladder permanently blocks the coder.
# ---------------------------------------------------------------------------


class TestAC5ExhaustedLadderBlocksPermanently:
    """AC-5: When the predecessor coder's EscalationLadder is exhausted,
    _retry_on_review_block permanently blocks the coder instead of looping."""

    def test_exhausted_audit_retries_permanently_blocks_coder(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """After audit_max_retries is exhausted, the coder is blocked (not reset to pending)."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_review_handler(audit_conn)

        # Pre-exhaust the audit retry counter (audit_max_retries=2)
        handler._audit_retry_counts["foo:2"] = 2

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        handler.check_skeptic_blocking(record, state)

        # With exhausted audit counter, the coder should be permanently blocked
        block_task_fn.assert_called_once()
        blocked_node_id = block_task_fn.call_args[0][0]
        assert blocked_node_id == "foo:2"

    def test_non_exhausted_ladder_still_retries(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """With a fresh ladder, the coder is reset to pending (not permanently blocked)."""
        finding = _make_audit_finding(
            severity="critical",
            spec_name="foo",
            task_group="2",
        )
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_review_handler(audit_conn)

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        handler.check_skeptic_blocking(record, state)

        # Fresh ladder → convert to retry, not permanent block
        block_task_fn.assert_not_called()
        assert state.node_states["foo:2"] == "pending"


# ---------------------------------------------------------------------------
# AC-6: audit_max_retries from ReviewerConfig controls the audit-review
#        retry limit independently of the generic EscalationLadder.
# ---------------------------------------------------------------------------


def _make_audit_handler_with_config(
    audit_conn: duckdb.DuckDBPyConnection,
    audit_max_retries: int = 2,
    retries_before_escalation: int = 5,
) -> tuple[SessionResultHandler, ExecutionState, MagicMock]:
    """Build a handler where audit_max_retries and retries_before_escalation differ."""
    node_states: dict[str, str] = {
        "foo:2": "completed",
        "foo:2:reviewer:audit-review": "completed",
    }
    edges_dict: dict[str, list[str]] = {
        "foo:2": [],
        "foo:2:reviewer:audit-review": ["foo:2"],
    }

    graph_sync = MagicMock()
    graph_sync.node_states = node_states
    graph_sync.predecessors = lambda nid: edges_dict.get(nid, [])

    def _transition(nid: str, new_status: str, *, reason: str = "") -> None:
        node_states[nid] = new_status

    graph_sync._transition.side_effect = _transition

    graph = TaskGraph(
        nodes={
            "foo:2": Node(
                id="foo:2",
                spec_name="foo",
                group_number=2,
                title="Write tests",
                optional=False,
                archetype="coder",
            ),
            "foo:2:reviewer:audit-review": Node(
                id="foo:2:reviewer:audit-review",
                spec_name="foo",
                group_number=2,
                title="Reviewer (audit-review)",
                optional=False,
                archetype="reviewer",
                mode="audit-review",
            ),
        },
        edges=[
            Edge(
                source="foo:2",
                target="foo:2:reviewer:audit-review",
                kind="intra_spec",
            )
        ],
        order=["foo:2", "foo:2:reviewer:audit-review"],
    )

    block_task_fn = MagicMock()
    archetypes_config = MagicMock()
    archetypes_config.reviewer_config.pre_review_block_threshold = 1
    archetypes_config.reviewer_config.audit_max_retries = audit_max_retries

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        routing_ladders={},
        retries_before_escalation=retries_before_escalation,
        max_retries=10,
        task_callback=None,
        sink=None,
        run_id="test-run",
        graph=graph,
        archetypes_config=archetypes_config,
        knowledge_db_conn=audit_conn,
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


class TestAC6AuditMaxRetriesConfig:
    """AC-6: audit_max_retries from ReviewerConfig controls audit-review retry
    limit independently of the generic EscalationLadder."""

    def test_audit_retries_limited_by_audit_max_retries(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """After audit_max_retries (2) cycles, coder is permanently blocked."""
        finding = _make_audit_finding(severity="critical", spec_name="foo", task_group="2")
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_handler_with_config(
            audit_conn, audit_max_retries=2, retries_before_escalation=5
        )

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")

        # First two retries should succeed (convert to pending)
        for i in range(2):
            state.node_states["foo:2"] = "completed"
            state.node_states["foo:2:reviewer:audit-review"] = "completed"
            handler._graph_sync.node_states["foo:2"] = "completed"
            handler._graph_sync.node_states["foo:2:reviewer:audit-review"] = "completed"
            blocked = handler.check_skeptic_blocking(record, state)
            assert blocked is False, f"Retry {i + 1} should convert to retry, not block"
            block_task_fn.assert_not_called()

        # Third attempt should permanently block
        state.node_states["foo:2"] = "completed"
        state.node_states["foo:2:reviewer:audit-review"] = "completed"
        handler._graph_sync.node_states["foo:2"] = "completed"
        handler._graph_sync.node_states["foo:2:reviewer:audit-review"] = "completed"
        blocked = handler.check_skeptic_blocking(record, state)
        assert blocked is True, "After audit_max_retries exhausted, coder must be permanently blocked"
        block_task_fn.assert_called_once()

    def test_audit_retries_do_not_consume_escalation_ladder(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Audit retries should not consume the coder's generic EscalationLadder budget."""
        finding = _make_audit_finding(severity="critical", spec_name="foo", task_group="2")
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_handler_with_config(
            audit_conn, audit_max_retries=1, retries_before_escalation=5
        )

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")

        # One retry allowed
        state.node_states["foo:2"] = "completed"
        handler._graph_sync.node_states["foo:2"] = "completed"
        handler.check_skeptic_blocking(record, state)
        block_task_fn.assert_not_called()

        # The coder's generic escalation ladder should not have been created/consumed
        assert "foo:2" not in handler._routing_ladders, (
            "Audit retries must not create or consume the coder's generic EscalationLadder"
        )

    def test_audit_max_retries_zero_blocks_immediately(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """With audit_max_retries=0, the very first audit block permanently blocks."""
        finding = _make_audit_finding(severity="critical", spec_name="foo", task_group="2")
        insert_findings(audit_conn, [finding])

        handler, state, block_task_fn = _make_audit_handler_with_config(audit_conn, audit_max_retries=0)

        record = _make_audit_review_record(node_id="foo:2:reviewer:audit-review")
        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is True
        block_task_fn.assert_called_once()

    def test_pre_review_still_uses_escalation_ladder(self, audit_conn: duckdb.DuckDBPyConnection) -> None:
        """Pre-review mode (not audit-review) still uses the generic EscalationLadder."""
        from agent_fox.knowledge.review_store import ReviewFinding

        finding = ReviewFinding(
            id=str(uuid.uuid4()),
            severity="critical",
            description="Security issue",
            requirement_ref=None,
            spec_name="foo",
            task_group="1",
            session_id="foo:0:reviewer:pre-review:1",
            category="security",
        )
        insert_findings(audit_conn, [finding])

        node_states: dict[str, str] = {
            "foo:0:reviewer:pre-review": "completed",
            "foo:1": "completed",
        }
        edges_dict: dict[str, list[str]] = {
            "foo:0:reviewer:pre-review": [],
            "foo:1": ["foo:0:reviewer:pre-review"],
        }
        graph_sync = MagicMock()
        graph_sync.node_states = node_states
        graph_sync.predecessors = lambda nid: edges_dict.get(nid, [])

        def _transition(nid: str, new_status: str, *, reason: str = "") -> None:
            node_states[nid] = new_status

        graph_sync._transition.side_effect = _transition

        graph = TaskGraph(
            nodes={
                "foo:0:reviewer:pre-review": Node(
                    id="foo:0:reviewer:pre-review",
                    spec_name="foo",
                    group_number=0,
                    title="Pre-review",
                    optional=False,
                    archetype="reviewer",
                    mode="pre-review",
                ),
                "foo:1": Node(
                    id="foo:1",
                    spec_name="foo",
                    group_number=1,
                    title="Coder",
                    optional=False,
                    archetype="coder",
                ),
            },
            edges=[Edge(source="foo:0:reviewer:pre-review", target="foo:1", kind="intra_spec")],
            order=["foo:0:reviewer:pre-review", "foo:1"],
        )

        block_task_fn = MagicMock()
        archetypes_config = MagicMock()
        archetypes_config.reviewer_config.pre_review_block_threshold = 1
        archetypes_config.reviewer_config.audit_max_retries = 0

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
            knowledge_db_conn=audit_conn,
            block_task_fn=block_task_fn,
            check_block_budget_fn=MagicMock(),
        )

        state = ExecutionState(
            plan_hash="test",
            node_states=node_states,
            started_at="2026-01-01",
            updated_at="2026-01-01",
        )

        record = _make_audit_review_record(
            node_id="foo:0:reviewer:pre-review",
        )
        record = SessionRecord(
            node_id="foo:0:reviewer:pre-review",
            archetype="reviewer",
            attempt=1,
            status="completed",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            duration_ms=0,
            error_message=None,
            timestamp="2026-01-01T00:00:00",
        )

        # Suppress errata file generation (side effect that pollutes the working tree)
        handler._generate_errata = MagicMock()

        # Pre-review with retry_predecessor=True should use the escalation ladder,
        # not audit_max_retries. audit_max_retries=0 would block immediately if
        # the code incorrectly applied it to pre-review.
        blocked = handler.check_skeptic_blocking(record, state)

        assert blocked is False, (
            "Pre-review should use the generic EscalationLadder (retries_before_escalation=2), not audit_max_retries=0"
        )
        block_task_fn.assert_not_called()
