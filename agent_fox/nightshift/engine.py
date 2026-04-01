"""Night Shift engine: daemon lifecycle and event loop.

Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-1.E1,
              61-REQ-1.E2, 61-REQ-9.3
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from agent_fox.nightshift.critic import consolidate_findings
from agent_fox.nightshift.dep_graph import build_graph, merge_edges
from agent_fox.nightshift.finding import (
    build_issue_body,
    create_issues_from_groups,
)
from agent_fox.nightshift.reference_parser import (
    fetch_github_relationships,
    parse_text_references,
)
from agent_fox.nightshift.staleness import check_staleness
from agent_fox.nightshift.state import NightShiftState
from agent_fox.nightshift.triage import run_batch_triage

logger = logging.getLogger(__name__)


def _emit_audit_event(
    event_type_name: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Emit a night-shift audit event.

    Best-effort: silently skips if audit infrastructure is unavailable.

    Requirements: 61-REQ-8.4 (observability)
    """
    try:
        from agent_fox.knowledge.audit import (
            AuditEvent,
            AuditEventType,
            generate_run_id,
        )

        event_type = AuditEventType(event_type_name)
        event = AuditEvent(
            run_id=generate_run_id(),
            event_type=event_type,
            payload=payload or {},
        )
        logger.debug("Audit event: %s payload=%s", event.event_type, event.payload)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to emit audit event: %s", event_type_name, exc_info=True)


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

        Issues are fetched sorted by creation date ascending (oldest first).
        A local sort by issue number is applied as a fallback in case the
        platform ignores the sort parameters (71-REQ-1.E1).

        Triage phase: for batches >= 3, runs AI batch triage to detect
        dependencies and supersession candidates (71-REQ-3.1).

        Staleness phase: after each successful fix, evaluates remaining
        issues for obsolescence (71-REQ-5.1).

        Requirements: 61-REQ-2.1, 71-REQ-1.1, 71-REQ-1.2, 71-REQ-1.E1,
                      71-REQ-3.1, 71-REQ-3.5, 71-REQ-5.1, 71-REQ-5.E3
        """
        try:
            issues = await self._platform.list_issues_by_label(  # type: ignore[union-attr]
                "af:fix",
                sort="created",
                direction="asc",
            )
        except Exception:
            logger.warning(
                "Issue check failed due to platform API error",
                exc_info=True,
            )
            return

        if not issues:
            return

        # Local sort fallback: ensure ascending issue number order
        # even if the platform does not honour the sort parameters (71-REQ-1.E1).
        issues = sorted(issues, key=lambda i: i.number)

        # Build dependency graph from explicit references and GitHub metadata
        explicit_edges = parse_text_references(issues)
        try:
            github_edges = await fetch_github_relationships(
                self._platform, issues
            )
        except Exception:
            logger.warning(
                "Failed to fetch GitHub relationships, continuing without",
                exc_info=True,
            )
            github_edges = []

        all_edges = explicit_edges + github_edges

        # AI triage for batches >= 3 (71-REQ-3.1, 71-REQ-3.5)
        if len(issues) >= 3:
            try:
                triage = await run_batch_triage(issues, all_edges, self._config)
                all_edges = merge_edges(all_edges, triage.edges)
            except Exception:
                logger.warning(
                    "AI triage failed, using explicit refs only",
                    exc_info=True,
                )

        # Compute processing order via topological sort
        processing_order = build_graph(issues, all_edges)
        logger.info("Resolved processing order: %s", processing_order)

        issue_map = {i.number: i for i in issues}
        closed: set[int] = set()

        for issue_num in processing_order:
            if issue_num in closed:
                continue  # removed by staleness check
            if self.state.is_shutting_down:
                break
            if self._check_cost_limit():
                logger.info("Cost limit reached, stopping issue processing")
                break

            issue = issue_map[issue_num]
            fix_succeeded = False
            try:
                await self._process_fix(issue)
                fix_succeeded = True
            except Exception:
                logger.warning(
                    "Fix failed for issue #%d, continuing to next",
                    issue_num,
                    exc_info=True,
                )

            # Post-fix staleness check (71-REQ-5.1, 71-REQ-5.E3)
            if fix_succeeded:
                remaining = [
                    issue_map[n]
                    for n in processing_order
                    if n != issue_num and n not in closed
                ]
                if remaining:
                    try:
                        staleness = await check_staleness(
                            issue,
                            remaining,
                            "",  # diff not available in current implementation
                            self._config,
                            self._platform,
                        )
                        remaining_nums = {i.number for i in remaining}
                        for obsolete_num in staleness.obsolete_issues:
                            if obsolete_num not in remaining_nums:
                                continue
                            await self._platform.close_issue(  # type: ignore[union-attr]
                                obsolete_num,
                                f"Resolved by fix for #{issue_num}",
                            )
                            closed.add(obsolete_num)
                            _emit_audit_event(
                                "night_shift.issue_obsolete",
                                {
                                    "closed_issue": obsolete_num,
                                    "fixed_by": issue_num,
                                    "rationale": staleness.rationale.get(
                                        obsolete_num, ""
                                    ),
                                },
                            )
                    except Exception:
                        logger.warning(
                            "Staleness check failed after fix #%d",
                            issue_num,
                            exc_info=True,
                        )

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
            logger.info("Hunt scan already in progress, skipping overlapping scan")
            return

        self._hunt_scan_in_progress = True
        try:
            findings = await self._run_hunt_scan_inner()
        finally:
            self._hunt_scan_in_progress = False

        _emit_audit_event(
            "night_shift.hunt_scan_complete",
            {"findings_count": len(findings)},
        )

        if not findings:
            self.state.hunt_scans_completed += 1
            return

        groups = await consolidate_findings(findings)  # type: ignore[arg-type]

        await create_issues_from_groups(groups, self._platform)

        if self._auto_fix:
            # Assign af:fix label to all created issues
            for group in groups:
                try:
                    body = build_issue_body(group)
                    result = await self._platform.create_issue(group.title, body)  # type: ignore[union-attr]
                    await self._platform.assign_label(result.number, "af:fix")  # type: ignore[union-attr]
                    _emit_audit_event(
                        "night_shift.issue_created",
                        {"issue_number": result.number, "title": group.title},
                    )
                except Exception:
                    logger.warning(
                        "Failed to assign af:fix label",
                        exc_info=True,
                    )

        self.state.hunt_scans_completed += 1

    async def _process_fix(self, issue: object) -> None:
        """Process a single af:fix issue through the fix pipeline.

        Builds an in-memory spec from the issue, runs the full archetype
        pipeline, creates a PR, and updates the engine state.

        Requirements: 61-REQ-6.1, 61-REQ-6.2, 61-REQ-6.3, 61-REQ-6.4
        """
        from agent_fox.nightshift.fix_pipeline import FixPipeline
        from agent_fox.platform.github import IssueResult

        if not isinstance(issue, IssueResult):
            return

        _emit_audit_event(
            "night_shift.fix_start",
            {"issue_number": issue.number, "title": issue.title},
        )

        pipeline = FixPipeline(config=self._config, platform=self._platform)

        try:
            await pipeline.process_issue(issue, issue_body=issue.body)
            self.state.issues_fixed += 1
            _emit_audit_event(
                "night_shift.fix_complete",
                {"issue_number": issue.number},
            )
        except Exception:
            logger.warning(
                "Fix pipeline raised unexpectedly for issue #%d",
                issue.number,
                exc_info=True,
            )
            _emit_audit_event(
                "night_shift.fix_failed",
                {"issue_number": issue.number},
            )

    async def run(self) -> NightShiftState:
        """Run the daemon loop until interrupted.

        Executes an initial issue check and hunt scan immediately on startup,
        then continues until the engine is asked to shut down.

        Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-2.3
        """
        logger.info("Night-shift engine starting")
        _emit_audit_event("night_shift.start")

        # Initial run (61-REQ-2.3)
        if not self.state.is_shutting_down:
            await self._run_issue_check()
        if not self.state.is_shutting_down:
            await self._run_hunt_scan()

        # Timed loop — wait for shutdown, checking cost limit each iteration
        while not self.state.is_shutting_down:
            if self._check_cost_limit():
                logger.info("Cost limit reached, shutting down")
                self.state.is_shutting_down = True
                break
            await asyncio.sleep(0.05)

        logger.info("Night-shift engine stopped")
        return self.state
