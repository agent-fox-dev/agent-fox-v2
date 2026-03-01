"""Timeout enforcer: wrap async coroutines with asyncio.wait_for().

Requirements: 03-REQ-6.1, 03-REQ-6.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine


async def with_timeout[T](
    coro: Coroutine[None, None, T],
    timeout_minutes: int,
) -> T:
    """Run a coroutine with a timeout.

    Wraps the coroutine in asyncio.wait_for() with the timeout
    converted from minutes to seconds.

    Raises:
        asyncio.TimeoutError: If the coroutine exceeds the timeout.
    """
    return await asyncio.wait_for(coro, timeout=timeout_minutes * 60)
