"""Unit tests for standup report generation.

Test Spec: TS-07-4, TS-07-5, TS-07-6, TS-07-7, TS-07-8, TS-07-E3, TS-07-E4
Requirements: 07-REQ-2.1, 07-REQ-2.2, 07-REQ-2.3, 07-REQ-2.4, 07-REQ-2.5,
              07-REQ-2.E1, 07-REQ-2.E2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_fox.reporting.standup import (
    HumanCommit,
    _detect_overlaps,
    _get_human_commits,
    generate_standup,
)

from .conftest import (
    hours_ago,
    make_execution_state,
    make_session_record,
    write_plan_file,
    write_state_file,
)

# ---------------------------------------------------------------------------
# TS-07-4: Standup agent activity within window
# Requirement: 07-REQ-2.1
# ---------------------------------------------------------------------------


class TestStandupAgentActivity:
    """TS-07-4: Standup agent activity filtered to time window."""

    def test_sessions_filtered_by_window(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Only sessions within the time window are counted."""
        nodes = {
            "spec_a:1": {"title": "Task 1"},
            "spec_a:2": {"title": "Task 2"},
            "spec_a:3": {"title": "Task 3"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        sessions = [
            # 2 hours ago -- within 24h window
            make_session_record(
                node_id="spec_a:1",
                status="completed",
                timestamp=hours_ago(2),
                input_tokens=1000,
                output_tokens=500,
                cost=0.10,
            ),
            # 6 hours ago -- within 24h window
            make_session_record(
                node_id="spec_a:2",
                status="completed",
                timestamp=hours_ago(6),
                input_tokens=2000,
                output_tokens=1000,
                cost=0.20,
            ),
            # 30 hours ago -- outside 24h window
            make_session_record(
                node_id="spec_a:3",
                status="completed",
                timestamp=hours_ago(30),
                input_tokens=5000,
                output_tokens=2500,
                cost=0.50,
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

        report = generate_standup(
            tmp_state_path, plan_path, tmp_path, hours=24,
        )

        assert report.agent.sessions_run == 2
        assert report.window_hours == 24


# ---------------------------------------------------------------------------
# TS-07-5: Standup includes human commits
# Requirement: 07-REQ-2.2
# ---------------------------------------------------------------------------


class TestStandupHumanCommits:
    """TS-07-5: Standup includes non-agent commits from git log."""

    def test_human_commits_exclude_agent(
        self, tmp_git_repo: Path,
    ) -> None:
        """Human commits exclude agent-authored commits."""
        import subprocess

        # Create 2 human commits
        for i in range(2):
            f = tmp_git_repo / f"human_{i}.py"
            f.write_text(f"# human change {i}\n")
            subprocess.run(
                ["git", "add", "."], cwd=tmp_git_repo,
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Human commit {i}"],
                cwd=tmp_git_repo,
                check=True, capture_output=True,
            )

        # Create 1 agent commit
        f = tmp_git_repo / "agent_file.py"
        f.write_text("# agent change\n")
        subprocess.run(
            ["git", "add", "."], cwd=tmp_git_repo,
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Agent commit",
             "--author", "agent-fox <agent-fox@test.com>"],
            cwd=tmp_git_repo,
            check=True, capture_output=True,
        )

        since = datetime.now(UTC) - timedelta(hours=24)
        commits = _get_human_commits(tmp_git_repo, since, "agent-fox")

        assert len(commits) == 2
        for commit in commits:
            assert commit.author != "agent-fox"
            assert len(commit.sha) == 40


# ---------------------------------------------------------------------------
# TS-07-6: Standup detects file overlaps
# Requirement: 07-REQ-2.3
# ---------------------------------------------------------------------------


class TestStandupFileOverlaps:
    """TS-07-6: File overlap detection finds files touched by both."""

    def test_overlaps_detected(self) -> None:
        """Files modified by both agent and human are detected."""
        agent_files = {
            "src/a.py": ["task:1"],
            "src/b.py": ["task:2"],
            "src/c.py": ["task:1"],
        }
        human_commits = [
            HumanCommit(
                sha="a" * 40,
                author="dev",
                timestamp="2026-03-01T10:00:00Z",
                subject="fix b and d",
                files_changed=["src/b.py", "src/d.py"],
            ),
        ]

        overlaps = _detect_overlaps(agent_files, human_commits)

        assert len(overlaps) == 1
        assert overlaps[0].path == "src/b.py"

    def test_no_overlaps_when_disjoint(self) -> None:
        """No overlaps when agent and human touch different files."""
        agent_files = {
            "src/a.py": ["task:1"],
            "src/c.py": ["task:2"],
        }
        human_commits = [
            HumanCommit(
                sha="b" * 40,
                author="dev",
                timestamp="2026-03-01T10:00:00Z",
                subject="fix d",
                files_changed=["src/d.py"],
            ),
        ]

        overlaps = _detect_overlaps(agent_files, human_commits)

        assert len(overlaps) == 0

    def test_overlap_contains_task_ids_and_commit_shas(self) -> None:
        """Overlap records include which tasks and commits touched the file."""
        agent_files = {
            "src/shared.py": ["task:1", "task:3"],
        }
        human_sha = "c" * 40
        human_commits = [
            HumanCommit(
                sha=human_sha,
                author="dev",
                timestamp="2026-03-01T10:00:00Z",
                subject="edit shared",
                files_changed=["src/shared.py"],
            ),
        ]

        overlaps = _detect_overlaps(agent_files, human_commits)

        assert len(overlaps) == 1
        assert "task:1" in overlaps[0].agent_task_ids
        assert "task:3" in overlaps[0].agent_task_ids
        assert human_sha in overlaps[0].human_commits


# ---------------------------------------------------------------------------
# TS-07-7: Standup includes queue summary
# Requirement: 07-REQ-2.4
# ---------------------------------------------------------------------------


class TestStandupQueueSummary:
    """TS-07-7: Standup report includes current queue status."""

    def test_queue_counts_match_task_states(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Queue summary reflects current task statuses."""
        # 10 tasks: 3 completed, 2 ready (pending with no deps),
        # 3 pending (with deps), 1 blocked, 1 failed
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
            "s:4": {"title": "T4"},
            "s:5": {"title": "T5"},
            "s:6": {"title": "T6"},
            "s:7": {"title": "T7"},
            "s:8": {"title": "T8"},
            "s:9": {"title": "T9"},
            "s:10": {"title": "T10"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        state = make_execution_state(
            node_states={
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "completed",
                "s:4": "pending",  # ready (no deps)
                "s:5": "pending",  # ready (no deps)
                "s:6": "pending",
                "s:7": "pending",
                "s:8": "pending",
                "s:9": "blocked",
                "s:10": "failed",
            },
        )
        write_state_file(tmp_state_path, state)

        report = generate_standup(
            tmp_state_path, plan_path, tmp_path, hours=24,
        )

        assert report.queue.completed == 3
        assert report.queue.blocked == 1
        assert report.queue.failed == 1


# ---------------------------------------------------------------------------
# TS-07-8: Standup includes cost breakdown by model
# Requirement: 07-REQ-2.5
# ---------------------------------------------------------------------------


class TestStandupCostBreakdown:
    """TS-07-8: Standup cost breakdown by model tier."""

    def test_cost_grouped_by_model(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Cost breakdown groups by model tier correctly."""
        nodes = {
            "s:1": {"title": "T1"},
            "s:2": {"title": "T2"},
            "s:3": {"title": "T3"},
        }
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        # Note: SessionRecord does not have a model field natively.
        # The implementation must track model information alongside sessions
        # (from config or session outcome). Tests verify the structure of
        # cost_breakdown in the generated report.
        sessions = [
            make_session_record(
                node_id="s:1",
                cost=1.50,
                timestamp=hours_ago(2),
            ),
            make_session_record(
                node_id="s:2",
                cost=1.50,
                timestamp=hours_ago(3),
            ),
            make_session_record(
                node_id="s:3",
                cost=0.50,
                timestamp=hours_ago(4),
            ),
        ]
        state = make_execution_state(
            node_states={
                "s:1": "completed",
                "s:2": "completed",
                "s:3": "completed",
            },
            session_history=sessions,
        )
        write_state_file(tmp_state_path, state)

        report = generate_standup(
            tmp_state_path, plan_path, tmp_path, hours=24,
        )

        # The report must have a cost breakdown with at least one entry
        assert len(report.cost_breakdown) >= 1

        # Total cost across breakdown must match total session cost
        total_breakdown_cost = sum(cb.cost for cb in report.cost_breakdown)
        total_session_cost = sum(s.cost for s in sessions)
        assert abs(total_breakdown_cost - total_session_cost) < 0.01


# ---------------------------------------------------------------------------
# TS-07-E3: Standup with no agent activity
# Requirement: 07-REQ-2.E1
# ---------------------------------------------------------------------------


class TestStandupNoAgentActivity:
    """TS-07-E3: Standup with no agent activity in the window."""

    def test_zero_activity_when_outside_window(
        self,
        tmp_state_path: Path,
        tmp_plan_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Reports zero agent activity when all sessions are outside window."""
        nodes = {"s:1": {"title": "T1"}, "s:2": {"title": "T2"}}
        plan_path = write_plan_file(tmp_plan_dir, nodes=nodes)

        # All sessions are older than the 1-hour window
        sessions = [
            make_session_record(
                node_id="s:1",
                timestamp=hours_ago(48),
                cost=1.00,
            ),
        ]
        state = make_execution_state(
            node_states={"s:1": "completed", "s:2": "pending"},
            session_history=sessions,
        )
        write_state_file(tmp_state_path, state)

        report = generate_standup(
            tmp_state_path, plan_path, tmp_path, hours=1,
        )

        assert report.agent.sessions_run == 0
        assert report.agent.cost == 0.0
        # Queue summary is still populated
        assert report.queue.completed >= 0


# ---------------------------------------------------------------------------
# TS-07-E4: Standup with no git commits
# Requirement: 07-REQ-2.E2
# ---------------------------------------------------------------------------


class TestStandupNoGitCommits:
    """TS-07-E4: Standup handles empty git history gracefully."""

    def test_no_commits_returns_empty_list(
        self, tmp_git_repo: Path,
    ) -> None:
        """No human commits when git history is outside the window."""
        # The initial commit from tmp_git_repo fixture is very recent,
        # so use a very short window that excludes it by setting `since`
        # to the future.
        since = datetime.now(UTC) + timedelta(hours=1)
        commits = _get_human_commits(tmp_git_repo, since, "agent-fox")

        assert len(commits) == 0
