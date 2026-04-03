"""Property tests for state persistence: save/load roundtrip.

Test Spec: TS-04-P5 (state save/load roundtrip)
Properties: Property 1 (resume idempotency) from design.md
Requirements: 04-REQ-4.1, 04-REQ-4.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager

# -- Hypothesis strategies for generating valid ExecutionState ----------------


@st.composite
def session_records(draw: st.DrawFn) -> SessionRecord:
    """Generate a valid SessionRecord."""
    node_id = draw(st.sampled_from(["A", "B", "C", "D", "E"]))
    attempt = draw(st.integers(min_value=1, max_value=5))
    status = draw(st.sampled_from(["completed", "failed"]))
    input_tokens = draw(st.integers(min_value=0, max_value=100000))
    output_tokens = draw(st.integers(min_value=0, max_value=100000))
    cost = draw(st.floats(min_value=0.0, max_value=10.0))
    duration_ms = draw(st.integers(min_value=0, max_value=600000))
    error_message = draw(st.text(min_size=1, max_size=50)) if status == "failed" else None

    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        duration_ms=duration_ms,
        error_message=error_message,
        timestamp="2026-03-01T10:00:00Z",
    )


@st.composite
def valid_execution_states(draw: st.DrawFn) -> ExecutionState:
    """Generate a valid ExecutionState."""
    node_ids = draw(
        st.lists(
            st.sampled_from(["A", "B", "C", "D", "E"]),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )

    statuses = ["pending", "completed", "blocked", "in_progress", "failed"]
    node_states = {nid: draw(st.sampled_from(statuses)) for nid in node_ids}

    history = draw(st.lists(session_records(), min_size=0, max_size=5))

    total_cost = sum(r.cost for r in history)
    total_input = sum(r.input_tokens for r in history)
    total_output = sum(r.output_tokens for r in history)
    total_sessions = len(history)

    run_status = draw(
        st.sampled_from(
            [
                "running",
                "completed",
                "interrupted",
                "cost_limit",
                "session_limit",
                "stalled",
            ]
        )
    )

    return ExecutionState(
        plan_hash=draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
                min_size=8,
                max_size=64,
            )
        ),
        node_states=node_states,
        session_history=history,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:55:00Z",
        updated_at="2026-03-01T10:00:00Z",
        run_status=run_status,
    )


# -- Property tests ----------------------------------------------------------


class TestStateSaveLoadRoundtrip:
    """TS-04-P5: State save/load roundtrip.

    Saving and loading an ExecutionState produces an equivalent object.

    Property 1 from design.md (resume idempotency).
    """

    @given(state=valid_execution_states())
    @settings(max_examples=50)
    def test_roundtrip_preserves_plan_hash(
        self,
        state: ExecutionState,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Plan hash is preserved through save/load."""
        tmp_path = tmp_path_factory.mktemp("state")
        state_path = tmp_path / "state.jsonl"

        manager = StateManager(state_path)
        manager.save(state)
        loaded = manager.load()

        assert loaded is not None
        assert loaded.plan_hash == state.plan_hash

    @given(state=valid_execution_states())
    @settings(max_examples=50)
    def test_roundtrip_preserves_node_states(
        self,
        state: ExecutionState,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Node states dict is preserved through save/load."""
        tmp_path = tmp_path_factory.mktemp("state")
        state_path = tmp_path / "state.jsonl"

        manager = StateManager(state_path)
        manager.save(state)
        loaded = manager.load()

        assert loaded is not None
        assert loaded.node_states == state.node_states

    @given(state=valid_execution_states())
    @settings(max_examples=50)
    def test_roundtrip_preserves_totals(
        self,
        state: ExecutionState,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Cumulative totals are preserved through save/load."""
        tmp_path = tmp_path_factory.mktemp("state")
        state_path = tmp_path / "state.jsonl"

        manager = StateManager(state_path)
        manager.save(state)
        loaded = manager.load()

        assert loaded is not None
        assert loaded.total_cost == pytest.approx(state.total_cost)
        assert loaded.total_sessions == state.total_sessions

    @given(state=valid_execution_states())
    @settings(max_examples=50)
    def test_roundtrip_preserves_session_history_length(
        self,
        state: ExecutionState,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Session history length is preserved through save/load."""
        tmp_path = tmp_path_factory.mktemp("state")
        state_path = tmp_path / "state.jsonl"

        manager = StateManager(state_path)
        manager.save(state)
        loaded = manager.load()

        assert loaded is not None
        assert len(loaded.session_history) == len(state.session_history)
