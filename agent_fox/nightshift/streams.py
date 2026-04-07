"""Concrete work stream implementations for the daemon framework.

Provides four built-in streams wrapping existing capabilities, plus a
``build_streams()`` factory that applies CLI flags, config, and platform
degradation rules.

Requirements: 85-REQ-1.1, 85-REQ-6.1, 85-REQ-6.2, 85-REQ-6.3,
              85-REQ-7.1, 85-REQ-7.E1, 85-REQ-10.1, 85-REQ-10.2,
              85-REQ-10.3, 85-REQ-10.E1
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.nightshift.daemon import SharedBudget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stream name mapping: config name <-> stream name
# ---------------------------------------------------------------------------

_CONFIG_TO_STREAM: dict[str, str] = {
    "specs": "spec-executor",
    "fixes": "fix-pipeline",
    "hunts": "hunt-scan",
    "spec_gen": "spec-generator",
}

_STREAM_TO_CONFIG: dict[str, str] = {v: k for k, v in _CONFIG_TO_STREAM.items()}


# ---------------------------------------------------------------------------
# SpecExecutorStream
# ---------------------------------------------------------------------------


class SpecExecutorStream:
    """Discovers and executes new specs from .specs/ directory.

    Requirements: 85-REQ-10.1, 85-REQ-10.2, 85-REQ-10.3, 85-REQ-10.E1
    """

    def __init__(
        self,
        config: object,
        budget: SharedBudget,
        *,
        discover_fn: Any | None = None,
        orch_factory: Callable[..., Any] | None = None,
        enabled: bool = True,
    ) -> None:
        self._config = config
        self._budget = budget
        self._discover_fn = discover_fn
        self._orch_factory = orch_factory
        self._enabled = enabled
        self._interval = getattr(getattr(config, "night_shift", None), "spec_interval", 60)

    @property
    def name(self) -> str:
        return "spec-executor"

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def run_once(self) -> None:
        """Discover new specs and run orchestrator for the batch.

        Requirements: 85-REQ-10.1, 85-REQ-10.2, 85-REQ-10.3, 85-REQ-10.E1
        """
        try:
            specs = await self._discover_fn() if self._discover_fn else []
        except Exception:
            logger.exception("discover_new_specs_gated() failed; will retry next cycle")
            return

        if not specs:
            logger.debug("No new specs discovered")
            return

        logger.info("Discovered %d new spec(s): %s", len(specs), [getattr(s, "name", str(s)) for s in specs])

        if self._orch_factory is None:
            logger.warning("No orchestrator factory configured; skipping spec execution")
            return

        try:
            orch = self._orch_factory(specs)
            result = await orch.run()
            cost = getattr(result, "total_cost", 0.0)
            self._budget.add_cost(cost)
            logger.info("Spec batch completed with cost %.4f", cost)
        except Exception:
            logger.exception("Orchestrator run failed for spec batch")

    async def shutdown(self) -> None:
        """No resources to clean up."""


# ---------------------------------------------------------------------------
# FixPipelineStream
# ---------------------------------------------------------------------------


class FixPipelineStream:
    """Wraps NightShiftEngine._drain_issues() as a work stream.

    Requirements: 85-REQ-1.1
    """

    def __init__(
        self,
        engine: object,
        budget: SharedBudget,
        *,
        enabled: bool = True,
        interval: int = 900,
    ) -> None:
        self._engine = engine
        self._budget = budget
        self._enabled = enabled
        self._interval = interval

    @property
    def name(self) -> str:
        return "fix-pipeline"

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def run_once(self) -> None:
        """Run one drain-issues cycle and report cost delta."""
        cost_before = getattr(getattr(self._engine, "state", None), "total_cost", 0.0)
        await self._engine._drain_issues()  # type: ignore[attr-defined]
        cost_after = getattr(getattr(self._engine, "state", None), "total_cost", 0.0)
        delta = cost_after - cost_before
        if delta > 0:
            self._budget.add_cost(delta)

    async def shutdown(self) -> None:
        """No resources to clean up."""


# ---------------------------------------------------------------------------
# HuntScanStream
# ---------------------------------------------------------------------------


class HuntScanStream:
    """Wraps NightShiftEngine._run_hunt_scan() as a work stream.

    Requirements: 85-REQ-1.1, 85-REQ-6.3
    """

    def __init__(
        self,
        engine: object,
        budget: SharedBudget,
        *,
        enabled: bool = True,
        auto_fix: bool = False,
        interval: int = 14400,
    ) -> None:
        self._engine = engine
        self._budget = budget
        self._enabled = enabled
        self.auto_fix = auto_fix
        self._interval = interval

    @property
    def name(self) -> str:
        return "hunt-scan"

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def run_once(self) -> None:
        """Run one hunt scan cycle and report cost delta."""
        cost_before = getattr(getattr(self._engine, "state", None), "total_cost", 0.0)
        await self._engine._run_hunt_scan()  # type: ignore[attr-defined]
        cost_after = getattr(getattr(self._engine, "state", None), "total_cost", 0.0)
        delta = cost_after - cost_before
        if delta > 0:
            self._budget.add_cost(delta)

    async def shutdown(self) -> None:
        """No resources to clean up."""


# ---------------------------------------------------------------------------
# SpecGeneratorStream (stub)
# ---------------------------------------------------------------------------


class SpecGeneratorStream:
    """Stub work stream for spec generation from af:spec issues.

    Placeholder for spec 86. run_once() is intentionally a no-op.

    Requirements: 85-REQ-1.1
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        interval: int = 300,
    ) -> None:
        self._enabled = enabled
        self._interval = interval

    @property
    def name(self) -> str:
        return "spec-generator"

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def run_once(self) -> None:
        """No-op stub — spec generation is not yet implemented (spec 86)."""
        logger.debug("spec-generator stream: not yet implemented (placeholder for spec 86)")

    async def shutdown(self) -> None:
        """No resources to clean up."""


# ---------------------------------------------------------------------------
# build_streams() factory
# ---------------------------------------------------------------------------


def build_streams(
    config: object,
    *,
    no_specs: bool = False,
    no_fixes: bool = False,
    no_hunts: bool = False,
    no_spec_gen: bool = False,
    auto: bool = False,
    engine: object | None = None,
    discover_fn: Any | None = None,
    orch_factory: Callable[..., Any] | None = None,
    budget: SharedBudget | None = None,
) -> list[SpecExecutorStream | FixPipelineStream | HuntScanStream | SpecGeneratorStream]:
    """Build all four work streams with proper enabled/disabled state.

    Applies three layers of filtering:
    1. Config ``enabled_streams`` list (empty = all enabled, 85-REQ-9.E2)
    2. CLI ``--no-*`` flags (85-REQ-6.1)
    3. Platform degradation: platform.type="none" disables platform-dependent
       streams (85-REQ-7.1)

    Requirements: 85-REQ-6.1, 85-REQ-6.2, 85-REQ-6.3, 85-REQ-7.1,
                  85-REQ-7.E1, 85-REQ-9.2, 85-REQ-9.E2
    """
    from agent_fox.nightshift.daemon import SharedBudget as _SharedBudget

    if budget is None:
        budget = _SharedBudget(max_cost=None)

    ns = getattr(config, "night_shift", None)
    enabled_streams_cfg: list[str] = getattr(ns, "enabled_streams", []) or []

    # Empty list = all enabled (85-REQ-9.E2)
    if not enabled_streams_cfg:
        effective_config_enabled = set(_CONFIG_TO_STREAM.keys())
    else:
        effective_config_enabled = set()
        for name in enabled_streams_cfg:
            if name in _CONFIG_TO_STREAM:
                effective_config_enabled.add(name)
            else:
                logger.warning("Unknown stream name in enabled_streams: %r (ignored)", name)

    # CLI flags determine CLI-enabled set
    cli_enabled: set[str] = set()
    if not no_specs:
        cli_enabled.add("specs")
    if not no_fixes:
        cli_enabled.add("fixes")
    if not no_hunts:
        cli_enabled.add("hunts")
    if not no_spec_gen:
        cli_enabled.add("spec_gen")

    # Platform degradation (85-REQ-7.1)
    platform_type = getattr(getattr(config, "platform", None), "type", "github")
    platform_dependent = {"fixes", "hunts", "spec_gen"}
    if platform_type == "none":
        logger.warning(
            "Platform type is 'none'; disabling platform-dependent streams (fix-pipeline, hunt-scan, spec-generator)"
        )
        cli_enabled -= platform_dependent

    # Final enabled set = intersection of config and CLI
    final_enabled = effective_config_enabled & cli_enabled

    # Get intervals from config
    spec_gen_interval = getattr(ns, "spec_gen_interval", 300)
    issue_check_interval = getattr(ns, "issue_check_interval", 900)
    hunt_scan_interval = getattr(ns, "hunt_scan_interval", 14400)

    # Build streams
    streams: list[SpecExecutorStream | FixPipelineStream | HuntScanStream | SpecGeneratorStream] = []

    streams.append(
        SpecExecutorStream(
            config=config,
            budget=budget,
            discover_fn=discover_fn,
            orch_factory=orch_factory,
            enabled="specs" in final_enabled,
        )
    )

    streams.append(
        FixPipelineStream(
            engine=engine,
            budget=budget,
            enabled="fixes" in final_enabled,
            interval=issue_check_interval,
        )
    )

    streams.append(
        HuntScanStream(
            engine=engine,
            budget=budget,
            enabled="hunts" in final_enabled,
            auto_fix=auto,
            interval=hunt_scan_interval,
        )
    )

    streams.append(
        SpecGeneratorStream(
            enabled="spec_gen" in final_enabled,
            interval=spec_gen_interval,
        )
    )

    return streams
