"""Fix pipeline: issue-to-branch workflow.

After the archetype sessions complete, the fix branch is harvested into
develop and pushed to origin via post_harvest_integrate.  PR creation was
removed from the platform layer (spec 65, 65-REQ-4.2).  The originating
issue is closed with a comment pointing to the fix branch.

Requirements: 61-REQ-6.1, 61-REQ-6.2, 61-REQ-6.3, 61-REQ-6.4,
              61-REQ-6.E1, 61-REQ-6.E2
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from agent_fox.nightshift.spec_builder import InMemorySpec, build_in_memory_spec
from agent_fox.platform.github import IssueResult
from agent_fox.ui.progress import ActivityCallback, TaskCallback, TaskEvent

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

    Drives an issue through investigation, coding, and review using
    the full archetype pipeline, then posts a completion comment with
    the branch name so the user can open a PR manually.

    Requirements: 61-REQ-6.1 through 61-REQ-6.4
    """

    def __init__(
        self,
        config: object,
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
        *args: object,
        **kwargs: object,
    ) -> object:
        """Run a single archetype session for an issue fix.

        Uses run_session() with prompts derived from the InMemorySpec.
        Subclasses or tests can override this for mock execution.

        Requirements: 61-REQ-6.3
        """
        from agent_fox.session.prompt import build_system_prompt
        from agent_fox.session.session import run_session
        from agent_fox.workspace.worktree import WorkspaceInfo

        spec: InMemorySpec = kwargs["spec"]  # type: ignore[assignment]
        repo_root = Path.cwd()

        # Build a minimal workspace on the fix branch.
        # The branch must already exist before this call.
        workspace = WorkspaceInfo(
            path=repo_root,
            branch=spec.branch_name,
            spec_name=f"fix-issue-{spec.issue_number}",
            task_group=0,
        )

        # Build the archetype-specific system prompt.
        system_prompt = build_system_prompt(
            context=spec.system_context,
            task_group=0,
            spec_name=f"fix-issue-{spec.issue_number}",
            archetype=archetype,
        )

        node_id = f"fix-issue-{spec.issue_number}:0:{archetype}"

        return await run_session(
            workspace=workspace,
            node_id=node_id,
            system_prompt=system_prompt,
            task_prompt=spec.task_prompt,
            config=self._config,  # type: ignore[arg-type]
            activity_callback=self._activity_callback,
        )

    async def _create_fix_branch(self, branch_name: str) -> None:
        """Create a git branch for the fix from develop HEAD.

        Requirements: 61-REQ-6.2
        """
        from agent_fox.workspace.git import run_git

        repo_root = Path.cwd()
        rc, _stdout, _stderr = await run_git(
            ["checkout", "-b", branch_name, "develop"],
            cwd=repo_root,
            check=False,
        )
        if rc != 0:
            # Branch may already exist — try to check it out
            await run_git(
                ["checkout", branch_name],
                cwd=repo_root,
                check=False,
            )

    def _accumulate_metrics(self, metrics: FixMetrics, outcome: object) -> None:
        """Add a SessionOutcome's tokens to the running metrics."""
        metrics.input_tokens += getattr(outcome, "input_tokens", 0)
        metrics.output_tokens += getattr(outcome, "output_tokens", 0)
        metrics.cache_read_input_tokens += getattr(outcome, "cache_read_input_tokens", 0)
        metrics.cache_creation_input_tokens += getattr(outcome, "cache_creation_input_tokens", 0)
        metrics.sessions_run += 1

    async def process_issue(
        self,
        issue: IssueResult,
        issue_body: str = "",
    ) -> FixMetrics:
        """Process an af:fix issue through the full pipeline.

        Returns FixMetrics with aggregated token counts from all sessions.

        Requirements: 61-REQ-6.1, 61-REQ-6.E2
        """
        metrics = FixMetrics()

        # 61-REQ-6.E2: reject empty issue body
        if not issue_body or not issue_body.strip():
            await self._platform.add_issue_comment(  # type: ignore[union-attr]
                issue.number,
                "Insufficient detail in issue body to build a fix. "
                "Please add more detail describing the problem and expected behavior.",
            )
            return metrics

        spec = build_in_memory_spec(issue, issue_body)

        # 61-REQ-6.2: create the fix branch from develop HEAD
        await self._create_fix_branch(spec.branch_name)

        # Post progress comment
        await self._platform.add_issue_comment(  # type: ignore[union-attr]
            issue.number,
            f"Starting fix session on branch `{spec.branch_name}`...",
        )

        try:
            # 61-REQ-6.3: full archetype pipeline
            # 81-REQ-5.3: emit TaskEvent per archetype with timing
            for archetype in ("skeptic", "coder", "verifier"):
                node_id = f"fix-issue-{spec.issue_number}:0:{archetype}"
                t0 = time.monotonic()
                try:
                    outcome = await self._run_session(archetype, spec=spec)
                    self._accumulate_metrics(metrics, outcome)
                    duration = time.monotonic() - t0
                    if self._task_callback is not None:
                        self._task_callback(
                            TaskEvent(
                                node_id=node_id,
                                status="completed",
                                duration_s=duration,
                                archetype=archetype,
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
                                archetype=archetype,
                            )
                        )
                    raise
        except Exception as exc:
            # 61-REQ-6.E1: post comment on failure
            await self._platform.add_issue_comment(  # type: ignore[union-attr]
                issue.number,
                f"Fix session failed: {exc}\n\nBranch: `{spec.branch_name}`",
            )
            logger.warning(
                "Fix session failed for issue #%d: %s",
                issue.number,
                exc,
            )
            return metrics

        # Harvest fix branch into develop and push to origin (65-REQ-3.2).
        if not await self._harvest_and_push(spec):
            await self._platform.add_issue_comment(  # type: ignore[union-attr]
                issue.number,
                f"Fix sessions completed but failed to merge branch "
                f"`{spec.branch_name}` into `develop`. "
                "Manual merge is required.",
            )
            return metrics

        # Close the originating issue with a comment pointing to the branch.
        # PR creation is no longer done via the platform layer (65-REQ-4.2).
        await self._platform.close_issue(  # type: ignore[union-attr]
            issue.number,
            f"Fix complete on branch `{spec.branch_name}`. "
            "Changes have been merged into `develop`. "
            "Create a PR from that branch to land them on `main`.",
        )
        logger.info(
            "Fix pipeline complete for issue #%d on branch %s",
            issue.number,
            spec.branch_name,
        )
        return metrics

    async def _restore_develop(self) -> None:
        """Check out develop to leave the repo in a clean state."""
        from agent_fox.workspace.git import run_git

        await run_git(["checkout", "develop"], cwd=Path.cwd(), check=False)

    async def _harvest_and_push(self, spec: InMemorySpec) -> bool:
        """Harvest the fix branch into develop and push to origin.

        Returns True on success, False on failure.  Always restores the
        working tree to ``develop`` afterwards.
        """
        from agent_fox.workspace.harvest import harvest, post_harvest_integrate
        from agent_fox.workspace.worktree import WorkspaceInfo

        repo_root = Path.cwd()
        workspace = WorkspaceInfo(
            path=repo_root,
            branch=spec.branch_name,
            spec_name=f"fix-issue-{spec.issue_number}",
            task_group=0,
        )
        try:
            await harvest(repo_root, workspace)
            await post_harvest_integrate(repo_root, workspace)
        except Exception as exc:
            logger.warning(
                "Harvest/push failed for issue #%d on branch %s: %s",
                spec.issue_number,
                spec.branch_name,
                exc,
            )
            await self._restore_develop()
            return False
        await self._restore_develop()
        return True
