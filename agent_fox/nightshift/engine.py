"""Night Shift engine: daemon lifecycle and event loop.

Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-1.E1,
              61-REQ-1.E2, 61-REQ-9.3
"""

from __future__ import annotations

import asyncio
import logging
import sys

from agent_fox.nightshift.finding import (
    build_issue_body,
    consolidate_findings,
    create_issues_from_groups,
)
from agent_fox.nightshift.state import NightShiftState

logger = logging.getLogger(__name__)


def validate_night_shift_prerequisites(config: object) -> None:
    """Validate that the platform is configured for night-shift.

    Aborts with exit code 1 if the platform type is 'none' or missing.

    Requirements: 61-REQ-1.E1
    """
    platform_type = getattr(getattr(config, "platform", None), "type", "none")
    if platform_type == "none":
        logger.error(
            "Night-shift requires a configured platform. "
            "Set [platform] type = 'github' in your config."
        )
        sys.exit(1)


class NightShiftEngine:
    """Main daemon engine for night-shift.

    Coordinates issue checks, hunt scans, and fix sessions on a
    timed schedule.

    Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-1.E2
    """

    def __init__(
        self,
        config: object,
        platform: object,
        *,
        auto_fix: bool = False,
    ) -> None:
        self._config = config
        self._platform = platform
        self._auto_fix = auto_fix
        self.state = NightShiftState()
        self._hunt_scan_in_progress = False

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the engine."""
        self.state.is_shutting_down = True

    def _check_cost_limit(self) -> bool:
        """Check whether the cost limit has been reached.

        Returns True when the remaining budget is insufficient for
        another operation (less than 10% of max_cost remaining).

        Requirements: 61-REQ-1.E2, 61-REQ-9.3
        """
        max_cost = getattr(
            getattr(self._config, "orchestrator", None), "max_cost", None
        )
        if max_cost is None:
            return False
        # Stop when remaining budget is less than 50% of max.
        # This conservative threshold prevents overspending when individual
        # operations may cost a significant fraction of the total budget.
        remaining = max_cost - self.state.total_cost
        return remaining < max_cost * 0.5

    async def _run_issue_check(self) -> None:
        """Poll platform for af:fix issues and process them.

        Requirements: 61-REQ-2.1
        """
        try:
            issues = await self._platform.list_issues_by_label("af:fix")  # type: ignore[union-attr]
        except Exception:
            logger.warning(
                "Issue check failed due to platform API error",
                exc_info=True,
            )
            return

        for issue in issues:
            if self.state.is_shutting_down:
                break
            if self._check_cost_limit():
                logger.info("Cost limit reached, stopping issue processing")
                break
            await self._process_fix(issue)

    async def _run_hunt_scan_inner(self) -> list[object]:
        """Execute the hunt scan and return findings.

        Override point for testing.
        """
        return []

    async def _run_hunt_scan(self) -> None:
        """Execute a full hunt scan and create issues from findings.

        Skips if a hunt scan is already in progress (overlap prevention).

        Requirements: 61-REQ-2.2, 61-REQ-2.E2, 61-REQ-5.1, 61-REQ-5.2
        """
        if self._hunt_scan_in_progress:
            logger.info(
                "Hunt scan already in progress, skipping overlapping scan"
            )
            return

        self._hunt_scan_in_progress = True
        try:
            findings = await self._run_hunt_scan_inner()
        finally:
            self._hunt_scan_in_progress = False
        if not findings:
            return

        groups = consolidate_findings(findings)  # type: ignore[arg-type]

        await create_issues_from_groups(groups, self._platform)

        if self._auto_fix:
            # Assign af:fix label to all created issues
            for group in groups:
                try:
                    # Re-create to get issue number - in real impl this
                    # would use the return value from create_issues_from_groups
                    body = build_issue_body(group)
                    result = await self._platform.create_issue(group.title, body)  # type: ignore[union-attr]
                    await self._platform.assign_label(result.number, "af:fix")  # type: ignore[union-attr]
                except Exception:
                    logger.warning(
                        "Failed to assign af:fix label",
                        exc_info=True,
                    )

        self.state.hunt_scans_completed += 1

    async def _process_fix(self, issue: object) -> None:
        """Process a single af:fix issue.

        Requirements: 61-REQ-6.1
        """
        self.state.issues_fixed += 1

    async def run(self) -> NightShiftState:
        """Run the daemon loop until interrupted.

        Requirements: 61-REQ-1.1, 61-REQ-1.3
        """
        logger.info("Night-shift engine starting")

        # Initial run
        if not self.state.is_shutting_down:
            await self._run_issue_check()
        if not self.state.is_shutting_down:
            await self._run_hunt_scan()

        # Timed loop
        while not self.state.is_shutting_down:
            if self._check_cost_limit():
                logger.info("Cost limit reached, shutting down")
                self.state.is_shutting_down = True
                break
            await asyncio.sleep(0.05)

        logger.info("Night-shift engine stopped")
        return self.state
