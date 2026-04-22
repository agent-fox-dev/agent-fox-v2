"""Property tests for the hard reset engine.

Test Spec: TS-35-P1, TS-35-P2, TS-35-P3, TS-35-P4, TS-35-P5
Requirements: 35-REQ-3.1, 35-REQ-3.6, 35-REQ-3.E1, 35-REQ-4.E1,
              35-REQ-1.3, 35-REQ-7.1, 35-REQ-7.2
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.engine.state import ExecutionState, SessionRecord
from tests.unit.engine.conftest import write_plan_to_db

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_STATUSES = st.sampled_from(["pending", "in_progress", "completed", "failed", "blocked"])


@st.composite
def session_record_strategy(draw: st.DrawFn) -> SessionRecord:
    """Generate a random SessionRecord with a commit_sha field."""
    return SessionRecord(
        node_id=draw(st.from_regex(r"[a-z]{1,8}:[1-9]", fullmatch=True)),
        attempt=draw(st.integers(min_value=1, max_value=5)),
        status=draw(st.sampled_from(["completed", "failed"])),
        input_tokens=draw(st.integers(min_value=0, max_value=100000)),
        output_tokens=draw(st.integers(min_value=0, max_value=100000)),
        cost=draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False)),
        duration_ms=draw(st.integers(min_value=0, max_value=600000)),
        error_message=draw(st.none() | st.text(max_size=50)),
        timestamp="2026-03-01T10:00:00Z",
        model="test-model",
        files_touched=[],
        commit_sha="",
    )


@st.composite
def execution_state_strategy(
    draw: st.DrawFn,
    min_tasks: int = 1,
    max_tasks: int = 20,
) -> ExecutionState:
    """Generate a random ExecutionState with N tasks."""
    n = draw(st.integers(min_value=min_tasks, max_value=max_tasks))
    node_states = {}
    for i in range(1, n + 1):
        node_states[f"s:{i}"] = draw(_STATUSES)

    session_history = draw(st.lists(session_record_strategy(), min_size=0, max_size=min(n, 10)))

    return ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        session_history=session_history,
        total_input_tokens=draw(st.integers(min_value=0, max_value=1000000)),
        total_output_tokens=draw(st.integers(min_value=0, max_value=1000000)),
        total_cost=draw(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False)),
        total_sessions=draw(st.integers(min_value=0, max_value=100)),
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


def _write_plan_from_state(state: ExecutionState):
    """Build a DuckDB connection with plan data derived from an ExecutionState."""
    nodes = {}
    for nid in state.node_states:
        parts = nid.split(":")
        spec_name = parts[0] if len(parts) > 1 else "test_spec"
        group_number = int(parts[-1]) if parts[-1].isdigit() else 1
        nodes[nid] = {
            "spec_name": spec_name,
            "group_number": group_number,
            "title": f"Task {nid}",
            "status": state.node_states[nid],
        }
    return write_plan_to_db(nodes, [])


def _mock_git_subprocess(*args, **kwargs):
    """Mock subprocess.run for git commands — always succeeds."""
    from unittest.mock import MagicMock

    result = MagicMock()
    result.returncode = 0
    result.stdout = ""
    result.stderr = ""
    return result


# ===========================================================================
# TS-35-P1: Total Task Reset
# Property 1: For any ExecutionState, hard reset sets all tasks to pending.
# Validates: 35-REQ-3.1, 35-REQ-4.2, 35-REQ-4.3
# ===========================================================================


class TestTotalTaskResetProperty:
    """TS-35-P1: For any state, hard_reset_all sets all tasks to pending."""

    @given(state=execution_state_strategy(min_tasks=1, max_tasks=20))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_tasks_become_pending(
        self,
        state: ExecutionState,
        tmp_path_factory,
    ) -> None:
        """Every task status is 'pending' after hard_reset_all."""
        from agent_fox.engine.reset import hard_reset_all

        tmp_path = tmp_path_factory.mktemp("prop_total_reset")
        agent_dir = tmp_path / ".agent-fox"
        agent_dir.mkdir(parents=True, exist_ok=True)

        worktrees_dir = agent_dir / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        memory_path = agent_dir / "memory.jsonl"
        memory_path.write_text("")

        db_conn = _write_plan_from_state(state)

        with (
            patch(
                "agent_fox.engine.reset.subprocess.run",
                side_effect=_mock_git_subprocess,
            ),
            patch(
                "agent_fox.engine.reset._load_state_or_raise",
                return_value=state,
            ),
        ):
            hard_reset_all(worktrees_dir, tmp_path, memory_path, db_conn=db_conn)

        for task_id in state.node_states:
            assert state.node_states[task_id] == "pending"


# ===========================================================================
# TS-35-P2: Counter Preservation
# Property 2: Hard reset never modifies counters or session history.
# Validates: 35-REQ-3.6
# ===========================================================================


class TestCounterPreservationProperty:
    """TS-35-P2: Counters and session history unchanged after hard reset."""

    @given(state=execution_state_strategy(min_tasks=1, max_tasks=10))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_counters_unchanged(
        self,
        state: ExecutionState,
        tmp_path_factory,
    ) -> None:
        """total_cost, tokens, sessions, history length are preserved."""
        from agent_fox.engine.reset import hard_reset_all

        original_cost = state.total_cost
        original_input = state.total_input_tokens
        original_output = state.total_output_tokens
        original_sessions = state.total_sessions
        original_history_len = len(state.session_history)

        tmp_path = tmp_path_factory.mktemp("prop_counter")
        agent_dir = tmp_path / ".agent-fox"
        agent_dir.mkdir(parents=True, exist_ok=True)

        worktrees_dir = agent_dir / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        memory_path = agent_dir / "memory.jsonl"
        memory_path.write_text("")

        db_conn = _write_plan_from_state(state)

        with (
            patch(
                "agent_fox.engine.reset.subprocess.run",
                side_effect=_mock_git_subprocess,
            ),
            patch(
                "agent_fox.engine.reset._load_state_or_raise",
                return_value=state,
            ),
        ):
            hard_reset_all(worktrees_dir, tmp_path, memory_path, db_conn=db_conn)

        assert state.total_cost == original_cost
        assert state.total_input_tokens == original_input
        assert state.total_output_tokens == original_output
        assert state.total_sessions == original_sessions
        assert len(state.session_history) == original_history_len


# ===========================================================================
# TS-35-P3: Graceful Degradation
# Property 6: When no commit_sha data exists, hard reset completes with
#              rollback_sha=None.
# Validates: 35-REQ-3.E1, 35-REQ-4.E1
# ===========================================================================


class TestGracefulDegradationProperty:
    """TS-35-P3: No commit_sha data => rollback_sha is None, all tasks reset."""

    @given(state=execution_state_strategy(min_tasks=1, max_tasks=10))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_shas_yields_no_rollback(
        self,
        state: ExecutionState,
        tmp_path_factory,
    ) -> None:
        """rollback_sha is None when all commit_shas are empty."""
        from agent_fox.engine.reset import hard_reset_all

        # Ensure all session records have empty commit_sha
        for record in state.session_history:
            record.commit_sha = ""

        tmp_path = tmp_path_factory.mktemp("prop_degrade")
        agent_dir = tmp_path / ".agent-fox"
        agent_dir.mkdir(parents=True, exist_ok=True)

        worktrees_dir = agent_dir / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        memory_path = agent_dir / "memory.jsonl"
        memory_path.write_text("")

        db_conn = _write_plan_from_state(state)

        with (
            patch(
                "agent_fox.engine.reset.subprocess.run",
                side_effect=_mock_git_subprocess,
            ),
            patch(
                "agent_fox.engine.reset._load_state_or_raise",
                return_value=state,
            ),
        ):
            result = hard_reset_all(worktrees_dir, tmp_path, memory_path, db_conn=db_conn)

        assert result.rollback_sha is None

        for task_id in state.node_states:
            assert state.node_states[task_id] == "pending"


# ===========================================================================
# TS-35-P4: Backward-Compatible Deserialization
# Property 7: Legacy SessionRecord JSON always yields commit_sha="".
# Validates: 35-REQ-1.3
# ===========================================================================


class TestBackwardCompatDeserProperty:
    """TS-35-P4: Deserialization of legacy SessionRecord always gives commit_sha=''."""

    @given(
        node_id=st.from_regex(r"[a-z]{1,5}:[1-9]", fullmatch=True),
        attempt=st.integers(min_value=1, max_value=5),
        status=st.sampled_from(["completed", "failed"]),
        input_tokens=st.integers(min_value=0, max_value=100000),
        output_tokens=st.integers(min_value=0, max_value=100000),
        cost=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        duration_ms=st.integers(min_value=0, max_value=600000),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_legacy_record_has_empty_commit_sha(
        self,
        node_id: str,
        attempt: int,
        status: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: int,
    ) -> None:
        """SessionRecord created without commit_sha has commit_sha=''."""
        record = SessionRecord(
            node_id=node_id,
            attempt=attempt,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            duration_ms=duration_ms,
            error_message=None,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert record.commit_sha == ""


# ===========================================================================
# TS-35-P5: Artifact Synchronization Consistency
# Property 8: After reset, tasks.md and plan.json are consistent.
# Validates: 35-REQ-7.1, 35-REQ-7.2
# NOTE: reset_plan_statuses() was removed with the StateManager→DB migration.
#       Plan node statuses are now persisted via _persist_resets() to DuckDB.
#       This property test was simplified to only test tasks.md checkboxes.
# ===========================================================================


class TestArtifactSyncProperty:
    """TS-35-P5: tasks.md checkboxes are consistent after reset."""

    @given(
        n_tasks=st.integers(min_value=1, max_value=10),
        statuses=st.lists(
            st.sampled_from(["completed", "in_progress", "failed"]),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_checkboxes_consistent(
        self,
        n_tasks: int,
        statuses: list[str],
        tmp_path_factory,
    ) -> None:
        """All affected task checkboxes are [ ] after reset."""
        from agent_fox.engine.reset import reset_tasks_md_checkboxes

        # Use min of n_tasks and len(statuses) for consistency
        actual_n = min(n_tasks, len(statuses))
        task_ids = [f"propspec:{i + 1}" for i in range(actual_n)]

        tmp_path = tmp_path_factory.mktemp("prop_sync")
        specs_dir = tmp_path / ".specs"
        spec_dir = specs_dir / "propspec"
        spec_dir.mkdir(parents=True)

        # Build tasks.md with mixed checkbox states
        checkbox_map = {"completed": "[x]", "in_progress": "[-]", "failed": "[x]"}
        lines = ["# Tasks\n"]
        for i in range(actual_n):
            status = statuses[i]
            cb = checkbox_map.get(status, "[x]")
            lines.append(f"- {cb} {i + 1}. Task group {i + 1}\n")
            lines.append(f"  - {cb} {i + 1}.1 Subtask\n")

        tasks_md = spec_dir / "tasks.md"
        tasks_md.write_text("".join(lines))

        # Run reset
        reset_tasks_md_checkboxes(task_ids, specs_dir)

        # Verify tasks.md checkboxes
        text = tasks_md.read_text()
        for i in range(actual_n):
            assert f"- [ ] {i + 1}." in text
