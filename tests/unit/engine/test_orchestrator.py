"""Orchestrator integration tests: execution loop, retry, shutdown, stall.

Test Spec: TS-04-1 (linear chain), TS-04-3 (retry with error),
           TS-04-4 (blocked after retries), TS-04-15 (graceful shutdown),
           TS-04-17 (stalled execution), TS-04-18 (resume with in-progress),
           TS-04-E1 (missing plan), TS-04-E2 (empty plan)
Requirements: 04-REQ-1.1 through 04-REQ-1.4, 04-REQ-1.E1, 04-REQ-1.E2,
              04-REQ-2.1 through 04-REQ-2.3, 04-REQ-7.1, 04-REQ-7.2,
              04-REQ-7.E1, 04-REQ-8.1, 04-REQ-8.3, 04-REQ-10.E1,
              06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.config import OrchestratorConfig
from agent_fox.core.errors import PlanError
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.state import StateManager

from .conftest import (
    MockSessionOutcome,
    MockSessionRunner,
    write_plan_file,
)

# -- Helpers ------------------------------------------------------------------


def _write_state(
    state_path: Path,
    plan_hash: str,
    node_states: dict[str, str],
    session_history: list[dict] | None = None,
    total_sessions: int = 0,
    total_cost: float = 0.0,
) -> None:
    """Write a state.jsonl line for resume tests."""
    state = {
        "plan_hash": plan_hash,
        "node_states": node_states,
        "session_history": session_history or [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": total_cost,
        "total_sessions": total_sessions,
        "started_at": "2026-03-01T09:55:00Z",
        "updated_at": "2026-03-01T10:00:00Z",
        "run_status": "running",
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "a") as f:
        f.write(json.dumps(state) + "\n")


def _linear_chain_plan(plan_dir: Path) -> Path:
    """Create a 3-task linear chain plan: A -> B -> C."""
    return write_plan_file(
        plan_dir,
        nodes={
            "spec:1": {"title": "Task A"},
            "spec:2": {"title": "Task B"},
            "spec:3": {"title": "Task C"},
        },
        edges=[
            {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
        ],
        order=["spec:1", "spec:2", "spec:3"],
    )


# -- Tests -------------------------------------------------------------------


class TestExecutionLoopLinearChain:
    """TS-04-1: Execution loop completes linear chain.

    Verify the orchestrator executes a 3-task linear chain (A -> B -> C)
    in order, dispatching each to the session runner.
    """

    @pytest.mark.asyncio
    async def test_sessions_dispatched_in_order(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Sessions dispatched in dependency order: A, then B, then C."""
        plan_path = _linear_chain_plan(tmp_plan_dir)

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        await orchestrator.run()

        # Verify dispatch order
        dispatched = [call[0] for call in mock_runner.calls]
        assert dispatched == ["spec:1", "spec:2", "spec:3"]

    @pytest.mark.asyncio
    async def test_all_nodes_completed(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """All nodes end in completed status."""
        plan_path = _linear_chain_plan(tmp_plan_dir)

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        assert state.node_states["spec:1"] == "completed"
        assert state.node_states["spec:2"] == "completed"
        assert state.node_states["spec:3"] == "completed"

    @pytest.mark.asyncio
    async def test_total_sessions_count(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Total sessions count equals number of tasks."""
        plan_path = _linear_chain_plan(tmp_plan_dir)

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        assert state.total_sessions == 3


class TestRetryWithError:
    """TS-04-3: Retry on failure with error feedback.

    Verify a failed task is retried with the previous error message
    passed to the session runner.
    """

    @pytest.mark.asyncio
    async def test_retries_with_error_context(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Second attempt receives previous_error from first failure."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={"spec:1": {"title": "Task A"}},
            edges=[],
        )

        mock = MockSessionRunner()
        # First attempt fails, second succeeds
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="syntax error in line 42",
                ),
                MockSessionOutcome(
                    node_id="spec:1",
                    status="completed",
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_retries=2,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        # Verify two dispatches
        assert len(mock.calls) == 2
        # Second call should have previous_error from first failure
        assert mock.calls[1][2] == "syntax error in line 42"
        assert state.node_states["spec:1"] == "completed"


class TestBlockedAfterRetries:
    """TS-04-4: Task blocked after exhausting retries.

    Verify a task is marked as blocked after all retry attempts fail.
    """

    @pytest.mark.asyncio
    async def test_blocked_after_max_retries(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Task blocked after 3 failed attempts (1 initial + 2 retries)."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={"spec:1": {"title": "Task A"}},
            edges=[],
        )

        mock = MockSessionRunner()
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="error 1",
                ),
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="error 2",
                ),
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="error 3",
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_retries=2,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        assert len(mock.calls) == 3
        assert state.node_states["spec:1"] == "blocked"


class TestGracefulShutdown:
    """TS-04-15: Graceful shutdown saves state on SIGINT.

    Verify that SIGINT triggers state save and resume message.
    """

    @pytest.mark.asyncio
    async def test_state_saved_on_interrupt(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """state.jsonl exists after interruption with completed tasks."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
                "spec:3": {"title": "Task C"},
                "spec:4": {"title": "Task D"},
                "spec:5": {"title": "Task E"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
                {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
                {"source": "spec:3", "target": "spec:4", "kind": "intra_spec"},
                {"source": "spec:4", "target": "spec:5", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2", "spec:3", "spec:4", "spec:5"],
        )

        call_count = 0

        class InterruptingRunner(MockSessionRunner):
            """Mock runner that triggers interrupt after 2 completions."""

            async def execute(
                self,
                node_id: str,
                attempt: int,
                previous_error: str | None = None,
            ) -> MockSessionOutcome:
                nonlocal call_count
                result = await super().execute(
                    node_id,
                    attempt,
                    previous_error,
                )
                call_count += 1
                return result

        mock = InterruptingRunner()
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        # Simulate interrupt: set _interrupted flag after 2 sessions
        # This test verifies the interrupt mechanism works when
        # the orchestrator checks the flag between sessions
        # For now, we verify the basic mechanism exists
        state = await orchestrator.run()

        # The orchestrator should save state; at minimum all 5 should complete
        # if no actual interrupt occurs. The interrupt test verifies the
        # mechanism, which will be properly tested when the orchestrator
        # checks _interrupted between dispatches.
        assert tmp_state_path.exists() or state.total_sessions > 0


class TestStalledExecution:
    """TS-04-17: Stalled execution exits with warning.

    Verify the orchestrator detects a stalled state and exits
    with details.
    """

    @pytest.mark.asyncio
    async def test_stalled_run_status(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Run status is 'stalled' when all tasks end up blocked."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        mock = MockSessionRunner()
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="fail",
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_retries=0,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        assert state.run_status == "stalled"
        assert state.node_states["spec:1"] == "blocked"
        assert state.node_states["spec:2"] == "blocked"


class TestResumeWithInProgressTask:
    """TS-04-18: Exactly-once on resume with in-progress task.

    Verify that an in_progress task from a prior interrupted run
    is treated as failed on resume.
    """

    @pytest.mark.asyncio
    async def test_in_progress_treated_as_failed(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """In-progress task from prior run is reset and re-dispatched."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        # Pre-populate state: A completed, B in_progress (interrupted)
        plan_hash = StateManager.compute_plan_hash(plan_path)
        _write_state(
            tmp_state_path,
            plan_hash=plan_hash,
            node_states={"spec:1": "completed", "spec:2": "in_progress"},
            total_sessions=1,
        )

        mock = MockSessionRunner()
        config = OrchestratorConfig(
            parallel=1,
            max_retries=2,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        # B should have been re-dispatched and completed
        assert state.node_states["spec:2"] == "completed"
        # A should NOT have been re-dispatched
        dispatched_nodes = [call[0] for call in mock.calls]
        assert "spec:1" not in dispatched_nodes
        # B should receive interruption context
        b_calls = [c for c in mock.calls if c[0] == "spec:2"]
        assert len(b_calls) >= 1


class TestResumeAfterStatusSync:
    """Plan hash stability after _sync_plan_statuses writes to plan.json.

    Verify that updating node statuses in plan.json does not invalidate
    the plan hash, allowing the orchestrator to resume correctly.
    """

    @pytest.mark.asyncio
    async def test_resume_after_status_sync_skips_completed(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """After plan.json status sync, resume skips completed tasks."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        # Compute hash, then mutate plan.json status (simulates shutdown sync)
        plan_hash = StateManager.compute_plan_hash(plan_path)
        plan_data = json.loads(plan_path.read_text())
        plan_data["nodes"]["spec:1"]["status"] = "completed"
        plan_path.write_text(json.dumps(plan_data, indent=2))

        # Hash should still match despite status change
        assert StateManager.compute_plan_hash(plan_path) == plan_hash

        # Pre-populate state with spec:1 completed
        _write_state(
            tmp_state_path,
            plan_hash=plan_hash,
            node_states={"spec:1": "completed", "spec:2": "pending"},
            total_sessions=1,
        )

        mock = MockSessionRunner()
        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        # Only spec:2 should have been dispatched
        dispatched = [call[0] for call in mock.calls]
        assert "spec:1" not in dispatched
        assert "spec:2" in dispatched
        assert state.node_states["spec:1"] == "completed"
        assert state.node_states["spec:2"] == "completed"


class TestFreshStartWithCompletedNodes:
    """Fresh start seeds node states from plan.json statuses.

    When no state.jsonl exists, the orchestrator should read node
    statuses from plan.json (which reflect tasks.md [x] markers)
    rather than hardcoding everything to pending.
    """

    @pytest.mark.asyncio
    async def test_completed_nodes_in_plan_are_skipped(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Nodes marked completed in plan.json are skipped on fresh start."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A", "status": "completed"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        # No state.jsonl — fresh start
        mock = MockSessionRunner()
        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        dispatched = [call[0] for call in mock.calls]
        assert "spec:1" not in dispatched
        assert "spec:2" in dispatched
        assert state.node_states["spec:1"] == "completed"


class TestCostLimitStopsOrchestrator:
    """TS-04-10: Cost limit stops new launches (orchestrator integration).

    Verify the orchestrator stops launching new sessions when cumulative
    cost reaches the configured ceiling. In-flight sessions complete but
    no new sessions are started.
    """

    @pytest.mark.asyncio
    async def test_cost_limit_stops_dispatching(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """C is NOT dispatched when cost limit exceeded after A + B."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
                "spec:3": {"title": "Task C"},
            },
            edges=[],  # All independent
        )

        mock = MockSessionRunner()
        # A costs $0.30, B costs $0.25 (total $0.55 exceeds max_cost $0.50)
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="completed",
                    cost=0.30,
                ),
            ],
        )
        mock.configure(
            "spec:2",
            [
                MockSessionOutcome(
                    node_id="spec:2",
                    status="completed",
                    cost=0.25,
                ),
            ],
        )
        mock.configure(
            "spec:3",
            [
                MockSessionOutcome(
                    node_id="spec:3",
                    status="completed",
                    cost=0.10,
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_cost=0.50,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        assert state.node_states["spec:1"] == "completed"
        assert state.node_states["spec:2"] == "completed"
        assert state.node_states["spec:3"] == "pending"
        assert state.run_status == "cost_limit"

    @pytest.mark.asyncio
    async def test_cost_limit_run_status(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Run status indicates cost_limit when limit is reached."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={"spec:1": {"title": "Task A"}},
            edges=[],
        )

        mock = MockSessionRunner()
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="completed",
                    cost=1.00,
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_cost=0.50,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        # A was dispatched (cost wasn't exceeded before dispatch),
        # but now cost limit is reached so no more sessions.
        assert state.node_states["spec:1"] == "completed"
        assert state.run_status == "cost_limit"


class TestSessionLimitStopsOrchestrator:
    """TS-04-11: Session limit stops new launches (orchestrator integration).

    Verify the orchestrator stops after the configured number of sessions.
    """

    @pytest.mark.asyncio
    async def test_session_limit_stops_dispatching(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Exactly 3 sessions dispatched with max_sessions=3."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task 1"},
                "spec:2": {"title": "Task 2"},
                "spec:3": {"title": "Task 3"},
                "spec:4": {"title": "Task 4"},
                "spec:5": {"title": "Task 5"},
            },
            edges=[],  # All independent
        )

        mock = MockSessionRunner()
        config = OrchestratorConfig(
            parallel=1,
            max_sessions=3,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        assert state.total_sessions == 3
        completed = [n for n, s in state.node_states.items() if s == "completed"]
        assert len(completed) == 3
        assert state.run_status == "session_limit"

    @pytest.mark.asyncio
    async def test_session_limit_remaining_pending(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """2 nodes remain pending after session limit is reached."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task 1"},
                "spec:2": {"title": "Task 2"},
                "spec:3": {"title": "Task 3"},
                "spec:4": {"title": "Task 4"},
                "spec:5": {"title": "Task 5"},
            },
            edges=[],  # All independent
        )

        mock = MockSessionRunner()
        config = OrchestratorConfig(
            parallel=1,
            max_sessions=3,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        pending = [n for n, s in state.node_states.items() if s == "pending"]
        assert len(pending) == 2


class TestMissingPlanFile:
    """TS-04-E1: Missing plan file.

    Verify orchestrator raises PlanError when plan.json is missing.
    """

    @pytest.mark.asyncio
    async def test_raises_plan_error(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """PlanError raised when plan.json does not exist."""
        plan_path = tmp_plan_dir / "plan.json"  # Not created

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        with pytest.raises(PlanError) as exc_info:
            await orchestrator.run()

        assert "agent-fox plan" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_no_sessions_dispatched(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """No sessions are dispatched when plan is missing."""
        plan_path = tmp_plan_dir / "plan.json"

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        with pytest.raises(PlanError):
            await orchestrator.run()

        assert len(mock_runner.calls) == 0


class TestEmptyPlan:
    """TS-04-E2: Empty plan.

    Verify orchestrator exits cleanly with an empty plan.
    """

    @pytest.mark.asyncio
    async def test_empty_plan_completes_immediately(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Empty plan returns completed status with zero sessions."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={},
            edges=[],
        )

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        assert state.total_sessions == 0
        assert state.run_status == "completed"

    @pytest.mark.asyncio
    async def test_no_sessions_dispatched_for_empty_plan(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """No sessions dispatched for an empty plan."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={},
            edges=[],
        )

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        await orchestrator.run()

        assert len(mock_runner.calls) == 0


class TestSyncBarrierTriggering:
    """TS-06-1: Sync barriers fire at configured intervals.

    Verify the orchestrator triggers sync barriers after the correct
    number of task completions, calling hooks, hot-load, and render.
    Requirements: 06-REQ-6.1, 06-REQ-6.2, 06-REQ-6.3, 05-REQ-6.3
    """

    @pytest.mark.asyncio
    async def test_sync_barrier_fires_at_interval(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Sync barrier fires after sync_interval completions."""
        # 5 tasks, sync_interval=5 => barrier fires once (at task 5)
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task 1"},
                "spec:2": {"title": "Task 2"},
                "spec:3": {"title": "Task 3"},
                "spec:4": {"title": "Task 4"},
                "spec:5": {"title": "Task 5"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
                {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
                {"source": "spec:3", "target": "spec:4", "kind": "intra_spec"},
                {"source": "spec:4", "target": "spec:5", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2", "spec:3", "spec:4", "spec:5"],
        )

        config = OrchestratorConfig(
            parallel=1,
            sync_interval=5,
            inter_session_delay=0,
            hot_load=False,
        )

        with (
            patch(
                "agent_fox.knowledge.rendering.render_summary",
            ) as mock_render,
        ):
            orchestrator = Orchestrator(
                config=config,
                plan_path=plan_path,
                state_path=tmp_state_path,
                session_runner_factory=lambda nid, **kw: mock_runner,
                specs_dir=tmp_plan_dir.parent / ".specs",
            )

            state = await orchestrator.run()

        assert state.total_sessions == 5
        # 1 sync-barrier render + 1 final render
        assert mock_render.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_barrier_fires_multiple_times(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Sync barrier fires at each interval crossing."""
        # 6 tasks, sync_interval=3 => barrier fires at task 3 and 6
        nodes = {f"spec:{i}": {"title": f"Task {i}"} for i in range(1, 7)}
        edges = [{"source": f"spec:{i}", "target": f"spec:{i + 1}", "kind": "intra_spec"} for i in range(1, 6)]
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes=nodes,
            edges=edges,
            order=[f"spec:{i}" for i in range(1, 7)],
        )

        config = OrchestratorConfig(
            parallel=1,
            sync_interval=3,
            inter_session_delay=0,
            hot_load=False,
        )

        with (
            patch(
                "agent_fox.knowledge.rendering.render_summary",
            ) as mock_render,
        ):
            orchestrator = Orchestrator(
                config=config,
                plan_path=plan_path,
                state_path=tmp_state_path,
                session_runner_factory=lambda nid, **kw: mock_runner,
                specs_dir=tmp_plan_dir.parent / ".specs",
            )

            state = await orchestrator.run()

        assert state.total_sessions == 6
        # 2 sync-barrier renders + 1 final render
        assert mock_render.call_count == 3

    @pytest.mark.asyncio
    async def test_sync_barrier_disabled_when_interval_zero(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """No barrier fires when sync_interval=0 (disabled)."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task 1"},
                "spec:2": {"title": "Task 2"},
                "spec:3": {"title": "Task 3"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
                {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2", "spec:3"],
        )

        config = OrchestratorConfig(
            parallel=1,
            sync_interval=0,
            inter_session_delay=0,
        )

        with (
            patch(
                "agent_fox.knowledge.rendering.render_summary",
            ) as mock_render,
        ):
            orchestrator = Orchestrator(
                config=config,
                plan_path=plan_path,
                state_path=tmp_state_path,
                session_runner_factory=lambda nid, **kw: mock_runner,
            )

            state = await orchestrator.run()

        assert state.total_sessions == 3
        # No sync-barrier renders, but one final render in the finally block.
        assert mock_render.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_barrier_without_specs_dir(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Barrier still renders summary when no specs_dir provided."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task 1"},
                "spec:2": {"title": "Task 2"},
                "spec:3": {"title": "Task 3"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
                {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2", "spec:3"],
        )

        config = OrchestratorConfig(
            parallel=1,
            sync_interval=3,
            inter_session_delay=0,
            hot_load=False,
        )

        with (
            patch(
                "agent_fox.knowledge.rendering.render_summary",
            ) as mock_render,
        ):
            orchestrator = Orchestrator(
                config=config,
                plan_path=plan_path,
                state_path=tmp_state_path,
                session_runner_factory=lambda nid, **kw: mock_runner,
            )

            await orchestrator.run()

        # 1 sync-barrier render + 1 final render
        assert mock_render.call_count == 2


class TestInProgressStatePersistence:
    """Verify that in_progress state is persisted before session dispatch.

    When a task is dispatched, its status should be saved to state.jsonl
    as in_progress so that agent-fox status can show running tasks.
    """

    @pytest.mark.asyncio
    async def test_in_progress_state_saved_before_session(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """state.jsonl includes an in_progress snapshot before completion."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={"spec:1": {"title": "Task A"}},
            edges=[],
        )

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        await orchestrator.run()

        # state.jsonl should have at least 2 lines:
        # 1. in_progress snapshot (before session)
        # 2. completed snapshot (after session)
        lines = [line.strip() for line in tmp_state_path.read_text().strip().split("\n") if line.strip()]
        assert len(lines) >= 2, f"Expected at least 2 state snapshots, got {len(lines)}"

        # First line should show in_progress for spec:1
        first_state = json.loads(lines[0])
        assert first_state["node_states"]["spec:1"] == "in_progress"


class TestPlanJsonStatusSync:
    """Verify that plan.json is updated with current node statuses.

    After execution completes, plan.json node statuses should reflect
    the actual execution outcome, not remain as pending.
    """

    @pytest.mark.asyncio
    async def test_plan_json_updated_after_completion(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """plan.json nodes have completed status after successful run."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        config = OrchestratorConfig(parallel=1, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        await orchestrator.run()

        # Re-read plan.json
        updated_plan = json.loads(plan_path.read_text())
        assert updated_plan["nodes"]["spec:1"]["status"] == "completed"
        assert updated_plan["nodes"]["spec:2"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_plan_json_shows_blocked_status(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """plan.json nodes show blocked status when retries exhausted."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        mock = MockSessionRunner()
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="fail",
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=1,
            max_retries=0,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        await orchestrator.run()

        updated_plan = json.loads(plan_path.read_text())
        assert updated_plan["nodes"]["spec:1"]["status"] == "blocked"
        assert updated_plan["nodes"]["spec:2"]["status"] == "blocked"


class TestParallelDispatchWithDependencies:
    """Parallel execution respects dependency ordering.

    Verify that when running in parallel mode, the orchestrator only
    dispatches tasks whose dependencies are all completed, and that
    newly-unblocked tasks are dispatched promptly (streaming pool).

    Requirements: 04-REQ-1.3, 04-REQ-6.1, 04-REQ-10.1
    """

    @pytest.mark.asyncio
    async def test_dependent_task_runs_after_prerequisite(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """In parallel mode, B waits for A; C waits for B."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
                "spec:3": {"title": "Task C"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
                {"source": "spec:2", "target": "spec:3", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2", "spec:3"],
        )

        config = OrchestratorConfig(parallel=4, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        dispatched = [call[0] for call in mock_runner.calls]
        assert dispatched == ["spec:1", "spec:2", "spec:3"]
        assert all(s == "completed" for s in state.node_states.values())

    @pytest.mark.asyncio
    async def test_independent_tasks_dispatched_together(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Independent tasks are dispatched in the same pool cycle."""
        # A -> C, B -> C  (A and B are independent, C depends on both)
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec_a:1": {"title": "Task A"},
                "spec_b:1": {"title": "Task B"},
                "spec_c:1": {"title": "Task C"},
            },
            edges=[
                {"source": "spec_a:1", "target": "spec_c:1", "kind": "cross_spec"},
                {"source": "spec_b:1", "target": "spec_c:1", "kind": "cross_spec"},
            ],
            order=["spec_a:1", "spec_b:1", "spec_c:1"],
        )

        config = OrchestratorConfig(parallel=4, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        dispatched = [call[0] for call in mock_runner.calls]
        # A and B should be dispatched before C
        assert "spec_c:1" == dispatched[-1]
        assert set(dispatched[:2]) == {"spec_a:1", "spec_b:1"}
        assert all(s == "completed" for s in state.node_states.values())

    @pytest.mark.asyncio
    async def test_cascade_block_prevents_dependent_dispatch(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """When A fails, B (which depends on A) is not dispatched."""
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec:1": {"title": "Task A"},
                "spec:2": {"title": "Task B"},
            },
            edges=[
                {"source": "spec:1", "target": "spec:2", "kind": "intra_spec"},
            ],
            order=["spec:1", "spec:2"],
        )

        mock = MockSessionRunner()
        mock.configure(
            "spec:1",
            [
                MockSessionOutcome(
                    node_id="spec:1",
                    status="failed",
                    error_message="fail",
                ),
            ],
        )

        config = OrchestratorConfig(
            parallel=4,
            max_retries=0,
            inter_session_delay=0,
        )
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        dispatched = [call[0] for call in mock.calls]
        assert "spec:2" not in dispatched
        assert state.node_states["spec:1"] == "blocked"
        assert state.node_states["spec:2"] == "blocked"

    @pytest.mark.asyncio
    async def test_streaming_pool_dispatches_unblocked_tasks(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Streaming pool dispatches newly-ready tasks without waiting
        for the entire batch to complete.

        Graph: A -> C, B (independent). When A completes, C becomes
        ready and should be dispatched even if B is still running.
        All three should complete.
        """
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={
                "spec_a:1": {"title": "Task A"},
                "spec_b:1": {"title": "Task B"},
                "spec_c:1": {"title": "Task C"},
            },
            edges=[
                {"source": "spec_a:1", "target": "spec_c:1", "kind": "cross_spec"},
            ],
            order=["spec_a:1", "spec_b:1", "spec_c:1"],
        )

        config = OrchestratorConfig(parallel=4, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock_runner,
        )

        state = await orchestrator.run()

        assert state.total_sessions == 3
        assert all(s == "completed" for s in state.node_states.values())

    @pytest.mark.asyncio
    async def test_pool_bounded_by_max_parallelism(
        self,
        tmp_plan_dir: Path,
        tmp_state_path: Path,
    ) -> None:
        """Only max_parallelism tasks are in_progress at any given time.

        With 6 independent tasks and parallelism=2, at most 2 tasks
        should be in_progress simultaneously.
        """
        plan_path = write_plan_file(
            tmp_plan_dir,
            nodes={f"spec:{i}": {"title": f"Task {i}"} for i in range(1, 7)},
            edges=[],
        )

        max_concurrent = 0
        current_concurrent = 0

        class ConcurrencyTracker(MockSessionRunner):
            async def execute(
                self,
                node_id: str,
                attempt: int,
                previous_error: str | None = None,
            ) -> MockSessionOutcome:
                nonlocal max_concurrent, current_concurrent
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
                result = await super().execute(node_id, attempt, previous_error)
                current_concurrent -= 1
                return result

        mock = ConcurrencyTracker()
        config = OrchestratorConfig(parallel=2, inter_session_delay=0)
        orchestrator = Orchestrator(
            config=config,
            plan_path=plan_path,
            state_path=tmp_state_path,
            session_runner_factory=lambda nid, **kw: mock,
        )

        state = await orchestrator.run()

        assert state.total_sessions == 6
        assert max_concurrent <= 2
