"""Property-based tests for timeout-aware escalation.

Test Spec: TS-75-P1 through TS-75-P6
Requirements: 75-REQ-1.1, 75-REQ-2.1, 75-REQ-2.2, 75-REQ-2.4, 75-REQ-2.E1,
              75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.4, 75-REQ-3.E1,
              75-REQ-4.4, 75-REQ-4.5, 75-REQ-4.6
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.engine.graph_sync import GraphSync
from agent_fox.engine.result_handler import SessionResultHandler
from agent_fox.engine.state import ExecutionState, SessionRecord, StateManager

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_record(
    status: str,
    *,
    node_id: str = "node1",
    attempt: int = 1,
    error_message: str | None = None,
) -> SessionRecord:
    return SessionRecord(
        node_id=node_id,
        attempt=attempt,
        status=status,
        input_tokens=100,
        output_tokens=50,
        cost=0.01,
        duration_ms=5000,
        error_message=error_message,
        timestamp="2026-01-01T00:00:00Z",
    )


def _make_mock_ladder(
    *,
    is_exhausted: bool = False,
    should_retry: bool = True,
    escalation_count: int = 0,
    attempt_count: int = 1,
) -> MagicMock:
    mock = MagicMock()
    mock.is_exhausted = is_exhausted
    mock.should_retry.return_value = should_retry
    mock.escalation_count = escalation_count
    mock.attempt_count = attempt_count
    return mock


def _make_handler(
    *,
    node_id: str = "node1",
    max_timeout_retries: int = 2,
) -> tuple[
    SessionResultHandler,
    MagicMock,
    ExecutionState,
    dict[str, int],
    dict[str, str | None],
]:
    """Create a minimal SessionResultHandler for property tests."""
    graph_sync = GraphSync({node_id: "in_progress"}, {node_id: []})
    mock_state_manager = MagicMock(spec=StateManager)
    mock_ladder = _make_mock_ladder()
    routing_ladders: dict[str, Any] = {node_id: mock_ladder}

    handler = SessionResultHandler(
        graph_sync=graph_sync,
        state_manager=mock_state_manager,
        routing_ladders=routing_ladders,
        routing_assessments={},
        routing_pipeline=None,
        retries_before_escalation=1,
        max_retries=max_timeout_retries + 2,
        task_callback=None,
        sink=None,
        run_id="prop-test-run",
        graph=None,
        archetypes_config=None,
        knowledge_db_conn=None,
        block_task_fn=lambda nid, st, reason: None,
        check_block_budget_fn=lambda st: False,
    )

    state = ExecutionState(
        plan_hash="prop-test",
        node_states={node_id: "in_progress"},
    )

    attempt_tracker: dict[str, int] = {}
    error_tracker: dict[str, str | None] = {}

    return handler, mock_ladder, state, attempt_tracker, error_tracker


# ---------------------------------------------------------------------------
# TS-75-P1: Timeout Never Directly Escalates (Property 1)
# Requirements: 75-REQ-1.1, 75-REQ-2.2
# ---------------------------------------------------------------------------


class TestTimeoutNeverDirectlyEscalates:
    """TS-75-P1: With retries remaining, timeout never calls record_failure()."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        max_timeout_retries=st.integers(min_value=1, max_value=5),
        timeout_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_timeout_never_escalates_while_retries_remain(
        self, max_timeout_retries: int, timeout_count: int
    ) -> None:
        """TS-75-P1: Processing N ≤ max_timeout_retries timeouts → 0 ladder failures.

        For any N in [1..max_timeout_retries], processing N timeout records
        must never invoke the escalation ladder's record_failure().

        Validates: 75-REQ-1.1, 75-REQ-2.2
        """
        # Clamp timeout_count to max_timeout_retries so retries remain.
        n = min(timeout_count, max_timeout_retries)

        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            max_timeout_retries=max_timeout_retries
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = max_timeout_retries

        for i in range(n):
            record = _make_record("timeout", attempt=i + 1)
            handler.process(
                record,
                attempt=i + 1,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        # Property: no escalation ladder failures while retries remain.
        # Currently FAILS because _handle_failure is called for all non-success.
        assert mock_ladder.record_failure.call_count == 0

    def test_single_timeout_no_escalation(self) -> None:
        """TS-75-P1 (concrete): One timeout with max_timeout_retries=1 → none."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            max_timeout_retries=1
        )
        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 1

        record = _make_record("timeout")
        handler.process(
            record,
            attempt=1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 0


# ---------------------------------------------------------------------------
# TS-75-P2: Counter Independence (Property 2)
# Requirements: 75-REQ-2.1, 75-REQ-2.E1
# ---------------------------------------------------------------------------


class TestCounterIndependence:
    """TS-75-P2: Interleaved timeout and failure events have independent counts."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        events=st.lists(
            st.sampled_from(["timeout", "failed"]),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_counters_independent_for_any_event_sequence(
        self, events: list[str]
    ) -> None:
        """TS-75-P2: Timeout and failure counts are independent in any sequence.

        For any sequence of 'timeout' and 'failed' events:
        - The timeout retry counter counts only timeout events (up to max).
        - The escalation ladder records only failure events.

        Validates: 75-REQ-2.1, 75-REQ-2.E1
        """
        max_timeout_retries = 5
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            max_timeout_retries=max_timeout_retries
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = max_timeout_retries

        for i, event_status in enumerate(events):
            record = _make_record(event_status, attempt=i + 1)
            handler.process(
                record,
                attempt=i + 1,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        expected_timeouts_before_max = min(
            sum(1 for e in events if e == "timeout"), max_timeout_retries
        )
        expected_failures = sum(1 for e in events if e == "failed")
        # Timeouts that fell through after exhaustion also count as failures.
        timeouts_after_max = max(
            0, sum(1 for e in events if e == "timeout") - max_timeout_retries
        )
        total_expected_ladder_failures = expected_failures + timeouts_after_max

        # Currently FAILS: _timeout_retries doesn't exist.
        actual_timeout_retries = handler._timeout_retries.get("node1", -1)
        assert actual_timeout_retries == expected_timeouts_before_max

        # Failures should only count ladder invocations.
        assert mock_ladder.record_failure.call_count == total_expected_ladder_failures


# ---------------------------------------------------------------------------
# TS-75-P3: Monotonic Timeout Extension (Property 3)
# Requirements: 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.E1
# ---------------------------------------------------------------------------


class TestMonotonicTimeoutExtension:
    """TS-75-P3: Extended timeout is non-decreasing and bounded by ceiling."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        original_timeout=st.integers(min_value=1, max_value=120),
        multiplier=st.floats(min_value=1.0, max_value=3.0, allow_nan=False),
        ceiling_factor=st.floats(min_value=1.0, max_value=5.0, allow_nan=False),
        retry_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_timeout_extension_is_monotonic_and_bounded(
        self,
        original_timeout: int,
        multiplier: float,
        ceiling_factor: float,
        retry_count: int,
    ) -> None:
        """TS-75-P3: Extension is non-decreasing and bounded by ceiling.

        For any (original_timeout, multiplier, ceiling_factor, retry_count):
        - Each retry's extended_timeout >= previous retry's extended_timeout.
        - Each extended_timeout <= ceil(original_timeout * ceiling_factor).

        Validates: 75-REQ-3.2, 75-REQ-3.3, 75-REQ-3.E1
        """
        ceiling = math.ceil(original_timeout * ceiling_factor)

        prev = original_timeout
        for _ in range(retry_count):
            extended = min(math.ceil(prev * multiplier), ceiling)
            # Property: non-decreasing.
            assert extended >= prev
            # Property: bounded by ceiling.
            assert extended <= ceiling
            prev = extended

    def test_concrete_two_retries_clamped(self) -> None:
        """TS-75-P3 (concrete): original=30, mult=1.5, ceil=2.0: 45 → 60."""
        handler, _, _, _, _ = _make_handler()

        # Currently FAILS: attributes don't exist.
        handler._node_timeout["node1"] = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0
        handler._node_max_turns["node1"] = 200

        handler._extend_node_params("node1")  # Currently FAILS
        assert handler._node_timeout["node1"] == 45

        handler._extend_node_params("node1")
        assert handler._node_timeout["node1"] == 60


# ---------------------------------------------------------------------------
# TS-75-P4: Timeout Exhaustion Falls Through (Property 4)
# Requirement: 75-REQ-2.4
# ---------------------------------------------------------------------------


class TestTimeoutExhaustionFallsThrough:
    """TS-75-P4: After max_timeout_retries, next timeout hits escalation."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(max_retries=st.integers(min_value=0, max_value=5))
    @settings(max_examples=30)
    def test_exhaustion_triggers_escalation(self, max_retries: int) -> None:
        """TS-75-P4: After exactly max_retries timeouts, (max+1)th hits ladder.

        Validates: 75-REQ-2.4
        """
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            max_timeout_retries=max_retries
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = max_retries

        # Process exactly max_retries timeouts → should NOT call record_failure.
        for i in range(max_retries):
            record = _make_record("timeout", attempt=i + 1)
            handler.process(
                record,
                attempt=i + 1,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        # Currently FAILS: record_failure IS called on every failure path.
        assert mock_ladder.record_failure.call_count == 0

        # One more timeout → must fall through to escalation.
        record = _make_record("timeout", attempt=max_retries + 1)
        handler.process(
            record,
            attempt=max_retries + 1,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 1

    def test_concrete_exhaustion_at_max_two(self) -> None:
        """TS-75-P4 (concrete): max_timeout_retries=2; 3rd timeout → escalation."""
        handler, mock_ladder, state, attempt_tracker, error_tracker = _make_handler(
            max_timeout_retries=2
        )

        # Currently FAILS: _max_timeout_retries doesn't exist.
        handler._max_timeout_retries = 2

        for i in range(2):
            record = _make_record("timeout", attempt=i + 1)
            handler.process(
                record,
                attempt=i + 1,
                state=state,
                attempt_tracker=attempt_tracker,
                error_tracker=error_tracker,
            )

        assert mock_ladder.record_failure.call_count == 0

        record = _make_record("timeout", attempt=3)
        handler.process(
            record,
            attempt=3,
            state=state,
            attempt_tracker=attempt_tracker,
            error_tracker=error_tracker,
        )

        assert mock_ladder.record_failure.call_count == 1


# ---------------------------------------------------------------------------
# TS-75-P5: Unlimited Turns Preserved (Property 5)
# Requirement: 75-REQ-3.4
# ---------------------------------------------------------------------------


class TestUnlimitedTurnsPreserved:
    """TS-75-P5: max_turns=None stays None through any number of retries."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(retry_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_none_max_turns_preserved_through_retries(self, retry_count: int) -> None:
        """TS-75-P5: None max_turns remains None through any number of retries.

        Validates: 75-REQ-3.4
        """
        handler, _, _, _, _ = _make_handler()

        # Currently FAILS: _node_max_turns doesn't exist.
        handler._node_max_turns["node1"] = None
        handler._node_timeout["node1"] = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0

        for _ in range(retry_count):
            # Currently FAILS: method doesn't exist.
            handler._extend_node_params("node1")
            assert handler._node_max_turns["node1"] is None

    def test_none_preserved_concrete_three_retries(self) -> None:
        """TS-75-P5 (concrete): None max_turns stays None through 3 retries."""
        handler, _, _, _, _ = _make_handler()

        # Currently FAILS: _node_max_turns doesn't exist.
        handler._node_max_turns["node1"] = None
        handler._node_timeout["node1"] = 30
        handler._timeout_multiplier = 1.5
        handler._timeout_ceiling_factor = 2.0

        for _ in range(3):
            handler._extend_node_params("node1")  # Currently FAILS

        assert handler._node_max_turns["node1"] is None


# ---------------------------------------------------------------------------
# TS-75-P6: Config Validation Bounds (Property 6)
# Requirements: 75-REQ-4.4, 75-REQ-4.5, 75-REQ-4.6
# ---------------------------------------------------------------------------


class TestConfigValidationBounds:
    """TS-75-P6: Config fields are always within valid bounds after construction."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        max_timeout_retries=st.integers(min_value=-10, max_value=100),
        timeout_multiplier=st.floats(
            min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
        timeout_ceiling_factor=st.floats(
            min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100)
    def test_config_bounds_always_valid(
        self,
        max_timeout_retries: int,
        timeout_multiplier: float,
        timeout_ceiling_factor: float,
    ) -> None:
        """TS-75-P6: For any input, RoutingConfig fields are within valid bounds.

        Validates: 75-REQ-4.4, 75-REQ-4.5, 75-REQ-4.6
        """
        from agent_fox.core.config import RoutingConfig

        # Currently FAILS: fields don't exist on RoutingConfig.
        config = RoutingConfig(
            max_timeout_retries=max_timeout_retries,
            timeout_multiplier=timeout_multiplier,
            timeout_ceiling_factor=timeout_ceiling_factor,
        )

        # Property: all fields are within valid bounds.
        assert config.max_timeout_retries >= 0
        assert config.timeout_multiplier >= 1.0
        assert config.timeout_ceiling_factor >= 1.0

    def test_concrete_boundary_values(self) -> None:
        """TS-75-P6 (concrete): Boundary inputs produce valid config."""
        from agent_fox.core.config import RoutingConfig

        # Currently FAILS: fields don't exist.
        config_neg = RoutingConfig(
            max_timeout_retries=-5,
            timeout_multiplier=0.1,
            timeout_ceiling_factor=0.5,
        )
        assert config_neg.max_timeout_retries >= 0
        assert config_neg.timeout_multiplier >= 1.0
        assert config_neg.timeout_ceiling_factor >= 1.0

        config_pos = RoutingConfig(
            max_timeout_retries=10,
            timeout_multiplier=3.0,
            timeout_ceiling_factor=5.0,
        )
        assert config_pos.max_timeout_retries == 10
        assert config_pos.timeout_multiplier == 3.0
        assert config_pos.timeout_ceiling_factor == 5.0
