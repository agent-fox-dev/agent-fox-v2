"""State persistence tests: save/load, record session, corrupt/mismatch handling.

Test Spec: TS-04-8 (persist after session), TS-04-9 (resume from state),
           TS-04-E3 (corrupted state), TS-04-E4 (plan hash mismatch)
Requirements: 04-REQ-4.1, 04-REQ-4.2, 04-REQ-4.3, 04-REQ-4.E1, 04-REQ-4.E2,
              04-REQ-7.2
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_fox.engine.state import (
    ExecutionState,
    SessionRecord,
    StateManager,
)

# -- Helpers ------------------------------------------------------------------


def _make_session_record(
    node_id: str = "A",
    attempt: int = 1,
    status: str = "completed",
    cost: float = 0.10,
) -> SessionRecord:
    """Create a SessionRecord for testing."""
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=100,
        output_tokens=200,
        cost=cost,
        duration_ms=5000,
        error_message=None if status == "completed" else "some error",
        timestamp="2026-03-01T10:00:00Z",
    )


def _make_execution_state(
    plan_hash: str = "abc123",
    node_states: dict[str, str] | None = None,
    session_history: list[SessionRecord] | None = None,
    total_sessions: int = 0,
    total_cost: float = 0.0,
) -> ExecutionState:
    """Create an ExecutionState for testing."""
    return ExecutionState(
        plan_hash=plan_hash,
        node_states=node_states or {},
        session_history=session_history or [],
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:55:00Z",
        updated_at="2026-03-01T10:00:00Z",
        run_status="running",
    )


# -- Tests --------------------------------------------------------------------


class TestStatePersistence:
    """TS-04-8: State persisted after every session.

    Verify that StateManager.save() writes to state.jsonl and
    record_session() correctly updates cumulative totals.
    """

    def test_save_creates_jsonl_file(self, tmp_state_path: Path) -> None:
        """Saving state creates the state.jsonl file."""
        manager = StateManager(tmp_state_path)
        state = _make_execution_state()

        manager.save(state)

        assert tmp_state_path.exists()

    def test_save_writes_valid_json_line(self, tmp_state_path: Path) -> None:
        """Each save appends a valid JSON line."""
        manager = StateManager(tmp_state_path)
        state = _make_execution_state(
            node_states={"A": "completed"},
            session_history=[_make_session_record("A")],
            total_sessions=1,
        )

        manager.save(state)

        lines = tmp_state_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["node_states"]["A"] == "completed"
        assert len(data["session_history"]) == 1

    def test_multiple_saves_append_lines(self, tmp_state_path: Path) -> None:
        """Multiple saves append multiple JSON lines."""
        manager = StateManager(tmp_state_path)

        state1 = _make_execution_state(
            node_states={"A": "completed"},
            total_sessions=1,
        )
        manager.save(state1)

        state2 = _make_execution_state(
            node_states={"A": "completed", "B": "completed"},
            total_sessions=2,
        )
        manager.save(state2)

        lines = tmp_state_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_record_session_updates_totals(
        self,
        tmp_state_path: Path,
    ) -> None:
        """record_session() updates cumulative token/cost/session totals."""
        manager = StateManager(tmp_state_path)
        state = _make_execution_state()

        record = _make_session_record("A", cost=0.15)
        updated = manager.record_session(state, record)

        assert updated.total_sessions == 1
        assert updated.total_cost == pytest.approx(0.15)
        assert updated.total_input_tokens == 100
        assert updated.total_output_tokens == 200
        assert len(updated.session_history) == 1

    def test_state_includes_plan_hash(self, tmp_state_path: Path) -> None:
        """Persisted state includes the plan hash."""
        manager = StateManager(tmp_state_path)
        state = _make_execution_state(plan_hash="test_hash_123")

        manager.save(state)

        data = json.loads(tmp_state_path.read_text().strip())
        assert data["plan_hash"] == "test_hash_123"


class TestResumeFromState:
    """TS-04-9: Resume from persisted state.

    Verify StateManager.load() reconstructs state and completed tasks
    are skipped on resume.
    """

    def test_load_returns_last_saved_state(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Loading returns the state from the last JSON line."""
        manager = StateManager(tmp_state_path)

        state1 = _make_execution_state(
            node_states={"A": "completed"},
            total_sessions=1,
        )
        manager.save(state1)

        state2 = _make_execution_state(
            node_states={"A": "completed", "B": "completed"},
            total_sessions=2,
        )
        manager.save(state2)

        loaded = manager.load()

        assert loaded is not None
        assert loaded.node_states["A"] == "completed"
        assert loaded.node_states["B"] == "completed"
        assert loaded.total_sessions == 2

    def test_load_returns_none_when_no_file(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Loading returns None when state file does not exist."""
        manager = StateManager(tmp_state_path)

        loaded = manager.load()

        assert loaded is None

    def test_completed_tasks_preserved_on_load(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Completed task statuses are preserved when loaded."""
        manager = StateManager(tmp_state_path)
        state = _make_execution_state(
            node_states={
                "A": "completed",
                "B": "completed",
                "C": "pending",
            },
            total_sessions=2,
        )
        manager.save(state)

        loaded = manager.load()

        assert loaded is not None
        assert loaded.node_states["A"] == "completed"
        assert loaded.node_states["B"] == "completed"
        assert loaded.node_states["C"] == "pending"

    def test_session_history_preserved_on_load(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Session history entries are preserved on load."""
        manager = StateManager(tmp_state_path)
        records = [
            _make_session_record("A", attempt=1),
            _make_session_record("B", attempt=1),
        ]
        state = _make_execution_state(
            session_history=records,
            total_sessions=2,
        )
        manager.save(state)

        loaded = manager.load()

        assert loaded is not None
        assert len(loaded.session_history) == 2


class TestCorruptedState:
    """TS-04-E3: Corrupted state file on resume.

    Verify StateManager handles corrupted state gracefully.
    """

    def test_corrupted_json_returns_none(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Corrupted JSON returns None (warning logged, fresh start)."""
        tmp_state_path.write_text("{{not valid json}}\n")

        manager = StateManager(tmp_state_path)
        loaded = manager.load()

        assert loaded is None

    def test_empty_file_returns_none(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Empty state file returns None."""
        tmp_state_path.write_text("")

        manager = StateManager(tmp_state_path)
        loaded = manager.load()

        assert loaded is None

    def test_partial_json_returns_none(
        self,
        tmp_state_path: Path,
    ) -> None:
        """Partially written JSON line returns None."""
        tmp_state_path.write_text('{"plan_hash": "abc", "node_states":')

        manager = StateManager(tmp_state_path)
        loaded = manager.load()

        assert loaded is None


class TestPlanHashMismatch:
    """TS-04-E4: Plan hash mismatch on resume.

    Verify StateManager detects plan hash changes.
    """

    def test_compute_plan_hash_returns_string(
        self,
        tmp_path: Path,
    ) -> None:
        """compute_plan_hash() returns a hex string."""
        plan_path = tmp_path / "plan.json"
        plan_path.write_text('{"nodes": {}, "edges": [], "order": []}')

        result = StateManager.compute_plan_hash(plan_path)

        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        """Same file content produces the same hash."""
        content = '{"nodes": {}, "edges": [], "order": []}'

        path1 = tmp_path / "plan1.json"
        path1.write_text(content)

        path2 = tmp_path / "plan2.json"
        path2.write_text(content)

        assert StateManager.compute_plan_hash(path1) == StateManager.compute_plan_hash(path2)

    def test_different_content_different_hash(
        self,
        tmp_path: Path,
    ) -> None:
        """Different file content produces different hashes."""
        path1 = tmp_path / "plan1.json"
        path1.write_text('{"nodes": {"A": {"id": "A"}}, "edges": [], "order": ["A"]}')

        path2 = tmp_path / "plan2.json"
        path2.write_text('{"nodes": {"B": {"id": "B"}}, "edges": [], "order": ["B"]}')

        assert StateManager.compute_plan_hash(path1) != StateManager.compute_plan_hash(path2)

    def test_status_change_does_not_change_hash(
        self,
        tmp_path: Path,
    ) -> None:
        """Changing a node's status does not change the plan hash."""
        path1 = tmp_path / "plan1.json"
        path1.write_text(
            json.dumps(
                {
                    "nodes": {"A": {"id": "A", "status": "pending"}},
                    "edges": [],
                    "order": ["A"],
                }
            )
        )

        path2 = tmp_path / "plan2.json"
        path2.write_text(
            json.dumps(
                {
                    "nodes": {"A": {"id": "A", "status": "completed"}},
                    "edges": [],
                    "order": ["A"],
                }
            )
        )

        assert StateManager.compute_plan_hash(path1) == StateManager.compute_plan_hash(path2)
