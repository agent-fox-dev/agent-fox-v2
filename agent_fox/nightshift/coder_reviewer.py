"""Coder-reviewer retry/escalation loop for the fix pipeline.

Extracted from fix_pipeline.py to isolate the retry state machine.
Manages the escalation ladder, reviewer parse-fail retry, and
verdict checking in a single cohesive class.

Requirements: 82-REQ-7.1, 82-REQ-8.1, 82-REQ-8.2, 82-REQ-8.3,
              82-REQ-8.4, 82-REQ-8.E1
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.knowledge.audit import AuditEventType
from agent_fox.nightshift.fix_pipeline import FixReviewResult, TriageResult
from agent_fox.nightshift.spec_builder import InMemorySpec
from agent_fox.ui.progress import TaskEvent
from agent_fox.workspace import WorkspaceInfo

logger = logging.getLogger(__name__)


class CoderReviewerLoop:
    """Coder-reviewer retry/escalation state machine.

    Runs coder -> reviewer in a loop with escalation ladder support,
    reviewer parse-fail retry, and verdict checking.  Delegates I/O
    operations (session running, comment posting) to the pipeline.

    Requirements: 82-REQ-7.1, 82-REQ-8.1 through 82-REQ-8.4, 82-REQ-8.E1
    """

    def __init__(self, pipeline: Any) -> None:
        self._pipeline = pipeline

    async def run(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        metrics: Any,
        workspace: WorkspaceInfo,
    ) -> bool:
        """Run the coder-reviewer loop. Returns True on PASS, False on exhaustion."""
        from agent_fox.core.models import ModelTier, resolve_model
        from agent_fox.routing.escalation import EscalationLadder

        p = self._pipeline

        retries_before = getattr(p._config.orchestrator, "retries_before_escalation", 1)
        max_retries = getattr(p._config.orchestrator, "max_retries", 3)

        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=retries_before,
        )

        review_feedback: FixReviewResult | None = None

        for attempt in range(max_retries + 1):
            tier = ladder.current_tier
            model_entry = resolve_model(tier.value)
            model_id: str | None = model_entry.model_id

            await self._run_coder_phase(
                spec,
                triage,
                workspace,
                metrics,
                model_id,
                review_feedback,
                attempt,
            )

            review_result = await self._run_reviewer_phase(
                spec,
                triage,
                workspace,
                metrics,
                attempt,
            )

            review_comment = p._format_review_comment(review_result) + f"\n(run: `{p._run_id}`)"
            await p._post_comment(spec.issue_number, review_comment)

            if review_result.overall_verdict == "PASS":
                return True

            ladder.record_failure()

            if ladder.is_exhausted or attempt >= max_retries:
                await p._post_comment(
                    spec.issue_number,
                    "Fix pipeline exhausted all retries. "
                    "The issue could not be resolved automatically. "
                    f"Manual intervention is required. (run: `{p._run_id}`)",
                )
                return False

            review_feedback = review_result

        return False  # pragma: no cover

    async def _run_coder_phase(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        workspace: WorkspaceInfo,
        metrics: Any,
        model_id: str | None,
        review_feedback: FixReviewResult | None,
        attempt: int,
    ) -> object:
        """Run one coder session, emitting events and tracking metrics."""
        p = self._pipeline

        system_prompt, task_prompt = p._build_coder_prompt(spec, triage, review_feedback=review_feedback)
        node_id = f"fix-issue-{spec.issue_number}:0:coder"
        attempt_suffix = f" (attempt {attempt + 1})" if attempt > 0 else ""
        p._update_spinner(f"Running coder for issue #{spec.issue_number}{attempt_suffix}…")

        t0 = time.monotonic()
        try:
            coder_outcome = await p._run_coder_session(
                workspace,
                spec,
                system_prompt,
                task_prompt,
                model_id=model_id,
            )
            p._accumulate_metrics(metrics, coder_outcome)
            p._emit_session_event(
                coder_outcome,
                "coder",
                p._run_id,
                node_id=node_id,
                attempt=attempt + 1,
            )
            duration = time.monotonic() - t0
            if p._task_callback is not None:
                p._task_callback(TaskEvent(node_id=node_id, status="completed", duration_s=duration, archetype="coder"))
            return coder_outcome
        except Exception as exc:
            duration = time.monotonic() - t0
            emit_audit_event(
                p._sink,
                p._run_id,
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
                archetype="coder",
                payload={
                    "archetype": "coder",
                    "model_id": model_id or p._get_model_id("coder"),
                    "error_message": str(exc),
                    "attempt": attempt + 1,
                },
            )
            if p._task_callback is not None:
                p._task_callback(TaskEvent(node_id=node_id, status="failed", duration_s=duration, archetype="coder"))
            raise

    async def _run_reviewer_phase(
        self,
        spec: InMemorySpec,
        triage: TriageResult,
        workspace: WorkspaceInfo,
        metrics: Any,
        attempt: int,
    ) -> FixReviewResult:
        """Run reviewer session with parse-fail retry. Returns the review result."""
        from agent_fox.session.review_parser import parse_fix_review_output

        p = self._pipeline

        reviewer_system, reviewer_task = p._build_reviewer_prompt(spec, triage)
        reviewer_node_id = f"fix-issue-{spec.issue_number}:0:reviewer"
        p._update_spinner(f"Reviewing fix for issue #{spec.issue_number}…")

        reviewer_outcome = await self._run_single_reviewer(
            workspace,
            spec,
            reviewer_system,
            reviewer_task,
            metrics,
            reviewer_node_id,
            attempt,
        )

        reviewer_response = getattr(reviewer_outcome, "response", "") or ""
        review_result = parse_fix_review_output(
            reviewer_response,
            f"fix-issue-{spec.issue_number}",
            f"fix-issue-{spec.issue_number}:0:reviewer",
        )

        if review_result.is_parse_failure:
            review_result = await self._retry_reviewer_on_parse_failure(
                spec,
                workspace,
                metrics,
                reviewer_system,
                reviewer_task,
                review_result,
                attempt,
            )

        return review_result

    async def _run_single_reviewer(
        self,
        workspace: WorkspaceInfo,
        spec: InMemorySpec,
        system_prompt: str,
        task_prompt: str,
        metrics: Any,
        node_id: str,
        attempt: int,
    ) -> object:
        """Run a single reviewer session, emitting events and tracking metrics."""
        p = self._pipeline

        t0 = time.monotonic()
        try:
            outcome = await p._run_session(
                "reviewer",
                workspace,
                spec=spec,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                mode="fix-review",
            )
            p._accumulate_metrics(metrics, outcome)
            p._emit_session_event(
                outcome,
                "reviewer",
                p._run_id,
                node_id=node_id,
                attempt=attempt + 1,
            )
            duration = time.monotonic() - t0
            if p._task_callback is not None:
                p._task_callback(
                    TaskEvent(node_id=node_id, status="completed", duration_s=duration, archetype="reviewer")
                )
            return outcome
        except Exception as exc:
            duration = time.monotonic() - t0
            emit_audit_event(
                p._sink,
                p._run_id,
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
                archetype="reviewer",
                payload={
                    "archetype": "reviewer",
                    "model_id": p._get_model_id("reviewer"),
                    "error_message": str(exc),
                    "attempt": attempt + 1,
                },
            )
            if p._task_callback is not None:
                p._task_callback(TaskEvent(node_id=node_id, status="failed", duration_s=duration, archetype="reviewer"))
            raise

    async def _retry_reviewer_on_parse_failure(
        self,
        spec: InMemorySpec,
        workspace: WorkspaceInfo,
        metrics: Any,
        reviewer_system: str,
        reviewer_task: str,
        original_result: FixReviewResult,
        attempt: int,
    ) -> FixReviewResult:
        """Retry reviewer once on parse failure. Returns best available result."""
        from agent_fox.session.review_parser import parse_fix_review_output

        p = self._pipeline

        logger.info("Reviewer output unparseable for issue #%d, retrying reviewer", spec.issue_number)
        retry_node_id = f"fix-issue-{spec.issue_number}:0:reviewer_retry"

        t0 = time.monotonic()
        try:
            retry_outcome = await p._run_session(
                "reviewer",
                workspace,
                spec=spec,
                system_prompt=reviewer_system,
                task_prompt=reviewer_task,
                mode="fix-review",
            )
            p._accumulate_metrics(metrics, retry_outcome)
            p._emit_session_event(
                retry_outcome,
                "reviewer",
                p._run_id,
                node_id=retry_node_id,
                attempt=attempt + 1,
            )
            duration = time.monotonic() - t0
            if p._task_callback is not None:
                p._task_callback(
                    TaskEvent(node_id=retry_node_id, status="completed", duration_s=duration, archetype="reviewer")
                )
            retry_response = getattr(retry_outcome, "response", "") or ""
            retry_result = parse_fix_review_output(
                retry_response,
                f"fix-issue-{spec.issue_number}",
                f"fix-issue-{spec.issue_number}:0:reviewer_retry",
            )
            if not retry_result.is_parse_failure:
                return retry_result
            logger.warning("Reviewer retry also unparseable for issue #%d, treating as FAIL", spec.issue_number)
        except Exception as exc:
            duration = time.monotonic() - t0
            emit_audit_event(
                p._sink,
                p._run_id,
                AuditEventType.SESSION_FAIL,
                node_id=retry_node_id,
                archetype="reviewer",
                payload={
                    "archetype": "reviewer",
                    "model_id": p._get_model_id("reviewer"),
                    "error_message": str(exc),
                    "attempt": attempt + 1,
                },
            )
            if p._task_callback is not None:
                p._task_callback(
                    TaskEvent(node_id=retry_node_id, status="failed", duration_s=duration, archetype="reviewer")
                )
            logger.warning("Reviewer retry failed for issue #%d, treating as FAIL", spec.issue_number, exc_info=True)

        return original_result
