"""Serial runner: sequential session execution with inter-session delay.

Requirements: 04-REQ-1.2, 04-REQ-9.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agent_fox.engine.state import SessionRecord


class SerialRunner:
    """Runs tasks one at a time with inter-session delay.

    The serial runner dispatches sessions sequentially, applying a
    configurable delay between sessions to avoid API rate limiting.
    """

    def __init__(
        self,
        session_runner_factory: Callable[..., Any],
        inter_session_delay: float,
    ) -> None:
        """Initialise the serial runner.

        Args:
            session_runner_factory: Factory that creates a session runner
                for a given node_id. The returned runner is a callable with
                signature (node_id, attempt, previous_error) -> SessionRecord.
            inter_session_delay: Seconds to wait between sessions.
        """
        self._session_runner_factory = session_runner_factory
        self._inter_session_delay = inter_session_delay

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
    ) -> SessionRecord:
        """Execute a single session and return the outcome record.

        Creates a session runner via the factory, invokes it with the
        given arguments, and returns the resulting SessionRecord.

        Args:
            node_id: The task graph node to execute.
            attempt: The attempt number (1-indexed).
            previous_error: Error message from prior attempt, if any.

        Returns:
            A SessionRecord with outcome, cost, and timing.
        """
        runner = self._session_runner_factory(node_id)

        # Support both callable runners and runners with execute() method
        if hasattr(runner, "execute") and callable(runner.execute):
            result = await runner.execute(node_id, attempt, previous_error)
        else:
            result = await runner(node_id, attempt, previous_error)

        # If the result is already a SessionRecord, return it directly
        if isinstance(result, SessionRecord):
            return result

        # Otherwise, convert from MockSessionOutcome or similar
        return SessionRecord(
            node_id=result.node_id,
            attempt=attempt,
            status=result.status,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost,
            duration_ms=result.duration_ms,
            error_message=result.error_message,
            timestamp=result.timestamp if hasattr(result, "timestamp") else "",
        )

    async def delay(self) -> None:
        """Wait for the configured inter-session delay.

        Skips waiting if the delay is zero.
        """
        if self._inter_session_delay > 0:
            await asyncio.sleep(self._inter_session_delay)
