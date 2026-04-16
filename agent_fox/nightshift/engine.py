"""Night Shift engine: business logic for fix pipeline and hunt scans.

Provides the core operations that work streams delegate to.  Lifecycle
management (scheduling, signals, budget) is handled by ``DaemonRunner``.

Requirements: 61-REQ-1.1, 61-REQ-1.E1, 61-REQ-9.3
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.audit_helpers import emit_audit_event as _emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, generate_run_id
from agent_fox.nightshift.critic import consolidate_findings
from agent_fox.nightshift.dedup import filter_known_duplicates
from agent_fox.nightshift.dep_graph import build_graph, merge_edges
from agent_fox.nightshift.finding import (
    create_issues_from_groups,
)
from agent_fox.nightshift.fix_pipeline import FixPipeline
from agent_fox.nightshift.ignore_filter import filter_ignored
from agent_fox.nightshift.ignore_ingest import ingest_ignore_signals
from agent_fox.nightshift.reference_parser import (
    fetch_github_relationships,
    parse_text_references,
)
from agent_fox.nightshift.staleness import check_staleness
from agent_fox.nightshift.state import NightShiftState
from agent_fox.nightshift.triage import run_batch_triage
from agent_fox.platform.labels import LABEL_FIX, LABEL_FIXED
from agent_fox.ui.progress import ActivityCallback, SpinnerCallback, TaskCallback

if TYPE_CHECKING:
    import duckdb

    from agent_fox.knowledge.embeddings import EmbeddingGenerator
    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


def validate_night_shift_prerequisites(config: AgentFoxConfig) -> None:
    """Validate that the platform is configured for night-shift.

    Aborts with exit code 1 if the platform type is 'none' or missing.

    Requirements: 61-REQ-1.E1
    """
    platform_type = getattr(getattr(config, "platform", None), "type", "none")
    if platform_type == "none":
        logger.error("Night-shift requires a configured platform. Set [platform] type = 'github' in your config.")
        sys.exit(1)


class NightShiftEngine:
    """Main daemon engine for night-shift.

    Coordinates issue checks, hunt scans, and fix sessions on a
    timed schedule.

    Requirements: 61-REQ-1.1, 61-REQ-1.3, 61-REQ-1.4, 61-REQ-1.E2
    """

    # Maximum drain iterations to prevent infinite loops if issues are
    # created faster than they are fixed.
    _MAX_DRAIN_ITERATIONS: int = 50

    def __init__(
        self,
        config: AgentFoxConfig,
        platform: object,
        *,
        auto_fix: bool = False,
        activity_callback: ActivityCallback | None = None,
        task_callback: TaskCallback | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        spinner_callback: SpinnerCallback | None = None,
        sink_dispatcher: SinkDispatcher | None = None,
        conn: duckdb.DuckDBPyConnection | None = None,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        self._config = config
        self._platform = platform
        self._auto_fix = auto_fix
        self._activity_callback = activity_callback
        self._task_callback = task_callback
        self._status_callback = status_callback
        self._spinner_callback = spinner_callback
        self._sink = sink_dispatcher
        self._conn = conn
        self._embedder = embedder
        self.state = NightShiftState()
        self._hunt_scan_in_progress = False

    def _check_cost_limit(self) -> bool:
        """Check whether the cost limit has been reached.

        Returns True when the remaining budget is less than 50% of
        max_cost.  This conservative threshold prevents overspending
        when individual operations may cost a significant fraction of
        the total budget.

        Requirements: 61-REQ-1.E2, 61-REQ-9.3
        """
        max_cost = getattr(getattr(self._config, "orchestrator", None), "max_cost", None)
        if max_cost is None:
            return False
        remaining = max_cost - self.state.total_cost
        return remaining < max_cost * 0.5

    def _check_session_limit(self) -> bool:
        """Check whether the session limit has been reached.

        Returns True when total_sessions >= max_sessions.

        Requirements: 61-REQ-9.3
        """
        max_sessions = getattr(getattr(self._config, "orchestrator", None), "max_sessions", None)
        if not isinstance(max_sessions, (int, float)):
            return False
        return self.state.total_sessions >= max_sessions

    def _emit_status(self, text: str, style: str = "bold cyan") -> None:
        """Emit a permanent status line via the status_callback.

        If no callback is set, this is a no-op.

        Requirements: 81-REQ-3.1, 81-REQ-3.2, 81-REQ-3.3, 81-REQ-3.4, 81-REQ-3.5
        """
        if self._status_callback is not None:
            try:
                self._status_callback(text, style)
            except Exception:
                logger.debug("Status callback failed", exc_info=True)

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
        self._emit_status("Checking for af:fix issues\u2026")
        try:
            issues = await self._platform.list_issues_by_label(  # type: ignore[attr-defined]
                LABEL_FIX,
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
            github_edges = await fetch_github_relationships(self._platform, issues)
        except Exception:
            logger.warning(
                "Failed to fetch GitHub relationships, continuing without",
                exc_info=True,
            )
            github_edges = []

        all_edges = explicit_edges + github_edges

        # AI triage for batches >= 3 (71-REQ-3.1, 71-REQ-3.5)
        issue_check_run_id = generate_run_id()
        supersession_pairs: list[tuple[int, int]] = []
        if len(issues) >= 3:
            try:
                triage = await run_batch_triage(
                    issues, all_edges, self._config, sink=self._sink, run_id=issue_check_run_id
                )
                all_edges = merge_edges(all_edges, triage.edges)
                supersession_pairs = triage.supersession_pairs
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

        # Close AI-identified superseded issues before processing (71-REQ-3.5)
        for _keep, obsolete in supersession_pairs:
            if obsolete not in issue_map or obsolete in closed:
                continue
            try:
                await self._platform.close_issue(  # type: ignore[attr-defined]
                    obsolete,
                    f"Superseded by #{_keep} (AI triage).",
                )
                closed.add(obsolete)
                _emit_audit_event(
                    self._sink,
                    issue_check_run_id,
                    AuditEventType.ISSUE_SUPERSEDED,
                    payload={"closed_issue": obsolete, "superseded_by": _keep},
                )
                try:
                    await self._platform.assign_label(  # type: ignore[attr-defined]
                        obsolete,
                        LABEL_FIXED,
                    )
                except Exception:
                    logger.warning(
                        "Failed to assign af:fixed label to superseded issue #%d",
                        obsolete,
                        exc_info=True,
                    )
            except Exception:
                logger.warning(
                    "Failed to close superseded issue #%d",
                    obsolete,
                    exc_info=True,
                )

        for issue_num in processing_order:
            if issue_num in closed:
                continue  # removed by staleness check
            if self.state.is_shutting_down:
                break
            if self._check_cost_limit():
                logger.info("Cost limit reached, stopping issue processing")
                break
            if self._check_session_limit():
                logger.info("Session limit reached, stopping issue processing")
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
                remaining = [issue_map[n] for n in processing_order if n != issue_num and n not in closed]
                if remaining:
                    try:
                        staleness = await check_staleness(
                            issue,
                            remaining,
                            "",  # diff not available in current implementation
                            self._config,
                            self._platform,
                            sink=self._sink,
                            run_id=issue_check_run_id,
                        )
                        remaining_nums = {i.number for i in remaining}
                        for obsolete_num in staleness.obsolete_issues:
                            if obsolete_num not in remaining_nums:
                                continue
                            await self._platform.close_issue(  # type: ignore[attr-defined]
                                obsolete_num,
                                f"Resolved by fix for #{issue_num}",
                            )
                            closed.add(obsolete_num)
                            _emit_audit_event(
                                self._sink,
                                issue_check_run_id,
                                AuditEventType.ISSUE_OBSOLETE,
                                payload={
                                    "closed_issue": obsolete_num,
                                    "fixed_by": issue_num,
                                    "rationale": staleness.rationale.get(obsolete_num, ""),
                                },
                            )
                            try:
                                await self._platform.assign_label(  # type: ignore[attr-defined]
                                    obsolete_num,
                                    LABEL_FIXED,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to assign af:fixed label to obsolete issue #%d",
                                    obsolete_num,
                                    exc_info=True,
                                )
                    except Exception:
                        logger.warning(
                            "Staleness check failed after fix #%d",
                            issue_num,
                            exc_info=True,
                        )

    async def _run_hunt_scan_inner(
        self,
        *,
        sink: SinkDispatcher | None = None,
        run_id: str = "",
    ) -> list[object]:
        """Execute the hunt scan using all enabled hunt categories.

        Requirements: 61-REQ-3.1, 61-REQ-3.2, 61-REQ-3.4
        """
        from agent_fox.nightshift.hunt import HuntCategoryRegistry, HuntScanner

        registry = HuntCategoryRegistry()
        scanner = HuntScanner(registry, self._config)
        return await scanner.run(Path.cwd(), sink=sink, run_id=run_id)  # type: ignore[return-value]

    def _query_false_positives(self) -> list[str]:
        """Query the knowledge store for anti_pattern facts from af:ignore signals.

        Returns a list of content strings for facts with category='anti_pattern'
        and spec_name='nightshift:ignore'. Returns an empty list on failure
        (fail-open).

        Requirements: 110-REQ-6.3, 110-REQ-6.E1
        """
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT content FROM memory_facts "
                "WHERE category = 'anti_pattern' AND spec_name = 'nightshift:ignore'",
            ).fetchall()
            return [row[0] for row in rows]
        except Exception:
            logger.warning(
                "Failed to query anti_pattern facts from knowledge store; "
                "proceeding with empty false_positives list (fail-open)",
                exc_info=True,
            )
            return []

    async def _run_hunt_scan(self) -> None:
        """Execute a full hunt scan and create issues from findings.

        Skips if a hunt scan is already in progress (overlap prevention).

        Requirements: 61-REQ-2.2, 61-REQ-2.E2, 61-REQ-5.1, 61-REQ-5.2,
                      110-REQ-4.1, 110-REQ-5.1, 110-REQ-6.3, 110-REQ-7.2
        """
        self._emit_status("Starting hunt scan\u2026")

        if self._hunt_scan_in_progress:
            logger.info("Hunt scan already in progress, skipping overlapping scan")
            return

        hunt_run_id = generate_run_id()

        # 110-REQ-5.1: Pre-phase — ingest af:ignore signals into knowledge store.
        # Fail-open: if conn is None or platform fails, returns 0 and logs warning.
        try:
            ingested = await ingest_ignore_signals(
                self._platform,  # type: ignore[arg-type]
                self._conn,
                self._embedder,
                sink=self._sink,
                run_id=hunt_run_id,
            )
            if ingested:
                logger.info("Ingested %d new af:ignore signal(s) into knowledge store", ingested)
        except Exception:
            logger.warning(
                "af:ignore ingestion pre-phase failed; "
                "continuing without ingestion (fail-open)",
                exc_info=True,
            )

        # 110-REQ-6.3: Query knowledge store for anti_pattern facts to pass
        # as false_positives to the AI critic.
        false_positives = self._query_false_positives()

        self._hunt_scan_in_progress = True
        try:
            findings = await self._run_hunt_scan_inner(sink=self._sink, run_id=hunt_run_id)
        finally:
            self._hunt_scan_in_progress = False

        _emit_audit_event(
            self._sink,
            hunt_run_id,
            AuditEventType.HUNT_SCAN_COMPLETE,
            payload={"findings_count": len(findings)},
        )

        if not findings:
            self.state.hunt_scans_completed += 1
            self._emit_status("Hunt scan complete: 0 issues created from 0 findings", "bold green")
            return

        # 110-REQ-6.1, 110-REQ-6.2: Pass false_positives to critic so it can
        # proactively drop findings matching known false-positive patterns.
        groups = await consolidate_findings(  # type: ignore[arg-type]
            findings,  # type: ignore[arg-type]
            false_positives=false_positives or None,
            sink=self._sink,
            run_id=hunt_run_id,
        )

        # Dedup gate: skip groups whose fingerprint or embedding matches an
        # existing af:hunt issue (open or closed). Fails open if the platform
        # API is unavailable.
        # Requirements: 79-REQ-4.1, 79-REQ-4.2, 110-REQ-3.1 through 110-REQ-3.5
        similarity_threshold = self._config.night_shift.similarity_threshold
        groups = await filter_known_duplicates(  # type: ignore[arg-type]
            groups,  # type: ignore[arg-type]
            self._platform,  # type: ignore[arg-type]
            similarity_threshold=similarity_threshold,
            embedder=self._embedder,
        )

        # 110-REQ-4.1: Ignore gate — filter groups similar to af:ignore issues.
        # Runs after dedup so only novel-by-fingerprint groups are checked.
        groups = await filter_ignored(  # type: ignore[arg-type]
            groups,  # type: ignore[arg-type]
            self._platform,  # type: ignore[arg-type]
            similarity_threshold=similarity_threshold,
            embedder=self._embedder,
        )

        # create_issues_from_groups returns the created IssueResults so we
        # can assign labels without creating duplicate issues (61-REQ-5.4).
        created = await create_issues_from_groups(groups, self._platform)  # type: ignore[arg-type]
        self.state.issues_created += len(created)

        if self._auto_fix:
            # Assign af:fix label to the issues already created above.
            for result in created:
                try:
                    await self._platform.assign_label(result.number, LABEL_FIX)  # type: ignore[attr-defined]
                    _emit_audit_event(
                        self._sink,
                        hunt_run_id,
                        AuditEventType.ISSUE_CREATED,
                        payload={"issue_number": result.number},  # type: ignore[attr-defined]
                    )
                except Exception:
                    logger.warning(
                        "Failed to assign af:fix label",
                        exc_info=True,
                    )

        self.state.hunt_scans_completed += 1
        self._emit_status(
            f"Hunt scan complete: {len(created)} issues created from {len(findings)} findings",
            "bold green",
        )

    def _calculate_fix_cost(self, metrics: object) -> float:
        """Calculate USD cost from FixMetrics token counts."""
        from agent_fox.core.config import PricingConfig
        from agent_fox.core.models import calculate_cost, resolve_model

        model_entry = resolve_model("ADVANCED")
        pricing = getattr(self._config, "pricing", PricingConfig())
        return calculate_cost(
            getattr(metrics, "input_tokens", 0),
            getattr(metrics, "output_tokens", 0),
            model_entry.model_id,
            pricing,
            cache_read_input_tokens=getattr(metrics, "cache_read_input_tokens", 0),
            cache_creation_input_tokens=getattr(metrics, "cache_creation_input_tokens", 0),
        )

    async def _process_fix(self, issue: object, issue_body: str = "") -> None:
        """Process a single af:fix issue through the fix pipeline.

        Builds an in-memory spec from the issue, runs the full archetype
        pipeline, harvests the branch, and updates the engine state
        including cost and session counters.

        Requirements: 61-REQ-6.1, 61-REQ-6.2, 61-REQ-6.3, 61-REQ-6.4,
                      61-REQ-9.3
        """
        from agent_fox.platform.protocol import IssueResult

        if not isinstance(issue, IssueResult):
            return

        import time

        fix_run_id = generate_run_id()
        fix_start = time.monotonic()
        self._emit_status(f"Fixing issue #{issue.number}: {issue.title}")

        _emit_audit_event(
            self._sink,
            fix_run_id,
            AuditEventType.FIX_START,
            payload={"issue_number": issue.number, "title": issue.title},
        )

        pipeline = FixPipeline(
            config=self._config,
            platform=self._platform,
            activity_callback=self._activity_callback,
            task_callback=self._task_callback,
            sink_dispatcher=self._sink,
            spinner_callback=self._spinner_callback,
        )

        effective_body = issue_body if issue_body else getattr(issue, "body", "")
        try:
            metrics = await pipeline.process_issue(issue, issue_body=effective_body)
            self.state.total_sessions += getattr(metrics, "sessions_run", 0)
            self.state.total_cost += self._calculate_fix_cost(metrics)
            self.state.issues_fixed += 1

            from agent_fox.ui.progress import format_duration

            duration_str = format_duration(time.monotonic() - fix_start)
            self._emit_status(
                f"\u2714 Issue #{issue.number} fixed ({duration_str})",
                "bold green",
            )

            _emit_audit_event(
                self._sink,
                fix_run_id,
                AuditEventType.FIX_COMPLETE,
                payload={"issue_number": issue.number},
            )
        except Exception:
            from agent_fox.ui.progress import format_duration

            duration_str = format_duration(time.monotonic() - fix_start)
            self._emit_status(
                f"\u2718 Issue #{issue.number} failed ({duration_str})",
                "bold red",
            )

            logger.warning(
                "Fix pipeline raised unexpectedly for issue #%d",
                issue.number,
                exc_info=True,
            )
            _emit_audit_event(
                self._sink,
                fix_run_id,
                AuditEventType.FIX_FAILED,
                payload={"issue_number": issue.number},
            )

    async def _drain_issues(self) -> bool:
        """Run issue checks until no open af:fix issues remain.

        Loops calling ``_run_issue_check`` and re-polling the platform until
        zero ``af:fix`` issues are reported.  Respects shutdown, cost, and
        session limits between iterations, and enforces a safety-valve
        maximum iteration count to prevent infinite loops.

        Returns True when no ``af:fix`` issues remain (drain succeeded),
        False when issues may still exist (limit hit, shutdown, or error).

        Requirements: 81-REQ-1.1, 81-REQ-1.4
        """
        for _ in range(self._MAX_DRAIN_ITERATIONS):
            if self.state.is_shutting_down:
                return False
            if self._check_cost_limit():
                logger.info("Cost limit reached during issue drain")
                return False
            if self._check_session_limit():
                logger.info("Session limit reached during issue drain")
                return False

            await self._run_issue_check()

            # Re-poll to see if any af:fix issues remain
            try:
                remaining = await self._platform.list_issues_by_label(  # type: ignore[attr-defined]
                    LABEL_FIX,
                    sort="created",
                    direction="asc",
                )
            except Exception:
                logger.warning(
                    "Failed to re-poll issues during drain",
                    exc_info=True,
                )
                # Fail-open: if we can't check, assume clear (81-REQ-1.E1)
                return True

            if not remaining:
                return True

        logger.warning("Issue drain safety valve reached after %d iterations", self._MAX_DRAIN_ITERATIONS)
        return False
