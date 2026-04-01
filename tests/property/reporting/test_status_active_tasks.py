"""Property tests for active tasks in status report.

Test Spec: TS-72-P1 (in-progress filter invariant), TS-72-P2 (text section presence)
Properties: Property 1, Property 4 from design.md
Requirements: 72-REQ-1.1, 72-REQ-1.2, 72-REQ-2.1, 72-REQ-2.5
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.state import ExecutionState, StateManager
from agent_fox.reporting.formatters import TableFormatter
from agent_fox.reporting.standup import TaskActivity
from agent_fox.reporting.status import StatusReport, generate_status

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

ALL_STATUSES = ["pending", "in_progress", "completed", "failed", "blocked"]

# Node IDs that cover both coder and non-coder archetype names
NODE_TEMPLATES = [
    "spec_a:coder",
    "spec_a:verifier",
    "spec_a:skeptic",
    "spec_b:coder",
    "spec_b:verifier",
    "spec_c:coder",
    "spec_c:auditor",
    "spec_d:coder",
]


@st.composite
def node_states_strategy(draw: st.DrawFn) -> dict[str, str]:
    """Generate a dict of node_id -> status with 1..8 nodes."""
    n = draw(st.integers(min_value=1, max_value=len(NODE_TEMPLATES)))
    node_ids = NODE_TEMPLATES[:n]
    return {nid: draw(st.sampled_from(ALL_STATUSES)) for nid in node_ids}


@st.composite
def task_activity_strategy(draw: st.DrawFn) -> TaskActivity:
    """Generate a single TaskActivity with in_progress status."""
    total = draw(st.integers(min_value=0, max_value=5))
    completed = draw(st.integers(min_value=0, max_value=total))
    in_tok = draw(st.integers(min_value=0, max_value=1_000_000))
    out_tok = draw(st.integers(min_value=0, max_value=1_000_000))
    cost = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    task_id = draw(st.sampled_from(NODE_TEMPLATES))
    return TaskActivity(
        task_id=task_id,
        current_status="in_progress",
        completed_sessions=completed,
        total_sessions=total,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=cost,
    )


@st.composite
def in_progress_tasks_strategy(draw: st.DrawFn) -> list[TaskActivity]:
    """Generate a list of 0..5 TaskActivity objects."""
    n = draw(st.integers(min_value=0, max_value=5))
    return [draw(task_activity_strategy()) for _ in range(n)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_plan_and_state(
    tmp_path: Path,
    node_states: dict[str, str],
) -> tuple[Path, Path]:
    """Write plan.json and state.jsonl; return (state_path, plan_path)."""
    agent_dir = tmp_path / ".agent-fox"
    agent_dir.mkdir(parents=True, exist_ok=True)

    plan_data = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {
            nid: {
                "id": nid,
                "spec_name": nid.split(":")[0],
                "group_number": 1,
                "title": f"Task {nid}",
                "optional": False,
                "status": "pending",
                "subtask_count": 0,
                "body": "",
            }
            for nid in node_states
        },
        "edges": [],
        "order": list(node_states.keys()),
    }
    plan_path = agent_dir / "plan.json"
    plan_path.write_text(json.dumps(plan_data, indent=2))

    state_path = agent_dir / "state.jsonl"
    state = ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )
    StateManager(state_path).save(state)

    return state_path, plan_path


def _make_report_with_tasks(tasks: list[TaskActivity]) -> StatusReport:
    """Return a minimal StatusReport with the given in_progress_tasks."""
    return StatusReport(
        counts={"pending": 1},
        total_tasks=1,
        input_tokens=0,
        output_tokens=0,
        estimated_cost=0.0,
        problem_tasks=[],
        per_spec={},
        in_progress_tasks=tasks,
    )


# ---------------------------------------------------------------------------
# TS-72-P1: In-Progress Filter Invariant
# Property 1: in_progress_tasks contains exactly nodes with in_progress status
# Requirements: 72-REQ-1.1, 72-REQ-1.2
# ---------------------------------------------------------------------------


class TestInProgressFilterInvariant:
    """TS-72-P1: in_progress_tasks count == number of in_progress nodes."""

    @given(node_states=node_states_strategy())
    @settings(max_examples=50)
    def test_filter_matches_inprogress_count(
        self,
        node_states: dict[str, str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """For any node state configuration, in_progress_tasks length equals
        the count of nodes with in_progress status.

        Requirements: 72-REQ-1.1, 72-REQ-1.2
        """
        tmp_path = tmp_path_factory.mktemp("active_tasks")
        state_path, plan_path = _write_plan_and_state(tmp_path, node_states)

        report = generate_status(state_path, plan_path)

        expected_count = sum(
            1 for s in node_states.values() if s == "in_progress"
        )
        assert len(report.in_progress_tasks) == expected_count
        assert all(
            ta.current_status == "in_progress" for ta in report.in_progress_tasks
        )


# ---------------------------------------------------------------------------
# TS-72-P2: Text Section Presence Invariant
# Property 4: "Active Tasks" in output iff in_progress_tasks is non-empty
# Requirements: 72-REQ-2.1, 72-REQ-2.5
# ---------------------------------------------------------------------------


class TestTextSectionPresenceInvariant:
    """TS-72-P2: 'Active Tasks' appears iff in_progress_tasks is non-empty."""

    @given(tasks=in_progress_tasks_strategy())
    @settings(max_examples=50)
    def test_active_tasks_heading_presence(
        self,
        tasks: list[TaskActivity],
    ) -> None:
        """For any StatusReport, 'Active Tasks' appears iff in_progress_tasks
        is non-empty.

        Requirements: 72-REQ-2.1, 72-REQ-2.5
        """
        report = _make_report_with_tasks(tasks)
        output = TableFormatter().format_status(report)

        assert ("Active Tasks" in output) == (len(tasks) > 0)
