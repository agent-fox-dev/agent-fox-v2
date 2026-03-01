"""Serial runner: sequential session execution with inter-session delay.

Stub module -- implementation in task group 3.
Requirements: 04-REQ-1.2, 04-REQ-9.1
"""

from __future__ import annotations

from typing import Any

from agent_fox.engine.state import SessionRecord


class SerialRunner:
    """Runs tasks one at a time with inter-session delay."""

    def __init__(
        self,
        session_runner_factory: Any,
        inter_session_delay: float,
    ) -> None:
        raise NotImplementedError

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
    ) -> SessionRecord:
        raise NotImplementedError

    async def delay(self) -> None:
        raise NotImplementedError
