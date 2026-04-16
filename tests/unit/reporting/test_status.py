"""Unit tests for status report generation.

Test Spec: TS-07-1, TS-07-2, TS-07-3, TS-07-E1, TS-07-E2
Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-1.E1, 07-REQ-1.E2
"""

from __future__ import annotations

from agent_fox.reporting.status import generate_status

from .conftest import (
    make_execution_state,
    make_session_record,
    mock_state,
    write_plan_to_db,
)

# ---------------------------------------------------------------------------
# TS-07-1: Status displays task counts by status
# Requirement: 07-REQ-1.1
# ---------------------------------------------------------------------------


class TestStatusTaskCounts:
    """TS-07-1: Status displays task counts by status."""

    def test_counts_match_task_states(self) -> None:
        """Task counts grouped by status match the execution state."""
        # Preconditions: 3 completed, 1 failed, 1 blocked, 2 pending = 7 total
        nodes = {
            "spec_a:1": {"title": "Task A1"},
            "spec_a:2": {"title": "Task A2"},
            "spec_a:3": {"title": "Task A3"},
            "spec_b:1": {"title": "Task B1"},
            "spec_b:2": {"title": "Task B2"},
            "spec_b:3": {"title": "Task B3"},
            "spec_b:4": {"title": "Task B4"},
        }
        conn = write_plan_to_db(nodes=nodes)

        state = make_execution_state(
            node_states={
                "spec_a:1": "completed",
                "spec_a:2": "completed",
                "spec_a:3": "completed",
                "spec_b:1": "failed",
                "spec_b:2": "blocked",
                "spec_b:3": "pending",
                "spec_b:4": "pending",
            },
        )

        with mock_state(state):
            report = generate_status(db_conn=conn)

        assert report.counts["completed"] == 3
        assert report.counts["failed"] == 1
        assert report.counts["blocked"] == 1
        assert report.counts["pending"] == 2
        assert report.total_tasks == 7

    def test_total_tasks_equals_node_count(self) -> None:
        """total_tasks equals the number of nodes in the plan."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
        }
        conn = write_plan_to_db(nodes=nodes)

        state = make_execution_state(
            node_states={
                "spec_a:1": "completed",
                "spec_a:2": "pending",
                "spec_a:3": "pending",
            },
        )

        with mock_state(state):
            report = generate_status(db_conn=conn)

        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# TS-07-2: Status displays token usage and cost
# Requirement: 07-REQ-1.2
# ---------------------------------------------------------------------------


class TestStatusTokensAndCost:
    """TS-07-2: Status displays token usage and cost."""

    def test_cumulative_tokens_and_cost(self) -> None:
        """Status report includes cumulative token and cost data."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
        }
        conn = write_plan_to_db(nodes=nodes)

        # 3 sessions totaling 100k input, 50k output, $2.50
        sessions = [
            make_session_record(
                node_id="spec_a:1",
                input_tokens=40_000,
                output_tokens=20_000,
                cost=1.00,
            ),
            make_session_record(
                node_id="spec_a:2",
                input_tokens=35_000,
                output_tokens=15_000,
                cost=0.80,
            ),
            make_session_record(
                node_id="spec_a:3",
                input_tokens=25_000,
                output_tokens=15_000,
                cost=0.70,
            ),
        ]
        state = make_execution_state(
            node_states={
                "spec_a:1": "completed",
                "spec_a:2": "completed",
                "spec_a:3": "completed",
            },
            session_history=sessions,
        )

        with mock_state(state):
            report = generate_status(db_conn=conn)

        assert report.input_tokens == 100_000
        assert report.output_tokens == 50_000
        assert report.estimated_cost is not None
        assert abs(report.estimated_cost - 2.50) < 0.01


# ---------------------------------------------------------------------------
# TS-07-3: Status lists blocked and failed tasks
# Requirement: 07-REQ-1.3
# ---------------------------------------------------------------------------


class TestStatusProblemTasks:
    """TS-07-3: Status lists blocked and failed tasks."""

    def test_problem_tasks_includes_failed_and_blocked(self) -> None:
        """Problem tasks list contains failed and blocked tasks with reasons."""
        nodes = {
            "spec_a:1": {"title": "Task A1"},
            "spec_a:2": {"title": "Task A2"},
            "spec_a:3": {"title": "Task A3"},
        }
        edges = [
            {"source": "spec_a:1", "target": "spec_a:2", "kind": "intra_spec"},
        ]
        conn = write_plan_to_db(nodes=nodes, edges=edges)

        # Session with failure
        sessions = [
            make_session_record(
                node_id="spec_a:1",
                status="failed",
                error_message="test failures",
            ),
        ]
        state = make_execution_state(
            node_states={
                "spec_a:1": "failed",
                "spec_a:2": "blocked",
                "spec_a:3": "pending",
            },
            session_history=sessions,
        )

        with mock_state(state):
            report = generate_status(db_conn=conn)

        assert len(report.problem_tasks) == 2

        failed = [t for t in report.problem_tasks if t.status == "failed"]
        assert len(failed) == 1
        assert "test failures" in failed[0].reason

        blocked = [t for t in report.problem_tasks if t.status == "blocked"]
        assert len(blocked) == 1


# ---------------------------------------------------------------------------
# TS-07-E1: Status with no state file
# Requirement: 07-REQ-1.E1
# ---------------------------------------------------------------------------


class TestStatusNoStateFile:
    """TS-07-E1: Status works with plan-only (no execution yet)."""

    def test_no_state_file_shows_all_pending(self) -> None:
        """All-pending plan tasks show as pending with no session data when no state."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
            "spec_a:4": {"title": "Task 4"},
            "spec_a:5": {"title": "Task 5"},
        }
        conn = write_plan_to_db(nodes=nodes)

        report = generate_status(db_conn=conn)

        assert report.counts["pending"] == 5
        # With DB-backed persistence, load_state_from_db always returns
        # a state (even with 0 sessions), so tokens/cost are 0 not None.
        assert report.input_tokens == 0
        assert report.output_tokens == 0
        assert report.estimated_cost == 0.0
        assert len(report.problem_tasks) == 0

    def test_no_state_file_reads_completed_from_plan(self) -> None:
        """Completed nodes in plan are reflected when no state exists."""
        nodes = {
            "spec_a:1": {"title": "Task 1", "status": "completed"},
            "spec_a:2": {"title": "Task 2", "status": "completed"},
            "spec_a:3": {"title": "Task 3"},
        }
        conn = write_plan_to_db(nodes=nodes)

        report = generate_status(db_conn=conn)

        assert report.counts.get("completed", 0) == 2
        assert report.counts.get("pending", 0) == 1
        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# TS-07-E2: Status with no plan
# Requirement: 07-REQ-1.E2
# ---------------------------------------------------------------------------


class TestStatusNoPlanFile:
    """TS-07-E2: Status fails gracefully when no plan exists."""

    def test_no_plan_returns_empty_report(self) -> None:
        """Empty report returned when no plan exists in DB."""
        report = generate_status()

        assert report.total_tasks == 0
        assert report.counts == {}


# ---------------------------------------------------------------------------
# Regression: issue #379 — generate_status shows correct cost when
# plan_nodes is empty but session_outcomes / runs tables have data.
# ---------------------------------------------------------------------------


class TestStatusEmptyPlanNodes:
    """Regression #379: token counts/costs must not be gated on plan_nodes."""

    def test_correct_cost_when_plan_nodes_empty(self) -> None:
        """generate_status shows real cost/tokens from DB even when plan_nodes is empty.

        Preconditions: DB has session_outcomes/runs data but plan_nodes table
        is empty (nightshift execution path).
        Expected: StatusReport reflects actual token counts and cost from DB.
        Assertion: report.input_tokens > 0 and report.estimated_cost > 0.
        """
        import uuid

        import duckdb

        from agent_fox.engine.state import (
            SessionOutcomeRecord,
            create_run,
            record_session,
            update_run_totals,
        )

        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
        }
        conn = write_plan_to_db(nodes=nodes)

        # Clear plan_nodes to simulate the nightshift case where
        # plan_nodes is empty but session data exists
        conn.execute("DELETE FROM plan_nodes")

        # Insert session data
        create_run(conn, "run_1", "hash_abc")
        record_session(
            conn,
            SessionOutcomeRecord(
                id=str(uuid.uuid4()),
                spec_name="spec_a",
                task_group="1",
                node_id="spec_a:1",
                touched_path="file.py",
                status="completed",
                input_tokens=8000,
                output_tokens=3000,
                duration_ms=20000,
                created_at="2026-01-01T00:00:00",
                run_id="run_1",
                attempt=1,
                cost=1.20,
                model="claude-sonnet-4-6",
                archetype="coder",
                commit_sha="abc123",
                error_message=None,
                is_transport_error=False,
            ),
        )
        update_run_totals(conn, "run_1", input_tokens=8000, output_tokens=3000, cost=1.20)

        report = generate_status(db_conn=conn)
        conn.close()

        assert report.input_tokens == 8000, (
            f"Expected 8000 input tokens from DB, got {report.input_tokens}. "
            "load_state_from_db must not gate on plan_nodes being non-empty."
        )
        assert report.output_tokens == 3000
        assert report.estimated_cost is not None
        assert abs(report.estimated_cost - 1.20) < 0.01, (
            f"Expected cost ~1.20 from DB, got {report.estimated_cost}. "
            "Cost must not silently fall back to $0.00 when plan_nodes is empty."
        )
