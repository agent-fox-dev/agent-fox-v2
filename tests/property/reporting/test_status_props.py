"""Property tests for status report and JSON formatter.

Test Spec: TS-07-P1 (count consistency), TS-07-P3 (JSON roundtrip)
Properties: Property 1, Property 6 from design.md
Requirements: 07-REQ-1.1, 07-REQ-3.2
"""

from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import patch

import duckdb
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.state import ExecutionState
from agent_fox.graph.persistence import save_plan
from agent_fox.graph.types import Node, NodeStatus, PlanMetadata, TaskGraph
from agent_fox.knowledge.migrations import run_migrations
from agent_fox.reporting.formatters import JsonFormatter
from agent_fox.reporting.status import StatusReport, TaskSummary, generate_status

# -- Hypothesis strategies ---------------------------------------------------


NODE_IDS = [f"s:{i}" for i in range(1, 9)]
ALL_STATUSES = ["pending", "in_progress", "completed", "failed", "blocked", "skipped"]


@st.composite
def valid_node_states(draw: st.DrawFn) -> dict[str, str]:
    """Generate a valid dict of node_id -> status."""
    n = draw(st.integers(min_value=1, max_value=8))
    ids = NODE_IDS[:n]
    return {nid: draw(st.sampled_from(ALL_STATUSES)) for nid in ids}


@st.composite
def valid_status_reports(draw: st.DrawFn) -> StatusReport:
    """Generate a valid StatusReport with consistent counts.

    Ensures that the sum of all counts equals total_tasks.
    """
    statuses = ["pending", "in_progress", "completed", "failed", "blocked", "skipped"]
    counts: dict[str, int] = {}
    for s in statuses:
        counts[s] = draw(st.integers(min_value=0, max_value=20))

    total_tasks = sum(counts.values())

    input_tokens = draw(st.integers(min_value=0, max_value=500_000))
    output_tokens = draw(st.integers(min_value=0, max_value=500_000))
    cost = draw(st.floats(min_value=0.0, max_value=100.0))

    # Generate problem tasks from the failed/blocked counts
    num_problems = min(counts["failed"] + counts["blocked"], 3)
    problem_tasks = [
        TaskSummary(
            task_id=f"spec:{i}",
            title=f"Task {i}",
            status=draw(st.sampled_from(["failed", "blocked"])),
            reason=f"reason_{i}",
        )
        for i in range(num_problems)
    ]

    per_spec: dict[str, dict[str, int]] = {}

    return StatusReport(
        counts=counts,
        total_tasks=total_tasks,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        problem_tasks=problem_tasks,
        per_spec=per_spec,
    )


# -- Helpers -----------------------------------------------------------------


def _write_plan_and_state_to_db(
    node_states: dict[str, str],
) -> tuple[ExecutionState, duckdb.DuckDBPyConnection]:
    """Write plan to an in-memory DuckDB and create state; return (state, conn)."""
    conn = duckdb.connect(":memory:")
    run_migrations(conn)

    node_objs: dict[str, Node] = {}
    for nid in node_states:
        parts = nid.split(":")
        spec_name = parts[0]
        group_number = int(parts[1])
        node_objs[nid] = Node(
            id=nid,
            spec_name=spec_name,
            group_number=group_number,
            title=f"Task {nid}",
            optional=False,
            status=NodeStatus.PENDING,
            subtask_count=0,
            body="",
            archetype="coder",
        )

    graph = TaskGraph(
        nodes=node_objs,
        edges=[],
        order=list(node_states.keys()),
        metadata=PlanMetadata(
            created_at="2026-01-01T00:00:00",
            fast_mode=False,
            filtered_spec=None,
            version="0.1.0",
        ),
    )
    save_plan(graph, conn)

    # Create in-memory state (loaded via mock)
    state = ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )

    return state, conn


# ---------------------------------------------------------------------------
# TS-07-P1: Status count consistency
# Property 1: sum(counts.values()) == total_tasks
# Requirement: 07-REQ-1.1
# ---------------------------------------------------------------------------


class TestStatusCountConsistency:
    """TS-07-P1: Sum of all status counts equals total_tasks.

    Tests that generate_status() always produces a report where the sum
    of status counts equals the total number of tasks.
    """

    @given(node_states=valid_node_states())
    @settings(max_examples=50)
    def test_counts_sum_equals_total(
        self,
        node_states: dict[str, str],
    ) -> None:
        """For any execution state, count sum == total_tasks."""
        state, conn = _write_plan_and_state_to_db(node_states)

        with (
            patch("agent_fox.reporting.status.load_state_from_db", return_value=state),
            patch("agent_fox.reporting.status.build_status_report_from_audit", return_value=None),
        ):
            report = generate_status(db_conn=conn)

        conn.close()
        assert sum(report.counts.values()) == report.total_tasks


# ---------------------------------------------------------------------------
# TS-07-P3: JSON roundtrip fidelity
# Property 6: JSON format/parse roundtrip preserves data
# Requirement: 07-REQ-3.2
# ---------------------------------------------------------------------------


class TestJsonRoundtripFidelity:
    """TS-07-P3: JSON format/parse roundtrip preserves data."""

    @given(report=valid_status_reports())
    @settings(max_examples=50)
    def test_json_roundtrip_preserves_data(
        self,
        report: StatusReport,
    ) -> None:
        """Formatting as JSON and parsing back produces equivalent dict."""
        formatter = JsonFormatter()
        output = formatter.format_status(report)
        parsed = json.loads(output)
        expected = asdict(report)

        assert parsed == expected
