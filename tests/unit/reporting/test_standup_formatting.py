"""Unit tests for standup report plain-text formatting.

Test Spec: TS-15-1 through TS-15-10, TS-15-E1 through TS-15-E6
Requirements: 15-REQ-1.* through 15-REQ-8.*
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_fox.reporting.formatters import (
    TableFormatter,
    _display_node_id,
    format_tokens,
)
from agent_fox.reporting.standup import (
    AgentActivity,
    CostBreakdown,
    FileOverlap,
    HumanCommit,
    QueueSummary,
    StandupReport,
    TaskActivity,
    generate_standup,
)

from .conftest import (
    hours_ago,
    make_execution_state,
    make_session_record,
    write_plan_file,
    write_state_file,
)

# -- Helpers ------------------------------------------------------------------


def _make_sample_report(
    *,
    window_hours: int = 24,
    window_end: str = "2026-03-02T12:30:00+00:00",
    task_activities: list[TaskActivity] | None = None,
    human_commits: list[HumanCommit] | None = None,
    agent_commits: list[HumanCommit] | None = None,
    file_overlaps: list[FileOverlap] | None = None,
    queue: QueueSummary | None = None,
    total_cost: float = 34.64,
) -> StandupReport:
    """Build a sample StandupReport with all new fields populated."""
    if task_activities is None:
        task_activities = [
            TaskActivity(
                task_id="s_a:1",
                current_status="completed",
                completed_sessions=1,
                total_sessions=1,
                input_tokens=12900,
                output_tokens=29500,
                cost=0.80,
            ),
            TaskActivity(
                task_id="s_a:2",
                current_status="completed",
                completed_sessions=1,
                total_sessions=2,
                input_tokens=14500,
                output_tokens=9300,
                cost=0.31,
            ),
        ]
    if human_commits is None:
        human_commits = [
            HumanCommit(
                sha="fd67aec1234567890abcdef1234567890abcdef0",
                author="Michael Kuehl",
                timestamp="2026-03-01T08:00:00Z",
                subject="updated README",
                files_changed=["README.md"],
            ),
        ]
    if agent_commits is None:
        agent_commits = [
            HumanCommit(
                sha="5cfee2a1234567890abcdef1234567890abcdef0",
                author="Michael Kuehl",
                timestamp="2026-03-01T09:00:00Z",
                subject="feat: rewrite prompt builder with templates",
                files_changed=["agent_fox/engine/prompt.py"],
            ),
        ]
    if file_overlaps is None:
        file_overlaps = [
            FileOverlap(
                path=".agent-fox/state.jsonl",
                agent_task_ids=["07_ops:3", "10_plat:2"],
                human_commits=[
                    "7510417abcdef1234567890abcdef1234567890ab",
                    "77156b5abcdef1234567890abcdef1234567890ab",
                ],
            ),
        ]
    if queue is None:
        queue = QueueSummary(
            total=76,
            ready=2,
            pending=3,
            in_progress=0,
            blocked=0,
            failed=0,
            completed=73,
            ready_task_ids=["fix_01:1", "fix_02:1"],
        )
    return StandupReport(
        window_hours=window_hours,
        window_start="2026-03-02T00:30:00+00:00",
        window_end=window_end,
        agent=AgentActivity(
            tasks_completed=2,
            sessions_run=3,
            input_tokens=27400,
            output_tokens=38800,
            cost=1.11,
            completed_task_ids=["s_a:1", "s_a:2"],
        ),
        task_activities=task_activities,
        human_commits=human_commits,
        agent_commits=agent_commits,
        file_overlaps=file_overlaps,
        cost_breakdown=[
            CostBreakdown(
                tier="default",
                sessions=3,
                input_tokens=27400,
                output_tokens=38800,
                cost=1.11,
            ),
        ],
        queue=queue,
        total_cost=total_cost,
    )


# ---------------------------------------------------------------------------
# TS-15-1: Plain-Text Header Format
# Requirements: 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.3
# ---------------------------------------------------------------------------


class TestPlainTextHeader:
    """TS-15-1: Header line, generated timestamp, and blank separator."""

    def test_header_contains_em_dash_and_hours(self) -> None:
        """Output starts with 'Standup Report — last 24h'."""
        report = _make_sample_report(window_hours=24)
        output = TableFormatter().format_standup(report)
        lines = output.split("\n")
        assert lines[0] == "Standup Report — last 24h"

    def test_generated_timestamp_on_second_line(self) -> None:
        """Second line is 'Generated: <window_end>'."""
        report = _make_sample_report(
            window_end="2026-03-02T12:30:00+00:00",
        )
        output = TableFormatter().format_standup(report)
        lines = output.split("\n")
        assert lines[1] == "Generated: 2026-03-02T12:30:00+00:00"

    def test_blank_line_after_header(self) -> None:
        """Third line is blank (separator before first section)."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        lines = output.split("\n")
        assert lines[2] == ""


# ---------------------------------------------------------------------------
# TS-15-2: Per-Task Agent Activity Lines
# Requirements: 15-REQ-2.1, 15-REQ-2.2
# ---------------------------------------------------------------------------


class TestPerTaskActivityLines:
    """TS-15-2: Each task produces an indented line with display ID."""

    def test_agent_activity_section_header(self) -> None:
        """Output contains 'Agent Activity' section header."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "Agent Activity" in output

    def test_per_task_line_format_first_task(self) -> None:
        """First task line matches expected format."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        expected = (
            "  s_a/1 [coder]: completed. 1/1 sessions. "
            "tokens 12.9k in / 29.5k out. $0.80"
        )
        assert expected in output

    def test_per_task_line_format_second_task(self) -> None:
        """Second task line matches expected format."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        expected = (
            "  s_a/2 [coder]: completed. 1/2 sessions. "
            "tokens 14.5k in / 9.3k out. $0.31"
        )
        assert expected in output


# ---------------------------------------------------------------------------
# Agent Commits Lines
# ---------------------------------------------------------------------------


class TestAgentCommitsLines:
    """Agent commit lines show 7-char SHA and subject (no author)."""

    def test_agent_commits_section_header(self) -> None:
        """Output contains 'Agent Commits' section header."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "Agent Commits" in output

    def test_agent_commit_line_format(self) -> None:
        """Agent commit line shows truncated SHA and subject."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "  5cfee2a feat: rewrite prompt builder with templates" in output

    def test_no_agent_commits_placeholder(self) -> None:
        """Output contains '(no agent commits)' when empty."""
        report = _make_sample_report(agent_commits=[])
        output = TableFormatter().format_standup(report)
        assert "  (no agent commits)" in output

    def test_agent_commits_before_human_commits(self) -> None:
        """Agent Commits section appears before Human Commits."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        idx_agent = output.index("Agent Commits")
        idx_human = output.index("Human Commits")
        assert idx_agent < idx_human


# ---------------------------------------------------------------------------
# TS-15-3: Human Commits Lines
# Requirements: 15-REQ-3.1
# ---------------------------------------------------------------------------


class TestHumanCommitsLines:
    """TS-15-3: Human commit lines show 7-char SHA, author, subject."""

    def test_human_commits_section_header(self) -> None:
        """Output contains 'Human Commits' section header."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "Human Commits" in output

    def test_human_commit_line_format(self) -> None:
        """Commit line shows truncated SHA, author, subject."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "  fd67aec Michael Kuehl: updated README" in output


# ---------------------------------------------------------------------------
# TS-15-4: Queue Status Summary Line
# Requirements: 15-REQ-4.1, 15-REQ-4.2
# ---------------------------------------------------------------------------


class TestQueueStatusLine:
    """TS-15-4: Queue status on one summary line plus ready list."""

    def test_queue_status_section_header(self) -> None:
        """Output contains 'Queue Status' section header."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "Queue Status" in output

    def test_queue_summary_line(self) -> None:
        """Summary line shows all counts."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        expected = (
            "  76 total: 73 done | 0 in progress | "
            "3 pending | 2 ready | 0 blocked | 0 failed"
        )
        assert expected in output

    def test_ready_task_ids_line(self) -> None:
        """Ready line lists task IDs in display format."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "  Ready: fix_01/1, fix_02/1" in output


# ---------------------------------------------------------------------------
# TS-15-5: File Overlaps Section
# Requirements: 15-REQ-5.1
# ---------------------------------------------------------------------------


class TestFileOverlapsSection:
    """TS-15-5: File overlap lines with em dash, SHAs, display IDs."""

    def test_file_overlaps_section_header(self) -> None:
        """Output contains 'Heads Up — File Overlaps' header."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        assert "Heads Up — File Overlaps" in output

    def test_file_overlap_line_format(self) -> None:
        """Overlap line shows path, truncated SHAs, display task IDs."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        expected = (
            "  .agent-fox/state.jsonl — "
            "commits: 7510417, 77156b5 | agents: 07_ops/3, 10_plat/2"
        )
        assert expected in output


# ---------------------------------------------------------------------------
# TS-15-6: Total Cost Line
# Requirements: 15-REQ-6.1
# ---------------------------------------------------------------------------


class TestTotalCostLine:
    """TS-15-6: All-time total cost at the end of the report."""

    def test_total_cost_line(self) -> None:
        """Output contains 'Total Cost: $34.64'."""
        report = _make_sample_report(total_cost=34.64)
        output = TableFormatter().format_standup(report)
        assert "Total Cost: $34.64" in output

    def test_total_cost_after_queue_status(self) -> None:
        """Total Cost appears after Queue Status."""
        report = _make_sample_report()
        output = TableFormatter().format_standup(report)
        idx_queue = output.index("Queue Status")
        idx_cost = output.index("Total Cost")
        assert idx_cost > idx_queue


# ---------------------------------------------------------------------------
# TS-15-7: Token Formatting Function
# Requirements: 15-REQ-7.1
# ---------------------------------------------------------------------------


class TestTokenFormatting:
    """TS-15-7: format_tokens() produces correct output."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            (0, "0"),
            (345, "345"),
            (999, "999"),
            (1000, "1.0k"),
            (12900, "12.9k"),
            (29500, "29.5k"),
            (100000, "100.0k"),
        ],
    )
    def test_format_tokens(self, input_val: int, expected: str) -> None:
        """Token formatting matches expected output."""
        assert format_tokens(input_val) == expected


# ---------------------------------------------------------------------------
# TS-15-8: Display Node ID Function
# Requirements: 15-REQ-8.1
# ---------------------------------------------------------------------------


class TestDisplayNodeId:
    """TS-15-8: _display_node_id() replaces colons with slashes."""

    @pytest.mark.parametrize(
        ("input_id", "expected"),
        [
            ("01_core_foundation:1", "01_core_foundation/1"),
            ("fix_01_ruff_format:1", "fix_01_ruff_format/1"),
            ("s:10", "s/10"),
        ],
    )
    def test_display_node_id(self, input_id: str, expected: str) -> None:
        """Node ID conversion matches expected output."""
        assert _display_node_id(input_id) == expected


# ---------------------------------------------------------------------------
# TS-15-9: Per-Task Activity Generation
# Requirements: 15-REQ-2.3
# ---------------------------------------------------------------------------


class TestPerTaskActivityGeneration:
    """TS-15-9: generate_standup() produces per-task breakdowns."""

    def test_per_task_breakdown_from_sessions(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Task activities computed from windowed session records."""
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        sessions = [
            make_session_record(
                node_id="s:1",
                status="completed",
                input_tokens=1000,
                output_tokens=500,
                cost=0.10,
                timestamp=hours_ago(2),
            ),
            make_session_record(
                node_id="s:1",
                status="failed",
                input_tokens=500,
                output_tokens=200,
                cost=0.05,
                timestamp=hours_ago(3),
            ),
            make_session_record(
                node_id="s:2",
                status="completed",
                input_tokens=2000,
                output_tokens=1000,
                cost=0.20,
                timestamp=hours_ago(4),
            ),
        ]
        state = make_execution_state(
            node_states={
                "s:1": "completed",
                "s:2": "completed",
            },
            session_history=sessions,
        )
        write_state_file(tmp_state_path, state)

        report = generate_standup(
            tmp_state_path,
            plan_path,
            tmp_path,
            hours=24,
        )

        assert len(report.task_activities) == 2

        s1 = [t for t in report.task_activities if t.task_id == "s:1"][0]
        assert s1.completed_sessions == 1
        assert s1.total_sessions == 2
        assert s1.input_tokens == 1500
        assert s1.output_tokens == 700
        assert pytest.approx(s1.cost, abs=0.001) == 0.15

        s2 = [t for t in report.task_activities if t.task_id == "s:2"][0]
        assert s2.completed_sessions == 1
        assert s2.total_sessions == 1
        assert s2.input_tokens == 2000
        assert s2.output_tokens == 1000
        assert pytest.approx(s2.cost, abs=0.001) == 0.20


# ---------------------------------------------------------------------------
# TS-15-10: Enriched Queue Summary Generation
# Requirements: 15-REQ-4.3
# ---------------------------------------------------------------------------


class TestEnrichedQueueSummary:
    """TS-15-10: generate_standup() populates enriched QueueSummary."""

    def test_queue_enriched_fields(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Queue summary includes total, in_progress, ready_task_ids."""
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
            "s:4": {"title": "T4"},
            "s:5": {"title": "T5"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        state = make_execution_state(
            node_states={
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "in_progress",
                "s:4": "pending",  # ready (no deps)
                "s:5": "pending",  # ready (no deps)
            },
        )
        write_state_file(tmp_state_path, state)

        report = generate_standup(
            tmp_state_path,
            plan_path,
            tmp_path,
            hours=24,
        )

        assert report.queue.total == 5
        assert report.queue.in_progress == 1
        assert report.queue.ready == 2
        assert set(report.queue.ready_task_ids) == {"s:4", "s:5"}


# ---------------------------------------------------------------------------
# TS-15-E1: No Agent Activity
# Requirements: 15-REQ-2.E1
# ---------------------------------------------------------------------------


class TestNoAgentActivity:
    """TS-15-E1: Empty task_activities shows placeholder text."""

    def test_no_agent_activity_placeholder(self) -> None:
        """Output contains '(no agent activity)' when no tasks."""
        report = _make_sample_report(task_activities=[])
        output = TableFormatter().format_standup(report)
        assert "  (no agent activity)" in output


# ---------------------------------------------------------------------------
# TS-15-E2: No Human Commits
# Requirements: 15-REQ-3.E1
# ---------------------------------------------------------------------------


class TestNoHumanCommits:
    """TS-15-E2: Empty human_commits shows placeholder text."""

    def test_no_human_commits_placeholder(self) -> None:
        """Output contains '(no human commits)' when no commits."""
        report = _make_sample_report(human_commits=[])
        output = TableFormatter().format_standup(report)
        assert "  (no human commits)" in output


# ---------------------------------------------------------------------------
# TS-15-E3: No File Overlaps
# Requirements: 15-REQ-5.E1
# ---------------------------------------------------------------------------


class TestNoFileOverlaps:
    """TS-15-E3: Empty file_overlaps omits the section entirely."""

    def test_no_file_overlaps_section_omitted(self) -> None:
        """Output does not contain 'Heads Up' when no overlaps."""
        report = _make_sample_report(file_overlaps=[])
        output = TableFormatter().format_standup(report)
        assert "Heads Up" not in output


# ---------------------------------------------------------------------------
# TS-15-E4: No Ready Tasks
# Requirements: 15-REQ-4.E1
# ---------------------------------------------------------------------------


class TestNoReadyTasks:
    """TS-15-E4: No ready tasks omits the Ready: line."""

    def test_no_ready_line_when_none_ready(self) -> None:
        """Output does not contain 'Ready:' when no tasks are ready."""
        queue = QueueSummary(
            total=5,
            ready=0,
            pending=2,
            in_progress=1,
            blocked=1,
            failed=1,
            completed=0,
            ready_task_ids=[],
        )
        report = _make_sample_report(queue=queue)
        output = TableFormatter().format_standup(report)
        assert "Queue Status" in output
        assert "Ready:" not in output


# ---------------------------------------------------------------------------
# TS-15-E5: Total Cost Zero
# Requirements: 15-REQ-6.E1
# ---------------------------------------------------------------------------


class TestTotalCostZero:
    """TS-15-E5: Zero total cost shows $0.00."""

    def test_zero_total_cost(self) -> None:
        """Output contains 'Total Cost: $0.00' when no sessions ever run."""
        report = _make_sample_report(total_cost=0.0)
        output = TableFormatter().format_standup(report)
        assert "Total Cost: $0.00" in output


# ---------------------------------------------------------------------------
# TS-15-E6: Hours Value of 1
# Requirements: 15-REQ-1.E1
# ---------------------------------------------------------------------------


class TestHoursValueOne:
    """TS-15-E6: Header shows singular '1h'."""

    def test_hours_one_header(self) -> None:
        """Output starts with 'Standup Report — last 1h'."""
        report = _make_sample_report(window_hours=1)
        output = TableFormatter().format_standup(report)
        assert output.startswith("Standup Report — last 1h")
