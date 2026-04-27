"""Fix pipeline: issue-to-branch workflow.

After the archetype sessions complete, the fix branch is harvested into
develop and pushed to origin via post_harvest_integrate.  PR creation was
removed from the platform layer (spec 65, 65-REQ-4.2).  The originating
issue is closed with a comment pointing to the fix branch.

Requirements: 61-REQ-6.1, 61-REQ-6.2, 61-REQ-6.3, 61-REQ-6.4,
              61-REQ-6.E1, 61-REQ-6.E2,
              82-REQ-3.1, 82-REQ-3.E1, 82-REQ-6.1, 82-REQ-6.E1,
              82-REQ-7.1, 82-REQ-7.2, 82-REQ-7.3, 82-REQ-7.E1,
              82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3, 82-REQ-8.4, 82-REQ-8.E1
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.core.config import AgentFoxConfig
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType, generate_run_id
from agent_fox.nightshift.spec_builder import InMemorySpec, build_in_memory_spec
from agent_fox.platform.labels import LABEL_FIXED, LABEL_NO_CHANGE
from agent_fox.platform.protocol import IssueResult
from agent_fox.ui.progress import ActivityCallback, SpinnerCallback, TaskCallback, TaskEvent
from agent_fox.workspace import WorkspaceInfo

if TYPE_CHECKING:
    import duckdb

    from agent_fox.knowledge.sink import SinkDispatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types for triage and review workflow (formerly nightshift/fix_types)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceCriterion:
    """A single acceptance criterion from the triage agent."""

    id: str
    description: str
    preconditions: str
    expected: str
    assertion: str


@dataclass(frozen=True)
class TriageResult:
    """Parsed triage output."""

    summary: str = ""
    affected_files: list[str] = field(default_factory=list)
    criteria: list[AcceptanceCriterion] = field(default_factory=list)


@dataclass(frozen=True)
class FixReviewVerdict:
    """A single per-criterion verdict from the fix reviewer."""

    criterion_id: str
    verdict: str
    evidence: str


@dataclass(frozen=True)
class FixReviewResult:
    """Parsed fix reviewer output."""

    verdicts: list[FixReviewVerdict] = field(default_factory=list)
    overall_verdict: str = "FAIL"
    summary: str = ""
    is_parse_failure: bool = False


@dataclass
class FixMetrics:
    """Aggregated token metrics from all sessions in a fix pipeline run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    sessions_run: int = 0


def build_pr_body(issue_number: int, summary: str) -> str:
    """Build a PR body with an issue reference.

    Requirements: 61-REQ-7.2
    """
    return f"## Summary\n\n{summary}\n\nFixes #{issue_number}\n"


class FixPipeline:
    """Issue-to-branch fix workflow.

    Drives an issue through triage, coding, and review using
    the full archetype pipeline, then posts a completion comment with
    the branch name so the user can open a PR manually.

    Sessions run in an isolated git worktree, consistent with the
    regular coding path (NodeSessionRunner).

    Requirements: 61-REQ-6.1 through 61-REQ-6.4,
                  82-REQ-7.1, 82-REQ-8.1 through 82-REQ-8.4
    """

    def __init__(
        self,
        config: AgentFoxConfig,
        platform: object,
        activity_callback: ActivityCallback | None = None,
        task_callback: TaskCallback | None = None,
        sink_dispatcher: SinkDispatcher | None = None,
        spinner_callback: SpinnerCallback | None = None,
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> None:
        self._config = config
        self._platform = platform
        self._activity_callback = activity_callback
        self._task_callback = task_callback
        self._sink = sink_dispatcher
        self._spinner_callback = spinner_callback
        self._conn = conn
        self._run_id: str = ""

    async def _post_comment(self, issue_number: int, message: str) -> None:
        """Post a comment on an issue, logging failures without raising."""
        try:
            await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                issue_number,
                message,
            )
        except Exception as exc:
            logger.warning("Failed to post comment for issue #%d: %s", issue_number, exc)

    def _update_spinner(self, text: str) -> None:
        """Update the spinner text with a phase hint.

        No-op when spinner_callback is not set.
        """
        if self._spinner_callback is not None:
            try:
                self._spinner_callback(text)
            except Exception:
                logger.debug("Spinner callback failed", exc_info=True)

    async def _run_session(
        self,
        archetype: str,
        workspace: WorkspaceInfo,
        *,
        spec: InMemorySpec,
        system_prompt: str | None = None,
        task_prompt: str | None = None,
        model_id: str | None = None,
        mode: str | None = None,
    ) -> object:
        """Run a single archetype session for an issue fix.

        Resolves SDK parameters (model, security, max_turns, thinking,
        fallback, budget) per archetype, consistent with the regular
        coding path.  Subclasses or tests can override this for mock
        execution.

        Requirements: 61-REQ-6.3
        """
        from agent_fox.core.models import resolve_model
        from agent_fox.engine.sdk_params import (
            resolve_model_tier,
            resolve_security_config,
            resolve_session_params,
        )
        from agent_fox.session.prompt import build_system_prompt
        from agent_fox.session.session import run_session

        # Build the archetype-specific system prompt.
        if system_prompt:
            effective_system = system_prompt
        else:
            effective_system = build_system_prompt(
                context=spec.system_context,
                archetype=archetype,
                mode=mode,
                project_dir=Path.cwd(),
            )

        effective_task = task_prompt if task_prompt else spec.task_prompt
        node_id = f"fix-issue-{spec.issue_number}:0:{archetype}"

        config = self._config
        resolved_model_id = model_id or resolve_model(resolve_model_tier(config, archetype, mode=mode)).model_id
        resolved_security = resolve_security_config(config, archetype, mode=mode)
        params = resolve_session_params(
            config,
            archetype,
            mode=mode,
            model_id=resolved_model_id,
        )

        return await run_session(
            workspace=workspace,
            node_id=node_id,
            system_prompt=effective_system,
            task_prompt=effective_task,
            config=config,
            activity_callback=self._activity_callback,
            model_id=resolved_model_id,
            security_config=resolved_security,
            max_turns=params.max_turns,
            max_budget_usd=params.max_budget_usd,
            fallback_model=params.fallback_model,
            thinking=params.thinking,
            archetype=archetype,
            sink_dispatcher=self._sink,
            run_id=self._run_id,
        )

    async def _setup_workspace(self, spec: InMemorySpec) -> WorkspaceInfo:
        """Create an isolated worktree for the fix branch.

        Uses the same ``create_worktree`` function as the regular coding
        path, with a custom branch name to preserve the ``fix/`` prefix
        convention.

        Requirements: 61-REQ-6.2
        """
        from agent_fox.workspace import create_worktree

        repo_root = Path.cwd()
        return await create_worktree(
            repo_root,
            spec_name=f"fix-issue-{spec.issue_number}",
            task_group=0,
            branch_name=spec.branch_name,
        )

    async def _cleanup_workspace(self, workspace: WorkspaceInfo) -> None:
        """Destroy the worktree created for the fix session."""
        from agent_fox.workspace import destroy_worktree

        repo_root = Path.cwd()
        try:
            await destroy_worktree(repo_root, workspace)
        except Exception:
            logger.warning(
                "Failed to clean up worktree for %s",
                workspace.branch,
                exc_info=True,
            )

    def _accumulate_metrics(self, metrics: FixMetrics, outcome: object) -> None:
        """Add a SessionOutcome's tokens to the running metrics."""
        metrics.input_tokens += getattr(outcome, "input_tokens", 0)
        metrics.output_tokens += getattr(outcome, "output_tokens", 0)
        metrics.cache_read_input_tokens += getattr(outcome, "cache_read_input_tokens", 0)
        metrics.cache_creation_input_tokens += getattr(outcome, "cache_creation_input_tokens", 0)
        metrics.sessions_run += 1

    def _get_model_id(self, archetype: str) -> str:
        """Resolve model_id for the given archetype, with a safe fallback.

        Requirements: 91-REQ-3.1
        """
        try:
            from agent_fox.core.models import resolve_model
            from agent_fox.engine.sdk_params import resolve_model_tier

            tier = resolve_model_tier(self._config, archetype)
            return resolve_model(tier).model_id
        except Exception:
            return "claude-sonnet-4-6"

    def _try_complete_run(self, status: str) -> None:
        """Mark the runs row as finished (best-effort).

        No-op when conn is not set.  The *status* value should be a
        ``RunStatus`` string (e.g. ``"completed"`` or ``"interrupted"``).
        """
        if self._conn is None:
            return
        try:
            from agent_fox.engine.state import complete_run

            complete_run(self._conn, self._run_id, status)
        except Exception:
            logger.warning("Failed to complete run record for run %s", self._run_id, exc_info=True)

    def _record_session_to_db(
        self,
        outcome: object,
        archetype: str,
        run_id: str,
        *,
        node_id: str = "",
        attempt: int = 1,
        cost: float = 0.0,
    ) -> None:
        """Write a session outcome row to session_outcomes and update runs totals.

        Best-effort: exceptions are logged and swallowed so the pipeline is
        never interrupted by a telemetry failure.
        """
        if self._conn is None:
            return

        import uuid as _uuid
        from datetime import UTC, datetime

        from agent_fox.engine.state import (
            SessionOutcomeRecord,
            record_session,
            update_run_totals,
        )

        try:
            input_tokens = getattr(outcome, "input_tokens", 0)
            output_tokens = getattr(outcome, "output_tokens", 0)
            duration_ms = getattr(outcome, "duration_ms", 0)
            status = getattr(outcome, "status", "completed")
            error_message = getattr(outcome, "error_message", None)
            is_transport_error = getattr(outcome, "is_transport_error", False)

            # Parse spec_name and task_group from node_id (format: spec:group:archetype)
            parts = node_id.split(":", 2)
            spec_name = parts[0] if parts else ""
            task_group = parts[1] if len(parts) > 1 else "0"

            model_id = self._get_model_id(archetype)

            record = SessionOutcomeRecord(
                id=str(_uuid.uuid4()),
                spec_name=spec_name,
                task_group=task_group,
                node_id=node_id,
                touched_path="",
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                created_at=datetime.now(UTC).isoformat(),
                run_id=run_id,
                attempt=attempt,
                cost=cost,
                model=model_id,
                archetype=archetype,
                commit_sha="",
                error_message=error_message,
                is_transport_error=is_transport_error,
            )
            record_session(self._conn, record)
            update_run_totals(
                self._conn,
                run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )
        except Exception:
            logger.warning(
                "Failed to record session to DB for %s",
                node_id,
                exc_info=True,
            )

    def _emit_session_event(
        self,
        outcome: object,
        archetype: str,
        run_id: str,
        *,
        node_id: str = "",
        attempt: int = 1,
    ) -> None:
        """Emit session.complete or session.fail based on outcome status.

        Also writes a row to session_outcomes and updates the runs totals via
        _record_session_to_db (best-effort).

        Best-effort: exceptions from audit infrastructure are logged and
        swallowed so the fix pipeline is never interrupted.

        Requirements: 91-REQ-3.1, 91-REQ-3.2, 91-REQ-3.E1
        """
        from agent_fox.engine.audit_helpers import calculate_session_cost

        status = getattr(outcome, "status", "failed")
        input_tokens = getattr(outcome, "input_tokens", 0)
        output_tokens = getattr(outcome, "output_tokens", 0)
        cache_read = getattr(outcome, "cache_read_input_tokens", 0)
        cache_creation = getattr(outcome, "cache_creation_input_tokens", 0)
        duration_ms = getattr(outcome, "duration_ms", 0)
        error_message = getattr(outcome, "error_message", None)

        model_id = self._get_model_id(archetype)

        if status == "completed":
            cost = calculate_session_cost(
                self._config,
                model_id,
                input_tokens,
                output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_creation,
            )
            emit_audit_event(
                self._sink,
                run_id,
                AuditEventType.SESSION_COMPLETE,
                node_id=node_id,
                archetype=archetype,
                payload={
                    "archetype": archetype,
                    "model_id": model_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_input_tokens": cache_read,
                    "cache_creation_input_tokens": cache_creation,
                    "cost": cost,
                    "duration_ms": duration_ms,
                },
            )
        else:
            cost = 0.0
            emit_audit_event(
                self._sink,
                run_id,
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
                archetype=archetype,
                payload={
                    "archetype": archetype,
                    "model_id": model_id,
                    "error_message": str(error_message) if error_message else "",
                    "attempt": attempt,
                },
            )

        # Write to session_outcomes table and update runs totals (best-effort).
        self._record_session_to_db(
            outcome,
            archetype,
            run_id,
            node_id=node_id,
            attempt=attempt,
            cost=cost,
        )

    # ------------------------------------------------------------------
    # Comment formatting (82-REQ-3.1, 82-REQ-6.1)
    # ------------------------------------------------------------------

    def _format_triage_comment(self, triage: TriageResult) -> str:
        """Render TriageResult as markdown for issue comment.

        Requirements: 82-REQ-3.1
        """
        lines: list[str] = ["## Triage Report", ""]
        if triage.summary:
            lines.append(f"**Summary:** {triage.summary}")
            lines.append("")
        if triage.affected_files:
            lines.append("**Affected files:**")
            for f in triage.affected_files:
                lines.append(f"- `{f}`")
            lines.append("")
        if triage.criteria:
            lines.append("## Acceptance Criteria")
            lines.append("")
            for c in triage.criteria:
                lines.append(f"### {c.id}: {c.description}")
                lines.append(f"- **Preconditions:** {c.preconditions}")
                lines.append(f"- **Expected:** {c.expected}")
                lines.append(f"- **Assertion:** {c.assertion}")
                lines.append("")
        return "\n".join(lines)

    def _format_review_comment(self, review: FixReviewResult) -> str:
        """Render FixReviewResult as markdown for issue comment.

        Requirements: 82-REQ-6.1
        """
        lines: list[str] = [
            "## Fix Review Report",
            "",
            f"**Overall verdict:** {review.overall_verdict}",
            "",
        ]
        if review.summary:
            lines.append(f"**Summary:** {review.summary}")
            lines.append("")
        if review.verdicts:
            lines.append("### Per-criterion verdicts")
            lines.append("")
            for v in review.verdicts:
                icon = "\u2705" if v.verdict == "PASS" else "\u274c"
                lines.append(f"- {icon} **{v.criterion_id}**: {v.verdict}")
                lines.append(f"  - Evidence: {v.evidence}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt building (82-REQ-7.2, 82-REQ-7.3, 82-REQ-8.1, 82-REQ-5.E1)
    # ------------------------------------------------------------------

    def _build_coder_prompt(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        review_feedback: FixReviewResult | None = None,
    ) -> tuple[str, str]:
        """Build system/task prompts with triage criteria and optional feedback.

        Requirements: 82-REQ-7.2, 82-REQ-8.1
        """
        from agent_fox.session.prompt import build_system_prompt

        # Assemble criteria context for the system prompt
        criteria_context = self._render_criteria_context(triage)
        context = spec.system_context
        if criteria_context:
            context = f"{context}\n\n{criteria_context}"

        system_prompt = build_system_prompt(
            context=context,
            archetype="coder",
            mode="fix",
            project_dir=Path.cwd(),
        )

        # Build task prompt, injecting reviewer feedback on retry
        task_prompt = spec.task_prompt
        if review_feedback is not None:
            feedback_section = self._render_review_feedback(review_feedback)
            task_prompt = f"{task_prompt}\n\n{feedback_section}"

        return system_prompt, task_prompt

    def _build_reviewer_prompt(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
    ) -> tuple[str, str]:
        """Build system/task prompts with triage criteria for verification.

        Requirements: 82-REQ-7.3, 82-REQ-5.3, 82-REQ-5.E1
        """
        from agent_fox.session.prompt import build_system_prompt

        # Include criteria in context, or fall back to issue description
        criteria_context = self._render_criteria_context(triage)
        if criteria_context:
            context = f"{spec.system_context}\n\n{criteria_context}"
        else:
            # No triage criteria: reviewer verifies from issue description
            context = (
                f"{spec.system_context}\n\n"
                "No acceptance criteria were produced by triage. "
                "Verify the fix based on the issue description above."
            )

        system_prompt = build_system_prompt(
            context=context,
            archetype="reviewer",
            mode="fix-review",
            project_dir=Path.cwd(),
        )

        task_prompt = (
            f"Review the fix for issue #{spec.issue_number}: {spec.title}\n\n"
            "Run `make check` and verify each acceptance criterion. "
            "Produce a JSON verdict report."
        )

        return system_prompt, task_prompt

    def _render_criteria_context(self, triage: TriageResult) -> str:
        """Render triage criteria as structured context text."""
        if not triage.criteria:
            return ""

        lines: list[str] = ["## Acceptance Criteria from Triage", ""]
        for c in triage.criteria:
            lines.append(f"### {c.id}: {c.description}")
            lines.append(f"- Preconditions: {c.preconditions}")
            lines.append(f"- Expected: {c.expected}")
            lines.append(f"- Assertion: {c.assertion}")
            lines.append("")
        return "\n".join(lines)

    def _render_review_feedback(self, review: FixReviewResult) -> str:
        """Render reviewer feedback for injection into coder retry prompt.

        Requirements: 82-REQ-8.1
        """
        lines: list[str] = [
            "## Previous Review Feedback (FAILED)",
            "",
            f"Overall verdict: {review.overall_verdict}",
            "",
        ]
        for v in review.verdicts:
            if v.verdict == "FAIL":
                lines.append(f"### {v.criterion_id}: FAIL")
                lines.append(f"Evidence: {v.evidence}")
                lines.append("")
        if review.summary:
            lines.append(f"Reviewer summary: {review.summary}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Session runners (82-REQ-7.E1, 82-REQ-8.3)
    # ------------------------------------------------------------------

    async def _run_coder_session(
        self,
        workspace: WorkspaceInfo,
        spec: InMemorySpec,
        system_prompt: str,
        task_prompt: str,
        model_id: str | None = None,
    ) -> object:
        """Run coder with optional model override for escalation.

        Requirements: 82-REQ-8.3, 98-REQ-2.2
        """
        return await self._run_session(
            "coder",
            workspace,
            spec=spec,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            model_id=model_id,
            mode="fix",
        )

    async def _run_triage(
        self,
        spec: InMemorySpec,
        workspace: WorkspaceInfo,
    ) -> TriageResult:
        """Run triage session, parse output, post comment.

        Catches exceptions and returns empty TriageResult on failure.
        Catches comment posting errors.

        Requirements: 82-REQ-3.1, 82-REQ-3.E1, 82-REQ-7.E1
        """
        from agent_fox.session.review_parser import parse_triage_output

        node_id = f"fix-issue-{spec.issue_number}:0:triage"
        triage_task = (
            f"Triage issue #{spec.issue_number}: {spec.title}\n\n"
            "Analyze the issue, identify the root cause and affected files, "
            "and produce a JSON triage report with acceptance criteria."
        )
        try:
            outcome = await self._run_session(
                "maintainer",
                workspace,
                spec=spec,
                mode="fix-triage",
                task_prompt=triage_task,
            )
            self._emit_session_event(outcome, "maintainer", self._run_id, node_id=node_id)
        except Exception as exc:
            logger.warning(
                "Triage session failed for issue #%d: %s",
                spec.issue_number,
                exc,
            )
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
                archetype="maintainer",
                payload={
                    "archetype": "maintainer",
                    "model_id": self._get_model_id("maintainer"),
                    "error_message": str(exc),
                    "attempt": 1,
                },
            )
            return TriageResult()

        response = getattr(outcome, "response", "") or ""
        triage = parse_triage_output(
            response,
            f"fix-issue-{spec.issue_number}",
            f"fix-issue-{spec.issue_number}:0:triage",
        )

        # Post triage comment if we have results
        if triage.criteria or triage.summary:
            comment = self._format_triage_comment(triage) + f"\n(run: `{self._run_id}`)"
            await self._post_comment(spec.issue_number, comment)

        return triage

    async def _coder_review_loop(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        metrics: FixMetrics,
        workspace: WorkspaceInfo,
    ) -> bool:
        """Coder-reviewer loop with retry and escalation.

        Delegates to CoderReviewerLoop collaborator class.
        Returns True on PASS, False on exhaustion.

        Requirements: 82-REQ-7.1, 82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3,
                      82-REQ-8.4, 82-REQ-8.E1
        """
        from agent_fox.nightshift.coder_reviewer import CoderReviewerLoop

        return await CoderReviewerLoop(self).run(spec, triage, metrics, workspace)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_issue(
        self,
        issue: IssueResult,
        issue_body: str = "",
        run_id: str | None = None,
    ) -> FixMetrics:
        """Process an af:fix issue through the full pipeline.

        Runs triage -> coder -> reviewer with retry/escalation loop
        inside an isolated git worktree.

        When ``run_id`` is provided (e.g. by the engine that already emitted
        a ``FIX_START`` lifecycle event), that same id is reused so all audit
        events share one ``run_id``.  When omitted a fresh id is generated,
        preserving backward-compatibility for standalone callers.

        Returns FixMetrics with aggregated token counts from all sessions.

        Args:
            issue: The issue to process.
            issue_body: The issue body text.
            run_id: Optional run ID to use for all audit events.  When
                provided (e.g. from NightShiftEngine), the same run_id is
                shared with the parent lifecycle events so that all events
                for a single fix pipeline can be retrieved with a single
                ``SELECT … WHERE run_id = ?`` query.  When omitted a fresh
                ID is generated (91-REQ-2.1).

        Requirements: 61-REQ-6.1, 61-REQ-6.E2, 82-REQ-7.1
        """
        metrics = FixMetrics()

        # Use the caller-supplied run_id when available so that lifecycle
        # events (fix_start / fix_complete) and session events all share the
        # same identifier.  Fall back to generating a fresh one when called
        # standalone (91-REQ-2.1).
        self._run_id = run_id if run_id else generate_run_id()

        # Create a run row in the runs table (best-effort).
        if self._conn is not None:
            try:
                from agent_fox.engine.state import create_run

                create_run(self._conn, self._run_id, f"fix-issue-{issue.number}")
            except Exception:
                logger.debug(
                    "Failed to create run record for issue #%d",
                    issue.number,
                    exc_info=True,
                )

        # 61-REQ-6.E2: reject empty issue body
        if not issue_body or not issue_body.strip():
            await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                issue.number,
                "Insufficient detail in issue body to build a fix. "
                "Please add more detail describing the problem and expected behavior. "
                f"(run: `{self._run_id}`)",
            )
            self._try_complete_run("completed")
            return metrics

        spec = build_in_memory_spec(issue, issue_body)

        # 61-REQ-6.2: create an isolated worktree for the fix branch
        self._update_spinner(f"Setting up workspace for issue #{issue.number}\u2026")
        workspace = await self._setup_workspace(spec)

        # Post progress comment
        await self._post_comment(
            issue.number,
            f"Starting fix session on branch `{spec.branch_name}`... (run: `{self._run_id}`)",
        )

        try:
            # 82-REQ-7.1: run triage first
            triage_node_id = f"fix-issue-{spec.issue_number}:0:triage"
            self._update_spinner(f"Analyzing issue #{issue.number} (triage)\u2026")
            t0 = time.monotonic()
            triage = await self._run_triage(spec, workspace)
            duration = time.monotonic() - t0

            # Emit triage task event if we got results
            if triage.criteria and self._task_callback is not None:
                self._task_callback(
                    TaskEvent(
                        node_id=triage_node_id,
                        status="completed",
                        duration_s=duration,
                        archetype="maintainer",
                    )
                )
            # Count triage session in metrics if it produced output
            if triage.criteria or triage.summary:
                metrics.sessions_run += 1

            # 82-REQ-7.1: coder-reviewer loop with retry/escalation
            success = await self._coder_review_loop(spec, triage, metrics, workspace)

            if not success:
                # Ladder exhausted — do NOT close issue
                self._try_complete_run("completed")
                return metrics

            # Optionally push fix branch to upstream remote (93-REQ-3.1).
            # Must run BEFORE harvest, which changes the working tree.
            if self._config.night_shift.push_fix_branch:
                self._update_spinner(f"Pushing fix branch for issue #{issue.number}\u2026")
                await self._push_fix_branch_upstream(spec, workspace)

            # Harvest fix branch into develop and push to origin (65-REQ-3.2).
            # Must run BEFORE cleanup destroys the feature branch.
            self._update_spinner(f"Merging fix for issue #{issue.number} into develop\u2026")
            harvest_result = await self._harvest_and_push(spec, workspace)

        except Exception as exc:
            # 61-REQ-6.E1: post comment on failure
            await self._post_comment(
                issue.number,
                f"Fix session failed: {exc}\n\nBranch: `{spec.branch_name}` (run: `{self._run_id}`)",
            )
            logger.warning(
                "Fix session failed for issue #%d: %s",
                issue.number,
                exc,
            )
            self._try_complete_run("interrupted")
            return metrics
        finally:
            await self._cleanup_workspace(workspace)

        if harvest_result == "error":
            await self._post_comment(
                issue.number,
                f"Fix sessions completed but changes from branch "
                f"`{spec.branch_name}` could not be merged into `develop`. "
                f"Manual investigation is required. (run: `{self._run_id}`)",
            )
            self._try_complete_run("completed")
            return metrics

        if harvest_result == "no_changes":
            # Coder produced no commits — leave the issue open for human review.
            logger.warning(
                "No changes produced for issue #%d on branch %s — leaving issue open",
                issue.number,
                spec.branch_name,
            )
            await self._post_comment(
                issue.number,
                f"Fix attempt on branch `{spec.branch_name}` produced no new commits. "
                "The issue has been left open for human review. "
                f"(run: `{self._run_id}`)",
            )
            try:
                await self._platform.assign_label(  # type: ignore[attr-defined]
                    issue.number,
                    LABEL_NO_CHANGE,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to assign af:no-change label to issue #%d: %s",
                    issue.number,
                    exc,
                )
            self._try_complete_run("completed")
            return metrics

        # harvest_result == "merged": close the originating issue with a comment
        # pointing to the branch.
        close_msg = (
            f"Fix complete on branch `{spec.branch_name}`. "
            "Changes have been merged into `develop`. "
            "Create a PR from that branch to land them on `main`."
            f" (run: `{self._run_id}`)"
        )
        try:
            await self._platform.close_issue(  # type: ignore[attr-defined]
                issue.number,
                close_msg,
            )
        except Exception as exc:
            logger.warning(
                "Failed to close issue #%d: %s",
                issue.number,
                exc,
            )
        # Add af:fixed label for provenance and re-processing guard (#429).
        # The af:fix label is intentionally preserved to record that the issue
        # was submitted for automated fixing. af:fixed signals it was resolved.
        try:
            await self._platform.assign_label(  # type: ignore[attr-defined]
                issue.number,
                LABEL_FIXED,
            )
        except Exception as exc:
            logger.warning(
                "Failed to assign af:fixed label to issue #%d: %s",
                issue.number,
                exc,
            )
        logger.info(
            "Fix pipeline complete for issue #%d on branch %s",
            issue.number,
            spec.branch_name,
        )
        self._try_complete_run("completed")
        return metrics

    async def _push_fix_branch_upstream(
        self,
        spec: InMemorySpec,
        workspace: WorkspaceInfo,
    ) -> bool:
        """Force-push the fix branch to origin. Returns True on success.

        Logs a warning and returns False on failure — never raises.

        Requirements: 93-REQ-3.1, 93-REQ-3.2, 93-REQ-3.E1, 93-REQ-3.E2
        """
        from agent_fox.workspace.git import push_to_remote

        try:
            success = await push_to_remote(
                workspace.path,
                spec.branch_name,
                force=True,
            )
            if not success:
                logger.warning(
                    "Failed to push fix branch '%s' to origin",
                    spec.branch_name,
                )
                return False
            logger.info("Pushed fix branch '%s' to origin", spec.branch_name)
            return True
        except Exception as exc:
            logger.warning(
                "Failed to push fix branch '%s' to origin: %s",
                spec.branch_name,
                exc,
            )
            return False

    async def _harvest_and_push(
        self,
        spec: InMemorySpec,
        workspace: WorkspaceInfo,
    ) -> str:
        """Harvest the fix branch into develop and push to origin.

        Returns:
            ``"merged"`` when changes were merged successfully.
            ``"no_changes"`` when harvest found no new commits on the
            fix branch (the fix may already be on develop).
            ``"error"`` when an error occurred during harvest or push.
        """
        from agent_fox.workspace.harvest import harvest, post_harvest_integrate

        repo_root = Path.cwd()
        try:
            changed_files = await harvest(repo_root, workspace)
            if not changed_files:
                logger.warning(
                    "No changes produced for issue #%d on branch %s",
                    spec.issue_number,
                    spec.branch_name,
                )
                return "no_changes"
            await post_harvest_integrate(repo_root, workspace)
        except Exception as exc:
            logger.warning(
                "Harvest/push failed for issue #%d on branch %s: %s",
                spec.issue_number,
                spec.branch_name,
                exc,
            )
            return "error"
        return "merged"
