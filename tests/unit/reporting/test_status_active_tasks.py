"""Unit tests for active tasks section in status report.

Test Spec: TS-72-1 through TS-72-10, TS-72-E1 through TS-72-E3
Requirements: 72-REQ-1.1, 72-REQ-1.2, 72-REQ-1.3,
              72-REQ-1.E1, 72-REQ-1.E2,
              72-REQ-2.1, 72-REQ-2.2, 72-REQ-2.3, 72-REQ-2.4, 72-REQ-2.5,
              72-REQ-2.E1, 72-REQ-3.1, 72-REQ-3.2
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from agent_fox.reporting.formatters import JsonFormatter, TableFormatter
from agent_fox.reporting.standup import TaskActivity
from agent_fox.reporting.status import StatusReport, generate_status

from .conftest import (
    make_execution_state,
    make_session_record,
    mock_state,
    write_plan_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_activity(
    task_id: str = "spec/0:coder",
    current_status: str = "in_progress",
    completed_sessions: int = 1,
    total_sessions: int = 2,
    input_tokens: int = 500_000,
    output_tokens: int = 750_000,
    cost: float = 12.34,
) -> TaskActivity:
    """Return a TaskActivity with sensible defaults."""
    return TaskActivity(
        task_id=task_id,
        current_status=current_status,
        completed_sessions=completed_sessions,
        total_sessions=total_sessions,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )


def _make_minimal_report(
    in_progress_tasks: list[TaskActivity] | None = None,
) -> StatusReport:
    """Return a minimal StatusReport with optional in_progress_tasks."""
    return StatusReport(
        counts={"completed": 1, "pending": 1},
        total_tasks=2,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0.0,
        problem_tasks=[],
        per_spec={},
        cost_by_archetype={"coder": 1.50},
        in_progress_tasks=in_progress_tasks if in_progress_tasks is not None else [],
    )


# ---------------------------------------------------------------------------
# TS-72-1: In-progress tasks populated in StatusReport
# Requirement: 72-REQ-1.1
# ---------------------------------------------------------------------------


class TestReportGeneration:
    """Tests for generate_status() populating in_progress_tasks."""

    def test_single_inprogress_task_included(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """TS-72-1: generate_status populates in_progress_tasks for in-progress nodes.

        Requirements: 72-REQ-1.1
        """
        nodes = {
            "spec/0:completed_task": {"title": "Done task"},
            "spec/0:coder": {"title": "Active coder"},
            "spec/0:pending_task": {"title": "Pending task"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        sessions = [
            make_session_record(node_id="spec/0:coder", status="completed"),
        ]
        state = make_execution_state(
            node_states={
                "spec/0:completed_task": "completed",
                "spec/0:coder": "in_progress",
                "spec/0:pending_task": "pending",
            },
            session_history=sessions,
        )

        with mock_state(state):
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert len(report.in_progress_tasks) == 1
        assert report.in_progress_tasks[0].task_id == "spec/0:coder"

    def test_coder_and_verifier_inprogress_included(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """TS-72-2: Both coder and non-coder in-progress nodes are included.

        Requirements: 72-REQ-1.2
        """
        nodes = {
            "spec/0:coder": {"title": "Coder task"},
            "spec/0:verifier": {"title": "Verifier task"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        state = make_execution_state(
            node_states={
                "spec/0:coder": "in_progress",
                "spec/0:verifier": "in_progress",
            },
        )

        with mock_state(state):
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert len(report.in_progress_tasks) == 2
        task_ids = {ta.task_id for ta in report.in_progress_tasks}
        assert any("coder" in tid for tid in task_ids)
        assert any("verifier" in tid for tid in task_ids)

    def test_session_metrics_computed_correctly(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """TS-72-3: Session counts and token totals match session history.

        Requirements: 72-REQ-1.3
        """
        nodes = {
            "spec/0:coder": {"title": "Active coder"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        sessions = [
            make_session_record(
                node_id="spec/0:coder",
                status="completed",
                input_tokens=1_000,
                output_tokens=500,
                cost=0.10,
            ),
            make_session_record(
                node_id="spec/0:coder",
                status="completed",
                input_tokens=2_000,
                output_tokens=1_000,
                cost=0.20,
            ),
            make_session_record(
                node_id="spec/0:coder",
                status="failed",
                input_tokens=500,
                output_tokens=200,
                cost=0.05,
            ),
        ]
        state = make_execution_state(
            node_states={"spec/0:coder": "in_progress"},
            session_history=sessions,
        )

        with mock_state(state):
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert len(report.in_progress_tasks) == 1
        ta = report.in_progress_tasks[0]
        assert ta.completed_sessions == 2
        assert ta.total_sessions == 3
        assert ta.input_tokens == 3_500
        assert ta.output_tokens == 1_700
        assert abs(ta.cost - 0.35) < 0.001


# ---------------------------------------------------------------------------
# TS-72-4 through TS-72-8: Text formatting
# Requirements: 72-REQ-2.1, 72-REQ-2.2, 72-REQ-2.3, 72-REQ-2.4, 72-REQ-2.5
# ---------------------------------------------------------------------------


class TestTextFormatting:
    """Tests for TableFormatter rendering the Active Tasks section."""

    def test_active_tasks_section_present_when_nonempty(self) -> None:
        """TS-72-4: 'Active Tasks' heading appears when in_progress_tasks is non-empty.

        Requirements: 72-REQ-2.1
        """
        ta = _make_task_activity()
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = TableFormatter().format_status(report)

        assert "Active Tasks" in output

    def test_active_tasks_before_cost_by_archetype(self) -> None:
        """TS-72-5: 'Active Tasks' section appears before 'Cost by Archetype'.

        Requirements: 72-REQ-2.2
        """
        ta = _make_task_activity()
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = TableFormatter().format_status(report)

        active_pos = output.index("Active Tasks")
        cost_pos = output.index("Cost by Archetype")
        assert active_pos < cost_pos

    def test_task_with_sessions_formatted_correctly(self) -> None:
        """TS-72-6: Tasks with sessions render full session/token/cost details.

        Requirements: 72-REQ-2.3
        """
        ta = _make_task_activity(
            task_id="spec/0:coder",
            current_status="in_progress",
            completed_sessions=1,
            total_sessions=2,
            input_tokens=500_000,
            output_tokens=750_000,
            cost=12.34,
        )
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = TableFormatter().format_status(report)

        expected_line = "spec/0/coder [coder]: in_progress. 1/2 sessions. tokens 500.0k in / 750.0k out. $12.34"
        assert expected_line in output

    def test_task_with_zero_sessions_formatted_correctly(self) -> None:
        """TS-72-7: Tasks with zero sessions render only id and status.

        Requirements: 72-REQ-2.4
        """
        ta = _make_task_activity(
            task_id="spec/0:verifier",
            current_status="in_progress",
            completed_sessions=0,
            total_sessions=0,
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
        )
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = TableFormatter().format_status(report)

        assert "spec/0/verifier [coder]: in_progress" in output
        # Must not have trailing dot (no session details)
        assert "spec/0/verifier [coder]: in_progress." not in output

    def test_active_tasks_section_absent_when_empty(self) -> None:
        """TS-72-8: 'Active Tasks' section is omitted when in_progress_tasks is empty.

        Requirements: 72-REQ-2.5
        """
        report = _make_minimal_report(in_progress_tasks=[])

        output = TableFormatter().format_status(report)

        assert "Active Tasks" not in output


# ---------------------------------------------------------------------------
# TS-72-9 and TS-72-10: JSON output
# Requirements: 72-REQ-3.1, 72-REQ-3.2
# ---------------------------------------------------------------------------


class TestJsonOutput:
    """Tests for JsonFormatter including in_progress_tasks in JSON output."""

    def test_json_includes_in_progress_tasks_array(self) -> None:
        """TS-72-9: JSON output contains 'in_progress_tasks' key with list.

        Requirements: 72-REQ-3.1
        """
        ta = _make_task_activity()
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = JsonFormatter().format_status(report)
        data = json.loads(output)

        assert "in_progress_tasks" in data
        assert len(data["in_progress_tasks"]) == 1

    def test_json_task_activity_has_all_required_fields(self) -> None:
        """TS-72-10: Each TaskActivity in JSON has all 7 required fields.

        Requirements: 72-REQ-3.2
        """
        ta = _make_task_activity()
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = JsonFormatter().format_status(report)
        data = json.loads(output)

        task = data["in_progress_tasks"][0]
        required_fields = {
            "task_id",
            "current_status",
            "completed_sessions",
            "total_sessions",
            "input_tokens",
            "output_tokens",
            "cost",
            "archetype",
        }
        assert set(task.keys()) == required_fields


# ---------------------------------------------------------------------------
# Edge cases: TS-72-E1, TS-72-E2, TS-72-E3
# Requirements: 72-REQ-1.E1, 72-REQ-1.E2, 72-REQ-2.E1
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for active tasks in status report."""

    def test_no_state_file_gives_empty_in_progress_tasks(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """TS-72-E1: When no state exists, in_progress_tasks is empty.

        Requirements: 72-REQ-1.E2
        """
        nodes = {"spec/0:coder": {"title": "Coder"}}
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        report = generate_status(plan_path=plan_path)

        assert report.in_progress_tasks == []

    def test_no_inprogress_nodes_gives_empty_list(
        self,
        tmp_plan_dir: Path,
    ) -> None:
        """TS-72-E2: When no nodes have in_progress status, list is empty.

        Requirements: 72-REQ-1.E1
        """
        nodes = {
            "spec/0:coder": {"title": "Coder A"},
            "spec/0:verifier": {"title": "Verifier"},
            "spec/0:skeptic": {"title": "Skeptic"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        state = make_execution_state(
            node_states={
                "spec/0:coder": "completed",
                "spec/0:verifier": "completed",
                "spec/0:skeptic": "pending",
            },
        )

        with mock_state(state):
            report = generate_status(plan_path=plan_path, db_conn=MagicMock())

        assert report.in_progress_tasks == []

    def test_zero_tokens_nonzero_sessions_displays_zero_tokens(self) -> None:
        """TS-72-E3: Task with sessions but zero tokens displays '0 in / 0 out'.

        Requirements: 72-REQ-2.E1
        """
        ta = _make_task_activity(
            task_id="spec/0:coder",
            current_status="in_progress",
            completed_sessions=1,
            total_sessions=1,
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
        )
        report = _make_minimal_report(in_progress_tasks=[ta])

        output = TableFormatter().format_status(report)

        assert "tokens 0 in / 0 out" in output
