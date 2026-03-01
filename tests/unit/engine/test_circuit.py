"""Circuit breaker tests: cost limit, session limit, retry limit.

Test Spec: TS-04-10 (cost limit), TS-04-11 (session limit),
           TS-04-5 (zero retries), TS-04-E8 (circuit denies at cost limit),
           TS-04-E9 (circuit denies at session limit)
Requirements: 04-REQ-2.E1, 04-REQ-5.1, 04-REQ-5.2, 04-REQ-5.3
"""

from __future__ import annotations

from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.engine.state import ExecutionState

from agent_fox.core.config import OrchestratorConfig

# -- Helpers ------------------------------------------------------------------


def _make_state(
    total_cost: float = 0.0,
    total_sessions: int = 0,
) -> ExecutionState:
    """Create an ExecutionState with specified cost/session totals."""
    return ExecutionState(
        plan_hash="test",
        node_states={},
        session_history=[],
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:55:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )


# -- Tests --------------------------------------------------------------------


class TestCostLimitStopsLaunches:
    """TS-04-10: Cost limit stops new launches.

    Verify the circuit breaker stops launching new sessions when
    cumulative cost reaches the configured ceiling.
    """

    def test_allows_launch_under_cost_limit(self) -> None:
        """Launches allowed when cost is under the limit."""
        config = OrchestratorConfig(max_cost=1.00)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=0.50)

        decision = circuit.should_stop(state)

        assert decision.allowed is True

    def test_denies_launch_at_cost_limit(self) -> None:
        """Launches denied when cost reaches the limit."""
        config = OrchestratorConfig(max_cost=1.00)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=1.00)

        decision = circuit.should_stop(state)

        assert decision.allowed is False

    def test_denies_launch_above_cost_limit(self) -> None:
        """Launches denied when cost exceeds the limit."""
        config = OrchestratorConfig(max_cost=0.50)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=0.55)

        decision = circuit.should_stop(state)

        assert decision.allowed is False

    def test_no_cost_limit_allows_all(self) -> None:
        """With no cost limit (None), all launches are allowed."""
        config = OrchestratorConfig(max_cost=None)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=999.99)

        decision = circuit.should_stop(state)

        assert decision.allowed is True


class TestSessionLimitStopsLaunches:
    """TS-04-11: Session limit stops new launches.

    Verify the circuit breaker stops after the configured number
    of sessions.
    """

    def test_allows_launch_under_session_limit(self) -> None:
        """Launches allowed when session count is under the limit."""
        config = OrchestratorConfig(max_sessions=10)
        circuit = CircuitBreaker(config)
        state = _make_state(total_sessions=5)

        decision = circuit.should_stop(state)

        assert decision.allowed is True

    def test_denies_launch_at_session_limit(self) -> None:
        """Launches denied when session count reaches the limit."""
        config = OrchestratorConfig(max_sessions=10)
        circuit = CircuitBreaker(config)
        state = _make_state(total_sessions=10)

        decision = circuit.should_stop(state)

        assert decision.allowed is False

    def test_no_session_limit_allows_all(self) -> None:
        """With no session limit (None), all launches are allowed."""
        config = OrchestratorConfig(max_sessions=None)
        circuit = CircuitBreaker(config)
        state = _make_state(total_sessions=1000)

        decision = circuit.should_stop(state)

        assert decision.allowed is True


class TestZeroRetriesBlocksImmediately:
    """TS-04-5: Zero retries blocks immediately.

    Verify that with max_retries=0, the circuit breaker allows
    exactly one attempt (attempt 1) and denies attempt 2.
    """

    def test_allows_first_attempt(self) -> None:
        """First attempt (attempt=1) is always allowed."""
        config = OrchestratorConfig(max_retries=0)
        circuit = CircuitBreaker(config)
        state = _make_state()

        decision = circuit.check_launch("A", attempt=1, state=state)

        assert decision.allowed is True

    def test_denies_second_attempt(self) -> None:
        """Second attempt (attempt=2) is denied with max_retries=0."""
        config = OrchestratorConfig(max_retries=0)
        circuit = CircuitBreaker(config)
        state = _make_state()

        decision = circuit.check_launch("A", attempt=2, state=state)

        assert decision.allowed is False

    def test_denies_reason_mentions_retry(self) -> None:
        """Denial reason mentions retry limit."""
        config = OrchestratorConfig(max_retries=0)
        circuit = CircuitBreaker(config)
        state = _make_state()

        decision = circuit.check_launch("A", attempt=2, state=state)

        assert decision.reason is not None
        assert "retry" in decision.reason.lower() or \
            "attempt" in decision.reason.lower()


class TestCircuitBreakerDeniesAtCostLimit:
    """TS-04-E8: Circuit breaker denies launch at cost limit.

    Verify should_stop() returns denied with reason mentioning cost.
    """

    def test_denied_reason_mentions_cost(self) -> None:
        """Denial reason mentions cost."""
        config = OrchestratorConfig(max_cost=1.00)
        circuit = CircuitBreaker(config)
        state = _make_state(total_cost=1.05)

        decision = circuit.should_stop(state)

        assert decision.allowed is False
        assert decision.reason is not None
        assert "cost" in decision.reason.lower()


class TestCircuitBreakerDeniesAtSessionLimit:
    """TS-04-E9: Circuit breaker denies launch at session limit.

    Verify should_stop() returns denied with reason mentioning session.
    """

    def test_denied_reason_mentions_session(self) -> None:
        """Denial reason mentions session limit."""
        config = OrchestratorConfig(max_sessions=10)
        circuit = CircuitBreaker(config)
        state = _make_state(total_sessions=10)

        decision = circuit.should_stop(state)

        assert decision.allowed is False
        assert decision.reason is not None
        assert "session" in decision.reason.lower()


class TestRetryLimitEnforcement:
    """Additional retry limit tests for CircuitBreaker.check_launch()."""

    def test_allows_up_to_max_retries_plus_one(self) -> None:
        """With max_retries=2, attempts 1, 2, 3 are allowed."""
        config = OrchestratorConfig(max_retries=2)
        circuit = CircuitBreaker(config)
        state = _make_state()

        for attempt in range(1, 4):  # 1, 2, 3
            decision = circuit.check_launch("A", attempt=attempt, state=state)
            assert decision.allowed is True, f"Attempt {attempt} should be allowed"

    def test_denies_beyond_max_retries(self) -> None:
        """With max_retries=2, attempt 4 is denied."""
        config = OrchestratorConfig(max_retries=2)
        circuit = CircuitBreaker(config)
        state = _make_state()

        decision = circuit.check_launch("A", attempt=4, state=state)

        assert decision.allowed is False
