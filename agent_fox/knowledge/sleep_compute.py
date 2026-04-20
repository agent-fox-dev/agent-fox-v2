"""Sleep-time compute pipeline: protocol, orchestrator, and shared helpers.

Provides the SleepTask protocol, SleepContext and SleepTaskResult data types,
the SleepComputer orchestrator, and shared utility functions (compute_content_hash,
upsert_artifact) used by all sleep task implementations.

Requirements: 112-REQ-1.1 through 112-REQ-1.5, 112-REQ-2.1 through 112-REQ-2.5,
              112-REQ-2.E1, 112-REQ-2.E2, 112-REQ-7.2, 112-REQ-7.3, 112-REQ-7.4,
              112-REQ-8.3
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import duckdb

if TYPE_CHECKING:
    from agent_fox.core.config import SleepConfig

    try:
        from agent_fox.knowledge.extraction import EmbeddingGenerator
    except ImportError:
        EmbeddingGenerator = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SleepContext:
    """Bundle of resources passed to each sleep task's run() method.

    Requirements: 112-REQ-1.4
    """

    conn: duckdb.DuckDBPyConnection
    repo_root: Path
    model: str
    embedder: object  # EmbeddingGenerator | None
    budget_remaining: float
    sink_dispatcher: object  # SinkDispatcher | None


@dataclass(frozen=True)
class SleepTaskResult:
    """Result produced by a single sleep task run.

    Requirements: 112-REQ-1.5
    """

    created: int
    refreshed: int
    unchanged: int
    llm_cost: float


@dataclass(frozen=True)
class SleepComputeResult:
    """Aggregate result from SleepComputer.run().

    Requirements: 112-REQ-2.2
    """

    task_results: dict[str, SleepTaskResult]
    total_llm_cost: float
    errors: list[str]


# ---------------------------------------------------------------------------
# SleepTask Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SleepTask(Protocol):
    """Protocol for sleep-time pre-computation tasks.

    Requirements: 112-REQ-1.1, 112-REQ-1.2, 112-REQ-1.3
    """

    @property
    def name(self) -> str:
        """Unique string identifier for this task."""
        ...

    @property
    def cost_estimate(self) -> float:
        """Estimated LLM cost (USD) for one run of this task.

        Used by SleepComputer to check whether the remaining budget can
        accommodate this task before running it.
        """
        ...

    async def run(self, ctx: SleepContext) -> SleepTaskResult:
        """Execute the sleep task, returning a result with artifact counts and cost."""
        ...

    def stale_scopes(self, conn: duckdb.DuckDBPyConnection) -> list[str]:
        """Return scope keys whose artifacts need regeneration."""
        ...


# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------


def compute_content_hash(facts: list[tuple[str, float]]) -> str:
    """Compute an order-independent SHA-256 hash over (fact_id, confidence) pairs.

    The hash is built by sorting the pairs before concatenating, ensuring the
    same result regardless of input order.

    Requirements: 112-REQ-3.2, 112-REQ-4.2 (Property 1: Staleness Determinism)
    """
    hash_input = "|".join(
        sorted(f"{fact_id}:{confidence}" for fact_id, confidence in facts)
    )
    return hashlib.sha256(hash_input.encode()).hexdigest()


def upsert_artifact(
    conn: duckdb.DuckDBPyConnection,
    *,
    task_name: str,
    scope_key: str,
    content: str,
    metadata_json: str,
    content_hash: str,
) -> None:
    """Insert a new sleep artifact, superseding any existing active artifact.

    Steps:
    1. SET superseded_at = NOW() on any existing active row for (task_name, scope_key).
    2. INSERT new row with superseded_at = NULL.

    This maintains the invariant that at most one active artifact exists per
    (task_name, scope_key) pair.

    Requirements: 112-REQ-8.3 (Property 2: Artifact Uniqueness)
    """
    # Supersede any existing active artifact for this (task_name, scope_key)
    conn.execute(
        """
        UPDATE sleep_artifacts
        SET superseded_at = CURRENT_TIMESTAMP
        WHERE task_name = ?
          AND scope_key = ?
          AND superseded_at IS NULL
        """,
        [task_name, scope_key],
    )

    # Insert the new artifact
    artifact_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO sleep_artifacts
            (id, task_name, scope_key, content, metadata_json, content_hash, created_at, superseded_at)
        VALUES
            (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, NULL)
        """,
        [artifact_id, task_name, scope_key, content, metadata_json, content_hash],
    )


# ---------------------------------------------------------------------------
# SleepComputer orchestrator
# ---------------------------------------------------------------------------

# Map of task name → SleepConfig field name for per-task enable flags.
# If a task name is not listed here, it defaults to enabled.
_TASK_ENABLE_FLAGS: dict[str, str] = {
    "context_rewriter": "context_rewriter_enabled",
    "bundle_builder": "bundle_builder_enabled",
}


class SleepComputer:
    """Orchestrates registered sleep tasks with budget control and error isolation.

    Tasks are executed in registration order. Each task receives a SleepContext
    with the remaining budget decremented by the sum of prior tasks' actual LLM
    costs. A task is skipped if:

    - Its per-task enable flag in SleepConfig is False, OR
    - The remaining budget is less than the task's declared cost_estimate.

    Exceptions from individual tasks are caught, logged, and recorded in the
    result's error list — subsequent tasks still run.

    Requirements: 112-REQ-2.1 through 112-REQ-2.5, 112-REQ-2.E1, 112-REQ-2.E2,
                  112-REQ-7.2, 112-REQ-7.3, 112-REQ-7.4
    """

    def __init__(
        self,
        tasks: Sequence[SleepTask],
        config: SleepConfig,
    ) -> None:
        self._tasks = list(tasks)
        self._config = config

    def _is_task_enabled(self, task: SleepTask) -> bool:
        """Check the per-task enable flag in SleepConfig.

        Requirements: 112-REQ-7.4
        """
        flag_name = _TASK_ENABLE_FLAGS.get(task.name)
        if flag_name is None:
            return True  # Unknown tasks are enabled by default
        return bool(getattr(self._config, flag_name, True))

    async def run(self, ctx: SleepContext) -> SleepComputeResult:
        """Execute all registered tasks in order with budget control.

        Requirements: 112-REQ-2.1, 112-REQ-2.2, 112-REQ-2.3, 112-REQ-2.4,
                      112-REQ-2.5, 112-REQ-7.3
        """
        task_results: dict[str, SleepTaskResult] = {}
        errors: list[str] = []
        total_cost = 0.0
        remaining_budget = ctx.budget_remaining

        for task in self._tasks:
            # Check per-task enable flag (REQ-7.4)
            if not self._is_task_enabled(task):
                logger.info("Skipping disabled task: %s", task.name)
                continue

            # Check budget (REQ-2.4): skip if remaining budget < task's cost estimate
            cost_estimate = getattr(task, "cost_estimate", 0.0)
            if remaining_budget < cost_estimate:
                msg = f"budget_exhausted: {task.name}"
                logger.info(
                    "Skipping task %s — insufficient budget (%.4f < %.4f)",
                    task.name,
                    remaining_budget,
                    cost_estimate,
                )
                errors.append(msg)
                continue

            # Build a context with the current remaining budget
            task_ctx = SleepContext(
                conn=ctx.conn,
                repo_root=ctx.repo_root,
                model=ctx.model,
                embedder=ctx.embedder,
                budget_remaining=remaining_budget,
                sink_dispatcher=ctx.sink_dispatcher,
            )

            # Run the task with error isolation (REQ-2.3)
            try:
                logger.info("Running sleep task: %s", task.name)
                result = await task.run(task_ctx)
                task_results[task.name] = result
                total_cost += result.llm_cost
                remaining_budget -= result.llm_cost
                logger.info(
                    "Sleep task %s complete: created=%d refreshed=%d unchanged=%d cost=%.4f",
                    task.name,
                    result.created,
                    result.refreshed,
                    result.unchanged,
                    result.llm_cost,
                )
            except Exception as exc:
                msg = f"{task.name}: {type(exc).__name__}: {exc}"
                logger.warning("Sleep task %s failed: %s", task.name, exc, exc_info=True)
                errors.append(msg)

        compute_result = SleepComputeResult(
            task_results=task_results,
            total_llm_cost=total_cost,
            errors=errors,
        )

        # Emit audit event (REQ-2.5)
        self._emit_audit_event(ctx, compute_result)

        return compute_result

    def _emit_audit_event(
        self,
        ctx: SleepContext,
        result: SleepComputeResult,
    ) -> None:
        """Emit SLEEP_COMPUTE_COMPLETE audit event if a sink dispatcher is present."""
        sink_dispatcher = ctx.sink_dispatcher
        if sink_dispatcher is None:
            return

        from agent_fox.knowledge.audit import AuditEvent, AuditEventType

        payload: dict[str, object] = {
            "total_cost": result.total_llm_cost,
            "task_count": len(result.task_results),
            "error_count": len(result.errors),
            "task_results": {
                name: {
                    "created": r.created,
                    "refreshed": r.refreshed,
                    "unchanged": r.unchanged,
                    "llm_cost": r.llm_cost,
                }
                for name, r in result.task_results.items()
            },
        }
        event = AuditEvent(
            run_id="sleep-compute",
            event_type=AuditEventType.SLEEP_COMPUTE_COMPLETE,
            payload=payload,
        )
        sink_dispatcher.emit_audit_event(event)
