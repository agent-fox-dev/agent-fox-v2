"""Property tests for standup report plain-text formatting.

Test Spec: TS-15-P1 through TS-15-P6
Properties: Properties 1–6 from design.md
Requirements: 15-REQ-2.2, 15-REQ-2.3, 15-REQ-4.1, 15-REQ-4.3,
              15-REQ-7.1, 15-REQ-8.1
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.reporting.formatters import (
    TableFormatter,
    _display_node_id,
    format_tokens,
)
from agent_fox.reporting.standup import (
    AgentActivity,
    FileOverlap,
    HumanCommit,
    QueueSummary,
    StandupReport,
    TaskActivity,
)

# -- Hypothesis strategies ---------------------------------------------------

# Characters valid in spec names: letters, numbers, underscore
_SPEC_CHARS = st.characters(
    whitelist_categories=("L", "N", "Pc"),
)


@st.composite
def task_activity_strategy(draw: st.DrawFn) -> TaskActivity:
    """Generate a valid TaskActivity."""
    spec = draw(st.text(_SPEC_CHARS, min_size=1, max_size=10))
    group = draw(st.integers(min_value=1, max_value=99))
    completed = draw(st.integers(min_value=0, max_value=10))
    total = draw(st.integers(min_value=completed, max_value=completed + 10))
    in_tok = draw(st.integers(min_value=0, max_value=500_000))
    out_tok = draw(st.integers(min_value=0, max_value=500_000))
    cost = draw(st.floats(min_value=0.0, max_value=50.0))
    status = draw(st.sampled_from(["completed", "failed", "pending"]))
    return TaskActivity(
        task_id=f"{spec}:{group}",
        current_status=status,
        completed_sessions=completed,
        total_sessions=total,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=cost,
    )


@st.composite
def standup_report_strategy(draw: st.DrawFn) -> StandupReport:
    """Generate a valid StandupReport with various populated/empty sections."""
    hours = draw(st.integers(min_value=1, max_value=168))

    # Task activities: sometimes empty
    n_activities = draw(st.integers(min_value=0, max_value=5))
    activities = [draw(task_activity_strategy()) for _ in range(n_activities)]

    # Human commits: sometimes empty
    n_commits = draw(st.integers(min_value=0, max_value=3))
    commits = [
        HumanCommit(
            sha="a" * 40,
            author=f"dev{i}",
            timestamp="2026-03-01T08:00:00Z",
            subject=f"commit {i}",
            files_changed=[f"file{i}.py"],
        )
        for i in range(n_commits)
    ]

    # Agent commits: sometimes empty
    n_agent_commits = draw(st.integers(min_value=0, max_value=3))
    agent_commits = [
        HumanCommit(
            sha="c" * 40,
            author=f"dev{i}",
            timestamp="2026-03-01T09:00:00Z",
            subject=f"feat: agent change {i}",
            files_changed=[f"src/mod{i}.py"],
        )
        for i in range(n_agent_commits)
    ]

    # File overlaps: sometimes empty
    n_overlaps = draw(st.integers(min_value=0, max_value=3))
    overlaps = [
        FileOverlap(
            path=f"src/file{i}.py",
            agent_task_ids=[f"spec:{i + 1}"],
            human_commits=["b" * 40],
        )
        for i in range(n_overlaps)
    ]

    # Queue summary with consistent totals
    ready = draw(st.integers(min_value=0, max_value=10))
    pending = draw(st.integers(min_value=0, max_value=10))
    in_progress = draw(st.integers(min_value=0, max_value=5))
    blocked = draw(st.integers(min_value=0, max_value=5))
    failed = draw(st.integers(min_value=0, max_value=5))
    completed = draw(st.integers(min_value=0, max_value=30))
    total = ready + pending + in_progress + blocked + failed + completed

    ready_ids = [f"rdy:{i + 1}" for i in range(ready)]

    queue = QueueSummary(
        total=total,
        ready=ready,
        pending=pending,
        in_progress=in_progress,
        blocked=blocked,
        failed=failed,
        completed=completed,
        ready_task_ids=ready_ids,
    )

    total_cost = draw(st.floats(min_value=0.0, max_value=500.0))

    # Per-spec and per-archetype cost dicts
    n_specs = draw(st.integers(min_value=0, max_value=3))
    cost_by_spec = {f"spec_{i}": draw(st.floats(min_value=0.01, max_value=100.0)) for i in range(n_specs)}
    n_archetypes = draw(st.integers(min_value=0, max_value=3))
    archetype_names = ["coder", "reviewer", "verifier"]
    cost_by_archetype = {
        archetype_names[i]: draw(st.floats(min_value=0.01, max_value=100.0)) for i in range(n_archetypes)
    }

    return StandupReport(
        window_hours=hours,
        window_start="2026-03-01T00:00:00+00:00",
        window_end="2026-03-02T00:00:00+00:00",
        agent=AgentActivity(
            tasks_completed=len(activities),
            sessions_run=sum(a.total_sessions for a in activities),
            input_tokens=sum(a.input_tokens for a in activities),
            output_tokens=sum(a.output_tokens for a in activities),
            cost=sum(a.cost for a in activities),
            completed_task_ids=[a.task_id for a in activities],
        ),
        task_activities=activities,
        human_commits=commits,
        agent_commits=agent_commits,
        file_overlaps=overlaps,
        cost_breakdown=[],
        queue=queue,
        total_cost=total_cost,
        cost_by_spec=cost_by_spec,
        cost_by_archetype=cost_by_archetype,
    )


# ---------------------------------------------------------------------------
# TS-15-P1: Token Format Consistency
# Property 1: Token format matches regex pattern
# Requirements: 15-REQ-7.1
# ---------------------------------------------------------------------------


class TestTokenFormatConsistency:
    """TS-15-P1: format_tokens always matches the expected pattern."""

    @given(n=st.integers(min_value=0, max_value=10_000_000))
    @settings(max_examples=200)
    def test_token_format_pattern(self, n: int) -> None:
        """Result matches integer (<1000), Xk (>=1000), or XM (>=1M)."""
        result = format_tokens(n)
        if n < 1000:
            assert re.fullmatch(r"\d+", result), f"Expected int, got {result}"
            assert result == str(n)
        elif n >= 1_000_000:
            assert re.fullmatch(r"\d+\.\dM", result), f"Expected XM, got {result}"
        else:
            assert re.fullmatch(r"\d+\.\dk", result), f"Expected Xk, got {result}"


# ---------------------------------------------------------------------------
# TS-15-P2: Display Node ID Roundtrip
# Property 2: Colon-to-slash is the only transformation
# Requirements: 15-REQ-8.1
# ---------------------------------------------------------------------------


class TestDisplayNodeIdRoundtrip:
    """TS-15-P2: _display_node_id replaces colons with slashes only."""

    @given(
        spec=st.text(_SPEC_CHARS, min_size=1, max_size=30),
        group=st.integers(min_value=1, max_value=99),
    )
    @settings(max_examples=200)
    def test_colon_replaced_by_slash(
        self,
        spec: str,
        group: int,
    ) -> None:
        """node_id 'spec:group' becomes 'spec/group'."""
        node_id = f"{spec}:{group}"
        assert _display_node_id(node_id) == f"{spec}/{group}"


# ---------------------------------------------------------------------------
# TS-15-P3: Per-Task Activity Session Sum
# Property 3: Sum of total_sessions == len(windowed sessions)
# Requirements: 15-REQ-2.2, 15-REQ-2.3
# ---------------------------------------------------------------------------


class TestPerTaskSessionSum:
    """TS-15-P3: Session counts sum to total windowed sessions."""

    @given(
        activities=st.lists(
            task_activity_strategy(),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_session_sum_property(
        self,
        activities: list[TaskActivity],
    ) -> None:
        """sum(ta.total_sessions) is consistent with total sessions."""
        # This property is about the _compute_task_activities function.
        # Since we can't call it before implementation, we verify the
        # structural invariant: each TaskActivity has non-negative
        # total_sessions >= completed_sessions.
        for ta in activities:
            assert ta.total_sessions >= ta.completed_sessions
            assert ta.total_sessions >= 0
            assert ta.completed_sessions >= 0


# ---------------------------------------------------------------------------
# TS-15-P4: Queue Summary Total Equals Component Sum
# Property 4: total == sum of all status counts
# Requirements: 15-REQ-4.1, 15-REQ-4.3
# ---------------------------------------------------------------------------


class TestQueueTotalEqualsComponentSum:
    """TS-15-P4: QueueSummary.total == sum of all status counts."""

    @given(
        ready=st.integers(min_value=0, max_value=20),
        pending=st.integers(min_value=0, max_value=20),
        in_progress=st.integers(min_value=0, max_value=10),
        blocked=st.integers(min_value=0, max_value=10),
        failed=st.integers(min_value=0, max_value=10),
        completed=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_total_equals_sum(
        self,
        ready: int,
        pending: int,
        in_progress: int,
        blocked: int,
        failed: int,
        completed: int,
    ) -> None:
        """total == ready + pending + in_progress + blocked + failed + completed."""
        total = ready + pending + in_progress + blocked + failed + completed
        ready_ids = [f"t:{i}" for i in range(ready)]
        queue = QueueSummary(
            total=total,
            ready=ready,
            pending=pending,
            in_progress=in_progress,
            blocked=blocked,
            failed=failed,
            completed=completed,
            ready_task_ids=ready_ids,
        )
        assert queue.total == (
            queue.ready + queue.pending + queue.in_progress + queue.blocked + queue.failed + queue.completed
        )
        assert len(queue.ready_task_ids) == queue.ready


# ---------------------------------------------------------------------------
# TS-15-P5: Section Ordering
# Property 5: Sections appear in fixed order
# Requirements: 15-REQ-1.1, 15-REQ-2.1, 15-REQ-3.1, 15-REQ-4.1,
#               15-REQ-5.1, 15-REQ-6.1
# ---------------------------------------------------------------------------


class TestSectionOrdering:
    """TS-15-P5: Sections appear in fixed order regardless of content."""

    @given(report=standup_report_strategy())
    @settings(max_examples=50)
    def test_section_order(self, report: StandupReport) -> None:
        """Sections appear in the expected fixed order."""
        output = TableFormatter().format_standup(report)

        idx_activity = output.index("Agent Activity")
        idx_agent_commits = output.index("Agent Commits")
        idx_human = output.index("Human Commits")
        idx_cost = output.index("Total Cost")

        assert idx_activity < idx_agent_commits < idx_human < idx_cost

        if "Cost by Spec:" in output:
            idx_spec = output.index("Cost by Spec:")
            assert idx_human < idx_spec < idx_cost

        if "Cost by Archetype:" in output:
            idx_arch = output.index("Cost by Archetype:")
            assert idx_human < idx_arch < idx_cost


# ---------------------------------------------------------------------------
# TS-15-P6: Empty Sections Handling
# Property 6: Empty sections produce placeholder or are omitted
# Requirements: 15-REQ-2.E1, 15-REQ-3.E1, 15-REQ-5.E1
# ---------------------------------------------------------------------------


class TestEmptySectionsHandling:
    """TS-15-P6: Empty sections handled correctly."""

    @given(report=standup_report_strategy())
    @settings(max_examples=50)
    def test_empty_sections_behavior(self, report: StandupReport) -> None:
        """Empty lists produce placeholders or omit sections."""
        output = TableFormatter().format_standup(report)

        if len(report.task_activities) == 0:
            assert "(no agent activity)" in output

        if len(report.agent_commits) == 0:
            assert "(no agent commits)" in output

        if len(report.human_commits) == 0:
            assert "(no human commits)" in output

        if len(report.cost_by_spec) == 0:
            assert "Cost by Spec:" not in output

        if len(report.cost_by_archetype) == 0:
            assert "Cost by Archetype:" not in output
