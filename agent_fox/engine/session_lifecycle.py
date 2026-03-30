"""Session lifecycle: workspace, hooks, prompts, execution, harvest, cleanup.

Handles the full lifecycle of a coding session for a single task graph
node. Extracted from cli/code.py to keep CLI wiring thin.

Requirements: 16-REQ-5.1, 16-REQ-5.E1, 06-REQ-1.1, 06-REQ-2.1,
              05-REQ-1.1, 11-REQ-4.2, 13-REQ-2.1, 13-REQ-7.1,
              40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-11.3
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig, HookConfig, SecurityConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.core.models import ModelTier, calculate_cost, resolve_model
from agent_fox.core.node_id import parse_node_id
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.engine.fact_cache import RankedFactCache, get_cached_facts
from agent_fox.engine.knowledge_harvest import extract_and_store_knowledge
from agent_fox.engine.review_parser import extract_json_array
from agent_fox.engine.state import SessionRecord
from agent_fox.hooks.hooks import (
    HookContext,
    run_post_session_hooks,
    run_pre_session_hooks,
)
from agent_fox.knowledge.audit import (
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    default_severity_for,
)
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.filtering import select_relevant_facts
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher
from agent_fox.knowledge.store import load_all_facts
from agent_fox.session.archetypes import get_archetype
from agent_fox.session.prompt import (
    assemble_context,
    build_system_prompt,
    build_task_prompt,
    select_context_with_causal,
)
from agent_fox.session.session import run_session
from agent_fox.ui.progress import ActivityCallback
from agent_fox.workspace import (
    WorkspaceInfo,
    create_worktree,
    destroy_worktree,
    ensure_develop,
)
from agent_fox.workspace.harvest import harvest, post_harvest_integrate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SDK parameter resolution helpers (Spec 56)
# ---------------------------------------------------------------------------


def _resolve_max_turns(config: AgentFoxConfig, archetype: str) -> int | None:
    """Resolve max_turns for the given archetype.

    Resolution order: config.toml override > archetype registry default.
    Returns None when configured as 0 (unlimited).

    Requirements: 56-REQ-1.1, 56-REQ-1.2, 56-REQ-1.4, 56-REQ-5.1
    """
    configured = config.archetypes.max_turns.get(archetype)
    if configured is not None:
        return configured if configured > 0 else None  # 0 = unlimited
    entry = get_archetype(archetype)
    return entry.default_max_turns


def _resolve_thinking(config: AgentFoxConfig, archetype: str) -> dict | None:
    """Resolve thinking configuration for the given archetype.

    Resolution order: config.toml override > archetype registry default.
    Returns None when mode is ``disabled``.

    Requirements: 56-REQ-4.1, 56-REQ-4.2, 56-REQ-4.3, 56-REQ-5.1
    """
    configured = config.archetypes.thinking.get(archetype)
    if configured is not None:
        if configured.mode == "disabled":
            return None
        return {"type": configured.mode, "budget_tokens": configured.budget_tokens}
    entry = get_archetype(archetype)
    if entry.default_thinking_mode == "disabled":
        return None
    return {
        "type": entry.default_thinking_mode,
        "budget_tokens": entry.default_thinking_budget,
    }


def _resolve_fallback_model(config: AgentFoxConfig) -> str | None:
    """Resolve the fallback model ID from config.

    Returns None when the configured value is empty.
    Logs a warning when the model is not in the local model registry.

    Requirements: 56-REQ-3.1, 56-REQ-3.2, 56-REQ-3.4, 56-REQ-3.E1
    """
    from agent_fox.core.models import MODEL_REGISTRY

    model = config.models.fallback_model
    if not model:
        return None
    if model not in MODEL_REGISTRY:
        logger.warning(
            "Fallback model '%s' is not in the model registry; "
            "passing to SDK anyway (56-REQ-3.E1)",
            model,
        )
    return model


def _resolve_max_budget(config: AgentFoxConfig) -> float | None:
    """Resolve max_budget_usd from config.

    Returns None when configured as 0.0 (unlimited).

    Requirements: 56-REQ-2.1, 56-REQ-2.2, 56-REQ-2.E1
    """
    budget = config.orchestrator.max_budget_usd
    if budget == 0.0:
        return None
    return budget


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


def _clamp_instances(archetype: str, instances: int) -> int:
    """Clamp instance counts to valid ranges.

    - Coder: always 1 (26-REQ-4.E1).
    - Any archetype: max 5 (26-REQ-4.E2).
    - Minimum: 1.
    """
    if archetype == "coder" and instances > 1:
        logger.warning(
            "Coder archetype does not support multi-instance; "
            "clamped instances from %d to 1",
            instances,
        )
        return 1
    if instances > 5:
        logger.warning(
            "Instances for archetype '%s' clamped from %d to 5 (maximum)",
            archetype,
            instances,
        )
        return 5
    if instances < 1:
        logger.warning(
            "Instances for archetype '%s' clamped from %d to 1 (minimum)",
            archetype,
            instances,
        )
        return 1
    return instances


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
        instances: int = 1,
        hook_config: HookConfig | None = None,
        no_hooks: bool = False,
        sink_dispatcher: SinkDispatcher | None = None,
        knowledge_db: KnowledgeDB,
        activity_callback: ActivityCallback | None = None,
        assessed_tier: ModelTier | None = None,
        run_id: str = "",
        fact_cache: dict[str, RankedFactCache] | None = None,
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._archetype = archetype
        self._instances = _clamp_instances(archetype, instances)
        self._hook_config = hook_config
        self._no_hooks = no_hooks
        self._sink = sink_dispatcher
        self._knowledge_db = knowledge_db
        self._activity_callback = activity_callback
        self._run_id = run_id
        self._fact_cache = fact_cache
        parsed = parse_node_id(node_id)
        self._spec_name = parsed.spec_name
        self._task_group = parsed.group_number

        # 30-REQ-7.2: Use assessed tier from adaptive routing if provided,
        # otherwise fall back to static resolution (26-REQ-4.4).
        if assessed_tier is not None:
            self._resolved_model_id = resolve_model(assessed_tier.value).model_id
        else:
            self._resolved_model_id = resolve_model(self._resolve_model_tier()).model_id
        self._resolved_security = self._resolve_security_config()

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
            conn=self._knowledge_db.connection,
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
            task_prompt = (
                f"{task_prompt}\n\n"
                f"**Note:** This is retry attempt {attempt}. "
                f"The previous attempt failed with:\n"
                f"```\n{previous_error}\n```\n"
                f"Please address this error.\n"
            )

        # 53-REQ-5.1: Inject active critical/major review findings for coder
        # retries so the coder can address identified issues.
        if self._archetype == "coder" and attempt > 1:
            retry_context = self._build_retry_context(self._spec_name)
            if retry_context:
                task_prompt = f"{retry_context}\n\n{task_prompt}"

        return system_prompt, task_prompt

    def _resolve_model_tier(self) -> str:
        """Resolve model tier for the archetype.

        Priority: config override > archetype registry default > global coding model.

        Requirements: 26-REQ-4.4, 26-REQ-6.3
        """
        # Check config override first
        config_override = self._config.archetypes.models.get(self._archetype)
        if config_override:
            return config_override

        # Fall back to archetype registry default
        entry = get_archetype(self._archetype)
        return entry.default_model_tier

    def _resolve_security_config(self) -> SecurityConfig | None:
        """Resolve security config for the archetype.

        Returns a SecurityConfig with the archetype's allowlist override,
        or None to use the global default.

        Priority: config override > archetype registry default > None (global).

        Requirements: 26-REQ-3.4, 26-REQ-6.4
        """
        # Check config override first
        config_allowlist = self._config.archetypes.allowlists.get(self._archetype)
        if config_allowlist is not None:
            return SecurityConfig(bash_allowlist=config_allowlist)

        # Fall back to archetype registry default
        entry = get_archetype(self._archetype)
        if entry.default_allowlist is not None:
            return SecurityConfig(bash_allowlist=entry.default_allowlist)

        # None means use global config.security
        return None

    def _load_relevant_facts(self) -> list:
        """Load relevant facts, using the pre-computed cache when available.

        When a valid cache entry exists for the current spec and the fact
        count has not changed since the cache was built, return cached facts
        directly. Otherwise fall back to live computation via
        select_relevant_facts().

        Requirements: 42-REQ-3.2, 42-REQ-3.3, 42-REQ-3.4
        """
        # 42-REQ-3.2: Try cache first when cache is available
        if self._fact_cache is not None:
            try:
                current_count: int = self._knowledge_db.connection.execute(
                    "SELECT COUNT(*) FROM memory_facts WHERE superseded_by IS NULL"
                ).fetchone()[0]
                cached = get_cached_facts(
                    self._fact_cache,
                    self._spec_name,
                    current_count,
                )
                if cached is not None:
                    logger.debug(
                        "Using cached fact rankings for %s (%d facts)",
                        self._spec_name,
                        len(cached),
                    )
                    return cached
                # 42-REQ-3.3: Cache is stale or missing — fall through to live
                logger.debug(
                    "Cache miss for %s (count mismatch or absent); "
                    "falling back to live computation",
                    self._spec_name,
                )
            except Exception:
                logger.debug(
                    "Cache lookup failed for %s; falling back to live computation",
                    self._spec_name,
                    exc_info=True,
                )

        # Live computation (no cache, stale cache, or cache lookup failure)
        all_facts = load_all_facts(self._knowledge_db.connection)
        if not all_facts:
            return []
        return select_relevant_facts(
            all_facts,
            self._spec_name,
            task_keywords=[self._spec_name],
            confidence_threshold=self._config.knowledge.confidence_threshold,
        )

    def _enhance_with_causal(
        self,
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
            self._knowledge_db.connection,
            self._spec_name,
            touched_files=[],
            keyword_facts=keyword_dicts,
        )
        return [f["content"] for f in enhanced]

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
                ["git", "diff", "HEAD~1"],
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

        Requirements: 56-REQ-1.2, 56-REQ-2.2, 56-REQ-3.2, 56-REQ-4.2
        """
        resolved_max_turns = _resolve_max_turns(self._config, self._archetype)
        resolved_thinking = _resolve_thinking(self._config, self._archetype)
        resolved_fallback = _resolve_fallback_model(self._config)
        resolved_budget = _resolve_max_budget(self._config)

        logger.info(
            "Session %s: max_turns=%s, max_budget_usd=%s, fallback_model=%s, "
            "thinking=%s",
            node_id,
            resolved_max_turns,
            resolved_budget,
            resolved_fallback,
            resolved_thinking,
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
        )

    async def _harvest_and_integrate(
        self,
        node_id: str,
        outcome: SessionOutcome,
        workspace: WorkspaceInfo,
        repo_root: Path,
    ) -> tuple[str, str, list[str]]:
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
                self._emit_audit(
                    AuditEventType.GIT_MERGE,
                    node_id=node_id,
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
            self._emit_audit(
                AuditEventType.GIT_CONFLICT,
                node_id=node_id,
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
                    platform_config=self._config.platform,
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
        self._persist_review_findings(transcript, node_id, attempt)

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
            self._emit_audit(
                AuditEventType.SESSION_COMPLETE,
                node_id=node_id,
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
            self._emit_audit(
                AuditEventType.SESSION_FAIL,
                node_id=node_id,
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
            self._emit_audit(
                AuditEventType.HARVEST_COMPLETE,
                node_id=node_id,
                payload={
                    "commit_sha": commit_sha,
                    "facts_extracted": 0,
                    "findings_persisted": 0,
                },
            )

        # 05-REQ-1.1, 52-REQ-1.1: Extract knowledge on success
        if status == "completed":
            await self._extract_knowledge_and_findings(node_id, attempt, workspace)

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
        )

    def _emit_audit(
        self,
        event_type: AuditEventType,
        *,
        node_id: str = "",
        session_id: str = "",
        severity: AuditSeverity | None = None,
        payload: dict | None = None,
    ) -> None:
        """Emit an audit event to the sink dispatcher (best-effort).

        Requirements: 40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-11.3
        """
        if self._sink is None or not self._run_id:
            return
        try:
            event = AuditEvent(
                run_id=self._run_id,
                event_type=event_type,
                severity=severity or default_severity_for(event_type),
                node_id=node_id or self._node_id,
                session_id=session_id,
                archetype=self._archetype,
                payload=payload or {},
            )
            self._sink.emit_audit_event(event)
        except Exception:
            logger.debug(
                "Failed to emit audit event %s for %s",
                event_type,
                node_id or self._node_id,
                exc_info=True,
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

    def _persist_review_findings(
        self,
        transcript: str,
        node_id: str,
        attempt: int,
    ) -> None:
        """Parse and persist structured findings from review archetypes.

        Uses extract_json_array to extract JSON from archetype output, then
        routes to the correct typed parser and insert function based on
        archetype:
        - skeptic  → parse_review_findings   → insert_findings
        - verifier → parse_verification_results → insert_verdicts
        - oracle   → parse_drift_findings    → insert_drift_findings

        Non-review archetypes (coder, librarian, etc.) are silently skipped.
        When JSON extraction fails, a review.parse_failure audit event is
        emitted at WARNING severity. All other failures are logged and
        swallowed to avoid blocking the orchestrator.

        Requirements: 53-REQ-1.1, 53-REQ-2.1, 53-REQ-3.1,
                      53-REQ-1.E1, 53-REQ-2.E1, 53-REQ-3.E1
        """
        if self._archetype not in ("skeptic", "verifier", "oracle", "auditor"):
            return

        session_id = f"{node_id}:{attempt}"
        task_group = str(self._task_group)

        try:
            if self._archetype in ("skeptic", "verifier", "oracle"):
                json_objects = extract_json_array(transcript)
                if json_objects is None:
                    self._emit_audit(
                        AuditEventType.REVIEW_PARSE_FAILURE,
                        node_id=node_id,
                        severity=AuditSeverity.WARNING,
                        payload={"raw_output": transcript[:2000]},
                    )
                    return

                from agent_fox.engine.review_parser import (
                    parse_drift_findings,
                    parse_review_findings,
                    parse_verification_results,
                )
                from agent_fox.knowledge.review_store import (
                    insert_drift_findings,
                    insert_findings,
                    insert_verdicts,
                )

                conn = self._knowledge_db.connection

                # Dispatch table: archetype -> (parser, inserter, label)
                _review_dispatch = {
                    "skeptic": (
                        parse_review_findings,
                        insert_findings,
                        "skeptic findings",
                    ),
                    "verifier": (
                        parse_verification_results,
                        insert_verdicts,
                        "verifier verdicts",
                    ),
                    "oracle": (
                        parse_drift_findings,
                        insert_drift_findings,
                        "oracle drift findings",
                    ),
                }
                parser, inserter, label = _review_dispatch[self._archetype]
                records = parser(json_objects, self._spec_name, task_group, session_id)
                if records:
                    count = inserter(conn, records)
                    logger.info("Persisted %d %s for %s", count, label, node_id)
                else:
                    self._emit_audit(
                        AuditEventType.REVIEW_PARSE_FAILURE,
                        node_id=node_id,
                        severity=AuditSeverity.WARNING,
                        payload={"raw_output": transcript[:2000]},
                    )

            elif self._archetype == "auditor":
                from agent_fox.session.auditor_output import (
                    persist_auditor_results,
                )
                from agent_fox.session.review_parser import parse_auditor_output

                audit_result = parse_auditor_output(transcript)
                if audit_result is not None:
                    spec_dir = Path.cwd() / ".specs" / self._spec_name
                    persist_auditor_results(spec_dir, audit_result, attempt=attempt)

        except Exception:
            logger.warning(
                "Failed to persist %s findings for %s, continuing",
                self._archetype,
                node_id,
                exc_info=True,
            )

    def _build_retry_context(self, spec_name: str) -> str:
        """Query active critical/major findings for the spec and format them.

        Returns a structured block for inclusion in coder retry prompts,
        listing all active critical and major review findings. Returns an
        empty string if no such findings exist or if the DB is unavailable.

        Requirements: 53-REQ-5.1, 53-REQ-5.2, 53-REQ-5.E1
        """
        try:
            from agent_fox.knowledge.review_store import query_active_findings

            conn = self._knowledge_db.connection
            findings = query_active_findings(conn, spec_name)
            critical_major = [
                f for f in findings if f.severity in ("critical", "major")
            ]
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
                ref_str = (
                    f" [{finding.requirement_ref}]" if finding.requirement_ref else ""
                )
                lines.append(
                    f"- **{finding.severity.upper()}**{ref_str}: {finding.description}"
                )
            return "\n".join(lines)

        except Exception:
            logger.warning(
                "Failed to build retry context for %s, continuing without",
                spec_name,
                exc_info=True,
            )
            return ""

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
        self._emit_audit(
            AuditEventType.SESSION_START,
            node_id=node_id,
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
            return await self._run_session_lifecycle(
                node_id, attempt, previous_error, repo_root, workspace
            )

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
