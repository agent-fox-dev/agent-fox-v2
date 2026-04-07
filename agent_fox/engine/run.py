"""Backing module for the ``code`` CLI command.

Configures and runs the orchestrator, returning an ``ExecutionState``
(or a lightweight result with ``status`` for interrupted runs).

This module can be called without the Click framework.

Requirements: 59-REQ-4.1, 59-REQ-4.2, 59-REQ-4.3, 59-REQ-4.E1
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.state import ExecutionState

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig, OrchestratorConfig
    from agent_fox.engine.fact_cache import RankedFactCache

logger = logging.getLogger(__name__)

# Callback type aliases for progress display integration.
ActivityCallback = Callable[..., Any]
TaskCallback = Callable[..., Any]


@dataclass(frozen=True)
class InterruptedResult:
    """Lightweight result returned when execution is interrupted."""

    status: str = "interrupted"


def _apply_overrides(
    config: OrchestratorConfig,
    parallel: int | None,
    max_cost: float | None = None,
    max_sessions: int | None = None,
    watch_interval: int | None = None,
) -> OrchestratorConfig:
    """Return a new OrchestratorConfig with CLI overrides applied.

    Only overrides fields that were explicitly provided (not None).
    All non-overridden fields are preserved from the original config.

    Requirements: 16-REQ-2.1, 16-REQ-2.3, 16-REQ-2.4, 16-REQ-2.5,
                  70-REQ-3.3
    """
    from agent_fox.core.config import OrchestratorConfig as OC

    overrides: dict[str, object] = {}
    if parallel is not None:
        overrides["parallel"] = parallel
    if max_cost is not None:
        overrides["max_cost"] = max_cost
    if max_sessions is not None:
        overrides["max_sessions"] = max_sessions
    if watch_interval is not None:
        overrides["watch_interval"] = watch_interval
    if overrides:
        merged = config.model_dump()
        merged.update(overrides)
        return OC.model_validate(merged)
    return config


def _setup_infrastructure(
    config: AgentFoxConfig,
    *,
    debug: bool = False,
    plan_path: Path | None = None,
    activity_callback: ActivityCallback | None = None,
    no_hooks: bool = False,
) -> dict[str, Any]:
    """Set up knowledge DB, sinks, fact cache, and other infrastructure.

    Returns a dict of infrastructure components needed by the orchestrator.
    This is separated from run_code so the orchestrator construction can
    be tested independently.
    """
    from agent_fox.core.paths import AUDIT_DIR, PLAN_PATH
    from agent_fox.engine.fact_cache import precompute_fact_rankings
    from agent_fox.engine.session_lifecycle import NodeSessionRunner
    from agent_fox.knowledge.db import open_knowledge_store
    from agent_fox.knowledge.duckdb_sink import DuckDBSink
    from agent_fox.knowledge.ingest import run_background_ingestion
    from agent_fox.knowledge.sink import SinkDispatcher

    resolved_plan = plan_path or PLAN_PATH

    # Create DuckDB sink for session outcome recording
    sink_dispatcher = SinkDispatcher()
    knowledge_db = open_knowledge_store(config.knowledge)
    sink_dispatcher.add(DuckDBSink(knowledge_db.connection, debug=debug))

    # Attach JSONL audit sink when debug is active
    if debug:
        from agent_fox.knowledge.jsonl_sink import JsonlSink

        jsonl_dir = Path(".agent-fox")
        sink_dispatcher.add(JsonlSink(jsonl_dir))

    # Ingest at startup
    try:
        run_background_ingestion(
            knowledge_db.connection,
            config.knowledge,
            Path.cwd(),
        )
    except Exception:
        logger.warning("Background ingestion failed", exc_info=True)

    # Pre-compute fact rankings if enabled
    fact_cache: dict[str, RankedFactCache] | None = None
    try:
        if config.knowledge.fact_cache_enabled:
            import json as _json

            plan_data = _json.loads(resolved_plan.read_text(encoding="utf-8"))
            nodes = plan_data.get("nodes", {})
            spec_names = sorted({n.get("spec_name", "") for n in nodes.values() if n.get("spec_name")})
            if spec_names:
                fact_cache = precompute_fact_rankings(
                    knowledge_db.connection,
                    spec_names,
                    confidence_threshold=config.knowledge.confidence_threshold,
                )
    except Exception:
        logger.warning(
            "Failed to pre-compute fact rankings; will use live computation",
            exc_info=True,
        )

    # Create assessment pipeline for adaptive routing
    assessment_pipeline = None
    try:
        from agent_fox.routing.assessor import AssessmentPipeline

        assessment_pipeline = AssessmentPipeline(
            config=config.routing,
            db=knowledge_db.connection,
        )
    except Exception:
        logger.warning(
            "Failed to initialize assessment pipeline, adaptive routing disabled",
            exc_info=True,
        )

    hook_cfg = config.hooks

    def session_runner_factory(
        node_id: str,
        *,
        archetype: str = "coder",
        instances: int = 1,
        assessed_tier: Any = None,
        run_id: str = "",
        timeout_override: int | None = None,
        max_turns_override: int | None = None,
    ) -> Any:
        """Create a session runner for the given node."""
        return NodeSessionRunner(
            node_id,
            config,
            archetype=archetype,
            instances=instances,
            hook_config=hook_cfg,
            no_hooks=no_hooks,
            sink_dispatcher=sink_dispatcher,
            knowledge_db=knowledge_db,
            activity_callback=activity_callback,
            assessed_tier=assessed_tier,
            run_id=run_id,
            fact_cache=fact_cache,
            timeout_override=timeout_override,
            max_turns_override=max_turns_override,
        )

    return {
        "sink_dispatcher": sink_dispatcher,
        "knowledge_db": knowledge_db,
        "fact_cache": fact_cache,
        "assessment_pipeline": assessment_pipeline,
        "session_runner_factory": session_runner_factory,
        "audit_dir": AUDIT_DIR,
    }


async def run_code(
    config: AgentFoxConfig,
    *,
    parallel: int | None = None,
    no_hooks: bool = False,
    max_cost: float | None = None,
    max_sessions: int | None = None,
    debug: bool = False,
    watch: bool = False,
    watch_interval: int | None = None,
    specs_dir: Path | None = None,
    activity_callback: ActivityCallback | None = None,
    task_callback: TaskCallback | None = None,
) -> ExecutionState | InterruptedResult:
    """Configure and run the orchestrator.

    Returns the final ``ExecutionState`` on normal completion, or an
    ``InterruptedResult`` when a ``KeyboardInterrupt`` is caught.

    This function can be called without the Click framework.

    Args:
        config: Loaded AgentFoxConfig.
        parallel: Override parallelism (1-8).
        no_hooks: Skip all hook scripts.
        debug: Enable debug audit trail.
        watch: Keep running and poll for new specs.
        watch_interval: Seconds between watch polls.
        specs_dir: Path to specs directory (default: .specs).
        activity_callback: Optional callback for tool activity display.
        task_callback: Optional callback for task event display.

    Returns:
        ExecutionState on success, InterruptedResult on interruption.

    Requirements: 59-REQ-4.1, 59-REQ-4.2, 59-REQ-4.3, 59-REQ-4.E1
    """
    from agent_fox.core.paths import PLAN_PATH, STATE_PATH

    # Apply CLI overrides to OrchestratorConfig
    try:
        orch_config = _apply_overrides(
            config.orchestrator,
            parallel,
            max_cost=max_cost,
            max_sessions=max_sessions,
            watch_interval=watch_interval,
        )
    except Exception:
        orch_config = config.orchestrator

    plan_path = PLAN_PATH
    state_path = STATE_PATH
    specs_path = Path(specs_dir) if specs_dir else Path(".specs")

    # Set up infrastructure (knowledge DB, sinks, fact cache, etc.)
    infra: dict[str, Any] | None = None
    try:
        infra = _setup_infrastructure(
            config,
            debug=debug,
            plan_path=plan_path,
            activity_callback=activity_callback,
            no_hooks=no_hooks,
        )
    except Exception:
        logger.warning("Infrastructure setup failed", exc_info=True)

    # Suppress noisy third-party warnings
    warnings.filterwarnings("ignore", module=r"huggingface_hub\..*")
    warnings.filterwarnings("ignore", module=r"sentence_transformers\..*")

    try:
        # Build orchestrator kwargs — use infra if available
        orch_kwargs: dict[str, Any] = {
            "plan_path": plan_path,
            "state_path": state_path,
            "hook_config": config.hooks,
            "specs_dir": specs_path,
            "no_hooks": no_hooks,
            "watch": watch,
            "task_callback": task_callback,
            "routing_config": config.routing,
            "archetypes_config": config.archetypes,
            "planning_config": config.planning,
            "config_path": Path(".agent-fox/config.toml"),
            "full_config": config,
        }

        if infra is not None:
            orch_kwargs.update(
                {
                    "session_runner_factory": infra["session_runner_factory"],
                    "barrier_callback": lambda: _barrier_sync(infra, config),
                    "assessment_pipeline": infra["assessment_pipeline"],
                    "sink_dispatcher": infra["sink_dispatcher"],
                    "audit_dir": infra["audit_dir"],
                    "audit_db_conn": infra["knowledge_db"].connection,
                    "knowledge_db_conn": infra["knowledge_db"].connection,
                }
            )

        orchestrator = Orchestrator(orch_config, **orch_kwargs)
        state: ExecutionState = await orchestrator.run()
        return state

    except KeyboardInterrupt:
        # 59-REQ-4.E1: Return interrupted result instead of raising
        return InterruptedResult(status="interrupted")
    finally:
        if infra is not None:
            _cleanup_infrastructure(infra, config)


def _barrier_sync(infra: dict[str, Any], config: Any) -> None:
    """Run ingestion, export facts, and rebuild fact cache at sync barrier."""
    from agent_fox.engine.fact_cache import precompute_fact_rankings
    from agent_fox.knowledge.ingest import run_background_ingestion
    from agent_fox.knowledge.store import DEFAULT_MEMORY_PATH, export_facts_to_jsonl

    knowledge_db = infra["knowledge_db"]
    try:
        run_background_ingestion(
            knowledge_db.connection,
            config.knowledge,
            Path.cwd(),
        )
    except Exception:
        logger.warning("Barrier ingestion failed", exc_info=True)
    try:
        export_facts_to_jsonl(knowledge_db.connection, DEFAULT_MEMORY_PATH)
    except Exception:
        logger.warning("Barrier JSONL export failed", exc_info=True)

    # Rebuild the fact cache in-place so all holders of the shared dict
    # (including session_runner_factory closures) see the refreshed rankings.
    fact_cache = infra.get("fact_cache")
    if fact_cache is not None:
        try:
            spec_names = list(fact_cache.keys())
            if spec_names:
                new_cache = precompute_fact_rankings(
                    knowledge_db.connection,
                    spec_names,
                    confidence_threshold=config.knowledge.confidence_threshold,
                )
                fact_cache.clear()
                fact_cache.update(new_cache)
                logger.debug("Barrier sync: rebuilt fact cache for %d specs", len(spec_names))
        except Exception:
            logger.warning("Barrier fact cache rebuild failed", exc_info=True)


def _cleanup_infrastructure(infra: dict[str, Any], config: Any) -> None:
    """Clean up infrastructure resources."""
    from agent_fox.knowledge.ingest import run_background_ingestion
    from agent_fox.knowledge.store import DEFAULT_MEMORY_PATH, export_facts_to_jsonl

    knowledge_db = infra["knowledge_db"]

    # Re-ingest to capture new commits/ADRs
    try:
        run_background_ingestion(
            knowledge_db.connection,
            config.knowledge,
            Path.cwd(),
        )
    except Exception:
        logger.warning("Final ingestion failed", exc_info=True)

    # Export facts to JSONL
    try:
        export_facts_to_jsonl(knowledge_db.connection, DEFAULT_MEMORY_PATH)
    except Exception:
        logger.warning("Final JSONL export failed", exc_info=True)

    # Close sinks and DB
    try:
        infra["sink_dispatcher"].close()
    except Exception:
        logger.warning("Sink dispatcher close failed", exc_info=True)
    try:
        knowledge_db.close()
    except Exception:
        logger.warning("Knowledge DB close failed", exc_info=True)
