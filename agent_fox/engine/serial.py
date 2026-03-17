"""Serial task runner: executes tasks one at a time with inter-session delay."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agent_fox.engine.state import SessionRecord, invoke_runner


class SerialRunner:
    """Runs tasks one at a time with inter-session delay."""

    def __init__(
        self,
        session_runner_factory: Callable[..., Any],
        inter_session_delay: float,
    ) -> None:
        self._session_runner_factory = session_runner_factory
        self._inter_session_delay = inter_session_delay

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
        *,
        archetype: str = "coder",
        instances: int = 1,
        assessed_tier: Any | None = None,
        run_id: str = "",
    ) -> SessionRecord:
        """Execute a single session and return the outcome record."""
        runner = self._session_runner_factory(
            node_id,
            archetype=archetype,
            instances=instances,
            assessed_tier=assessed_tier,
            run_id=run_id,
        )
        return await invoke_runner(runner, node_id, attempt, previous_error)

    async def delay(self) -> None:
        """Wait for the configured inter-session delay."""
        if self._inter_session_delay > 0:
            await asyncio.sleep(self._inter_session_delay)
