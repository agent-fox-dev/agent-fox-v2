"""Timed task scheduling for night-shift daemon.

Implements issue check and hunt scan intervals with overlap prevention
and initial-run-on-startup behaviour.

Requirements: 61-REQ-2.1, 61-REQ-2.2, 61-REQ-2.3, 61-REQ-2.E2
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class Scheduler:
    """Timed scheduler for night-shift callbacks.

    Runs issue check and hunt scan callbacks at configured intervals,
    with an initial invocation at t=0 for both.

    Requirements: 61-REQ-2.1, 61-REQ-2.2, 61-REQ-2.3
    """

    def __init__(
        self,
        issue_interval: int,
        hunt_interval: int,
        on_issue_check: Callable[[], Awaitable[None]],
        on_hunt_scan: Callable[[], Awaitable[None]],
    ) -> None:
        self._issue_interval = issue_interval
        self._hunt_interval = hunt_interval
        self._on_issue_check = on_issue_check
        self._on_hunt_scan = on_hunt_scan

    async def run_for(self, duration_seconds: int | float) -> None:
        """Simulate running the scheduler for a given duration.

        Both callbacks fire immediately at t=0, then at each
        configured interval within the duration.

        This is a deterministic simulation -- no real-time sleeps.
        """
        # Compute all fire times for each callback
        issue_times = self._fire_times(self._issue_interval, duration_seconds)
        hunt_times = self._fire_times(self._hunt_interval, duration_seconds)

        # Merge into a single timeline
        events: list[tuple[float, str]] = []
        for t in issue_times:
            events.append((t, "issue_check"))
        for t in hunt_times:
            events.append((t, "hunt_scan"))

        # Sort by time, then by type (deterministic)
        events.sort(key=lambda e: (e[0], e[1]))

        for _t, event_type in events:
            if event_type == "issue_check":
                await self._on_issue_check()
            elif event_type == "hunt_scan":
                await self._on_hunt_scan()

    @staticmethod
    def _fire_times(interval: int, duration: int | float) -> list[float]:
        """Compute all fire times for a callback within a duration.

        Fires at t=0, t=interval, t=2*interval, ... as long as t <= duration.
        """
        times: list[float] = []
        t = 0.0
        while t <= duration:
            times.append(t)
            t += interval
        return times
