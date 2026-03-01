"""Unit tests for status report generation.

Test Spec: TS-07-1, TS-07-2, TS-07-3, TS-07-E1, TS-07-E2
Requirements: 07-REQ-1.1, 07-REQ-1.2, 07-REQ-1.3, 07-REQ-1.E1, 07-REQ-1.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.status import generate_status

from .conftest import (
    make_execution_state,
    make_session_record,
    write_plan_file,
    write_state_file,
)

# ---------------------------------------------------------------------------
# TS-07-1: Status displays task counts by status
# Requirement: 07-REQ-1.1
# ---------------------------------------------------------------------------


class TestStatusTaskCounts:
    """TS-07-1: Status displays task counts by status."""

    def test_counts_match_task_states(
        self, tmp_state_path: Path, tmp_plan_dir: Path,
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
        write_state_file(tmp_state_path, state)

        report = generate_status(tmp_state_path, plan_path)

        assert report.counts["completed"] == 3
        assert report.counts["failed"] == 1
        assert report.counts["blocked"] == 1
        assert report.counts["pending"] == 2
        assert report.total_tasks == 7

    def test_total_tasks_equals_node_count(
        self, tmp_state_path: Path, tmp_plan_dir: Path,
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
        write_state_file(tmp_state_path, state)

        report = generate_status(tmp_state_path, plan_path)

        assert report.total_tasks == 3


# ---------------------------------------------------------------------------
# TS-07-2: Status displays token usage and cost
# Requirement: 07-REQ-1.2
# ---------------------------------------------------------------------------


class TestStatusTokensAndCost:
    """TS-07-2: Status displays token usage and cost."""

    def test_cumulative_tokens_and_cost(
        self, tmp_state_path: Path, tmp_plan_dir: Path,
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
        write_state_file(tmp_state_path, state)

        report = generate_status(tmp_state_path, plan_path)

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
        self, tmp_state_path: Path, tmp_plan_dir: Path,
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
        write_state_file(tmp_state_path, state)

        report = generate_status(tmp_state_path, plan_path)

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
        self, tmp_plan_dir: Path,
    ) -> None:
        """All tasks show as pending with zero cost when no state file exists."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
            "spec_a:4": {"title": "Task 4"},
            "spec_a:5": {"title": "Task 5"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)
        nonexistent_state = Path("/nonexistent/state.jsonl")

        report = generate_status(nonexistent_state, plan_path)

        assert report.counts["pending"] == 5
        assert report.input_tokens == 0
        assert report.output_tokens == 0
        assert report.estimated_cost == 0.0
        assert len(report.problem_tasks) == 0


# ---------------------------------------------------------------------------
# TS-07-E2: Status with no plan file
# Requirement: 07-REQ-1.E2
# ---------------------------------------------------------------------------


class TestStatusNoPlanFile:
    """TS-07-E2: Status fails gracefully when no plan exists."""

    def test_no_plan_file_raises_error(self) -> None:
        """AgentFoxError raised when neither state nor plan file exists."""
        bad_state = Path("/nonexistent/state.jsonl")
        bad_plan = Path("/nonexistent/plan.json")

        with pytest.raises(AgentFoxError) as exc_info:
            generate_status(bad_state, bad_plan)

        assert "plan" in str(exc_info.value).lower()
