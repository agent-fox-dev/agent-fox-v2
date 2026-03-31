"""Backing module for the ``plan`` CLI command.

Provides ``run_plan()`` as a callable entry point for building
execution plans, usable without the Click framework.

Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from agent_fox.graph.types import TaskGraph

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)


def run_plan(
    config: AgentFoxConfig,
    *,
    specs_dir: Path | None = None,
    force: bool = False,
    fast: bool = False,
    filter_spec: str | None = None,
) -> TaskGraph:
    """Build or rebuild the task graph.

    This function can be called without the Click framework.

    Args:
        config: Loaded AgentFoxConfig.
        specs_dir: Path to specs directory (default: .specs).
        force: Discard cached plan and rebuild.
        fast: Exclude optional tasks.
        filter_spec: Plan a single spec only.

    Returns:
        A fully resolved TaskGraph.

    Requirements: 59-REQ-5.1, 59-REQ-5.2, 59-REQ-5.3
    """
    from agent_fox.cli.plan import (
        _build_plan,
        _compute_config_hash,
        _compute_specs_hash,
    )
    from agent_fox.graph.persistence import load_plan, save_plan

    resolved_specs_dir = specs_dir or Path(".specs")
    plan_path = Path(".agent-fox") / "plan.json"

    specs_hash = _compute_specs_hash(resolved_specs_dir)
    config_hash = _compute_config_hash(config)

    graph: TaskGraph | None = None

    # Use cached plan unless forced
    if not force and plan_path.exists():
        existing = load_plan(plan_path)
        if existing is not None:
            from agent_fox.cli.plan import _cache_matches_request

            if _cache_matches_request(
                existing,
                fast=fast,
                filter_spec=filter_spec,
                specs_hash=specs_hash,
                config_hash=config_hash,
            ):
                logger.info("Using cached plan from %s", plan_path)
                return existing

    # Build fresh plan
    graph = _build_plan(resolved_specs_dir, filter_spec, fast, config)

    # Persist
    save_plan(graph, plan_path)

    return graph
