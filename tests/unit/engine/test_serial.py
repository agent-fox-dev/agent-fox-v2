"""Serial runner tests: inter-session delay behavior.

Test Spec: TS-04-16 (inter-session delay), TS-04-E7 (zero delay)
Requirements: 04-REQ-9.1, 04-REQ-9.E1
"""

from __future__ import annotations

import asyncio
import time

import pytest

from agent_fox.engine.serial import SerialRunner
from agent_fox.engine.state import SessionRecord

# -- Mock session runner for serial tests ------------------------------------


class MockSerialSessionRunner:
    """Simple mock that records timestamps and returns success."""

    def __init__(self) -> None:
        self.dispatch_times: dict[str, float] = {}
        self.complete_times: dict[str, float] = {}

    async def __call__(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None = None,
    ) -> SessionRecord:
        self.dispatch_times[node_id] = time.monotonic()
        # Simulate minimal work
        await asyncio.sleep(0.01)
        self.complete_times[node_id] = time.monotonic()
        return SessionRecord(
            node_id=node_id,
            attempt=attempt,
            status="completed",
            input_tokens=100,
            output_tokens=200,
            cost=0.10,
            duration_ms=100,
            error_message=None,
            timestamp="2026-03-01T10:00:00Z",
        )


# -- Tests -------------------------------------------------------------------


class TestInterSessionDelay:
    """TS-04-16: Inter-session delay is applied.

    Verify the serial runner waits the configured delay between sessions.
    """

    @pytest.mark.asyncio
    async def test_delay_applied_between_sessions(self) -> None:
        """Wall-clock gap between sessions >= configured delay."""
        mock = MockSerialSessionRunner()
        runner = SerialRunner(
            session_runner_factory=lambda node_id: mock,
            inter_session_delay=0.5,  # 500ms delay
        )

        # Execute two sessions
        await runner.execute("A", attempt=1, previous_error=None)
        await runner.delay()
        await runner.execute("B", attempt=1, previous_error=None)

        gap = mock.dispatch_times["B"] - mock.complete_times["A"]
        assert gap >= 0.4  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_delay_method_waits(self) -> None:
        """The delay() method actually pauses execution."""
        runner = SerialRunner(
            session_runner_factory=lambda node_id: MockSerialSessionRunner(),
            inter_session_delay=0.3,
        )

        start = time.monotonic()
        await runner.delay()
        elapsed = time.monotonic() - start

        assert elapsed >= 0.25  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_execute_returns_session_record(self) -> None:
        """execute() returns a SessionRecord with correct node_id."""
        mock = MockSerialSessionRunner()
        runner = SerialRunner(
            session_runner_factory=lambda node_id: mock,
            inter_session_delay=0,
        )

        record = await runner.execute("A", attempt=1, previous_error=None)

        assert isinstance(record, SessionRecord)
        assert record.node_id == "A"
        assert record.status == "completed"


class TestZeroDelay:
    """TS-04-E7: Inter-session delay of zero.

    Verify no delay when inter_session_delay is 0.
    """

    @pytest.mark.asyncio
    async def test_no_delay_between_sessions(self) -> None:
        """Sessions dispatched back-to-back with negligible gap."""
        mock = MockSerialSessionRunner()
        runner = SerialRunner(
            session_runner_factory=lambda node_id: mock,
            inter_session_delay=0,
        )

        await runner.execute("A", attempt=1, previous_error=None)
        await runner.delay()
        await runner.execute("B", attempt=1, previous_error=None)

        gap = mock.dispatch_times["B"] - mock.complete_times["A"]
        assert gap < 0.1  # Less than 100ms

    @pytest.mark.asyncio
    async def test_zero_delay_returns_immediately(self) -> None:
        """delay() with inter_session_delay=0 returns nearly instantly."""
        runner = SerialRunner(
            session_runner_factory=lambda node_id: MockSerialSessionRunner(),
            inter_session_delay=0,
        )

        start = time.monotonic()
        await runner.delay()
        elapsed = time.monotonic() - start

        assert elapsed < 0.05  # Less than 50ms
