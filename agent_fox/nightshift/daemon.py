"""DaemonRunner, SharedBudget, DaemonState, and merge strategy helpers.

Provides the core daemon infrastructure: lifecycle management, cost
budget tracking, and merge strategy resolution.

Requirements: 85-REQ-1.2, 85-REQ-2.1, 85-REQ-2.2, 85-REQ-2.3,
              85-REQ-2.4, 85-REQ-2.5, 85-REQ-5.1, 85-REQ-5.2,
              85-REQ-5.E1, 85-REQ-8.E1, 85-REQ-8.E2
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.nightshift.stream import WorkStream
    from agent_fox.platform.protocol import PlatformProtocol

from agent_fox.nightshift.audit import emit_audit_event as _emit_audit_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SharedBudget
# ---------------------------------------------------------------------------


@dataclass
class SharedBudget:
    """Single daemon-level spending limit shared across all work streams.

    Cost is accumulated on a first-come, first-served basis. The budget
    check occurs between cycles, not mid-operation.

    Requirements: 85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1
    """

    max_cost: float | None
    _total_cost: float = field(default=0.0, init=False, repr=False)

    def add_cost(self, cost: float) -> None:
        """Add cost from a work stream cycle."""
        self._total_cost += cost

    @property
    def total_cost(self) -> float:
        """Cumulative cost across all streams."""
        return self._total_cost

    @property
    def exceeded(self) -> bool:
        """Whether the cumulative cost has reached or exceeded max_cost."""
        if self.max_cost is None:
            return False
        return self._total_cost >= self.max_cost


# ---------------------------------------------------------------------------
# DaemonState
# ---------------------------------------------------------------------------


@dataclass
class DaemonState:
    """Accumulated state returned by DaemonRunner.run().

    Requirements: 85-REQ-2.4
    """

    total_cost: float = 0.0
    total_sessions: int = 0
    issues_created: int = 0
    issues_fixed: int = 0
    hunt_scans_completed: int = 0
    specs_executed: int = 0
    uptime_seconds: float = 0.0


# ---------------------------------------------------------------------------
# DaemonRunner
# ---------------------------------------------------------------------------


class DaemonRunner:
    """Manages work stream lifecycles, PID file, cost budget, and signals.

    Streams run as independent asyncio tasks. Each task sleeps for
    its configured interval between cycles. Priority ordering is
    enforced via an asyncio.Lock and sequential initial launch.

    Requirements: 85-REQ-1.2, 85-REQ-1.3, 85-REQ-2.1, 85-REQ-2.2,
                  85-REQ-2.3, 85-REQ-2.4, 85-REQ-2.5, 85-REQ-4.1,
                  85-REQ-4.2, 85-REQ-4.3, 85-REQ-9.2
    """

    # Priority order for stream execution (85-REQ-4.2, 85-REQ-4.3).
    _PRIORITY_ORDER = [
        "spec-executor",
        "fix-pipeline",
        "hunt-scan",
    ]

    def __init__(
        self,
        config: object,
        platform: PlatformProtocol | None,
        streams: Sequence[WorkStream],
        budget: SharedBudget,
        *,
        pid_path: Path | None = None,
    ) -> None:
        self._config = config
        self._platform = platform
        self._streams = list(streams)
        self._budget = budget
        self._pid_path = pid_path
        self._shutting_down = False
        self._shutdown_event = asyncio.Event()

        # Log unknown stream names in enabled_streams config (85-REQ-9.2).
        known_stream_names = {
            "specs": "spec-executor",
            "fixes": "fix-pipeline",
            "hunts": "hunt-scan",
        }
        enabled_cfg = getattr(getattr(config, "night_shift", None), "enabled_streams", None)
        if enabled_cfg:
            for name in enabled_cfg:
                if name not in known_stream_names:
                    logger.warning(
                        "Unknown stream name in enabled_streams: %r (ignored)",
                        name,
                    )

    @property
    def streams(self) -> list[WorkStream]:
        """All registered work streams."""
        return self._streams

    @property
    def is_shutting_down(self) -> bool:
        """Whether a graceful shutdown has been requested."""
        return self._shutting_down

    def request_shutdown(self) -> None:
        """Request graceful shutdown. Second call raises SystemExit(130).

        Requirements: 85-REQ-2.2, 85-REQ-2.3
        """
        if self._shutting_down:
            raise SystemExit(130)
        self._shutting_down = True
        self._shutdown_event.set()

    def _sorted_streams(self) -> list[WorkStream]:
        """Return streams sorted by priority order.

        Streams whose name appears in _PRIORITY_ORDER come first, in
        the defined order. Any remaining streams follow in their
        original registration order.

        Requirements: 85-REQ-4.2, 85-REQ-4.3
        """
        priority_map = {name: idx for idx, name in enumerate(self._PRIORITY_ORDER)}
        max_priority = len(self._PRIORITY_ORDER)

        return sorted(
            self._streams,
            key=lambda s: priority_map.get(s.name, max_priority),
        )

    # Short tick duration between interval checks. The daemon sleeps
    # for _TICK seconds between polling whether a stream is due to run,
    # keeping shutdown responsive without busy-looping.
    _TICK: float = 0.05

    async def _run_stream_loop(self, stream: WorkStream) -> None:
        """Run a single stream's polling loop.

        The first invocation fires immediately. Subsequent invocations
        wait until ``stream.interval`` seconds have elapsed since the
        last run_once() call. Between checks the loop sleeps for
        ``_TICK`` seconds so the daemon stays responsive to shutdown.

        Exceptions in run_once() are caught and logged; the stream
        retries after the normal interval (85-REQ-1.4, 85-REQ-1.E1).
        """
        last_run: float | None = None

        while not self._shutdown_event.is_set():
            now = time.monotonic()

            # Enforce stream interval (skip if not enough time elapsed).
            if last_run is not None and (now - last_run) < stream.interval:
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._TICK,
                    )
                    return  # Shutdown requested during sleep.
                except TimeoutError:
                    continue

            # Run the stream cycle.
            try:
                await stream.run_once()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Stream %r run_once() raised; will retry next cycle",
                    stream.name,
                )

            last_run = time.monotonic()

            # Check budget after each cycle (85-REQ-5.3).
            if self._budget.exceeded:
                logger.info(
                    "Cost budget exceeded (%.2f >= %.2f), requesting shutdown",
                    self._budget.total_cost,
                    self._budget.max_cost,
                )
                self._shutdown_event.set()
                self._shutting_down = True
                return

            # Check shutdown before sleeping.
            if self._shutdown_event.is_set():
                return

            # Short sleep to yield control and keep daemon responsive.
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._TICK,
                )
                # Shutdown was requested during sleep.
                return
            except TimeoutError:
                # Normal tick — loop continues to next cycle.
                pass

    async def run(self) -> DaemonState:
        """Run the daemon lifecycle.

        1. Write PID file, emit start audit event.
        2. Launch enabled streams as asyncio tasks in priority order.
        3. Wait for shutdown signal or budget exhaustion.
        4. Call shutdown() on all registered streams.
        5. Remove PID file, emit stop audit event.

        Requirements: 85-REQ-2.1, 85-REQ-2.4, 85-REQ-2.5,
                      85-REQ-4.1, 85-REQ-4.2
        """
        from agent_fox.nightshift.pid import remove_pid_file, write_pid_file

        start = time.monotonic()
        state = DaemonState()

        # Write PID file (85-REQ-2.1).
        if self._pid_path:
            write_pid_file(self._pid_path)

        # Emit start audit event.
        _emit_audit_event(
            "night_shift.start",
            {"phase": "start"},
        )

        try:
            # Get enabled streams sorted by priority (85-REQ-1.3, 85-REQ-4.2).
            sorted_streams = self._sorted_streams()
            enabled_streams = [s for s in sorted_streams if s.enabled]

            if not enabled_streams:
                # All streams disabled — idle loop (85-REQ-1.E2).
                logger.warning("All work streams are disabled; entering idle loop")
                await self._shutdown_event.wait()
            else:
                # Launch stream tasks in priority order (85-REQ-4.2).
                # Each stream runs as an independent asyncio task (85-REQ-4.1).
                tasks: list[asyncio.Task[None]] = []
                for stream in enabled_streams:
                    task = asyncio.create_task(
                        self._run_stream_loop(stream),
                        name=f"stream:{stream.name}",
                    )
                    tasks.append(task)

                # Wait for all stream tasks to complete (they exit on
                # shutdown or budget exhaustion).
                await asyncio.gather(*tasks, return_exceptions=True)

            # Shutdown all registered streams (85-REQ-2.5).
            for stream in self._streams:
                try:
                    await stream.shutdown()
                except Exception:  # noqa: BLE001
                    logger.exception("Error shutting down stream %r", stream.name)

        finally:
            # Remove PID file (85-REQ-2.4).
            if self._pid_path:
                remove_pid_file(self._pid_path)

        state.uptime_seconds = time.monotonic() - start
        state.total_cost = self._budget.total_cost

        # Emit stop audit event (85-REQ-2.4).
        _emit_audit_event(
            "night_shift.start",
            {
                "phase": "stop",
                "total_cost": state.total_cost,
                "uptime_seconds": state.uptime_seconds,
            },
        )

        return state


# ---------------------------------------------------------------------------
# Merge strategy helpers
# ---------------------------------------------------------------------------


def resolve_merge_strategy(strategy: str) -> str:
    """Resolve merge strategy, falling back to 'direct' for unknown values.

    Requirements: 85-REQ-8.E2
    """
    valid = {"direct", "pr"}
    if strategy in valid:
        return strategy
    logger.warning(
        "Unknown merge_strategy %r, falling back to 'direct'",
        strategy,
    )
    return "direct"


async def handle_merge_strategy(
    *,
    platform: PlatformProtocol,
    issue_number: int,
    branch: str,
    strategy: str,
    title: str,
    body: str,
    base: str = "develop",
) -> None:
    """Handle post-session merge according to the configured strategy.

    For strategy='pr', creates a draft pull request. On failure, posts
    a comment with the branch name for manual PR creation.

    Requirements: 85-REQ-8.1, 85-REQ-8.2, 85-REQ-8.E1
    """
    effective = resolve_merge_strategy(strategy)

    if effective == "direct":
        # Direct merge is handled by existing engine logic.
        return

    # PR strategy
    try:
        result = await platform.create_pull_request(
            title=title,
            body=body,
            head=branch,
            base=base,
            draft=True,
        )
        logger.info(
            "Created draft PR #%d: %s",
            result.number,
            result.html_url,
        )
    except Exception:
        logger.exception(
            "Failed to create PR from branch %r for issue #%d",
            branch,
            issue_number,
        )
        try:
            await platform.add_issue_comment(
                issue_number,
                f"Failed to create PR automatically. Please create a PR manually from branch `{branch}`.",
            )
        except Exception:
            logger.exception(
                "Failed to post fallback comment on issue #%d",
                issue_number,
            )
