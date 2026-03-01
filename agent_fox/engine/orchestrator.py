"""Orchestrator: deterministic execution engine. Zero LLM calls.

Loads the task graph, dispatches sessions in dependency order, manages
retries with error feedback, cascade-blocks failed tasks, persists state
after every session, and handles graceful interruption.

Requirements: 04-REQ-1.1 through 04-REQ-1.4, 04-REQ-1.E1, 04-REQ-1.E2,
              04-REQ-2.1 through 04-REQ-2.3, 04-REQ-2.E1,
              04-REQ-7.1, 04-REQ-7.2, 04-REQ-7.E1,
              04-REQ-8.1, 04-REQ-8.3, 04-REQ-8.E1,
              04-REQ-9.1, 04-REQ-9.E1
"""

from __future__ import annotations

import json
import logging
import signal
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_fox.core.config import OrchestratorConfig
from agent_fox.core.errors import PlanError
from agent_fox.engine.serial import SerialRunner
from agent_fox.engine.state import (
    ExecutionState,
    RunStatus,
    SessionRecord,
    StateManager,
)
from agent_fox.engine.sync import GraphSync

logger = logging.getLogger(__name__)


class Orchestrator:
    """Deterministic execution engine. Zero LLM calls.

    Reads the task graph from plan.json, dispatches sessions in dependency
    order (serial or parallel), manages retries with error feedback,
    cascade-blocks failed tasks, persists state, and handles graceful
    interruption via SIGINT.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        plan_path: Path,
        state_path: Path,
        session_runner_factory: Callable[..., Any],
    ) -> None:
        """Initialise the orchestrator.

        Args:
            config: Orchestrator configuration (parallelism, retries, etc.)
            plan_path: Path to .agent-fox/plan.json
            state_path: Path to .agent-fox/state.jsonl
            session_runner_factory: Factory that creates a SessionRunner for
                a given node_id. Injected to enable testing with mocks.
        """
        self._config = config
        self._plan_path = plan_path
        self._state_path = state_path
        self._session_runner_factory = session_runner_factory
        self._state_manager = StateManager(state_path)
        self._graph_sync: GraphSync | None = None
        self._interrupted = False
        self._interrupt_count = 0
        self._serial_runner = SerialRunner(
            session_runner_factory=session_runner_factory,
            inter_session_delay=float(config.inter_session_delay),
        )

    async def run(self) -> ExecutionState:
        """Execute the full orchestration loop.

        1. Load plan from plan.json
        2. Load or initialize execution state
        3. Register SIGINT handler
        4. Loop: pick ready tasks, dispatch, update state
        5. Return final execution state

        Raises:
            PlanError: if plan.json is missing or corrupted
        """
        # 1. Load plan
        plan_data = self._load_plan()
        nodes = plan_data.get("nodes", {})
        edges_list = plan_data.get("edges", [])

        # 04-REQ-1.E2: Empty plan
        if not nodes:
            state = ExecutionState(
                plan_hash=self._compute_plan_hash(),
                node_states={},
                run_status=RunStatus.COMPLETED,
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            )
            return state

        # Build edges dict: target -> [source] (dependencies)
        edges_dict = self._build_edges_dict(nodes, edges_list)

        # 2. Load or initialize execution state
        plan_hash = self._compute_plan_hash()
        state = self._load_or_init_state(plan_hash, nodes)

        # Handle in-progress tasks from interrupted runs (04-REQ-7.E1)
        self._reset_in_progress_tasks(state)

        # Initialize graph sync
        self._graph_sync = GraphSync(state.node_states, edges_dict)

        # Track per-task attempt counts
        attempt_tracker: dict[str, int] = self._init_attempt_tracker(state)

        # Track last error per task for retry context
        error_tracker: dict[str, str | None] = (
            self._init_error_tracker(state)
        )

        # 3. Install signal handler
        self._install_signal_handler()

        # 4. Main execution loop
        first_dispatch = True
        try:
            while True:
                # Check for interruption
                if self._interrupted:
                    await self._shutdown(state)
                    return state

                # Get ready tasks
                ready = self._graph_sync.ready_tasks()

                if not ready:
                    # Check if stalled or completed
                    if self._graph_sync.is_stalled():
                        state.run_status = RunStatus.STALLED
                        logger.warning(
                            "Execution stalled. Summary: %s",
                            self._graph_sync.summary(),
                        )
                        self._state_manager.save(state)
                        return state

                    # All tasks completed
                    state.run_status = RunStatus.COMPLETED
                    self._state_manager.save(state)
                    return state

                # Dispatch ready tasks (serial mode: one at a time)
                for node_id in ready:
                    if self._interrupted:
                        break

                    attempt = attempt_tracker.get(node_id, 0) + 1
                    attempt_tracker[node_id] = attempt

                    # Check retry limit
                    if attempt > self._config.max_retries + 1:
                        # Should not happen in normal flow, but guard
                        self._block_task(
                            node_id, state,
                            f"Retry limit exceeded for {node_id}",
                        )
                        continue

                    # Apply inter-session delay (skip before first dispatch)
                    if not first_dispatch:
                        await self._serial_runner.delay()
                    first_dispatch = False

                    # Mark as in-progress
                    self._graph_sync.mark_in_progress(node_id)

                    # Get previous error for retry context
                    previous_error = error_tracker.get(node_id)

                    # Dispatch session
                    record = await self._dispatch_session(
                        node_id, attempt, previous_error,
                    )

                    # Record session result
                    self._state_manager.record_session(state, record)

                    # Update graph based on result
                    if record.status == "completed":
                        self._graph_sync.mark_completed(node_id)
                        state.node_states[node_id] = "completed"
                        error_tracker.pop(node_id, None)
                    else:
                        # Failed
                        error_tracker[node_id] = record.error_message

                        if attempt >= self._config.max_retries + 1:
                            # Exhausted retries: block task and cascade
                            self._block_task(
                                node_id, state,
                                f"Retries exhausted for {node_id}: "
                                f"{record.error_message}",
                            )
                        else:
                            # Will retry: reset to pending
                            self._graph_sync.node_states[node_id] = "pending"
                            state.node_states[node_id] = "pending"

                    # Persist state after every session
                    self._state_manager.save(state)

                    # Only dispatch one task per loop iteration in serial
                    # mode to re-evaluate ready tasks after each completion
                    break

        finally:
            self._restore_signal_handler()

        return state  # pragma: no cover

    def _load_plan(self) -> dict:
        """Load plan.json and return the raw plan dict.

        Raises:
            PlanError: if plan.json is missing or corrupted
        """
        if not self._plan_path.exists():
            raise PlanError(
                f"Plan file not found: {self._plan_path}. "
                f"Run `agent-fox plan` first to generate a plan.",
                path=str(self._plan_path),
            )

        try:
            raw = self._plan_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            raise PlanError(
                f"Corrupted plan file {self._plan_path}: {exc}. "
                f"Run `agent-fox plan` to regenerate.",
                path=str(self._plan_path),
            ) from exc

    def _compute_plan_hash(self) -> str:
        """Compute plan hash, returning empty string if file doesn't exist."""
        if self._plan_path.exists():
            return StateManager.compute_plan_hash(self._plan_path)
        return ""

    def _build_edges_dict(
        self,
        nodes: dict,
        edges_list: list[dict],
    ) -> dict[str, list[str]]:
        """Build adjacency list from plan edges.

        Returns dict mapping each node to its dependencies (predecessors).
        Edge source must complete before edge target, so target depends on
        source.
        """
        edges_dict: dict[str, list[str]] = {nid: [] for nid in nodes}
        for edge in edges_list:
            source = edge["source"]
            target = edge["target"]
            if target in edges_dict:
                edges_dict[target].append(source)
        return edges_dict

    def _load_or_init_state(
        self,
        plan_hash: str,
        nodes: dict,
    ) -> ExecutionState:
        """Load existing state or initialize fresh state.

        If state exists but plan hash differs, warn and start fresh.
        If state is corrupted, warn and start fresh.
        """
        existing = self._state_manager.load()

        if existing is not None:
            if existing.plan_hash != plan_hash:
                logger.warning(
                    "Plan has changed since last run "
                    "(plan hash mismatch). Starting fresh.",
                )
            else:
                # Resume from existing state
                # Ensure all current plan nodes are in state
                for nid in nodes:
                    if nid not in existing.node_states:
                        existing.node_states[nid] = "pending"
                return existing

        # Initialize fresh state with all nodes pending
        now = datetime.now(UTC).isoformat()
        return ExecutionState(
            plan_hash=plan_hash,
            node_states={nid: "pending" for nid in nodes},
            started_at=now,
            updated_at=now,
        )

    def _reset_in_progress_tasks(self, state: ExecutionState) -> None:
        """Reset in_progress tasks to pending on resume (04-REQ-7.E1).

        Tasks left in_progress from a prior interrupted run are treated
        as failed. They are reset to pending and will be re-dispatched
        with an error message indicating prior interruption.
        """
        for node_id, status in state.node_states.items():
            if status == "in_progress":
                state.node_states[node_id] = "pending"
                logger.info(
                    "Task %s was in_progress from prior run; "
                    "resetting to pending.",
                    node_id,
                )

    def _init_attempt_tracker(
        self,
        state: ExecutionState,
    ) -> dict[str, int]:
        """Initialize attempt counter from session history.

        Counts how many attempts each node has had so far, so we can
        continue from the correct attempt number on resume.
        """
        tracker: dict[str, int] = {}
        for record in state.session_history:
            current = tracker.get(record.node_id, 0)
            tracker[record.node_id] = max(current, record.attempt)
        return tracker

    def _init_error_tracker(
        self,
        state: ExecutionState,
    ) -> dict[str, str | None]:
        """Initialize error tracker from session history.

        For tasks that were previously in_progress (interrupted), set
        a default error message indicating interruption.
        """
        tracker: dict[str, str | None] = {}

        # Get last error for each node from history
        for record in state.session_history:
            if record.status == "failed" and record.error_message:
                tracker[record.node_id] = record.error_message

        # For nodes that were reset from in_progress, add interruption context
        for node_id, status in state.node_states.items():
            if status == "pending" and node_id not in tracker:
                # Check if this node had prior attempts
                prior_attempts = [
                    r for r in state.session_history
                    if r.node_id == node_id
                ]
                if prior_attempts:
                    last = prior_attempts[-1]
                    if last.error_message:
                        tracker[node_id] = last.error_message

        return tracker

    async def _dispatch_session(
        self,
        node_id: str,
        attempt: int,
        previous_error: str | None,
    ) -> SessionRecord:
        """Dispatch a single session via the serial runner.

        Returns a SessionRecord with the session outcome.
        """
        return await self._serial_runner.execute(
            node_id, attempt, previous_error,
        )

    def _block_task(
        self,
        node_id: str,
        state: ExecutionState,
        reason: str,
    ) -> None:
        """Mark a task as blocked and cascade-block all dependents."""
        if self._graph_sync is not None:
            cascade_blocked = self._graph_sync.mark_blocked(node_id, reason)
            state.node_states[node_id] = "blocked"
            for blocked_id in cascade_blocked:
                state.node_states[blocked_id] = "blocked"
                logger.info(
                    "Cascade-blocked %s due to %s", blocked_id, node_id,
                )

    def _install_signal_handler(self) -> None:
        """Register SIGINT handler that sets _interrupted flag.

        Double-SIGINT exits immediately (04-REQ-8.E1).
        """
        def handler(signum: int, frame: Any) -> None:
            self._interrupt_count += 1
            if self._interrupt_count >= 2:
                # Double SIGINT: exit immediately
                logger.warning("Double SIGINT received, exiting immediately.")
                raise SystemExit(1)
            self._interrupted = True
            logger.info("SIGINT received, shutting down gracefully...")

        try:
            self._prev_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, handler)
        except (OSError, ValueError):
            # Can't set signal handler in non-main thread
            self._prev_handler = None

    def _restore_signal_handler(self) -> None:
        """Restore the previous SIGINT handler."""
        if hasattr(self, "_prev_handler") and self._prev_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._prev_handler)
            except (OSError, ValueError):
                pass

    async def _shutdown(self, state: ExecutionState) -> None:
        """Save state and print resume instructions on interruption."""
        state.run_status = RunStatus.INTERRUPTED
        self._state_manager.save(state)

        summary = (
            self._graph_sync.summary() if self._graph_sync else {}
        )
        completed = summary.get("completed", 0)
        total = sum(summary.values()) if summary else 0
        remaining = total - completed

        logger.info(
            "Execution interrupted. %d/%d tasks completed, "
            "%d remaining. Resume with: agent-fox code",
            completed,
            total,
            remaining,
        )
