"""Parallel runner: concurrent session execution via asyncio.

Stub module -- implementation in task group 4.
Requirements: 04-REQ-6.1, 04-REQ-6.2, 04-REQ-6.3
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_fox.engine.state import SessionRecord


class ParallelRunner:
    """Runs up to N tasks concurrently via asyncio."""

    def __init__(
        self,
        session_runner_factory: Any,
        max_parallelism: int,
        inter_session_delay: float,
    ) -> None:
        raise NotImplementedError

    async def execute_batch(
        self,
        tasks: list[tuple[str, int, str | None]],
        on_complete: Callable[[SessionRecord], Awaitable[None]],
    ) -> list[SessionRecord]:
        raise NotImplementedError

    async def cancel_all(self) -> None:
        raise NotImplementedError
