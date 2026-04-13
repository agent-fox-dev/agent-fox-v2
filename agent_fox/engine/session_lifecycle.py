"""Session lifecycle: workspace, hooks, prompts, execution, harvest, cleanup.

Handles the full lifecycle of a coding session for a single task graph
node. Extracted from cli/code.py to keep CLI wiring thin.

Requirements: 16-REQ-5.1, 16-REQ-5.E1, 06-REQ-1.1, 06-REQ-2.1,
              05-REQ-1.1, 11-REQ-4.2, 13-REQ-2.1, 13-REQ-7.1,
              40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-11.3,
              05-REQ-4.1, 05-REQ-4.2, 42-REQ-3.2, 53-REQ-5.1
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig, HookConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.core.models import ModelTier, calculate_cost, resolve_model
from agent_fox.core.node_id import parse_node_id
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts
from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge
from agent_fox.engine.review_persistence import (
    persist_review_findings,
    record_session_to_sink,
)
from agent_fox.engine.sdk_params import (
    clamp_instances,
    resolve_fallback_model,
    resolve_max_budget,
    resolve_max_turns,
    resolve_model_tier,
    resolve_security_config,
    resolve_thinking,
)
from agent_fox.engine.state import SessionRecord
from agent_fox.hooks.hooks import (
    HookContext,
    run_post_session_hooks,
    run_pre_session_hooks,
)
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.embeddings import EmbeddingGenerator
from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.search import SearchResult, VectorSearch
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher
from agent_fox.knowledge.store import load_all_facts
from agent_fox.session.context import select_context_with_causal
from agent_fox.session.prompt import (
    assemble_context,
    build_system_prompt,
    build_task_prompt,
)
from agent_fox.session.session import run_session
from agent_fox.spec.parser import _GROUP_PATTERN, _SUBTASK_PATTERN, parse_tasks
from agent_fox.ui.progress import ActivityCallback
from agent_fox.workspace import (
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
    ensure_develop,
)
from agent_fox.workspace.harvest import harvest, post_harvest_integrate

logger = logging.getLogger(__name__)


def extract_subtask_descriptions(spec_dir: Path, task_group: int) -> list[str]:
    """Extract the first non-metadata bullet from each subtask in a task group.

    Scans tasks.md line-by-line: locates the target task group, then iterates
    its body to find each subtask line (matching _SUBTASK_PATTERN) and captures
    the first bullet whose text does not start with '_'.

    We scan the raw file rather than using TaskGroupDef.body because
    parse_tasks() strips the body string, which removes leading whitespace
    from the first line and causes _SUBTASK_PATTERN (which requires ^\\s+) to
    miss the first subtask.

    Args:
        spec_dir: Path to the spec folder (e.g., .specs/12_rate_limiting/).
        task_group: The task group number to extract from.

    Returns:
        List of description strings. Empty if tasks.md is missing, the group
        is not found, or no subtasks have non-metadata bullets.

    Requirements: 94-REQ-1.1, 94-REQ-1.2, 94-REQ-1.E1, 94-REQ-1.E2
    """
    tasks_path = spec_dir / "tasks.md"
    if not tasks_path.exists():
        return []

    try:
        lines = tasks_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        logger.debug("extract_subtask_descriptions: failed to read %s", tasks_path, exc_info=True)
        return []

    # Verify the group exists by also parsing (cheap; validates group number)
    try:
        groups = parse_tasks(tasks_path)
    except Exception:
        logger.debug("extract_subtask_descriptions: failed to parse %s", tasks_path, exc_info=True)
        return []

    if not any(g.number == task_group for g in groups):
        return []

    descriptions: list[str] = []
    in_target_group = False
    in_subtask = False
    found_first = False

    for line in lines:
        group_match = _GROUP_PATTERN.match(line)
        if group_match:
            group_num = int(group_match.group(3))
            if group_num == task_group:
                in_target_group = True
                in_subtask = False
                found_first = False
            elif in_target_group:
                # Reached the next top-level group — stop
                break
            continue

        if not in_target_group:
            continue

        if _SUBTASK_PATTERN.match(line):
            # Starting a new subtask — reset the "found first bullet" flag
            in_subtask = True
            found_first = False
            continue

        if in_subtask and not found_first:
            stripped = line.strip()
            if stripped.startswith("- "):
                bullet_text = stripped[2:].strip()
                if not bullet_text.startswith("_"):
                    # First non-metadata bullet for this subtask
                    descriptions.append(bullet_text)
                    found_first = True

    return descriptions


async def _capture_develop_head(repo_root: Path) -> str:
    """Return the current SHA of the develop branch HEAD.

    Returns empty string if git rev-parse fails.

    Requirements: 35-REQ-1.1, 35-REQ-1.E1
    """
    from agent_fox.workspace.git import run_git

    try:
        rc, stdout, _stderr = await run_git(
            ["rev-parse", "develop"],
            cwd=repo_root,
            check=False,
        )
        if rc != 0:
            logger.warning(
                "git rev-parse develop failed (returncode %d) in %s",
                rc,
                repo_root,
            )
            return ""
        return stdout.strip()
    except Exception as exc:
        logger.warning(
            "Failed to capture develop HEAD in %s: %s",
            repo_root,
            exc,
        )
        return ""


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
        archetype: str = "coder",
        mode: str | None = None,
        instances: int = 1,
        hook_config: HookConfig | None = None,
        no_hooks: bool = False,
        sink_dispatcher: SinkDispatcher | None = None,
        knowledge_db: KnowledgeDB,
        activity_callback: ActivityCallback | None = None,
        assessed_tier: ModelTier | None = None,
        run_id: str = "",
        fact_cache: dict[str, RankedFactCache] | None = None,
        timeout_override: int | None = None,
        max_turns_override: int | None = None,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._archetype = archetype
        self._mode = mode  # 97-REQ-5.3: mode for per-mode configuration resolution
        self._instances = clamp_instances(archetype, instances, mode=mode)
        self._hook_config = hook_config
        self._no_hooks = no_hooks
        self._sink = sink_dispatcher
        self._knowledge_db = knowledge_db
        self._activity_callback = activity_callback
        self._run_id = run_id
        self._fact_cache = fact_cache
        # 75-REQ-3.5: Per-node timeout/turns overrides from timeout-aware escalation
        self._timeout_override = timeout_override
        self._max_turns_override = max_turns_override
        # 94-REQ-6.1, 94-REQ-6.2: Optional shared embedding generator for cross-spec retrieval
        self._embedder = embedder
        parsed = parse_node_id(node_id)
        self._spec_name = parsed.spec_name
        self._task_group = parsed.group_number

        # 30-REQ-7.2: Use assessed tier from adaptive routing if provided,
        # otherwise fall back to static resolution (26-REQ-4.4, 97-REQ-5.3).
        if assessed_tier is not None:
            self._resolved_model_id = resolve_model(assessed_tier.value).model_id
        else:
            self._resolved_model_id = resolve_model(
                resolve_model_tier(self._config, self._archetype, mode=self._mode)
            ).model_id
        self._resolved_security = resolve_security_config(self._config, self._archetype, mode=self._mode)

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
            relevant = self._load_relevant_facts()
            # 94-REQ-3.2: Merge with cross-spec facts before causal enhancement
            # (also runs when relevant is empty, so cross-spec can provide facts)
            merged = self._retrieve_cross_spec_facts(spec_dir, relevant)
            if merged:
                # 13-REQ-7.1: Enhance with causal context if DB available
                memory_facts = self._enhance_with_causal(merged)
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
            conn=self._knowledge_db.connection,
            project_root=Path.cwd(),
        )

        system_prompt = build_system_prompt(
            context=context,
            task_group=self._task_group,
            spec_name=self._spec_name,
            archetype=self._archetype,
        )
        task_prompt = build_task_prompt(
            task_group=self._task_group,
            spec_name=self._spec_name,
            archetype=self._archetype,
        )

        if previous_error and attempt > 1:
            safe_error = sanitize_prompt_content(previous_error, label="previous-error")
            task_prompt = (
                f"{task_prompt}\n\n"
                f"**Note:** This is retry attempt {attempt}. "
                f"The previous attempt failed with:\n"
                f"{safe_error}\n"
                f"Please address this error.\n"
            )

        # 53-REQ-5.1: Inject active critical/major review findings for coder
        # retries so the coder can address identified issues.
        if self._archetype == "coder" and attempt > 1:
            retry_context = self._build_retry_context(self._spec_name)
            if retry_context:
                task_prompt = f"{retry_context}\n\n{task_prompt}"

        return system_prompt, task_prompt

    def _load_relevant_facts(self) -> list:
        """Load relevant facts, using the pre-computed cache when available.

        Requirements: 42-REQ-3.2, 42-REQ-3.3, 42-REQ-3.4
        """
        return load_relevant_facts(
            self._knowledge_db,
            self._spec_name,
            self._config.knowledge.confidence_threshold,
            fact_cache=self._fact_cache,
        )

    def _enhance_with_causal(
        self,
        relevant_facts: list,
    ) -> list[str]:
        """Enhance keyword-selected facts with causal context.

        Requirements: 13-REQ-7.1, 13-REQ-7.2, 38-REQ-2.1, 38-REQ-2.3
        """
        return enhance_with_causal(
            self._knowledge_db,
            self._spec_name,
            relevant_facts,
        )

    def _retrieve_cross_spec_facts(
        self,
        spec_dir: Path,
        relevant_facts: list[Fact],
    ) -> list[Fact]:
        """Retrieve and merge cross-spec facts via vector similarity search.

        Extracts subtask descriptions from the current task group, embeds them,
        searches across all facts, and merges with the spec-specific facts
        (deduplicating by fact ID). Returns the merged list. If any step fails
        or cross-spec retrieval is disabled, returns relevant_facts unchanged.

        Args:
            spec_dir: Path to the current spec folder.
            relevant_facts: Spec-specific facts from _load_relevant_facts().

        Returns:
            Merged fact list (spec-specific + cross-spec, deduplicated by ID).

        Requirements: 94-REQ-2.1, 94-REQ-2.2, 94-REQ-3.1, 94-REQ-3.2,
                      94-REQ-4.2, 94-REQ-5.1, 94-REQ-6.2
        """
        # 94-REQ-6.2: Skip if no embedder provided
        if self._embedder is None:
            logger.debug(
                "Cross-spec retrieval skipped for %s: no embedder",
                self._spec_name,
            )
            return relevant_facts

        # 94-REQ-4.2: Skip if cross_spec_top_k is 0 (disabled)
        top_k = self._config.knowledge.cross_spec_top_k
        if top_k == 0:
            logger.debug(
                "Cross-spec retrieval skipped for %s: cross_spec_top_k=0",
                self._spec_name,
            )
            return relevant_facts

        try:
            # 94-REQ-1.1: Extract subtask descriptions
            descriptions = extract_subtask_descriptions(spec_dir, self._task_group)
            if not descriptions:
                logger.debug(
                    "Cross-spec retrieval skipped for %s: no subtask descriptions",
                    self._spec_name,
                )
                return relevant_facts

            # 94-REQ-2.1: Concatenate and embed
            query = "\n".join(descriptions)
            embedding = self._embedder.embed_text(query)

            # 94-REQ-2.E1: Skip if embedding failed
            if embedding is None:
                logger.debug(
                    "Cross-spec retrieval skipped for %s: embed_text returned None",
                    self._spec_name,
                )
                return relevant_facts

            # 94-REQ-2.2: Vector search across all facts
            vs = VectorSearch(self._knowledge_db.connection, self._config.knowledge)
            results = vs.search(embedding, top_k=top_k, exclude_superseded=True)

            # 94-REQ-2.E2: Skip merge if no results
            if not results:
                return relevant_facts

            # 94-REQ-3.1: Merge and deduplicate by ID
            merged = merge_cross_spec_facts(relevant_facts, results)
            added = len(merged) - len(relevant_facts)
            logger.debug(
                "Cross-spec retrieval added %d facts for %s group %d",
                added,
                self._spec_name,
                self._task_group,
            )
            return merged

        except Exception:
            # 94-REQ-5.1: Graceful degradation — never break session startup
            logger.debug(
                "Cross-spec retrieval skipped for %s: exception in pipeline",
                self._spec_name,
                exc_info=True,
            )
            return relevant_facts

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

    def _build_fallback_input(
        self,
        workspace: WorkspaceInfo,
        node_id: str,
    ) -> str:
        """Construct fallback extraction input from session metadata.

        Returns a structured text block with spec name, task group,
        node ID, and commit diff. Returns empty string if no meaningful
        metadata is available.

        The ``## Changes`` section is omitted when no commits exist.

        Requirements: 52-REQ-1.2, 52-REQ-1.E1
        """
        import subprocess

        parts = [
            "# Session Knowledge Extraction",
            "",
            f"Spec: {self._spec_name}",
            f"Task Group: {self._task_group}",
            f"Node ID: {node_id}",
        ]

        # Try to get commit diff from the worktree
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--", ".", ":!.agent-fox/"],
                cwd=workspace.path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff = result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            diff = ""

        if diff:
            safe_diff = sanitize_prompt_content(diff, label="diff", max_chars=50_000)
            parts.extend(["", "## Changes", "", safe_diff])

        return "\n".join(parts)

    async def _execute_session(
        self,
        node_id: str,
        workspace: WorkspaceInfo,
        system_prompt: str,
        task_prompt: str,
    ) -> SessionOutcome:
        """Resolve SDK params and run the coding session.

        Requirements: 56-REQ-1.2, 56-REQ-2.2, 56-REQ-3.2, 56-REQ-4.2,
                      75-REQ-3.5
        """
        # 75-REQ-3.5: Apply per-node overrides when available, otherwise
        # fall back to config-based resolution.
        if self._max_turns_override is not None:
            resolved_max_turns: int | None = self._max_turns_override
        else:
            resolved_max_turns = resolve_max_turns(self._config, self._archetype)
        resolved_thinking = resolve_thinking(self._config, self._archetype)
        resolved_fallback = resolve_fallback_model(self._config)
        resolved_budget = resolve_max_budget(self._config)

        # Claude CLI rejects fallback_model when it equals the main model.
        if resolved_fallback and resolved_fallback == self._resolved_model_id:
            resolved_fallback = None

        logger.info(
            "Session %s: max_turns=%s, max_budget_usd=%s, fallback_model=%s, thinking=%s, timeout_override=%s",
            node_id,
            resolved_max_turns,
            resolved_budget,
            resolved_fallback,
            resolved_thinking,
            self._timeout_override,
        )

        return await run_session(
            workspace=workspace,
            node_id=node_id,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            config=self._config,
            activity_callback=self._activity_callback,
            model_id=self._resolved_model_id,
            security_config=self._resolved_security,
            sink_dispatcher=self._sink,
            run_id=self._run_id,
            max_turns=resolved_max_turns,
            max_budget_usd=resolved_budget,
            fallback_model=resolved_fallback,
            thinking=resolved_thinking,
            session_timeout=self._timeout_override,
            archetype=self._archetype,
        )

    async def _harvest_and_integrate(
        self,
        node_id: str,
        outcome: SessionOutcome,
        workspace: WorkspaceInfo,
        repo_root: Path,
    ) -> tuple[str, str | None, list[str]]:
        """Harvest changes on success and run post-harvest integration.

        Returns (status, error_message, touched_files).

        Requirements: 03-REQ-7.1, 19-REQ-3.4, 35-REQ-1.1,
                      40-REQ-11.1, 40-REQ-11.2
        """
        error_message = outcome.error_message
        status = outcome.status
        touched_files: list[str] = []

        if outcome.status != "completed":
            return status, error_message, touched_files

        # 03-REQ-7.1: Harvest changes into develop on success
        try:
            touched_files = await harvest(repo_root, workspace)
            # 40-REQ-11.1: Emit git.merge after successful harvest
            if touched_files:
                emit_audit_event(
                    self._sink,
                    self._run_id,
                    AuditEventType.GIT_MERGE,
                    node_id=node_id,
                    archetype=self._archetype,
                    payload={
                        "branch": workspace.branch,
                        "commit_sha": "",
                        "files_touched": touched_files,
                    },
                )
        except IntegrationError as exc:
            status = "failed"
            error_message = (
                f"Session completed but harvest failed: {exc}. "
                f"The coding work was done — the merge into develop "
                f"encountered a conflict."
            )
            # 40-REQ-11.2: Emit git.conflict on merge failure
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.GIT_CONFLICT,
                node_id=node_id,
                archetype=self._archetype,
                severity=AuditSeverity.WARNING,
                payload={
                    "branch": workspace.branch,
                    "strategy": "default",
                    "error": str(exc),
                },
            )
            logger.error(
                "Harvest failed for %s after successful session: %s",
                node_id,
                exc,
            )
            return status, error_message, touched_files

        # 35-REQ-1.1: Capture develop HEAD SHA after successful harvest
        # 19-REQ-3.4: Post-harvest remote integration
        if touched_files:
            try:
                await post_harvest_integrate(
                    repo_root=repo_root,
                    workspace=workspace,
                )
            except Exception as exc:
                logger.warning(
                    "Post-harvest integration failed for %s: %s",
                    node_id,
                    exc,
                    exc_info=True,
                )

        return status, error_message, touched_files

    async def _extract_knowledge_and_findings(
        self,
        node_id: str,
        attempt: int,
        workspace: WorkspaceInfo,
        outcome_response: str = "",
    ) -> None:
        """Extract knowledge facts and review findings from session output.

        Requirements: 05-REQ-1.1, 27-REQ-3.1, 52-REQ-1.1, 52-REQ-1.2
        """
        summary = self._read_session_artifacts(workspace)
        transcript = (summary or {}).get("summary", "")
        if not transcript:
            transcript = self._build_fallback_input(workspace, node_id)
        if not transcript:
            return

        try:
            await extract_and_store_knowledge(
                transcript=transcript,
                spec_name=self._spec_name,
                node_id=node_id,
                memory_extraction_model=self._config.models.memory_extraction,
                knowledge_db=self._knowledge_db,
                sink_dispatcher=self._sink,
                run_id=self._run_id,
                causal_context_limit=self._config.orchestrator.causal_context_limit,
            )
        except Exception:
            logger.warning(
                "Knowledge extraction failed for %s, continuing",
                node_id,
                exc_info=True,
            )

        # 27-REQ-3.1: Parse and persist structured findings from
        # review archetypes (skeptic, verifier, oracle).
        # Prefer the actual session response (which contains the agent's
        # JSON output) over the fallback transcript (which is metadata).
        review_text = outcome_response or transcript
        self._persist_review_findings(review_text, node_id, attempt)

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

        Requirements: 05-REQ-1.1, 11-REQ-4.2
        """
        outcome = await self._execute_session(
            node_id,
            workspace,
            system_prompt,
            task_prompt,
        )

        from agent_fox.core.config import PricingConfig

        pricing = getattr(self._config, "pricing", PricingConfig())
        cost = calculate_cost(
            outcome.input_tokens,
            outcome.output_tokens,
            self._resolved_model_id,
            pricing,
            cache_read_input_tokens=outcome.cache_read_input_tokens,
            cache_creation_input_tokens=outcome.cache_creation_input_tokens,
        )

        status, error_message, touched_files = await self._harvest_and_integrate(
            node_id,
            outcome,
            workspace,
            repo_root,
        )

        # 35-REQ-1.1: Capture develop HEAD SHA after successful harvest
        commit_sha = ""
        if touched_files and status == "completed":
            commit_sha = await _capture_develop_head(repo_root)

        # Record and emit audit events
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

        # 40-REQ-7.2, 40-REQ-7.3: Emit session.complete or session.fail
        if status == "completed":
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.SESSION_COMPLETE,
                node_id=node_id,
                archetype=self._archetype,
                payload={
                    "archetype": self._archetype,
                    "model_id": self._resolved_model_id,
                    "prompt_template": self._archetype,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "cache_read_input_tokens": outcome.cache_read_input_tokens,
                    "cache_creation_input_tokens": outcome.cache_creation_input_tokens,
                    "cost": cost,
                    "duration_ms": outcome.duration_ms,
                    "files_touched": touched_files,
                },
            )
        else:
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
                archetype=self._archetype,
                severity=AuditSeverity.ERROR,
                payload={
                    "archetype": self._archetype,
                    "model_id": self._resolved_model_id,
                    "prompt_template": self._archetype,
                    "error_message": error_message or "Unknown error",
                    "attempt": attempt,
                },
            )

        # 40-REQ-11.3: Emit harvest.complete on successful harvest
        if touched_files and status == "completed":
            emit_audit_event(
                self._sink,
                self._run_id,
                AuditEventType.HARVEST_COMPLETE,
                node_id=node_id,
                archetype=self._archetype,
                payload={
                    "commit_sha": commit_sha,
                    "facts_extracted": 0,
                    "findings_persisted": 0,
                },
            )

        # 05-REQ-1.1, 52-REQ-1.1: Extract knowledge on success
        if status == "completed":
            await self._extract_knowledge_and_findings(
                node_id,
                attempt,
                workspace,
                outcome_response=outcome.response,
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
            model=self._resolved_model_id,
            files_touched=touched_files,
            archetype=self._archetype,
            commit_sha=commit_sha,
            is_transport_error=getattr(outcome, "is_transport_error", False),
        )

    def _record_session_to_sink(
        self,
        outcome: SessionOutcome,
        node_id: str,
    ) -> None:
        """Record a session outcome to the sink dispatcher (best-effort)."""
        record_session_to_sink(self._sink, outcome, node_id)

    def _persist_review_findings(
        self,
        transcript: str,
        node_id: str,
        attempt: int,
    ) -> None:
        """Parse and persist structured findings from review archetypes.

        Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1
        """
        try:
            conn = self._knowledge_db.connection
        except Exception:
            logger.warning(
                "Failed to access knowledge DB for review persistence on %s",
                node_id,
                exc_info=True,
            )
            return
        persist_review_findings(
            transcript,
            node_id,
            attempt,
            archetype=self._archetype,
            spec_name=self._spec_name,
            task_group=self._task_group,
            knowledge_db_conn=conn,
            sink=self._sink,
            run_id=self._run_id,
        )

    def _build_retry_context(self, spec_name: str) -> str:
        """Query active critical/major findings for the spec and format them.

        Requirements: 53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1
        """
        return build_retry_context(self._knowledge_db, spec_name)

    async def _setup_workspace(
        self,
        repo_root: Path,
        node_id: str,
    ) -> WorkspaceInfo:
        """Ensure develop is ready and create an isolated worktree.

        19-REQ-1.1, 19-REQ-1.6: ensure develop branch exists and is
        up-to-date before creating the worktree.
        """
        try:
            await ensure_develop(repo_root)
        except Exception:
            logger.warning(
                "ensure_develop failed for %s, continuing with existing branch state",
                node_id,
                exc_info=True,
            )

        return await create_worktree(
            repo_root,
            self._spec_name,
            self._task_group,
        )

    async def _run_session_lifecycle(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
        repo_root: Path,
        workspace: WorkspaceInfo,
    ) -> SessionRecord:
        """Run hooks, build prompts, execute session, and read artifacts.

        06-REQ-1.1: pre-session hooks
        06-REQ-2.1: post-session hooks
        """
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

        # 40-REQ-7.1: Emit session.start audit event before SDK call
        emit_audit_event(
            self._sink,
            self._run_id,
            AuditEventType.SESSION_START,
            node_id=node_id,
            archetype=self._archetype,
            payload={
                "archetype": self._archetype,
                "model_id": self._resolved_model_id,
                "prompt_template": self._archetype,
                "attempt": attempt,
            },
        )

        record = await self._run_and_harvest(
            node_id,
            attempt,
            workspace,
            system_prompt,
            task_prompt,
            repo_root,
        )

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

        summary = self._read_session_artifacts(workspace)
        if summary:
            logger.info(
                "Session summary for %s: %s",
                node_id,
                summary.get("summary", ""),
            )

        return record

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
            workspace = await self._setup_workspace(repo_root, node_id)
            return await self._run_session_lifecycle(node_id, attempt, previous_error, repo_root, workspace)

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
                archetype=self._archetype,
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


# ---------------------------------------------------------------------------
# Context assembly helpers (inlined from context_assembly.py)
# ---------------------------------------------------------------------------


def load_relevant_facts(
    knowledge_db: KnowledgeDB,
    spec_name: str,
    confidence_threshold: float,
    fact_cache: dict[str, RankedFactCache] | None = None,
) -> list:
    """Load relevant facts, using the pre-computed cache when available.

    When a valid cache entry exists for the current spec and the fact
    count has not changed since the cache was built, return cached facts
    directly. Otherwise fall back to live computation via
    select_relevant_facts().

    Requirements: 42-REQ-3.2, 42-REQ-3.3, 42-REQ-3.4
    """
    # 42-REQ-3.2: Try cache first when cache is available
    if fact_cache is not None:
        try:
            _row = knowledge_db.connection.execute(
                "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
            ).fetchone()
            current_count: int = _row[0] if _row else 0
            cached = get_cached_facts(fact_cache, spec_name, current_count)
            if cached is not None:
                logger.debug(
                    "Using cached fact rankings for %s (%d facts)",
                    spec_name,
                    len(cached),
                )
                return cached
            # 42-REQ-3.3: Cache is stale or missing — fall through to live
            logger.debug(
                "Cache miss for %s (count mismatch or absent); falling back to live computation",
                spec_name,
            )
        except Exception:
            logger.debug(
                "Cache lookup failed for %s; falling back to live computation",
                spec_name,
                exc_info=True,
            )

    # Live computation (no cache, stale cache, or cache lookup failure)
    all_facts = load_all_facts(knowledge_db.connection)
    if not all_facts:
        return []
    return select_relevant_facts(
        all_facts,
        spec_name,
        task_keywords=[spec_name],
        confidence_threshold=confidence_threshold,
    )


def enhance_with_causal(
    knowledge_db: KnowledgeDB,
    spec_name: str,
    relevant_facts: list,
) -> list[str]:
    """Enhance keyword-selected facts with causal context.

    Uses select_context_with_causal() to augment the keyword-matched
    facts with causally-linked facts from the DuckDB knowledge store.

    Requirements: 13-REQ-7.1, 13-REQ-7.2, 38-REQ-2.1, 38-REQ-2.3
    """
    keyword_dicts = [
        {
            "id": f.id,
            "content": f.content,
            "spec_name": f.spec_name,
        }
        for f in relevant_facts
    ]

    enhanced = select_context_with_causal(
        knowledge_db.connection,
        spec_name,
        touched_files=[],
        keyword_facts=keyword_dicts,
    )
    return [f["content"] for f in enhanced]


def merge_cross_spec_facts(
    spec_facts: list[Fact],
    cross_results: list[SearchResult],
) -> list[Fact]:
    """Merge cross-spec search results with spec-specific facts, deduplicating by ID.

    Spec-specific facts take precedence: if a cross-spec result has the same
    ID as a spec-specific fact, the spec-specific version is kept.

    Args:
        spec_facts: Spec-specific facts (output of _load_relevant_facts).
        cross_results: SearchResults from VectorSearch.

    Returns:
        Merged list: all spec_facts followed by any cross-spec facts whose
        IDs are not already in spec_facts. Order is preserved.

    Requirements: 94-REQ-3.1, 94-REQ-3.E1
    """
    existing_ids = {f.id for f in spec_facts}
    merged: list[Fact] = list(spec_facts)
    for result in cross_results:
        if result.fact_id not in existing_ids:
            merged.append(
                Fact(
                    id=result.fact_id,
                    content=result.content,
                    category=result.category,
                    spec_name=result.spec_name,
                    keywords=[],
                    confidence=1.0,
                    created_at="",
                    session_id=result.session_id,
                    commit_sha=result.commit_sha,
                )
            )
            existing_ids.add(result.fact_id)
    return merged


def build_retry_context(
    knowledge_db: KnowledgeDB,
    spec_name: str,
) -> str:
    """Query active critical/major findings for the spec and format them.

    Returns a structured block for inclusion in coder retry prompts,
    listing all active critical and major review findings. Returns an
    empty string if no such findings exist or if the DB is unavailable.

    Requirements: 53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1
    """
    try:
        from agent_fox.knowledge.review_store import query_active_findings

        conn = knowledge_db.connection
        findings = query_active_findings(conn, spec_name)
        critical_major = [f for f in findings if f.severity in ("critical", "major")]
        if not critical_major:
            return ""

        lines = [
            f"## Prior Review Findings for {spec_name}",
            "",
            "The following critical/major issues were identified in prior "
            "review sessions. Please address these in your implementation:",
            "",
        ]
        for finding in critical_major:
            ref_str = f" [{finding.requirement_ref}]" if finding.requirement_ref else ""
            safe_desc = sanitize_prompt_content(finding.description, label="review-finding")
            lines.append(f"- **{finding.severity.upper()}**{ref_str}: {safe_desc}")
        return "\n".join(lines)

    except Exception:
        logger.warning(
            "Failed to build retry context for %s, continuing without",
            spec_name,
            exc_info=True,
        )
        return ""
