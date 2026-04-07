"""DaemonRunner, SharedBudget, DaemonState, and merge strategy helpers.

Provides the core daemon infrastructure: lifecycle management, cost
budget tracking, and merge strategy resolution.

Requirements: 85-REQ-1.2, 85-REQ-2.1, 85-REQ-2.2, 85-REQ-2.3,
              85-REQ-2.4, 85-REQ-2.5, 85-REQ-5.1, 85-REQ-5.2,
              85-REQ-5.E1, 85-REQ-8.E1, 85-REQ-8.E2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.nightshift.stream import WorkStream
    from agent_fox.platform.protocol import PlatformProtocol

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

    Requirements: 85-REQ-1.2, 85-REQ-1.3, 85-REQ-2.1, 85-REQ-2.2,
                  85-REQ-2.3, 85-REQ-2.4, 85-REQ-2.5, 85-REQ-4.1,
                  85-REQ-4.2, 85-REQ-4.3, 85-REQ-9.2
    """

    def __init__(
        self,
        config: object,
        platform: PlatformProtocol | None,
        streams: list[WorkStream],
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

        # Log unknown stream names in enabled_streams config (85-REQ-9.2).
        known_stream_names = {
            "specs": "spec-executor",
            "fixes": "fix-pipeline",
            "hunts": "hunt-scan",
            "spec_gen": "spec-generator",
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

    async def run(self) -> DaemonState:
        """Run the daemon lifecycle.

        Placeholder — full implementation in task group 3.

        Requirements: 85-REQ-2.1, 85-REQ-2.4, 85-REQ-2.5
        """
        import time

        from agent_fox.nightshift.pid import remove_pid_file, write_pid_file

        start = time.monotonic()
        state = DaemonState()

        # Write PID file
        if self._pid_path:
            write_pid_file(self._pid_path)

        try:
            # Call shutdown on all streams
            for stream in self._streams:
                await stream.shutdown()
        finally:
            # Remove PID file
            if self._pid_path:
                remove_pid_file(self._pid_path)

        state.uptime_seconds = time.monotonic() - start
        state.total_cost = self._budget.total_cost
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
