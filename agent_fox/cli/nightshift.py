"""CLI command for the night-shift autonomous maintenance daemon.

Runs continuously, scanning the codebase on a timed schedule using both
static tooling and AI-powered agents to discover maintenance issues.
Each finding is reported as a platform issue. Issues labelled ``af:fix``
are automatically processed through the full archetype pipeline and a
pull request is opened per fix.

Requirements: 61-REQ-1.1, 61-REQ-1.2, 61-REQ-1.3, 61-REQ-1.4,
              85-REQ-2.1, 85-REQ-4.1, 85-REQ-6.1, 85-REQ-10.2
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig
    from agent_fox.spec.discovery import SpecInfo
    from agent_fox.ui.progress import ProgressDisplay

logger = logging.getLogger(__name__)


class _SpecBatchRunner:
    """Builds a plan from discovered specs and runs the orchestrator.

    Wraps ``run_code()`` so that ``SpecExecutorStream`` can call
    ``runner.run()`` and get back an ``ExecutionState`` with
    ``total_cost``.

    Requirements: 85-REQ-10.2
    """

    def __init__(
        self,
        config: AgentFoxConfig,
        specs: list[SpecInfo],
        progress: ProgressDisplay | None = None,
    ) -> None:
        self._config = config
        self._specs = specs
        self._progress = progress

    async def run(self) -> Any:
        from agent_fox.engine.run import run_code
        from agent_fox.graph.builder import build_graph
        from agent_fox.graph.persistence import save_plan
        from agent_fox.graph.resolver import resolve_order
        from agent_fox.knowledge.db import open_knowledge_store
        from agent_fox.spec.parser import parse_cross_deps, parse_tasks

        # Build plan from the discovered specs
        task_groups: dict[str, list] = {}
        cross_deps = []
        for spec in self._specs:
            if not spec.has_tasks:
                continue
            groups = parse_tasks(spec.path / "tasks.md")
            if groups:
                task_groups[spec.name] = groups
            if spec.has_prd:
                deps = parse_cross_deps(spec.path / "prd.md", spec_name=spec.name)
                cross_deps.extend(deps)

        discovered_names = {s.name for s in self._specs}
        cross_deps = [d for d in cross_deps if d.from_spec in discovered_names and d.to_spec in discovered_names]

        graph = build_graph(
            self._specs,
            task_groups,
            cross_deps,
            archetypes_config=self._config.archetypes,
        )
        graph.order = resolve_order(graph)
        _knowledge_db = open_knowledge_store(self._config.knowledge)
        try:
            save_plan(graph, _knowledge_db.connection)
        finally:
            _knowledge_db.close()

        return await run_code(
            self._config,
            activity_callback=(self._progress.activity_callback if self._progress else None),
            task_callback=(self._progress.task_callback if self._progress else None),
        )


@click.command("night-shift")
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help="Auto-assign af:fix label to every issue created during hunt scans.",
)
@click.option(
    "--no-specs",
    is_flag=True,
    default=False,
    help="Disable the spec-executor stream.",
)
@click.option(
    "--no-fixes",
    is_flag=True,
    default=False,
    help="Disable the fix-pipeline stream.",
)
@click.option(
    "--no-hunts",
    is_flag=True,
    default=False,
    help="Disable the hunt-scan stream.",
)
@click.option(
    "--specs-dir",
    type=click.Path(),
    default=None,
    help="Path to specs directory (default: from config, or .agent-fox/specs)",
)
@click.pass_context
def night_shift_cmd(
    ctx: click.Context,
    auto: bool,
    no_specs: bool,
    no_fixes: bool,
    no_hunts: bool,
    specs_dir: str | None,
) -> None:
    """Run the night-shift autonomous maintenance daemon.

    Polls for open issues labelled ``af:fix`` and runs hunt scans on
    configurable intervals.  Continues until interrupted with Ctrl-C
    (SIGINT) or until the configured cost limit is reached.

    Exit codes:
      0 -- clean shutdown (single SIGINT or cost limit reached)
      1 -- startup failure (platform not configured, etc.)
      130 -- immediate abort (double SIGINT)
    """
    from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget
    from agent_fox.nightshift.engine import (
        NightShiftEngine,
        validate_night_shift_prerequisites,
    )
    from agent_fox.nightshift.platform_factory import create_platform
    from agent_fox.nightshift.streams import build_streams

    config = ctx.obj["config"]
    project_root = Path.cwd()

    # 61-REQ-1.E1: Validate platform is configured before entering the loop.
    validate_night_shift_prerequisites(config)

    # Instantiate the platform from config (exits with code 1 on failure).
    platform = create_platform(config, project_root)

    # Create DuckDB-backed SinkDispatcher for audit cost tracking (91-REQ-1.2).
    # If DuckDB cannot be opened, proceed without cost tracking (91-REQ-1.E1).
    _knowledge_db = None
    _sink_dispatcher = None
    try:
        from agent_fox.knowledge.db import open_knowledge_store
        from agent_fox.knowledge.duckdb_sink import DuckDBSink
        from agent_fox.knowledge.sink import SinkDispatcher

        _knowledge_db = open_knowledge_store(config.knowledge)
        _db_sink = DuckDBSink(_knowledge_db.connection)
        _sink_dispatcher = SinkDispatcher([_db_sink])
    except Exception:
        logger.warning(
            "Failed to open knowledge store for night-shift audit — cost tracking will be unavailable for this session",
            exc_info=True,
        )

    # --- ProgressDisplay setup (81-REQ-2.1) ---------------------------------
    from agent_fox.core.config import ThemeConfig
    from agent_fox.ui.display import create_theme
    from agent_fox.ui.progress import ProgressDisplay

    theme_config = getattr(config, "theme", None) or ThemeConfig()
    theme = create_theme(theme_config)
    quiet = ctx.obj.get("quiet", False) if isinstance(ctx.obj, dict) else False
    progress = ProgressDisplay(theme, quiet=quiet)
    progress.start()
    # -----------------------------------------------------------------------

    # Create EmbeddingGenerator for similarity-based dedup and ignore filter
    # (110-REQ-2.1, 110-REQ-3.3, 110-REQ-4.3). Falls back to None on failure,
    # which causes both filter functions to skip embedding-based matching
    # (fingerprint-only dedup).
    _embedder = None
    try:
        from agent_fox.knowledge.embeddings import EmbeddingGenerator

        _embedder = EmbeddingGenerator(config.knowledge)
    except Exception:
        logger.warning(
            "Failed to create EmbeddingGenerator for night-shift; "
            "similarity-based dedup and ignore filtering will be disabled",
            exc_info=True,
        )

    # Create the engine for business logic (fix pipeline, hunt scan).
    # Streams delegate to engine methods; the engine is NOT the lifecycle
    # manager.  DaemonRunner handles lifecycle, scheduling, and budget.
    engine = NightShiftEngine(
        config=config,
        platform=platform,
        auto_fix=auto,
        activity_callback=progress.activity_callback,
        task_callback=progress.task_callback,
        status_callback=progress.print_status,
        spinner_callback=progress.update_spinner_text,
        sink_dispatcher=_sink_dispatcher,
        conn=(_knowledge_db.connection if _knowledge_db is not None else None),
        embedder=_embedder,
    )

    # Shared cost budget (85-REQ-5.1, 85-REQ-5.2)
    max_cost = getattr(getattr(config, "orchestrator", None), "max_cost", None)
    budget = SharedBudget(max_cost=max_cost)

    # Spec discovery closure (85-REQ-10.1) — tracks already-seen specs
    # across cycles so each spec is only surfaced once per daemon run.
    from agent_fox.core.config import resolve_spec_root
    from agent_fox.engine.hot_load import discover_new_specs_gated

    _known_specs: set[str] = set()
    _specs_dir = Path(specs_dir) if specs_dir else resolve_spec_root(config, project_root)
    _db_conn = _knowledge_db.connection if _knowledge_db is not None else None

    async def _discover_fn() -> list:
        found = await discover_new_specs_gated(_specs_dir, _known_specs, project_root, db_conn=_db_conn)
        for spec in found:
            _known_specs.add(spec.name)
        return found

    # Orchestrator factory for the spec-executor stream (85-REQ-10.2).
    # Each call builds a plan from the discovered specs, then delegates
    # to run_code() which handles infrastructure setup, orchestrator
    # creation, execution, and cleanup.
    def _orch_factory(specs: list) -> _SpecBatchRunner:
        return _SpecBatchRunner(config, specs, progress=progress)

    # Build work streams with CLI flags (85-REQ-6.1)
    streams = build_streams(
        config,
        no_specs=no_specs,
        no_fixes=no_fixes,
        no_hunts=no_hunts,
        auto=auto,
        engine=engine,
        budget=budget,
        discover_fn=_discover_fn,
        orch_factory=_orch_factory,
    )

    # Create the daemon runner (85-REQ-1.2, 85-REQ-2.1, 85-REQ-4.1)
    pid_path = project_root / ".agent-fox" / "daemon.pid"
    runner = DaemonRunner(
        config=config,
        platform=platform,
        streams=streams,
        budget=budget,
        pid_path=pid_path,
        idle_callback=progress.update_spinner_text,
    )

    # --- Signal handling ----------------------------------------------------
    # First SIGINT/SIGTERM: graceful shutdown (current operation completes).
    # Second interrupt: immediate abort with exit code 130.
    # 61-REQ-1.3, 61-REQ-1.4, 85-REQ-2.2, 85-REQ-2.3
    _interrupt_count = 0

    def _signal_handler(signum: int, frame: object) -> None:
        nonlocal _interrupt_count
        _interrupt_count += 1
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        if _interrupt_count == 1:
            logger.info(
                "%s received — completing current operation then exiting (send another signal to abort immediately)",
                sig_name,
            )
            runner.request_shutdown()
        else:
            logger.warning("Second interrupt received — aborting immediately")
            sys.exit(130)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    # -----------------------------------------------------------------------

    click.echo("Night-shift daemon starting. Press Ctrl-C to stop gracefully.")

    try:
        daemon_state = asyncio.run(runner.run())
    except SystemExit:
        raise
    except Exception as exc:
        logger.error("Night-shift daemon failed: %s", exc, exc_info=True)
        click.echo(f"Error: night-shift daemon failed: {exc}", err=True)
        sys.exit(1)
    finally:
        progress.stop()
        # Close platform connection if it supports it
        try:
            if hasattr(platform, "close"):
                asyncio.run(platform.close())
        except Exception:  # noqa: BLE001
            pass
        # Close knowledge store connection used for audit (91-REQ-1.2)
        try:
            if _knowledge_db is not None:
                _knowledge_db.close()
        except Exception:  # noqa: BLE001
            pass

    # Pull detailed stats from the engine state (streams don't track these).
    click.echo(
        f"Night-shift stopped. "
        f"Scans completed: {engine.state.hunt_scans_completed}, "
        f"Issues fixed: {engine.state.issues_fixed}, "
        f"Total cost: ${daemon_state.total_cost:.4f}"
    )
