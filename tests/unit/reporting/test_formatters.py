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

# -- Helpers ------------------------------------------------------------------


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
# TS-07-9: JSON formatter produces valid JSON
# Requirement: 07-REQ-3.2
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    """TS-07-9: JSON formatter produces valid JSON."""

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
