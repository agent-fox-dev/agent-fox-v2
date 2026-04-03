"""Property tests for circuit breaker: retry bound, cost limit enforcement.

Test Spec: TS-04-P3 (retry bound), TS-04-P4 (cost limit enforcement)
Properties: Property 6 (retry bound), Property 3 (cost limit enforcement)
Requirements: 04-REQ-2.1, 04-REQ-2.3, 04-REQ-5.1, 04-REQ-5.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.state import ExecutionState

# -- Helpers ------------------------------------------------------------------


def _make_state(
    total_cost: float = 0.0,
    total_sessions: int = 0,
) -> ExecutionState:
    """Create a minimal ExecutionState for testing."""
    return ExecutionState(
        plan_hash="test",
        node_states={},
        session_history=[],
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:55:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


# -- Property tests ----------------------------------------------------------


class TestRetryBound:
    """TS-04-P3: Retry bound.

    For any max_retries value and any sequence of failures, the total
    attempt count never exceeds max_retries + 1.

    Property 6 from design.md.
    """

    @given(max_retries=st.integers(min_value=0, max_value=5))
    @settings(max_examples=50)
    def test_attempt_count_bounded(self, max_retries: int) -> None:
        """Session dispatch count for a task == max_retries + 1."""
        config = OrchestratorConfig(max_retries=max_retries)
        circuit = CircuitBreaker(config)
        state = _make_state()

        for attempt in range(1, max_retries + 10):
            decision = circuit.check_launch("A", attempt, state)
            if attempt <= max_retries + 1:
                assert decision.allowed, f"Attempt {attempt} should be allowed with max_retries={max_retries}"
            else:
                assert not decision.allowed, f"Attempt {attempt} should be denied with max_retries={max_retries}"

    @given(max_retries=st.integers(min_value=0, max_value=5))
    @settings(max_examples=50)
    def test_exactly_max_plus_one_attempts_allowed(
        self,
        max_retries: int,
    ) -> None:
        """Exactly max_retries + 1 attempts are allowed."""
        config = OrchestratorConfig(max_retries=max_retries)
        circuit = CircuitBreaker(config)
        state = _make_state()

        allowed_count = 0
        for attempt in range(1, max_retries + 5):
            decision = circuit.check_launch("A", attempt, state)
            if decision.allowed:
                allowed_count += 1

        assert allowed_count == max_retries + 1


class TestCostLimitEnforcement:
    """TS-04-P4: Cost limit enforcement.

    No sessions are launched after cumulative cost reaches the
    configured ceiling.

    Property 3 from design.md.
    """

    @given(
        max_cost=st.floats(min_value=0.01, max_value=100.0),
        costs=st.lists(
            st.floats(min_value=0.01, max_value=10.0),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_no_launches_after_limit_reached(
        self,
        max_cost: float,
        costs: list[float],
    ) -> None:
        """Once total_cost >= max_cost, should_stop() returns denied."""
        config = OrchestratorConfig(max_cost=max_cost)
        circuit = CircuitBreaker(config)

        cumulative = 0.0
        for cost in costs:
            cumulative += cost
            state = _make_state(total_cost=cumulative)
            decision = circuit.should_stop(state)
            if cumulative >= max_cost:
                assert not decision.allowed, f"Should deny at cumulative={cumulative:.2f} with max_cost={max_cost:.2f}"

    @given(
        max_cost=st.floats(min_value=0.01, max_value=100.0),
        total_cost=st.floats(min_value=0.0, max_value=200.0),
    )
    @settings(max_examples=100)
    def test_allows_under_limit_denies_at_or_above(
        self,
        max_cost: float,
        total_cost: float,
    ) -> None:
        """Allowed iff total_cost < max_cost."""
        config = OrchestratorConfig(max_cost=max_cost)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=total_cost)

        decision = circuit.should_stop(state)

        if total_cost >= max_cost:
            assert not decision.allowed
        else:
            assert decision.allowed
