"""Unit tests for output formatters: JSON, YAML, write_output.

Test Spec: TS-07-9, TS-07-10, TS-07-E5
Requirements: 07-REQ-3.2, 07-REQ-3.3, 07-REQ-3.E1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agent_fox.core.errors import AgentFoxError
from agent_fox.reporting.formatters import (
    JsonFormatter,
    YamlFormatter,
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
# TS-07-10: YAML formatter produces valid YAML
# Requirement: 07-REQ-3.3
# ---------------------------------------------------------------------------


class TestYamlFormatter:
    """TS-07-10: YAML formatter produces valid YAML."""

    def test_format_standup_produces_valid_yaml(self) -> None:
        """YAML output is parseable by yaml.safe_load."""
        formatter = YamlFormatter()
        report = _make_standup_report()

        output = formatter.format_standup(report)
        parsed = yaml.safe_load(output)

        assert parsed["window_hours"] == report.window_hours

    def test_format_status_produces_valid_yaml(self) -> None:
        """YAML output for status is parseable."""
        formatter = YamlFormatter()
        report = _make_status_report()

        output = formatter.format_status(report)
        parsed = yaml.safe_load(output)

        assert parsed["total_tasks"] == 7
        assert parsed["estimated_cost"] == pytest.approx(2.50)


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
