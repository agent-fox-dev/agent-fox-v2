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
from dataclasses import dataclass
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.nightshift.fix_types import (
    FixReviewResult,
    TriageResult,
)
from agent_fox.nightshift.spec_builder import InMemorySpec, build_in_memory_spec
from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import ActivityCallback, TaskCallback, TaskEvent
from agent_fox.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._config = config
        self._platform = platform
        self._activity_callback = activity_callback
        self._task_callback = task_callback

    async def _run_session(
        self,
        archetype: str,
        workspace: WorkspaceInfo,
        *,
        spec: InMemorySpec,
        system_prompt: str | None = None,
        task_prompt: str | None = None,
        model_id: str | None = None,
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
            resolve_fallback_model,
            resolve_max_budget,
            resolve_max_turns,
            resolve_model_tier,
            resolve_security_config,
            resolve_thinking,
        )
        from agent_fox.session.prompt import build_system_prompt
        from agent_fox.session.session import run_session

        # Build the archetype-specific system prompt.
        if system_prompt:
            effective_system = system_prompt
        else:
            effective_system = build_system_prompt(
                context=spec.system_context,
                task_group=0,
                spec_name=f"fix-issue-{spec.issue_number}",
                archetype=archetype,
            )

        effective_task = task_prompt if task_prompt else spec.task_prompt
        node_id = f"fix-issue-{spec.issue_number}:0:{archetype}"

        # Resolve SDK params per archetype, matching NodeSessionRunner
        config = self._config
        resolved_model_id = model_id or resolve_model(resolve_model_tier(config, archetype)).model_id
        resolved_security = resolve_security_config(config, archetype)
        resolved_max_turns = resolve_max_turns(config, archetype)
        resolved_thinking = resolve_thinking(config, archetype)
        resolved_fallback = resolve_fallback_model(config)
        resolved_budget = resolve_max_budget(config)

        # Claude CLI rejects fallback_model when it equals the main model
        if resolved_fallback and resolved_fallback == resolved_model_id:
            resolved_fallback = None

        return await run_session(
            workspace=workspace,
            node_id=node_id,
            system_prompt=effective_system,
            task_prompt=effective_task,
            config=config,
            activity_callback=self._activity_callback,
            model_id=resolved_model_id,
            security_config=resolved_security,
            max_turns=resolved_max_turns,
            max_budget_usd=resolved_budget,
            fallback_model=resolved_fallback,
            thinking=resolved_thinking,
            archetype=archetype,
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
            task_group=0,
            spec_name=f"fix-issue-{spec.issue_number}",
            archetype="fix_coder",
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
            task_group=0,
            spec_name=f"fix-issue-{spec.issue_number}",
            archetype="fix_reviewer",
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

        Requirements: 82-REQ-8.3
        """
        return await self._run_session(
            "fix_coder",
            workspace,
            spec=spec,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            model_id=model_id,
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

        try:
            outcome = await self._run_session("triage", workspace, spec=spec)
        except Exception as exc:
            logger.warning(
                "Triage session failed for issue #%d: %s",
                spec.issue_number,
                exc,
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
            comment = self._format_triage_comment(triage)
            try:
                await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                    spec.issue_number, comment
                )
            except Exception as exc:
                logger.warning(
                    "Failed to post triage comment for issue #%d: %s",
                    spec.issue_number,
                    exc,
                )

        return triage

    # ------------------------------------------------------------------
    # Coder-reviewer loop (82-REQ-8.1 through 82-REQ-8.4, 82-REQ-8.E1)
    # ------------------------------------------------------------------

    async def _coder_review_loop(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        metrics: FixMetrics,
        workspace: WorkspaceInfo,
    ) -> bool:
        """Coder-reviewer loop with retry and escalation.

        Returns True on PASS, False on exhaustion.

        Requirements: 82-REQ-7.1, 82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3,
                      82-REQ-8.4, 82-REQ-8.E1
        """
        from agent_fox.core.models import ModelTier, resolve_model
        from agent_fox.routing.escalation import EscalationLadder
        from agent_fox.session.review_parser import parse_fix_review_output

        retries_before = getattr(
            self._config.orchestrator,
            "retries_before_escalation",
            1,
        )
        max_retries = getattr(
            self._config.orchestrator,
            "max_retries",
            3,
        )

        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=retries_before,
        )

        review_feedback: FixReviewResult | None = None

        for _attempt in range(max_retries + 1):
            # Resolve model from current tier
            tier = ladder.current_tier
            model_entry = resolve_model(tier.value)
            model_id: str | None = model_entry.model_id

            # Build and run coder session
            system_prompt, task_prompt = self._build_coder_prompt(spec, triage, review_feedback=review_feedback)

            node_id = f"fix-issue-{spec.issue_number}:0:fix_coder"
            t0 = time.monotonic()
            try:
                coder_outcome = await self._run_coder_session(
                    workspace,
                    spec,
                    system_prompt,
                    task_prompt,
                    model_id=model_id,
                )
                self._accumulate_metrics(metrics, coder_outcome)
                duration = time.monotonic() - t0
                if self._task_callback is not None:
                    self._task_callback(
                        TaskEvent(
                            node_id=node_id,
                            status="completed",
                            duration_s=duration,
                            archetype="fix_coder",
                        )
                    )
            except Exception:
                duration = time.monotonic() - t0
                if self._task_callback is not None:
                    self._task_callback(
                        TaskEvent(
                            node_id=node_id,
                            status="failed",
                            duration_s=duration,
                            archetype="fix_coder",
                        )
                    )
                raise

            # Build and run reviewer session
            reviewer_system, reviewer_task = self._build_reviewer_prompt(spec, triage)

            reviewer_node_id = f"fix-issue-{spec.issue_number}:0:fix_reviewer"
            t0 = time.monotonic()
            try:
                reviewer_outcome = await self._run_session(
                    "fix_reviewer",
                    workspace,
                    spec=spec,
                    system_prompt=reviewer_system,
                    task_prompt=reviewer_task,
                )
                self._accumulate_metrics(metrics, reviewer_outcome)
                duration = time.monotonic() - t0
                if self._task_callback is not None:
                    self._task_callback(
                        TaskEvent(
                            node_id=reviewer_node_id,
                            status="completed",
                            duration_s=duration,
                            archetype="fix_reviewer",
                        )
                    )
            except Exception:
                duration = time.monotonic() - t0
                if self._task_callback is not None:
                    self._task_callback(
                        TaskEvent(
                            node_id=reviewer_node_id,
                            status="failed",
                            duration_s=duration,
                            archetype="fix_reviewer",
                        )
                    )
                raise

            # Parse reviewer output, retrying reviewer once on parse failure
            reviewer_response = getattr(reviewer_outcome, "response", "") or ""
            review_result = parse_fix_review_output(
                reviewer_response,
                f"fix-issue-{spec.issue_number}",
                f"fix-issue-{spec.issue_number}:0:fix_reviewer",
            )

            if review_result.is_parse_failure:
                logger.info(
                    "Reviewer output unparseable for issue #%d, retrying reviewer",
                    spec.issue_number,
                )
                retry_node_id = f"fix-issue-{spec.issue_number}:0:fix_reviewer_retry"
                t0 = time.monotonic()
                try:
                    retry_outcome = await self._run_session(
                        "fix_reviewer",
                        workspace,
                        spec=spec,
                        system_prompt=reviewer_system,
                        task_prompt=reviewer_task,
                    )
                    self._accumulate_metrics(metrics, retry_outcome)
                    duration = time.monotonic() - t0
                    if self._task_callback is not None:
                        self._task_callback(
                            TaskEvent(
                                node_id=retry_node_id,
                                status="completed",
                                duration_s=duration,
                                archetype="fix_reviewer",
                            )
                        )
                    retry_response = getattr(retry_outcome, "response", "") or ""
                    retry_result = parse_fix_review_output(
                        retry_response,
                        f"fix-issue-{spec.issue_number}",
                        f"fix-issue-{spec.issue_number}:0:fix_reviewer_retry",
                    )
                    if not retry_result.is_parse_failure:
                        review_result = retry_result
                    else:
                        logger.warning(
                            "Reviewer retry also unparseable for issue #%d, treating as FAIL",
                            spec.issue_number,
                        )
                except Exception:
                    duration = time.monotonic() - t0
                    if self._task_callback is not None:
                        self._task_callback(
                            TaskEvent(
                                node_id=retry_node_id,
                                status="failed",
                                duration_s=duration,
                                archetype="fix_reviewer",
                            )
                        )
                    logger.warning(
                        "Reviewer retry failed for issue #%d, treating as FAIL",
                        spec.issue_number,
                        exc_info=True,
                    )

            # Post review comment
            review_comment = self._format_review_comment(review_result)
            try:
                await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                    spec.issue_number, review_comment
                )
            except Exception as exc:
                logger.warning(
                    "Failed to post review comment for issue #%d: %s",
                    spec.issue_number,
                    exc,
                )

            # Check verdict
            if review_result.overall_verdict == "PASS":
                return True

            # FAIL: record and maybe escalate
            ladder.record_failure()

            if ladder.is_exhausted or _attempt >= max_retries:
                # Post failure comment and stop
                try:
                    await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                        spec.issue_number,
                        "Fix pipeline exhausted all retries. "
                        "The issue could not be resolved automatically. "
                        "Manual intervention is required.",
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to post exhaustion comment for issue #%d: %s",
                        spec.issue_number,
                        exc,
                    )
                return False

            # Set up feedback for next coder attempt
            review_feedback = review_result

        # Should not reach here, but safety fallback
        return False  # pragma: no cover

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_issue(
        self,
        issue: IssueResult,
        issue_body: str = "",
    ) -> FixMetrics:
        """Process an af:fix issue through the full pipeline.

        Runs triage -> coder -> fix_reviewer with retry/escalation loop
        inside an isolated git worktree.

        Returns FixMetrics with aggregated token counts from all sessions.

        Requirements: 61-REQ-6.1, 61-REQ-6.E2, 82-REQ-7.1
        """
        metrics = FixMetrics()

        # 61-REQ-6.E2: reject empty issue body
        if not issue_body or not issue_body.strip():
            await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                issue.number,
                "Insufficient detail in issue body to build a fix. "
                "Please add more detail describing the problem and expected behavior.",
            )
            return metrics

        spec = build_in_memory_spec(issue, issue_body)

        # 61-REQ-6.2: create an isolated worktree for the fix branch
        workspace = await self._setup_workspace(spec)

        # Post progress comment
        try:
            await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                issue.number,
                f"Starting fix session on branch `{spec.branch_name}`...",
            )
        except Exception as exc:
            logger.warning(
                "Failed to post starting comment for issue #%d: %s",
                issue.number,
                exc,
            )

        try:
            # 82-REQ-7.1: run triage first
            triage_node_id = f"fix-issue-{spec.issue_number}:0:triage"
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
                        archetype="triage",
                    )
                )
            # Count triage session in metrics if it produced output
            if triage.criteria or triage.summary:
                metrics.sessions_run += 1

            # 82-REQ-7.1: coder-reviewer loop with retry/escalation
            success = await self._coder_review_loop(spec, triage, metrics, workspace)

            if not success:
                # Ladder exhausted — do NOT close issue
                return metrics

            # Harvest fix branch into develop and push to origin (65-REQ-3.2).
            # Must run BEFORE cleanup destroys the feature branch.
            harvest_result = await self._harvest_and_push(spec, workspace)

        except Exception as exc:
            # 61-REQ-6.E1: post comment on failure
            try:
                await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                    issue.number,
                    f"Fix session failed: {exc}\n\nBranch: `{spec.branch_name}`",
                )
            except Exception as comment_exc:
                logger.warning(
                    "Failed to post failure comment for issue #%d: %s",
                    issue.number,
                    comment_exc,
                )
            logger.warning(
                "Fix session failed for issue #%d: %s",
                issue.number,
                exc,
            )
            return metrics
        finally:
            await self._cleanup_workspace(workspace)

        if harvest_result == "error":
            try:
                await self._platform.add_issue_comment(  # type: ignore[attr-defined]
                    issue.number,
                    f"Fix sessions completed but changes from branch "
                    f"`{spec.branch_name}` could not be merged into `develop`. "
                    "Manual investigation is required.",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to post merge failure comment for issue #%d: %s",
                    issue.number,
                    exc,
                )
            return metrics

        # Close the originating issue with a comment pointing to the branch.
        # When harvest_result is "no_changes", the reviewer confirmed PASS
        # but there are no new commits — the fix is already on develop.
        if harvest_result == "no_changes":
            close_msg = (
                f"Fix verified on branch `{spec.branch_name}`. "
                "No new commits were needed — the fix is already present on `develop`."
            )
        else:
            close_msg = (
                f"Fix complete on branch `{spec.branch_name}`. "
                "Changes have been merged into `develop`. "
                "Create a PR from that branch to land them on `main`."
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
        # Remove the af:fix label so the issue is not re-processed (#295).
        try:
            await self._platform.remove_label(  # type: ignore[attr-defined]
                issue.number,
                "af:fix",
            )
        except Exception as exc:
            logger.warning(
                "Failed to remove af:fix label from issue #%d: %s",
                issue.number,
                exc,
            )
        logger.info(
            "Fix pipeline complete for issue #%d on branch %s",
            issue.number,
            spec.branch_name,
        )
        return metrics

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
