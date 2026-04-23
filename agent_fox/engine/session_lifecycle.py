"""Session lifecycle: workspace, hooks, prompts, execution, harvest, cleanup.

Handles the full lifecycle of a coding session for a single task graph
node. Extracted from cli/code.py to keep CLI wiring thin.

Requirements: 16-REQ-5.1, 16-REQ-5.E1, 06-REQ-1.1, 06-REQ-2.1,
              05-REQ-1.1, 11-REQ-4.2, 13-REQ-2.1, 13-REQ-7.1,
              40-REQ-7.1, 40-REQ-7.2, 40-REQ-7.3, 40-REQ-11.3,
              05-REQ-4.1, 05-REQ-4.2, 42-REQ-3.2, 53-REQ-5.1
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.errors import IntegrationError
from agent_fox.core.models import ModelTier, calculate_cost, resolve_model
from agent_fox.core.node_id import parse_node_id
from agent_fox.core.prompt_safety import sanitize_prompt_content
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.review_persistence import persist_review_findings
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
from agent_fox.knowledge.audit import AuditEventType, AuditSeverity
from agent_fox.knowledge.db import KnowledgeDB
from agent_fox.knowledge.provider import KnowledgeProvider
from agent_fox.knowledge.sink import SessionOutcome, SinkDispatcher
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
    run_git,
)
from agent_fox.workspace.harvest import harvest, post_harvest_integrate

logger = logging.getLogger(__name__)

# Archetypes whose outputs are captured as structured findings via
# _persist_review_findings rather than free-form factual knowledge.
# Skipping LLM extraction for these avoids ~18k-token overhead per session
# when the extraction reliably returns zero facts.
_REVIEW_ARCHETYPES: frozenset[str] = frozenset({"reviewer", "skeptic", "verifier", "oracle", "auditor"})


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
        sink_dispatcher: SinkDispatcher | None = None,
        knowledge_db: KnowledgeDB,
        knowledge_provider: KnowledgeProvider | None = None,
        activity_callback: ActivityCallback | None = None,
        assessed_tier: ModelTier | None = None,
        run_id: str = "",
        timeout_override: int | None = None,
        max_turns_override: int | None = None,
        trace_enabled: bool = True,
    ) -> None:
        self._node_id = node_id
        self._config = config
        self._archetype = archetype
        self._mode = mode  # 97-REQ-5.3: mode for per-mode configuration resolution
        self._instances = clamp_instances(archetype, instances, mode=mode)
        self._sink = sink_dispatcher
        self._sink_dispatcher = sink_dispatcher  # alias for retrieval audit events
        self._knowledge_db = knowledge_db
        self._activity_callback = activity_callback
        self._run_id = run_id
        self._trace_enabled = trace_enabled
        # 75-REQ-3.5: Per-node timeout/turns overrides from timeout-aware escalation
        self._timeout_override = timeout_override
        self._max_turns_override = max_turns_override
        # 114-REQ-2.4: Use provided KnowledgeProvider or default to NoOp
        if knowledge_provider is not None:
            self._knowledge_provider = knowledge_provider
        else:
            from agent_fox.knowledge.provider import NoOpKnowledgeProvider

            self._knowledge_provider = NoOpKnowledgeProvider()
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

        Uses KnowledgeProvider.retrieve() to produce knowledge context,
        then passes it to assemble_context.

        Requirements: 05-REQ-4.1, 05-REQ-4.2, 114-REQ-3.1, 114-REQ-3.3
        """
        from agent_fox.core.config import resolve_spec_root

        spec_dir = resolve_spec_root(self._config, repo_root) / self._spec_name

        # 114-REQ-3.1: Use KnowledgeProvider for knowledge context retrieval
        memory_facts: list[str] | None = None
        try:
            descriptions = extract_subtask_descriptions(spec_dir, self._task_group)
            task_description = "\n".join(descriptions) if descriptions else self._spec_name
            retrieved = self._knowledge_provider.retrieve(self._spec_name, task_description)
            if retrieved:
                memory_facts = retrieved
        except Exception:
            # 114-REQ-3.E1: Log WARNING and proceed with empty knowledge context
            logger.warning(
                "KnowledgeProvider.retrieve() failed for %s, continuing without knowledge context",
                self._spec_name,
                exc_info=True,
            )

        context = assemble_context(
            spec_dir,
            self._task_group,
            memory_facts=memory_facts,
            conn=self._knowledge_db.connection,
            project_root=Path.cwd(),
            archetype=self._archetype,
        )

        system_prompt = build_system_prompt(
            context=context,
            task_group=self._task_group,
            spec_name=self._spec_name,
            archetype=self._archetype,
            mode=self._mode,
            project_dir=repo_root,
        )
        task_prompt = build_task_prompt(
            task_group=self._task_group,
            spec_name=self._spec_name,
            archetype=self._archetype,
            mode=self._mode,
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

        # 53-REQ-5.1, 113-REQ-4.2: Inject active critical/major review
        # findings (including audit findings) for all coder attempts so the
        # coder can address identified issues.
        if self._archetype == "coder":
            retry_context = self._build_retry_context(self._spec_name)
            if retry_context:
                task_prompt = f"{retry_context}\n\n{task_prompt}"

        return system_prompt, task_prompt

    @staticmethod
    def _read_session_artifacts(workspace: WorkspaceInfo) -> dict | None:
        """Read session-summary.json from the worktree if it exists.

        Looks in ``.agent-fox/session-summary.json`` inside the worktree.
        Returns the parsed JSON dict or None if the file is absent or
        cannot be parsed.
        """
        from agent_fox.core.paths import AGENT_FOX_DIR, SESSION_SUMMARY_FILENAME

        summary_path = workspace.path / AGENT_FOX_DIR / SESSION_SUMMARY_FILENAME
        if not summary_path.exists():
            return None
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning(
                "Failed to read session summary from %s: %s",
                summary_path,
                exc,
            )
            return None

    @staticmethod
    def _cleanup_session_artifacts(workspace: WorkspaceInfo) -> None:
        """Delete transient session artifacts from the worktree.

        Called after all consumers have read the artifacts.  Prevents
        stale files from leaking into the working directory when worktree
        cleanup is skipped or fails.
        """
        from agent_fox.core.paths import AGENT_FOX_DIR, SESSION_SUMMARY_FILENAME

        summary_path = workspace.path / AGENT_FOX_DIR / SESSION_SUMMARY_FILENAME
        try:
            summary_path.unlink(missing_ok=True)
        except OSError:
            pass

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
            resolved_max_turns = resolve_max_turns(self._config, self._archetype, mode=self._mode)
        resolved_thinking = resolve_thinking(self._config, self._archetype, mode=self._mode)
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
                # Capture the resulting commit SHA for traceability
                _, sha_out, _ = await run_git(
                    ["rev-parse", "HEAD"],
                    cwd=repo_root,
                    check=False,
                )
                commit_sha = sha_out.strip()
                emit_audit_event(
                    self._sink,
                    self._run_id,
                    AuditEventType.GIT_MERGE,
                    node_id=node_id,
                    archetype=self._archetype,
                    payload={
                        "branch": workspace.branch,
                        "commit_sha": commit_sha,
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

    def _ingest_knowledge(
        self,
        node_id: str,
        touched_files: list[str],
        commit_sha: str,
        session_status: str,
    ) -> None:
        """Ingest knowledge from a completed session via the KnowledgeProvider.

        Builds a context dict with session metadata and delegates to the
        provider's ingest() method.

        Requirements: 114-REQ-4.1, 114-REQ-4.E1
        """
        context: dict[str, object] = {
            "touched_files": touched_files,
            "commit_sha": commit_sha,
            "session_status": session_status,
        }
        try:
            self._knowledge_provider.ingest(node_id, self._spec_name, context)
        except Exception:
            # 114-REQ-4.E1: Log WARNING and continue without retrying
            logger.warning(
                "KnowledgeProvider.ingest() failed for %s, continuing",
                node_id,
                exc_info=True,
            )

    async def _extract_knowledge_and_findings(
        self,
        node_id: str,
        attempt: int,
        workspace: WorkspaceInfo,
        outcome_response: str = "",
    ) -> None:
        """Extract review findings from session output.

        113-REQ-1.1: Reconstructs the full conversation transcript from the
        agent trace JSONL events for the session's node_id and uses it as the
        primary transcript source.
        113-REQ-1.3: Continues to use session summary for the log message.
        113-REQ-1.E1: Falls back to _build_fallback_input when trace is
        unavailable.

        Knowledge ingestion is now handled by _ingest_knowledge() via the
        KnowledgeProvider protocol (114-REQ-4.1).

        Requirements: 27-REQ-3.1, 113-REQ-1.1, 113-REQ-1.E1, 113-REQ-1.E2
        """
        # 113-REQ-1.1: Reconstruct full transcript from agent trace JSONL
        from agent_fox.core.paths import AUDIT_DIR
        from agent_fox.knowledge.agent_trace import reconstruct_transcript

        audit_dir = getattr(self, "_audit_dir", None) or AUDIT_DIR
        transcript = reconstruct_transcript(audit_dir, self._run_id, node_id)

        # 113-REQ-1.E1, 113-REQ-1.E2: Fall back to _build_fallback_input
        # when trace is unavailable or has no assistant messages
        if not transcript:
            transcript = self._build_fallback_input(workspace, node_id)
        if not transcript:
            return

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

        # Detect budget exhaustion: SDK returns is_error=True with no message
        # when the max-budget-usd limit is hit.  The session did real work
        # (high token count) so retrying would just burn the same budget again.
        _BUDGET_EXHAUST_RATIO = 0.9
        resolved_budget = resolve_max_budget(self._config)
        is_budget_exhausted = (
            outcome.status == "failed"
            and (outcome.error_message or "") in ("Unknown error", "")
            and resolved_budget is not None
            and cost >= resolved_budget * _BUDGET_EXHAUST_RATIO
        )
        if is_budget_exhausted:
            logger.warning(
                "Session %s budget exhausted (cost=$%.2f of $%.2f budget), will not retry",
                node_id,
                cost,
                resolved_budget,
            )

        status, error_message, touched_files = await self._harvest_and_integrate(
            node_id,
            outcome,
            workspace,
            repo_root,
        )

        if is_budget_exhausted:
            error_message = f"Budget exhausted (${cost:.2f} of ${resolved_budget:.2f})"

        # 35-REQ-1.1: Capture develop HEAD SHA after successful harvest
        commit_sha = ""
        if touched_files and status == "completed":
            commit_sha = await _capture_develop_head(repo_root)

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
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "cache_read_input_tokens": outcome.cache_read_input_tokens,
                    "cache_creation_input_tokens": outcome.cache_creation_input_tokens,
                    "cost": cost,
                    "duration_ms": outcome.duration_ms,
                },
            )

        # Extract review findings and ingest knowledge on success.
        if status == "completed":
            await self._extract_knowledge_and_findings(
                node_id,
                attempt,
                workspace,
                outcome_response=outcome.response,
            )
            # 114-REQ-4.1: Ingest knowledge via KnowledgeProvider
            self._ingest_knowledge(node_id, touched_files, commit_sha, status)

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
            is_budget_exhausted=is_budget_exhausted,
        )

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
        from agent_fox.core.config import resolve_spec_root

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
            mode=self._mode,
            specs_dir=resolve_spec_root(self._config, Path.cwd()),
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
        """Build prompts, execute session, and read artifacts."""
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

        summary = self._read_session_artifacts(workspace)
        if summary:
            logger.info(
                "Session summary for %s: %s",
                node_id,
                summary.get("summary", ""),
            )

        self._cleanup_session_artifacts(workspace)

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
