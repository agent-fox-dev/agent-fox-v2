"""Session lifecycle: workspace, hooks, prompts, execution, harvest, cleanup.

Handles the full lifecycle of a coding session for a single task graph
node. Extracted from cli/code.py to keep CLI wiring thin.

Requirements: 16-REQ-5.1, 16-REQ-5.E1, 06-REQ-1.1, 06-REQ-2.1,
              05-REQ-1.1, 11-REQ-4.2, 13-REQ-2.1, 13-REQ-7.1
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig, HookConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.core.models import calculate_cost, resolve_model
from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge
from agent_fox.engine.state import SessionRecord
from agent_fox.hooks.hooks import (
    HookContext,
    run_post_session_hooks,
    run_pre_session_hooks,
)
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher
from agent_fox.memory.filter import select_relevant_facts
from agent_fox.memory.memory import load_all_facts
from agent_fox.session.prompt import (
    assemble_context,
    build_system_prompt,
    build_task_prompt,
    select_context_with_causal,
)
from agent_fox.session.session import run_session
from agent_fox.ui.events import ActivityCallback
from agent_fox.workspace.harvester import harvest
from agent_fox.workspace.integration import post_harvest_integrate
from agent_fox.workspace.workspace import (
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
    ensure_develop,
)

logger = logging.getLogger(__name__)


class NodeSessionRunner:
    """Session runner for a single task graph node.

    Created by the session_runner_factory closure. Handles the full
    session lifecycle: workspace creation, hooks, context assembly,
    prompt building, session execution, artifact collection, harvest,
    and cleanup.

    Requirements: 16-REQ-5.1, 16-REQ-5.E1, 06-REQ-1.1, 06-REQ-2.1
    """

    def __init__(
        self,
        node_id: str,
        config: AgentFoxConfig,
        *,
        hook_config: HookConfig | None = None,
        no_hooks: bool = False,
        sink_dispatcher: SinkDispatcher | None = None,
        knowledge_db: KnowledgeDB | None = None,
        activity_callback: ActivityCallback | None = None,
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._hook_config = hook_config
        self._no_hooks = no_hooks
        self._sink = sink_dispatcher
        self._knowledge_db = knowledge_db
        self._activity_callback = activity_callback
        # Parse node_id format: "{spec_name}:{group_number}"
        parts = node_id.rsplit(":", 1)
        self._spec_name = parts[0]
        self._task_group = int(parts[1])

    def _build_prompts(
        self,
        repo_root: Path,
        attempt: int,
        previous_error: str | None,
    ) -> tuple[str, str]:
        """Assemble context and build system/task prompts.

        Loads relevant memory facts from the JSONL store and passes
        them to assemble_context for inclusion in session context.
        When the DuckDB knowledge store is available, enhances context
        with causally-linked facts.

        Requirements: 05-REQ-4.1, 05-REQ-4.2, 13-REQ-7.1
        """
        spec_dir = repo_root / ".specs" / self._spec_name

        # 05-REQ-4.1: Load and select relevant facts for context injection
        memory_facts: list[str] | None = None
        try:
            all_facts = load_all_facts()
            if all_facts:
                relevant = select_relevant_facts(
                    all_facts,
                    self._spec_name,
                    task_keywords=[self._spec_name],
                )
                if relevant:
                    # 13-REQ-7.1: Enhance with causal context if DB available
                    memory_facts = self._enhance_with_causal(relevant)
        except Exception:
            logger.warning(
                "Failed to load memory facts for %s, continuing without",
                self._spec_name,
                exc_info=True,
            )

        context = assemble_context(
            spec_dir,
            self._task_group,
            memory_facts=memory_facts,
        )

        system_prompt = build_system_prompt(
            context=context,
            task_group=self._task_group,
            spec_name=self._spec_name,
        )
        task_prompt = build_task_prompt(
            task_group=self._task_group,
            spec_name=self._spec_name,
        )

        if previous_error and attempt > 1:
            task_prompt = (
                f"{task_prompt}\n\n"
                f"**Note:** This is retry attempt {attempt}. "
                f"The previous attempt failed with:\n"
                f"```\n{previous_error}\n```\n"
                f"Please address this error.\n"
            )

        return system_prompt, task_prompt

    def _enhance_with_causal(
        self,
        relevant_facts: list,
    ) -> list[str]:
        """Enhance keyword-selected facts with causal context.

        When the DuckDB knowledge store is available, uses
        select_context_with_causal() to augment the keyword-matched
        facts with causally-linked facts. Falls back to keyword-only
        content if DB is unavailable.

        Requirements: 13-REQ-7.1, 13-REQ-7.2
        """
        keyword_dicts = [
            {
                "id": f.id,
                "content": f.content,
                "spec_name": f.spec_name,
            }
            for f in relevant_facts
        ]

        if self._knowledge_db is not None:
            try:
                enhanced = select_context_with_causal(
                    self._knowledge_db.connection,
                    self._spec_name,
                    touched_files=[],
                    keyword_facts=keyword_dicts,
                )
                return [f["content"] for f in enhanced]
            except Exception:
                logger.debug(
                    "Causal context enhancement failed, falling back to keyword-only",
                    exc_info=True,
                )

        return [f.content for f in relevant_facts]

    def _build_hook_context(self, workspace: WorkspaceInfo) -> HookContext:
        """Build a HookContext for pre/post-session hooks."""
        return HookContext(
            spec_name=self._spec_name,
            task_group=str(self._task_group),
            workspace=str(workspace.path),
            branch=workspace.branch,
        )

    @staticmethod
    def _read_session_artifacts(workspace: WorkspaceInfo) -> dict | None:
        """Read .session-summary.json from the worktree if it exists.

        Returns the parsed JSON dict or None if the file is absent or
        cannot be parsed.
        """
        summary_path = workspace.path / ".session-summary.json"
        if not summary_path.exists():
            return None
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to read session summary from %s: %s",
                summary_path,
                exc,
            )
            return None

    async def _run_and_harvest(
        self,
        node_id: str,
        attempt: int,
        workspace: WorkspaceInfo,
        system_prompt: str,
        task_prompt: str,
        repo_root: Path,
    ) -> SessionRecord:
        """Execute the session, harvest on success, return a record.

        Handles IntegrationError separately from session failures so
        the orchestrator gets an accurate error message about merge
        problems vs coding problems.

        On success, also extracts knowledge facts from the session
        summary and records the session outcome to sinks.

        Requirements: 05-REQ-1.1, 11-REQ-4.2
        """
        outcome = await run_session(
            workspace=workspace,
            node_id=node_id,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            config=self._config,
            activity_callback=self._activity_callback,
        )

        model_entry = resolve_model(self._config.models.coding)
        cost = calculate_cost(
            outcome.input_tokens,
            outcome.output_tokens,
            model_entry,
        )

        error_message = outcome.error_message
        status = outcome.status

        # 03-REQ-7.1: Harvest changes into develop on success
        touched_files: list[str] = []
        if outcome.status == "completed":
            try:
                touched_files = await harvest(repo_root, workspace)
            except IntegrationError as exc:
                # Coding session succeeded but merge to develop failed.
                # Mark as failed with a clear integration error so the
                # retry can focus on the merge issue, not the coding.
                status = "failed"
                error_message = (
                    f"Session completed but harvest failed: {exc}. "
                    f"The coding work was done — the merge into develop "
                    f"encountered a conflict."
                )
                logger.error(
                    "Harvest failed for %s after successful session: %s",
                    node_id,
                    exc,
                )

        # 19-REQ-3.4: Post-harvest remote integration (after successful harvest)
        if touched_files and status == "completed":
            try:
                await post_harvest_integrate(
                    repo_root=repo_root,
                    workspace=workspace,
                    platform_config=self._config.platform,
                )
            except Exception as exc:
                logger.warning(
                    "Post-harvest integration failed for %s: %s",
                    node_id,
                    exc,
                    exc_info=True,
                )

        sink_outcome = outcome
        if status != outcome.status or error_message != outcome.error_message:
            sink_outcome = dataclasses.replace(
                sink_outcome,
                status=status,
                error_message=error_message,
            )
        if touched_files:
            sink_outcome = dataclasses.replace(
                sink_outcome,
                touched_paths=touched_files,
            )

        # 11-REQ-4.2: Record session outcome to sinks (always, best-effort)
        self._record_session_to_sink(sink_outcome, node_id)

        # 05-REQ-1.1: Extract facts from session summary (on success only)
        if status == "completed":
            summary = self._read_session_artifacts(workspace)
            transcript = (summary or {}).get("summary", "")
            if transcript:
                try:
                    await extract_and_store_knowledge(
                        transcript=transcript,
                        spec_name=self._spec_name,
                        node_id=node_id,
                        memory_extraction_model=self._config.models.memory_extraction,
                        knowledge_db=self._knowledge_db,
                    )
                except Exception:
                    logger.warning(
                        "Knowledge extraction failed for %s, continuing",
                        node_id,
                        exc_info=True,
                    )

        return SessionRecord(
            node_id=node_id,
            attempt=attempt,
            status=status,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            cost=cost,
            duration_ms=outcome.duration_ms,
            error_message=error_message,
            timestamp=datetime.now(UTC).isoformat(),
            model=model_entry.model_id,
            files_touched=touched_files,
        )

    def _record_session_to_sink(
        self,
        outcome: SessionOutcome,
        node_id: str,
    ) -> None:
        """Record a session outcome to the sink dispatcher (best-effort)."""
        if self._sink is None:
            return
        try:
            self._sink.record_session_outcome(outcome)
        except Exception:
            logger.warning(
                "Failed to record session outcome to sink for %s",
                node_id,
                exc_info=True,
            )

    async def execute(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None = None,
    ) -> SessionRecord:
        """Execute a coding session and return a SessionRecord.

        Full lifecycle:
        1. Create isolated worktree
        2. Run pre-session hooks (06-REQ-1.1)
        3. Assemble context, build prompts
        4. Run coding session via claude-code-sdk
        5. Run post-session hooks (06-REQ-2.1)
        6. Read session artifacts (.session-summary.json)
        7. Harvest changes into develop on success (03-REQ-7.1)
        8. Clean up the worktree (03-REQ-2.1)

        16-REQ-5.E1: Catches all exceptions and returns a failed
        SessionRecord so the orchestrator can apply retry logic.
        """
        repo_root = Path.cwd()
        workspace: WorkspaceInfo | None = None

        try:
            # 19-REQ-1.1, 19-REQ-1.6: Ensure develop branch exists
            # and is up-to-date before creating the worktree.
            try:
                await ensure_develop(repo_root)
            except Exception:
                logger.warning(
                    "ensure_develop failed for %s, continuing with "
                    "existing branch state",
                    node_id,
                    exc_info=True,
                )

            workspace = await create_worktree(
                repo_root,
                self._spec_name,
                self._task_group,
            )

            # 06-REQ-1.1: Run pre-session hooks
            if self._hook_config is not None:
                hook_ctx = self._build_hook_context(workspace)
                run_pre_session_hooks(
                    hook_ctx,
                    self._hook_config,
                    no_hooks=self._no_hooks,
                )

            system_prompt, task_prompt = self._build_prompts(
                repo_root,
                attempt,
                previous_error,
            )

            record = await self._run_and_harvest(
                node_id,
                attempt,
                workspace,
                system_prompt,
                task_prompt,
                repo_root,
            )

            # 06-REQ-2.1: Run post-session hooks
            if self._hook_config is not None:
                hook_ctx = self._build_hook_context(workspace)
                try:
                    run_post_session_hooks(
                        hook_ctx,
                        self._hook_config,
                        no_hooks=self._no_hooks,
                    )
                except Exception:
                    logger.warning(
                        "Post-session hooks failed for %s",
                        node_id,
                        exc_info=True,
                    )

            # Read session artifacts before worktree cleanup
            summary = self._read_session_artifacts(workspace)
            if summary:
                logger.info(
                    "Session summary for %s: %s",
                    node_id,
                    summary.get("summary", ""),
                )

            return record

        except Exception as exc:
            logger.error(
                "Session runner failed for %s (attempt %d): %s",
                node_id,
                attempt,
                exc,
            )
            return SessionRecord(
                node_id=node_id,
                attempt=attempt,
                status="failed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=str(exc),
                timestamp=datetime.now(UTC).isoformat(),
            )

        finally:
            # 03-REQ-2.1: Always clean up the worktree
            if workspace is not None:
                try:
                    await destroy_worktree(repo_root, workspace)
                except Exception:
                    logger.warning(
                        "Failed to clean up worktree for %s",
                        node_id,
                        exc_info=True,
                    )
