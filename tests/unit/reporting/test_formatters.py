"""Unit tests for output formatters: JSON, write_output.

Test Spec: TS-07-9, TS-07-E5
Requirements: 07-REQ-3.2, 07-REQ-3.E1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.formatters import (
    JsonFormatter,
    TableFormatter,
    write_output,
)
from agent_fox.reporting.standup import (
    AgentActivity,
    CostBreakdown,
    FileOverlap,
    HumanCommit,
    QueueSummary,
    StandupReport,
)
from agent_fox.reporting.status import StatusReport, TaskSummary

# -- Helpers ------------------------------------------------------------------


def _make_status_report() -> StatusReport:
    """Create a sample StatusReport for formatter tests."""
    return StatusReport(
        counts={
            "completed": 3,
            "failed": 1,
            "blocked": 1,
            "pending": 2,
        },
        total_tasks=7,
        input_tokens=100_000,
        output_tokens=50_000,
        estimated_cost=2.50,
        problem_tasks=[
            TaskSummary(
                task_id="spec_a:2",
                title="Task A2",
                status="failed",
                reason="test failures",
            ),
        ],
        per_spec={
            "spec_a": {"completed": 2, "failed": 1},
            "spec_b": {"completed": 1, "pending": 2, "blocked": 1},
        },
    )


def _make_standup_report() -> StandupReport:
    """Create a sample StandupReport for formatter tests."""
    return StandupReport(
        window_hours=24,
        window_start="2026-02-28T10:00:00Z",
        window_end="2026-03-01T10:00:00Z",
        agent=AgentActivity(
            tasks_completed=2,
            sessions_run=3,
            input_tokens=50_000,
            output_tokens=25_000,
            cost=1.50,
            completed_task_ids=["spec_a:1", "spec_a:2"],
        ),
        human_commits=[
            HumanCommit(
                sha="a" * 40,
                author="dev",
                timestamp="2026-03-01T08:00:00Z",
                subject="fix bug",
                files_changed=["src/main.py"],
            ),
        ],
        agent_commits=[
            HumanCommit(
                sha="b" * 40,
                author="dev",
                timestamp="2026-03-01T09:00:00Z",
                subject="feat: add login flow",
                files_changed=["src/auth.py"],
            ),
        ],
        file_overlaps=[
            FileOverlap(
                path="src/main.py",
                agent_task_ids=["spec_a:1"],
                human_commits=["a" * 40],
            ),
        ],
        cost_breakdown=[
            CostBreakdown(
                tier="STANDARD",
                sessions=3,
                input_tokens=50_000,
                output_tokens=25_000,
                cost=1.50,
            ),
        ],
        queue=QueueSummary(
            ready=2,
            pending=3,
            blocked=1,
            failed=0,
            completed=4,
        ),
    )


# ---------------------------------------------------------------------------
# Issue #379: "no session data" instead of silent zero when DB has no records
# ---------------------------------------------------------------------------


class TestNoSessionDataDisplay:
    """Regression #379: formatters show 'no session data' instead of $0.00."""

    def test_status_no_session_data_when_tokens_none(self) -> None:
        """format_status shows 'no session data' when input_tokens is None."""
        import dataclasses

        formatter = TableFormatter()
        report = dataclasses.replace(
            _make_status_report(),
            input_tokens=None,
            output_tokens=None,
            estimated_cost=None,
        )
        output = formatter.format_status(report)

        assert "no session data" in output
        assert "$" not in output.split("\n")[1], (
            "Cost line must not show a dollar amount when tokens are None"
        )

    def test_status_tokens_and_cost_shown_when_data_available(self) -> None:
        """format_status shows normal token/cost line when values are present."""
        formatter = TableFormatter()
        report = _make_status_report()  # has real values
        output = formatter.format_status(report)

        assert "Tokens:" in output
        assert "$2.50" in output
        assert "no session data" not in output

    def test_standup_no_session_data_when_cost_none(self) -> None:
        """format_standup shows 'no session data' when total_cost is None."""
        import dataclasses

        formatter = TableFormatter()
        report = dataclasses.replace(
            _make_standup_report(),
            total_cost=None,
        )
        output = formatter.format_standup(report)

        assert "Total Cost: no session data" in output

    def test_standup_cost_shown_when_data_available(self) -> None:
        """format_standup shows dollar amount when total_cost is not None."""
        import dataclasses

        formatter = TableFormatter()
        report = dataclasses.replace(
            _make_standup_report(),
            total_cost=1.23,
        )
        output = formatter.format_standup(report)

        assert "Total Cost: $1.23" in output
        assert "no session data" not in output


# ---------------------------------------------------------------------------
# Issue #375: TableFormatter must not display Memory line in status header
# ---------------------------------------------------------------------------


class TestTableFormatter:
    """Regression tests for TableFormatter.format_status text output."""

    def test_memory_line_absent_when_zero_facts(self) -> None:
        """'Memory: 0 facts' must not appear in status output (issue #375)."""
        formatter = TableFormatter()
        report = _make_status_report()  # memory_total defaults to 0

        output = formatter.format_status(report)

        assert "Memory" not in output, (
            "Status header must not contain a Memory line (issue #375)"
        )

    def test_memory_line_absent_when_facts_present(self) -> None:
        """'Memory: N facts' must not appear even when facts exist (issue #375)."""
        import dataclasses

        formatter = TableFormatter()
        report = dataclasses.replace(
            _make_status_report(),
            memory_total=5,
            memory_by_category={"pattern": 3, "decision": 2},
        )

        output = formatter.format_status(report)

        assert "Memory" not in output, (
            "Status header must not contain a Memory line even when facts exist (issue #375)"
        )


# ---------------------------------------------------------------------------
# TS-07-9: JSON formatter produces valid JSON
# Requirement: 07-REQ-3.2
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    """TS-07-9: JSON formatter produces valid JSON."""

    def test_format_status_produces_valid_json(self) -> None:
        """JSON output is parseable by json.loads."""
        formatter = JsonFormatter()
        report = _make_status_report()

        output = formatter.format_status(report)
        parsed = json.loads(output)

        assert parsed["total_tasks"] == report.total_tasks
        assert parsed["estimated_cost"] == report.estimated_cost

    def test_format_status_includes_counts(self) -> None:
        """Parsed JSON contains task counts."""
        formatter = JsonFormatter()
        report = _make_status_report()

        output = formatter.format_status(report)
        parsed = json.loads(output)

        assert parsed["counts"]["completed"] == 3
        assert parsed["counts"]["failed"] == 1

    def test_format_standup_produces_valid_json(self) -> None:
        """JSON output for standup is parseable."""
        formatter = JsonFormatter()
        report = _make_standup_report()

        output = formatter.format_standup(report)
        parsed = json.loads(output)

        assert parsed["window_hours"] == 24
        assert parsed["agent"]["sessions_run"] == 3


# ---------------------------------------------------------------------------
# TS-07-E5: Output file not writable
# Requirement: 07-REQ-3.E1
# ---------------------------------------------------------------------------


class TestWriteOutputErrors:
    """TS-07-E5: Writing to unwritable path raises error."""

    def test_unwritable_path_raises_error(self) -> None:
        """AgentFoxError raised when output path is not writable."""
        bad_path = Path("/nonexistent/dir/report.json")

        with pytest.raises(AgentFoxError):
            write_output("report data", output_path=bad_path)
