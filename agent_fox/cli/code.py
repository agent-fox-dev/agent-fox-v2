"""CLI code command: execute the task plan via the orchestrator.

Thin CLI wrapper that connects the Click command group to the
orchestrator engine. Reads configuration, applies CLI overrides,
constructs the orchestrator, runs execution, prints a summary,
and exits with a meaningful code.

Requirements: 16-REQ-1.1 through 16-REQ-5.2
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from agent_fox.core.config import AgentFoxConfig, HookConfig, OrchestratorConfig
from agent_fox.core.errors import AgentFoxError, IntegrationError
from agent_fox.core.models import calculate_cost, resolve_model
from agent_fox.engine.orchestrator import Orchestrator
from agent_fox.engine.state import ExecutionState, SessionRecord
from agent_fox.hooks.runner import (
    HookContext,
    run_post_session_hooks,
    run_pre_session_hooks,
)
from agent_fox.knowledge.causal import store_causal_links
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.sink import SessionOutcome as SinkSessionOutcome
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.memory.extraction import (
    enrich_extraction_with_causal,
    extract_facts,
    parse_causal_links,
)
from agent_fox.memory.filter import select_relevant_facts
from agent_fox.memory.store import append_facts, load_all_facts
from agent_fox.reporting.formatters import format_tokens
from agent_fox.session.context import assemble_context, select_context_with_causal
from agent_fox.session.prompt import build_system_prompt, build_task_prompt
from agent_fox.session.runner import SessionOutcome, run_session
from agent_fox.workspace.harvester import harvest
from agent_fox.workspace.worktree import (
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
)

logger = logging.getLogger(__name__)

# Exit code mapping: run_status -> shell exit code
# 16-REQ-4.1 through 16-REQ-4.5, 16-REQ-4.E1
_EXIT_CODES: dict[str, int] = {
    "completed": 0,
    "stalled": 2,
    "cost_limit": 3,
    "session_limit": 3,
    "interrupted": 130,
}


def _exit_code_for_status(run_status: str) -> int:
    """Map a run status string to a shell exit code.

    Returns the documented exit code for known statuses, or 1 for
    any unrecognized status.

    Requirements: 16-REQ-4.1 through 16-REQ-4.5, 16-REQ-4.E1
    """
    return _EXIT_CODES.get(run_status, 1)


def _apply_overrides(
    config: OrchestratorConfig,
    parallel: int | None,
    max_cost: float | None,
    max_sessions: int | None,
) -> OrchestratorConfig:
    """Return a new OrchestratorConfig with CLI overrides applied.

    Only overrides fields that were explicitly provided (not None).
    All non-overridden fields are preserved from the original config.

    Requirements: 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5
    """
    overrides: dict[str, object] = {}
    if parallel is not None:
        overrides["parallel"] = parallel
    if max_cost is not None:
        overrides["max_cost"] = max_cost
    if max_sessions is not None:
        overrides["max_sessions"] = max_sessions
    if overrides:
        return config.model_copy(update=overrides)
    return config


def _count_by_status(node_states: dict[str, str]) -> dict[str, int]:
    """Count tasks grouped by their status value."""
    counts: dict[str, int] = {}
    for status in node_states.values():
        counts[status] = counts.get(status, 0) + 1
    return counts


def _print_summary(state: ExecutionState) -> None:
    """Print a compact execution summary.

    Displays task counts, token usage, cost, and run status in the
    same compact text style used by ``agent-fox status``.

    Requirements: 16-REQ-3.1, 16-REQ-3.2, 16-REQ-3.E1
    """
    total = len(state.node_states)

    # 16-REQ-3.E1: empty plan
    if total == 0:
        click.echo("No tasks to execute.")
        return

    counts = _count_by_status(state.node_states)
    done = counts.get("completed", 0)
    in_progress = counts.get("in_progress", 0)
    pending = counts.get("pending", 0)
    failed = counts.get("failed", 0) + counts.get("blocked", 0)

    parts = [f"{done}/{total} done"]
    if in_progress:
        parts.append(f"{in_progress} in progress")
    if pending:
        parts.append(f"{pending} pending")
    if failed:
        parts.append(f"{failed} failed")

    click.echo(f"Tasks:  {', '.join(parts)}")
    click.echo(
        f"Tokens: {format_tokens(state.total_input_tokens)} in / "
        f"{format_tokens(state.total_output_tokens)} out"
    )
    click.echo(f"Cost:   ${state.total_cost:.2f}")
    click.echo(f"Status: {state.run_status}")


class _NodeSessionRunner:
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
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._hook_config = hook_config
        self._no_hooks = no_hooks
        self._sink = sink_dispatcher
        self._knowledge_db = knowledge_db
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

        # 11-REQ-4.2: Record session outcome to sinks (always, best-effort)
        self._record_session_to_sink(outcome, node_id, touched_files=touched_files)

        # 05-REQ-1.1: Extract facts from session summary (on success only)
        if status == "completed":
            await self._extract_session_knowledge(workspace, node_id)

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
        )

    def _record_session_to_sink(
        self,
        outcome: SessionOutcome,
        node_id: str,
        touched_files: list[str] | None = None,
    ) -> None:
        """Record a session outcome to the sink dispatcher (best-effort)."""
        if self._sink is None:
            return
        try:
            sink_outcome = SinkSessionOutcome(
                spec_name=outcome.spec_name,
                task_group=str(outcome.task_group),
                node_id=node_id,
                touched_paths=touched_files or outcome.files_touched,
                status=outcome.status,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                duration_ms=outcome.duration_ms,
            )
            self._sink.record_session_outcome(sink_outcome)
        except Exception:
            logger.warning(
                "Failed to record session outcome to sink for %s",
                node_id,
                exc_info=True,
            )

    async def _extract_session_knowledge(
        self,
        workspace: WorkspaceInfo,
        node_id: str,
    ) -> None:
        """Extract facts and causal links from the session (best-effort).

        Uses .session-summary.json as the transcript source. Extracted
        facts are appended to the JSONL store. If DuckDB is available,
        also extracts and stores causal links between new and prior facts.

        Requirements: 05-REQ-1.1, 05-REQ-1.E1, 13-REQ-2.1, 13-REQ-2.2
        """
        summary = self._read_session_artifacts(workspace)
        if not summary:
            logger.debug(
                "No session summary for %s, skipping extraction",
                node_id,
            )
            return

        transcript = summary.get("summary", "")
        if not transcript:
            return

        try:
            model_name = self._config.models.memory_extraction
            facts = await extract_facts(
                transcript, self._spec_name, model_name, session_id=node_id
            )
            if facts:
                append_facts(facts)
                logger.info(
                    "Extracted %d facts from session %s",
                    len(facts),
                    node_id,
                )
                # 13-REQ-2.1: Extract causal links if DuckDB available
                self._extract_causal_links(facts, node_id)
        except Exception:
            logger.warning(
                "Fact extraction failed for %s, continuing",
                node_id,
                exc_info=True,
            )

    def _extract_causal_links(
        self,
        new_facts: list,
        node_id: str,
    ) -> None:
        """Extract and store causal links between new and prior facts.

        Loads prior facts, builds a causal extraction prompt, sends
        it to the LLM, parses causal links from the response, and
        stores them in the DuckDB fact_causes table.

        Best-effort — failures are logged only.

        Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-3.1
        """
        if self._knowledge_db is None:
            return

        try:
            prior_facts = load_all_facts()
            all_dicts = [{"id": f.id, "content": f.content} for f in prior_facts]
            # Include new facts so the LLM can link them
            for f in new_facts:
                all_dicts.append({"id": f.id, "content": f.content})

            if len(all_dicts) < 2:
                return

            # Build the new-facts summary as the base prompt
            new_summary = "\n".join(f"- [{f.id}] {f.content}" for f in new_facts)

            # Enrich with causal extraction instructions
            prompt = enrich_extraction_with_causal(new_summary, all_dicts)

            # Call the LLM for causal analysis
            import anthropic

            model_entry = resolve_model(self._config.models.memory_extraction)
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=model_entry.model_id,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = getattr(response.content[0], "text", "[]")
            links = parse_causal_links(raw_text)
            if links:
                stored = store_causal_links(self._knowledge_db.connection, links)
                logger.info(
                    "Stored %d causal links for session %s",
                    stored,
                    node_id,
                )
        except Exception:
            logger.debug(
                "Causal link extraction failed for %s, continuing",
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


@click.command("code")
@click.option(
    "--parallel",
    type=int,
    default=None,
    help="Override parallelism (1-8)",
)
@click.option(
    "--no-hooks",
    is_flag=True,
    default=False,
    help="Skip all hook scripts",
)
@click.option(
    "--max-cost",
    type=float,
    default=None,
    help="Cost ceiling in USD",
)
@click.option(
    "--max-sessions",
    type=int,
    default=None,
    help="Session count limit",
)
@click.pass_context
def code_cmd(
    ctx: click.Context,
    parallel: int | None,
    no_hooks: bool,
    max_cost: float | None,
    max_sessions: int | None,
) -> None:
    """Execute the task plan."""
    # 16-REQ-1.2: load config from Click context
    config = ctx.obj["config"]

    # 16-REQ-1.E1: check plan file exists
    plan_path = Path(".agent-fox/plan.json")
    if not plan_path.exists():
        click.echo(
            "Error: Plan file not found. "
            "Run `agent-fox plan` first to generate a plan.",
            err=True,
        )
        sys.exit(1)

    state_path = Path(".agent-fox/state.jsonl")

    # 16-REQ-2.5: apply CLI overrides to OrchestratorConfig
    orch_config = _apply_overrides(
        config.orchestrator,
        parallel,
        max_cost,
        max_sessions,
    )

    # Session runner factory (16-REQ-5.1, 16-REQ-5.2)
    full_config: AgentFoxConfig = config
    hook_cfg: HookConfig | None = config.hooks

    # 11-REQ-4.2: Create DuckDB sink for session outcome recording
    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(config.knowledge)
    if knowledge_db is not None:
        sink_dispatcher.add(DuckDBSink(knowledge_db.connection))

    def session_runner_factory(node_id: str) -> _NodeSessionRunner:
        """Create a session runner for the given node.

        Parses the node_id to extract spec_name and task_group, then
        returns a runner configured with the project's AgentFoxConfig,
        hook config, and task-specific prompts.

        16-REQ-5.E1: If construction fails, the runner's execute()
        method will catch and report the failure as a session error.
        """
        return _NodeSessionRunner(
            node_id,
            full_config,
            hook_config=hook_cfg,
            no_hooks=no_hooks,
            sink_dispatcher=sink_dispatcher,
            knowledge_db=knowledge_db,
        )

    try:
        # 16-REQ-1.3: construct Orchestrator
        orchestrator = Orchestrator(
            orch_config,
            plan_path=plan_path,
            state_path=state_path,
            session_runner_factory=session_runner_factory,
            hook_config=config.hooks,
            specs_dir=Path(".specs"),
            no_hooks=no_hooks,
        )

        # 16-REQ-1.4: execute via asyncio.run()
        state: ExecutionState = asyncio.run(orchestrator.run())

    except AgentFoxError as exc:
        logger.debug("Execution failed", exc_info=True)
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        # 16-REQ-1.E2: unexpected exceptions
        logger.debug("Unexpected error during execution", exc_info=True)
        click.echo(f"Error: unexpected error: {exc}", err=True)
        sys.exit(1)
    finally:
        # Clean up knowledge store connection
        sink_dispatcher.close()
        if knowledge_db is not None:
            knowledge_db.close()

    # 16-REQ-3.1: print summary
    _print_summary(state)

    # 16-REQ-4.*: exit with appropriate code
    exit_code = _exit_code_for_status(state.run_status)
    if exit_code != 0:
        sys.exit(exit_code)
