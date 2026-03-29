"""CLI code command: execute the task plan via the orchestrator.

Thin CLI wrapper that connects the Click command group to the
orchestrator engine. Reads configuration, applies CLI overrides,
constructs the orchestrator, runs execution, prints a summary,
and exits with a meaningful code.

Requirements: 16-REQ-1.1 through 16-REQ-5.2, 23-REQ-5.1, 23-REQ-5.E1
"""

from __future__ import annotations

import asyncio
import logging
import sys
import warnings
from pathlib import Path

import click

from agent_fox.cli import json_io
from agent_fox.core.config import AgentFoxConfig, HookConfig, OrchestratorConfig
from agent_fox.core.errors import AgentFoxError
from agent_fox.core.models import ModelTier
from agent_fox.core.paths import AUDIT_DIR, PLAN_PATH, STATE_PATH
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.fact_cache import RankedFactCache, precompute_fact_rankings
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.engine.state import ExecutionState
from agent_fox.knowledge.db import KnowledgeDB, open_knowledge_store
from agent_fox.knowledge.duckdb_sink import DuckDBSink
from agent_fox.knowledge.ingest import run_background_ingestion
from agent_fox.knowledge.sink import SinkDispatcher
from agent_fox.knowledge.store import DEFAULT_MEMORY_PATH, export_facts_to_jsonl
from agent_fox.reporting.formatters import format_tokens
from agent_fox.ui.display import create_theme
from agent_fox.ui.progress import ProgressDisplay

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
        merged = config.model_dump()
        merged.update(overrides)
        return OrchestratorConfig.model_validate(merged)
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
    failed = counts.get("failed", 0)
    blocked = counts.get("blocked", 0)

    parts = [f"{done}/{total} done"]
    if in_progress:
        parts.append(f"{in_progress} in progress")
    if pending:
        parts.append(f"{pending} pending")
    if failed:
        parts.append(f"{failed} failed")
    if blocked:
        parts.append(f"{blocked} blocked")

    click.echo(f"Tasks:  {', '.join(parts)}")
    click.echo(
        f"Tokens: {format_tokens(state.total_input_tokens)} in / "
        f"{format_tokens(state.total_output_tokens)} out"
    )
    click.echo(f"Cost:   ${state.total_cost:.2f}")
    click.echo(f"Status: {state.run_status}")


def _run_ingestion(
    knowledge_db: KnowledgeDB,
    config: AgentFoxConfig,
) -> None:
    """Run background knowledge ingestion.

    Requirements: 38-REQ-1.3
    """
    try:
        run_background_ingestion(
            knowledge_db.connection,
            config.knowledge,
            Path.cwd(),
        )
    except Exception:
        logger.warning("Background ingestion failed", exc_info=True)


def _run_barrier_sync(
    knowledge_db: KnowledgeDB,
    config: AgentFoxConfig,
) -> None:
    """Run ingestion and export facts to JSONL at sync barrier.

    Called between task groups so that memory.jsonl stays reasonably
    up-to-date during long runs, not just at the very end.
    """
    _run_ingestion(knowledge_db, config)
    try:
        export_facts_to_jsonl(knowledge_db.connection, DEFAULT_MEMORY_PATH)
    except Exception:
        logger.warning("Barrier JSONL export failed", exc_info=True)


def _precompute_plan_fact_cache(
    plan_path: Path,
    knowledge_db: KnowledgeDB,
    config: AgentFoxConfig,
) -> dict[str, RankedFactCache] | None:
    """Pre-compute ranked fact cache for all specs in the plan.

    Reads spec names from plan.json and calls precompute_fact_rankings()
    with the configured confidence threshold. Returns None if computation
    fails so callers fall back to live fact selection.

    Requirements: 42-REQ-3.1
    """
    import json as _json

    try:
        plan_data = _json.loads(plan_path.read_text(encoding="utf-8"))
        nodes = plan_data.get("nodes", {})
        spec_names = sorted(
            {n.get("spec_name", "") for n in nodes.values() if n.get("spec_name")}
        )
        if not spec_names:
            return None
        cache = precompute_fact_rankings(
            knowledge_db.connection,
            spec_names,
            confidence_threshold=config.knowledge.confidence_threshold,
        )
        logger.debug(
            "Pre-computed fact rankings for %d specs: %s",
            len(cache),
            ", ".join(spec_names),
        )
        return cache
    except Exception:
        logger.warning(
            "Failed to pre-compute fact rankings; will use live computation",
            exc_info=True,
        )
        return None


def _run_review_only_mode(
    config: AgentFoxConfig,
    specs_dir_override: str | None,
) -> None:
    """Execute review-only mode: run review archetypes without coder sessions.

    Builds a review-only task graph, emits run.start/run.complete audit
    events, and prints a summary of findings, verdicts, and drift findings.
    When no specs are eligible (no source files or requirements.md found),
    prints a diagnostic message and exits cleanly.

    Requirements: 53-REQ-6.1, 53-REQ-6.3, 53-REQ-6.5, 53-REQ-6.E1
    """
    from agent_fox.graph.injection import (  # noqa: PLC0415
        build_review_only_graph,
        run_review_only,
    )

    specs_path = Path(specs_dir_override) if specs_dir_override else Path(".specs")
    full_config: AgentFoxConfig = config

    graph = build_review_only_graph(specs_path, full_config.archetypes)

    if not graph.nodes:
        click.echo("No specs eligible for review")
        return

    # Emit review-only audit events via a lightweight sink
    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(full_config.knowledge)
    sink_dispatcher.add(DuckDBSink(knowledge_db.connection))

    try:
        run_review_only(specs_path, full_config.archetypes, sink=sink_dispatcher)

        from agent_fox.graph.injection import print_review_only_summary  # noqa: PLC0415

        print_review_only_summary(knowledge_db.connection)
    finally:
        sink_dispatcher.close()
        knowledge_db.close()


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
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug audit trail (JSONL + DuckDB tool signals)",
)
@click.option(
    "--review-only",
    is_flag=True,
    default=False,
    help="Run only review archetypes (Skeptic, Verifier, Oracle), skip coder sessions",
)
@click.option(
    "--specs-dir",
    type=click.Path(),
    default=None,
    help="Path to specs directory (default: .specs)",
)
@click.pass_context
def code_cmd(
    ctx: click.Context,
    parallel: int | None,
    no_hooks: bool,
    max_cost: float | None,
    max_sessions: int | None,
    debug: bool,
    review_only: bool,
    specs_dir: str | None,
) -> None:
    """Execute the task plan."""
    # 16-REQ-1.2: load config from Click context
    config = ctx.obj["config"]
    quiet: bool = ctx.obj.get("quiet", False)
    json_mode: bool = ctx.obj.get("json", False)

    # 53-REQ-6.1: review-only mode — skip coder sessions, run review archetypes only
    if review_only:
        _run_review_only_mode(config, specs_dir)
        return

    # 23-REQ-7.1: read stdin JSON when in JSON mode
    if json_mode:
        stdin_data = json_io.read_stdin()
        if parallel is None and "parallel" in stdin_data:
            parallel = int(stdin_data["parallel"])
        if max_cost is None and "max_cost" in stdin_data:
            max_cost = float(stdin_data["max_cost"])
        if max_sessions is None and "max_sessions" in stdin_data:
            max_sessions = int(stdin_data["max_sessions"])

    # 16-REQ-1.E1: check plan file exists
    plan_path = PLAN_PATH
    if not plan_path.exists():
        if json_mode:
            json_io.emit_error(
                "Plan file not found. Run `agent-fox plan` first to generate a plan."
            )
            sys.exit(1)
        click.echo(
            "Error: Plan file not found. "
            "Run `agent-fox plan` first to generate a plan.",
            err=True,
        )
        sys.exit(1)

    state_path = STATE_PATH

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

    # 11-REQ-4.2, 38-REQ-1.3: Create DuckDB sink for session outcome recording
    # DuckDB is a hard requirement — open_knowledge_store raises on failure
    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(config.knowledge)
    sink_dispatcher.add(DuckDBSink(knowledge_db.connection, debug=debug))

    # 40-REQ-6.1: Audit JSONL directory — run-specific file added in engine.execute()
    audit_dir = AUDIT_DIR

    # v2: attach JSONL audit sink when --debug is active
    if debug:
        from agent_fox.knowledge.jsonl_sink import JsonlSink

        jsonl_dir = Path(".agent-fox")
        sink_dispatcher.add(JsonlSink(jsonl_dir))

    # 12-REQ-4.1, 12-REQ-4.2: Ingest ADRs and git commits at startup
    _run_ingestion(knowledge_db, config)

    # 42-REQ-3.1: Pre-compute fact rankings at plan dispatch time if enabled
    fact_cache: dict[str, RankedFactCache] | None = None
    if config.knowledge.fact_cache_enabled:
        fact_cache = _precompute_plan_fact_cache(
            plan_path,
            knowledge_db,
            config,
        )

    # 18-REQ-5.1: Create progress display (suppressed in JSON mode)
    theme = create_theme(config.theme)
    progress = ProgressDisplay(theme, quiet=quiet or json_mode)

    def session_runner_factory(
        node_id: str,
        *,
        archetype: str = "coder",
        instances: int = 1,
        assessed_tier: ModelTier | None = None,
        run_id: str = "",
    ) -> NodeSessionRunner:
        """Create a session runner for the given node.

        Parses the node_id to extract spec_name and task_group, then
        returns a runner configured with the project's AgentFoxConfig,
        hook config, and task-specific prompts.

        26-REQ-4.4: Passes archetype and instances from the plan node
        so the runner resolves the correct prompt, model, and allowlist.

        30-REQ-7.2: Passes assessed_tier from adaptive routing to override
        static model resolution.

        40-REQ-2.2: Passes run_id for audit event correlation.

        16-REQ-5.E1: If construction fails, the runner's execute()
        method will catch and report the failure as a session error.
        """
        return NodeSessionRunner(
            node_id,
            full_config,
            archetype=archetype,
            instances=instances,
            hook_config=hook_cfg,
            no_hooks=no_hooks,
            sink_dispatcher=sink_dispatcher,
            knowledge_db=knowledge_db,
            activity_callback=progress.activity_callback,
            assessed_tier=assessed_tier,
            run_id=run_id,
            fact_cache=fact_cache,
        )

    # 30-REQ-7.1, 38-REQ-1.3: Create assessment pipeline for adaptive routing
    assessment_pipeline = None
    try:
        from agent_fox.routing.assessor import AssessmentPipeline

        assessment_pipeline = AssessmentPipeline(
            config=full_config.routing,
            db=knowledge_db.connection,
        )
    except Exception:
        logger.warning(
            "Failed to initialize assessment pipeline, adaptive routing disabled",
            exc_info=True,
        )

    # Suppress noisy third-party warnings (e.g. HF Hub auth) that would
    # corrupt the Rich Live spinner display when written to stderr.
    warnings.filterwarnings("ignore", module=r"huggingface_hub\..*")
    warnings.filterwarnings("ignore", module=r"sentence_transformers\..*")

    # 18-REQ-5.1, 18-REQ-5.E1: Wrap execution with progress start/stop
    progress.start()
    try:
        # 16-REQ-1.3: construct Orchestrator
        # 40-REQ-9.1: pass sink_dispatcher for audit event emission
        # 40-REQ-12.2: pass audit_dir and db_conn for retention enforcement
        orchestrator = Orchestrator(
            orch_config,
            plan_path=plan_path,
            state_path=state_path,
            session_runner_factory=session_runner_factory,
            hook_config=config.hooks,
            specs_dir=Path(".specs"),
            no_hooks=no_hooks,
            task_callback=progress.task_callback,
            barrier_callback=lambda: _run_barrier_sync(knowledge_db, config),
            routing_config=full_config.routing,
            assessment_pipeline=assessment_pipeline,
            archetypes_config=full_config.archetypes,
            planning_config=full_config.planning,
            sink_dispatcher=sink_dispatcher,
            audit_dir=audit_dir,
            audit_db_conn=knowledge_db.connection,
            knowledge_db_conn=knowledge_db.connection,
        )

        # 16-REQ-1.4: execute via asyncio.run()
        state: ExecutionState = asyncio.run(orchestrator.run())

    except KeyboardInterrupt:
        # 23-REQ-5.E1: emit interrupted status in JSON mode
        if json_mode:
            json_io.emit_line({"status": "interrupted"})
        sys.exit(130)
    except AgentFoxError as exc:
        logger.debug("Execution failed", exc_info=True)
        if json_mode:
            json_io.emit_error(str(exc))
            sys.exit(1)
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        # 16-REQ-1.E2: unexpected exceptions
        logger.debug("Unexpected error during execution", exc_info=True)
        if json_mode:
            json_io.emit_error(str(exc))
            sys.exit(1)
        click.echo(f"Error: unexpected error: {exc}", err=True)
        sys.exit(1)
    finally:
        progress.stop()
        # 12-REQ-4.1, 12-REQ-4.2: Re-ingest to capture new commits/ADRs
        _run_ingestion(knowledge_db, config)
        # 39-REQ-3.2: Export all non-superseded facts to JSONL at session end
        export_facts_to_jsonl(knowledge_db.connection, DEFAULT_MEMORY_PATH)
        # Clean up knowledge store connection
        sink_dispatcher.close()
        knowledge_db.close()

    # 23-REQ-5.1: emit JSONL summary in JSON mode
    if json_mode:
        counts = _count_by_status(state.node_states)
        json_io.emit_line(
            {
                "event": "complete",
                "summary": {
                    "tasks": len(state.node_states),
                    "completed": counts.get("completed", 0),
                    "failed": counts.get("failed", 0),
                    "input_tokens": state.total_input_tokens,
                    "output_tokens": state.total_output_tokens,
                    "cost": state.total_cost,
                    "run_status": state.run_status,
                },
            }
        )
    else:
        # 16-REQ-3.1: print summary
        _print_summary(state)

    # 16-REQ-4.*: exit with appropriate code
    exit_code = _exit_code_for_status(state.run_status)
    if exit_code != 0:
        sys.exit(exit_code)
