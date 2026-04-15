"""Unit tests for status report generation.

Test Spec: TS-07-1, TS-07-2, TS-07-3, TS-07-E1, TS-07-E2
Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-1.E1, 07-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.status import generate_status

from .conftest import (
    make_execution_state,
    make_session_record,
    mock_state,
    write_plan_file,
)

# ---------------------------------------------------------------------------
# TS-07-1: Status displays task counts by status
# Requirement: 07-REQ-1.1
# ---------------------------------------------------------------------------


class TestStatusTaskCounts:
    """TS-07-1: Status displays task counts by status."""

    def test_counts_match_task_states(
        self,
        tmp_plan_dir: Path,
    ) -> None:
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
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

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
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert report.counts["completed"] == 3
        assert report.counts["failed"] == 1
        assert report.counts["blocked"] == 1
        assert report.counts["pending"] == 2
        assert report.total_tasks == 7

    def test_total_tasks_equals_node_count(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """total_tasks equals the number of nodes in the plan."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        state = make_execution_state(
            node_states={
                "spec_a:1": "completed",
                "spec_a:2": "pending",
                "spec_a:3": "pending",
            },
        )

        with mock_state(state):
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# TS-07-2: Status displays token usage and cost
# Requirement: 07-REQ-1.2
# ---------------------------------------------------------------------------


class TestStatusTokensAndCost:
    """TS-07-2: Status displays token usage and cost."""

    def test_cumulative_tokens_and_cost(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """Status report includes cumulative token and cost data."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

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
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert report.input_tokens == 100_000
        assert report.output_tokens == 50_000
        assert abs(report.estimated_cost - 2.50) < 0.01


# ---------------------------------------------------------------------------
# TS-07-3: Status lists blocked and failed tasks
# Requirement: 07-REQ-1.3
# ---------------------------------------------------------------------------


class TestStatusProblemTasks:
    """TS-07-3: Status lists blocked and failed tasks."""

    def test_problem_tasks_includes_failed_and_blocked(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """Problem tasks list contains failed and blocked tasks with reasons."""
        nodes = {
            "spec_a:1": {"title": "Task A1"},
            "spec_a:2": {"title": "Task A2"},
            "spec_a:3": {"title": "Task A3"},
        }
        edges = [
            {"source": "spec_a:1", "target": "spec_a:2", "kind": "intra_spec"},
        ]
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes, edges=edges)

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
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

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

    def test_no_state_file_shows_all_pending(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """All-pending plan tasks show as pending with zero cost when no state."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
            "spec_a:4": {"title": "Task 4"},
            "spec_a:5": {"title": "Task 5"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        report = generate_status(plan_path=plan_path)

        assert report.counts["pending"] == 5
        assert report.input_tokens == 0
        assert report.output_tokens == 0
        assert report.estimated_cost == 0.0
        assert len(report.problem_tasks) == 0

    def test_no_state_file_reads_completed_from_plan(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """Completed nodes in plan.json are reflected when no state exists."""
        nodes = {
            "spec_a:1": {"title": "Task 1", "status": "completed"},
            "spec_a:2": {"title": "Task 2", "status": "completed"},
            "spec_a:3": {"title": "Task 3"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        report = generate_status(plan_path=plan_path)

        assert report.counts.get("completed", 0) == 2
        assert report.counts.get("pending", 0) == 1
        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# TS-07-E2: Status with no plan file
# Requirement: 07-REQ-1.E2
# ---------------------------------------------------------------------------


class TestStatusNoPlanFile:
    """TS-07-E2: Status fails gracefully when no plan exists."""

    def test_no_plan_file_raises_error(self) -> None:
        """AgentFoxError raised when plan file does not exist."""
        bad_plan = Path("/nonexistent/plan.json")

        with pytest.raises(AgentFoxError) as exc_info:
            generate_status(plan_path=bad_plan)

        assert "plan" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Regression: issue #379 — generate_status shows correct cost when
# plan_nodes is empty but session_outcomes / runs tables have data.
# ---------------------------------------------------------------------------


class TestStatusEmptyPlanNodes:
    """Regression #379: token counts/costs must not be gated on plan_nodes."""

    def test_correct_cost_when_plan_nodes_empty(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """generate_status shows real cost/tokens from DB even when plan_nodes is empty.

        Preconditions: plan.json exists, DB has session_outcomes/runs data but
        plan_nodes table is empty (nightshift execution path).
        Expected: StatusReport reflects actual token counts and cost from DB.
        Assertion: report.input_tokens > 0 and report.estimated_cost > 0.
        """
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
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        # Build a real in-memory DB with session data but empty plan_nodes
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE plan_nodes (
                id VARCHAR PRIMARY KEY, spec_name VARCHAR NOT NULL,
                group_number INTEGER NOT NULL, title VARCHAR NOT NULL,
                body TEXT NOT NULL DEFAULT '', archetype VARCHAR NOT NULL DEFAULT 'coder',
                mode VARCHAR, model_tier VARCHAR,
                status VARCHAR NOT NULL DEFAULT 'pending',
                subtask_count INTEGER NOT NULL DEFAULT 0,
                optional BOOLEAN NOT NULL DEFAULT FALSE,
                instances INTEGER NOT NULL DEFAULT 1,
                sort_position INTEGER NOT NULL DEFAULT 0,
                blocked_reason VARCHAR,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE plan_meta (
                id INTEGER PRIMARY KEY, content_hash VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fast_mode BOOLEAN NOT NULL DEFAULT FALSE,
                filtered_spec VARCHAR, version VARCHAR NOT NULL DEFAULT ''
            );
            CREATE TABLE runs (
                id VARCHAR PRIMARY KEY, plan_content_hash VARCHAR NOT NULL,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status VARCHAR NOT NULL DEFAULT 'running',
                total_input_tokens BIGINT NOT NULL DEFAULT 0,
                total_output_tokens BIGINT NOT NULL DEFAULT 0,
                total_cost DOUBLE NOT NULL DEFAULT 0.0,
                total_sessions INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE session_outcomes (
                id VARCHAR PRIMARY KEY, spec_name VARCHAR, task_group VARCHAR,
                node_id VARCHAR, touched_path VARCHAR, status VARCHAR,
                input_tokens INTEGER, output_tokens INTEGER, duration_ms INTEGER,
                created_at TIMESTAMP, run_id VARCHAR, attempt INTEGER DEFAULT 1,
                cost DOUBLE DEFAULT 0.0, model VARCHAR, archetype VARCHAR,
                commit_sha VARCHAR, error_message TEXT,
                is_transport_error BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id VARCHAR PRIMARY KEY,
                event_type VARCHAR,
                payload VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # plan_nodes is empty — the nightshift case

        # Insert session data
        create_run(conn, "run_1", "hash_abc")
        record_session(
            conn,
            SessionOutcomeRecord(
                id="s1",
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

        report = generate_status(plan_path=plan_path, db_conn=conn)
        conn.close()

        assert report.input_tokens == 8000, (
            f"Expected 8000 input tokens from DB, got {report.input_tokens}. "
            "load_state_from_db must not gate on plan_nodes being non-empty."
        )
        assert report.output_tokens == 3000
        assert abs(report.estimated_cost - 1.20) < 0.01, (
            f"Expected cost ~1.20 from DB, got {report.estimated_cost}. "
            "Cost must not silently fall back to $0.00 when plan_nodes is empty."
        )
