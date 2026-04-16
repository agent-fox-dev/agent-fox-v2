"""Property-based tests for watch mode invariants.

Test Spec: TS-70-P1 through TS-70-P4
Properties: 1-4 from design.md
Requirements: 70-REQ-3.2, 70-REQ-3.E1, 70-REQ-5.2, 70-REQ-1.2, 70-REQ-4.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import OrchestratorConfig
from agent_fox.knowledge.audit import AuditEvent, AuditEventType
from agent_fox.knowledge.sink import SinkDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CapturingSink:
    """Simple event capture for property tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record_session_outcome(self, outcome: Any) -> None:
        pass

    def record_tool_call(self, call: Any) -> None:
        pass

    def record_tool_error(self, error: Any) -> None:
        pass

    def emit_audit_event(self, event: AuditEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


def _watch_poll_events(sink: _CapturingSink) -> list[AuditEvent]:
    """Return only WATCH_POLL events from captured events."""
    return [e for e in sink.events if e.event_type == AuditEventType.WATCH_POLL]


def _write_empty_plan_db():
    """Write an empty plan to DB and return the connection."""
    from tests.unit.engine.conftest import write_plan_to_db

    return write_plan_to_db(nodes={}, edges=[])


def _write_stalled_plan_db():
    """Write a plan with a blocked node to DB and return the connection."""
    from tests.unit.engine.conftest import write_plan_to_db

    return write_plan_to_db(
        nodes={"spec:1": {"title": "Task 1", "status": "blocked"}},
        edges=[],
    )


# ---------------------------------------------------------------------------
# TS-70-P1: Watch Interval Clamping
# Property 2: For any watch_interval V, effective interval is max(V, 10)
# Requirements: 70-REQ-3.2, 70-REQ-3.E1
# ---------------------------------------------------------------------------


class TestWatchIntervalClamping:
    """TS-70-P1: watch_interval is always >= 10 after config validation."""

    @given(watch_interval=st.integers(min_value=-100, max_value=9))
    @settings(max_examples=50)
    def test_values_below_10_are_clamped_to_10(self, watch_interval: int) -> None:
        """For any watch_interval < 10, effective value is 10."""
        config = OrchestratorConfig(watch_interval=watch_interval)
        assert config.watch_interval == 10  # noqa: PLR2004

    @given(watch_interval=st.integers(min_value=10, max_value=1000))
    @settings(max_examples=50)
    def test_values_at_or_above_10_are_unchanged(self, watch_interval: int) -> None:
        """For any watch_interval >= 10, effective value equals input."""
        config = OrchestratorConfig(watch_interval=watch_interval)
        assert config.watch_interval == watch_interval

    @given(watch_interval=st.integers(min_value=-100, max_value=1000))
    @settings(max_examples=100)
    def test_watch_interval_always_at_least_10(self, watch_interval: int) -> None:
        """For any watch_interval, the configured value is always >= 10."""
        config = OrchestratorConfig(watch_interval=watch_interval)
        assert config.watch_interval >= 10  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TS-70-P2: Poll Number Monotonicity
# Property 4: poll_numbers in WATCH_POLL events are [1, 2, ..., N]
# Requirements: 70-REQ-5.2
# ---------------------------------------------------------------------------


class TestPollNumberMonotonicity:
    """TS-70-P2: poll_number values in WATCH_POLL events are strictly increasing."""

    @given(n=st.integers(min_value=1, max_value=10))
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_poll_numbers_are_monotonically_increasing(self, n: int, tmp_path: Path) -> None:
        """For N poll cycles, poll_numbers are [1, 2, ..., N]."""
        import asyncio

        from agent_fox.engine.engine import Orchestrator

        db_conn = _write_empty_plan_db()

        sink = _CapturingSink()
        sink_dispatcher = SinkDispatcher()
        sink_dispatcher.add(sink)  # type: ignore[arg-type]

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            watch_interval=10,
        )

        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: MagicMock(),
            sink_dispatcher=sink_dispatcher,
            knowledge_db_conn=db_conn,
        )
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_try_end_of_run_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= n:
                orch._signal.interrupted = True
            return False

        _method = "_try_end_of_run_discovery"

        async def run() -> None:
            with patch.object(orch, _method, side_effect=fake_try_end_of_run_discovery):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await orch.run()

        asyncio.run(run())

        events = _watch_poll_events(sink)
        assert len(events) == n, f"Expected {n} WATCH_POLL events, got {len(events)}"
        poll_numbers = [e.payload["poll_number"] for e in events]
        assert poll_numbers == list(range(1, n + 1)), f"poll_numbers should be [1..{n}], got {poll_numbers}"


# ---------------------------------------------------------------------------
# TS-70-P3: Hot-Load Gate
# Property 3: When hot_load=False, watch loop never activates
# Requirements: 70-REQ-1.2
# ---------------------------------------------------------------------------


class TestHotLoadGate:
    """TS-70-P3: hot_load=False prevents watch loop from activating."""

    @given(watch_interval=st.integers(min_value=10, max_value=300))
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_hot_load_false_always_terminates_completed(self, watch_interval: int, tmp_path: Path) -> None:
        """For any watch_interval, hot_load=False produces COMPLETED, no WATCH_POLL."""
        import asyncio

        from agent_fox.engine.engine import Orchestrator

        db_conn = _write_empty_plan_db()

        sink = _CapturingSink()
        sink_dispatcher = SinkDispatcher()
        sink_dispatcher.add(sink)  # type: ignore[arg-type]

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=False,
            watch_interval=watch_interval,
        )

        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: MagicMock(),
            sink_dispatcher=sink_dispatcher,
            knowledge_db_conn=db_conn,
        )
        orch._watch = True  # type: ignore[attr-defined]

        async def run() -> Any:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                return await orch.run()

        state = asyncio.run(run())

        assert state.run_status == "completed"
        events = _watch_poll_events(sink)
        assert len(events) == 0, f"No WATCH_POLL events expected with hot_load=False, got {len(events)}"


# ---------------------------------------------------------------------------
# TS-70-P4: Stall Overrides Watch
# Property 6: Stalled runs always return STALLED, never enter watch loop
# Requirements: 70-REQ-4.1
# ---------------------------------------------------------------------------


class TestStallOverridesWatch:
    """TS-70-P4: Stalled graph terminates STALLED regardless of watch mode."""

    @given(watch=st.booleans())
    @settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_stall_always_terminates_stalled(self, watch: bool, tmp_path: Path) -> None:
        """For any watch setting, stalled graph returns STALLED."""
        import asyncio

        from agent_fox.engine.engine import Orchestrator

        db_conn = _write_stalled_plan_db()

        sink = _CapturingSink()
        sink_dispatcher = SinkDispatcher()
        sink_dispatcher.add(sink)  # type: ignore[arg-type]

        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
        )

        orch = Orchestrator(
            config=config,
            session_runner_factory=lambda nid, **kw: MagicMock(),
            sink_dispatcher=sink_dispatcher,
            knowledge_db_conn=db_conn,
        )
        if watch:
            orch._watch = True  # type: ignore[attr-defined]

        async def run() -> Any:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                return await orch.run()

        state = asyncio.run(run())

        assert state.run_status == "stalled"
        if watch:
            events = _watch_poll_events(sink)
            assert len(events) == 0, "No WATCH_POLL events for stalled run"
