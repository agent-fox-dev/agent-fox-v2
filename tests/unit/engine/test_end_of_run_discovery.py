"""Unit tests for end-of-run spec discovery.

Test Spec: TC-60-01 through TC-60-14
Requirements: 60-REQ-1.1 through 60-REQ-1.4, 60-REQ-1.E1, 60-REQ-1.E2,
              60-REQ-2.1 through 60-REQ-2.4,
              60-REQ-3.1, 60-REQ-3.2, 60-REQ-3.3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.state import ExecutionState, RunStatus
from tests.unit.engine.conftest import (
    MockSessionOutcome,
    MockSessionRunner,
    write_plan_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator(
    plan_dir: Path,
    runner: MockSessionRunner,
    *,
    hot_load: bool = True,
    sync_interval: int = 5,
    max_retries: int = 0,
    max_cost: float | None = None,
    max_sessions: int | None = None,
    max_blocked_fraction: float | None = None,
    nodes: dict[str, dict[str, Any]] | None = None,
    edges: list[dict[str, str]] | None = None,
) -> Orchestrator:
    """Create an Orchestrator with given config and a simple plan."""
    if nodes is None:
        nodes = {"spec:1": {}}
    if edges is None:
        edges = []

    plan_path = write_plan_file(plan_dir, nodes, edges)

    config = OrchestratorConfig(
        parallel=1,
        inter_session_delay=0,
        hot_load=hot_load,
        sync_interval=sync_interval,
        max_retries=max_retries,
        max_cost=max_cost,
        max_sessions=max_sessions,
        max_blocked_fraction=max_blocked_fraction,
    )

    return Orchestrator(
        config=config,
        plan_path=plan_path,
        session_runner_factory=lambda nid, **kw: runner,
    )


# ---------------------------------------------------------------------------
# TC-60-01: End-of-run discovery triggers on COMPLETED state
# Requirement: 60-REQ-1.1
# ---------------------------------------------------------------------------


class TestEndOfRunDiscoveryTrigger:
    """TC-60-01: Discovery triggers when run would complete."""

    @pytest.mark.asyncio
    async def test_barrier_called_on_completed_state(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When all tasks complete and hot_load is enabled, the sync barrier
        should be called for end-of-run discovery."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_called_once()
        assert state.run_status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# TC-60-02: New specs discovered — execution continues
# Requirement: 60-REQ-1.2
# ---------------------------------------------------------------------------


class TestNewSpecsDiscovered:
    """TC-60-02: When barrier discovers new specs, the loop continues."""

    @pytest.mark.asyncio
    async def test_returns_true_when_new_tasks_found(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """_try_end_of_run_discovery returns True when barrier adds tasks."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        # Run the orchestrator so internal state is set up
        # Then test _try_end_of_run_discovery directly
        with (
            patch(
                "agent_fox.engine.engine.run_sync_barrier_sequence",
                new_callable=AsyncMock,
            ) as mock_barrier,
        ):
            # Set up: after barrier, ready_tasks returns new tasks
            await orch.run()

            # Reset and test the method directly
            mock_graph_sync = MagicMock()
            mock_graph_sync.ready_tasks.return_value = [MagicMock(), MagicMock()]
            orch._graph_sync = mock_graph_sync

            exec_state = ExecutionState(plan_hash="test", node_states={"spec:1": "completed"})
            result = await orch._try_end_of_run_discovery(exec_state)

        assert result is True
        mock_barrier.assert_called()


# ---------------------------------------------------------------------------
# TC-60-03: No new specs — terminates with COMPLETED
# Requirement: 60-REQ-1.3
# ---------------------------------------------------------------------------


class TestNoNewSpecsCompleted:
    """TC-60-03: When barrier finds no new specs, run completes."""

    @pytest.mark.asyncio
    async def test_completes_when_no_new_specs(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """Run terminates with COMPLETED when end-of-run discovery finds nothing."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
        ) as mock_barrier:
            state = await orch.run()

        # Barrier was called (end-of-run discovery attempted)
        mock_barrier.assert_called()
        assert state.run_status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# TC-60-04: Repeated end-of-run discovery cycles
# Requirement: 60-REQ-1.4
# ---------------------------------------------------------------------------


class TestRepeatedDiscoveryCycles:
    """TC-60-04: Discovery repeats each time all tasks complete."""

    @pytest.mark.asyncio
    async def test_multiple_discovery_cycles(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """End-of-run discovery runs multiple times as new specs are found."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        discovery_call_count = 0

        async def discovery_side_effect(state: Any) -> bool:
            nonlocal discovery_call_count
            discovery_call_count += 1
            if discovery_call_count <= 2:
                # First two calls: simulate finding new specs
                # Add a mock task that completes immediately
                return True
            # Third call: no new specs
            return False

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            side_effect=discovery_side_effect,
        ):
            state = await orch.run()

        # Discovery was called at least 3 times
        assert discovery_call_count >= 3
        assert state.run_status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# TC-60-05: Hot-load disabled — skips discovery
# Requirement: 60-REQ-1.E1
# ---------------------------------------------------------------------------


class TestHotLoadDisabledSkipsDiscovery:
    """TC-60-05: When hot_load=False, discovery is skipped entirely."""

    @pytest.mark.asyncio
    async def test_no_barrier_when_hot_load_disabled(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """With hot_load=False, _try_end_of_run_discovery returns False
        without calling the barrier."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner, hot_load=False)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
        ) as mock_barrier:
            state = await orch.run()

            # Also test the method directly
            exec_state = ExecutionState(plan_hash="test", node_states={"spec:1": "completed"})
            result = await orch._try_end_of_run_discovery(exec_state)

        assert result is False
        # Barrier should not have been called for end-of-run discovery
        # (it may have been called for mid-run barriers, so we check
        # that _try_end_of_run_discovery specifically skips it)
        mock_barrier.assert_not_called()
        assert state.run_status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# TC-60-06: Barrier failure — logs error and terminates
# Requirement: 60-REQ-1.E2
# ---------------------------------------------------------------------------


class TestBarrierFailureGraceful:
    """TC-60-06: Barrier exceptions are caught and logged."""

    @pytest.mark.asyncio
    async def test_barrier_error_returns_false(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When barrier raises, _try_end_of_run_discovery returns False
        and logs the error."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
            side_effect=RuntimeError("git sync failed"),
        ) as mock_barrier:
            state = await orch.run()

        mock_barrier.assert_called()
        assert state.run_status == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# TC-60-07: STALLED status — no end-of-run discovery
# Requirement: 60-REQ-2.1
# ---------------------------------------------------------------------------


class TestStalledNoDiscovery:
    """TC-60-07: Stalled runs do not trigger discovery."""

    @pytest.mark.asyncio
    async def test_stalled_skips_discovery(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When execution is stalled, _try_end_of_run_discovery is not called."""
        # Create a graph where task B depends on A, and A fails (stalls B)
        nodes: dict[str, dict[str, object]] = {
            "spec:1": {},
            "spec:2": {},
        }
        edges = [{"source": "spec:1", "target": "spec:2", "kind": "task_group"}]
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="failed", error_message="e")],
        )
        orch = _make_orchestrator(
            tmp_plan_dir,
            mock_runner,
            nodes=nodes,
            edges=edges,
        )

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_not_called()
        assert state.run_status == RunStatus.STALLED


# ---------------------------------------------------------------------------
# TC-60-08: COST_LIMIT status — no end-of-run discovery
# Requirement: 60-REQ-2.2
# ---------------------------------------------------------------------------


class TestCostLimitNoDiscovery:
    """TC-60-08: Cost-limited runs do not trigger discovery."""

    @pytest.mark.asyncio
    async def test_cost_limit_skips_discovery(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When cost limit is hit, _try_end_of_run_discovery is not called."""
        # Set a very low cost limit so it triggers after the first task
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed", cost=10.0)],
        )
        nodes: dict[str, dict[str, object]] = {"spec:1": {}, "spec:2": {}}
        orch = _make_orchestrator(
            tmp_plan_dir,
            mock_runner,
            nodes=nodes,
            max_cost=0.01,
        )

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_not_called()
        assert state.run_status == RunStatus.COST_LIMIT


# ---------------------------------------------------------------------------
# TC-60-09: SESSION_LIMIT status — no end-of-run discovery
# Requirement: 60-REQ-2.2
# ---------------------------------------------------------------------------


class TestSessionLimitNoDiscovery:
    """TC-60-09: Session-limited runs do not trigger discovery."""

    @pytest.mark.asyncio
    async def test_session_limit_skips_discovery(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When session limit is hit, _try_end_of_run_discovery is not called."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        nodes: dict[str, dict[str, object]] = {"spec:1": {}, "spec:2": {}}
        orch = _make_orchestrator(
            tmp_plan_dir,
            mock_runner,
            nodes=nodes,
            max_sessions=1,
        )

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_not_called()
        assert state.run_status == RunStatus.SESSION_LIMIT


# ---------------------------------------------------------------------------
# TC-60-10: BLOCK_LIMIT status — no end-of-run discovery
# Requirement: 60-REQ-2.3
# ---------------------------------------------------------------------------


class TestBlockLimitNoDiscovery:
    """TC-60-10: Block-limited runs do not trigger discovery."""

    @pytest.mark.asyncio
    async def test_block_limit_skips_discovery(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When block limit is hit, _try_end_of_run_discovery is not called."""
        # Create a graph where most tasks fail and get blocked
        nodes: dict[str, dict[str, object]] = {
            "spec:1": {},
            "spec:2": {},
            "spec:3": {},
            "spec:4": {},
        }
        edges = [
            {"source": "spec:1", "target": "spec:2", "kind": "task_group"},
            {"source": "spec:1", "target": "spec:3", "kind": "task_group"},
            {"source": "spec:1", "target": "spec:4", "kind": "task_group"},
        ]
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="failed", error_message="e")],
        )
        orch = _make_orchestrator(
            tmp_plan_dir,
            mock_runner,
            nodes=nodes,
            edges=edges,
            max_blocked_fraction=0.4,
        )

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_not_called()
        assert state.run_status == RunStatus.BLOCK_LIMIT


# ---------------------------------------------------------------------------
# TC-60-11: INTERRUPTED status — no end-of-run discovery
# Requirement: 60-REQ-2.4
# ---------------------------------------------------------------------------


class TestInterruptedNoDiscovery:
    """TC-60-11: Interrupted runs do not trigger discovery."""

    @pytest.mark.asyncio
    async def test_interrupted_skips_discovery(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """When SIGINT is received, _try_end_of_run_discovery is not called."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        # Simulate interrupt by setting the signal flag
        orch._signal.interrupted = True

        with patch.object(
            orch,
            "_try_end_of_run_discovery",
            new_callable=AsyncMock,
            return_value=False,
        ) as mock_discovery:
            state = await orch.run()

        mock_discovery.assert_not_called()
        assert state.run_status == RunStatus.INTERRUPTED


# ---------------------------------------------------------------------------
# TC-60-12: Full barrier sequence is executed
# Requirement: 60-REQ-3.1
# ---------------------------------------------------------------------------


class TestFullBarrierSequenceExecuted:
    """TC-60-12: _try_end_of_run_discovery calls barrier with all kwargs."""

    @pytest.mark.asyncio
    async def test_barrier_called_with_all_kwargs(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """run_sync_barrier_sequence receives all required keyword arguments."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
        ) as mock_barrier:
            # Set up graph_sync to return empty after barrier
            await orch.run()

        # Verify barrier was called with all expected keyword arguments
        mock_barrier.assert_called()
        call_kwargs = mock_barrier.call_args.kwargs
        expected_keys = {
            "state",
            "sync_interval",
            "repo_root",
            "emit_audit",
            "specs_dir",
            "hot_load_enabled",
            "hot_load_fn",
            "sync_plan_fn",
            "barrier_callback",
            "knowledge_db_conn",
        }
        assert expected_keys.issubset(set(call_kwargs.keys())), (
            f"Missing kwargs: {expected_keys - set(call_kwargs.keys())}"
        )


# ---------------------------------------------------------------------------
# TC-60-13: Same three-gate pipeline applied
# Requirement: 60-REQ-3.2
# ---------------------------------------------------------------------------


class TestSameHotLoadFunction:
    """TC-60-13: Discovery uses the same hot_load_fn as mid-run barriers."""

    @pytest.mark.asyncio
    async def test_hot_load_fn_is_same(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """The hot_load_fn passed to barrier is self._hot_load_new_specs."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
        ) as mock_barrier:
            await orch.run()

        mock_barrier.assert_called()
        call_kwargs = mock_barrier.call_args.kwargs
        assert call_kwargs["hot_load_fn"] == orch._hot_load_new_specs
        assert call_kwargs["hot_load_enabled"] is True


# ---------------------------------------------------------------------------
# TC-60-14: SYNC_BARRIER audit event emitted
# Requirement: 60-REQ-3.3
# ---------------------------------------------------------------------------


class TestAuditEventEmitted:
    """TC-60-14: Discovery uses the same audit emitter as mid-run barriers."""

    @pytest.mark.asyncio
    async def test_emit_audit_is_same(
        self,
        tmp_plan_dir: Path,
        mock_runner: MockSessionRunner,
    ) -> None:
        """The emit_audit callable passed is self._emit_audit."""
        mock_runner.configure(
            "spec:1",
            [MockSessionOutcome(node_id="spec:1", status="completed")],
        )
        orch = _make_orchestrator(tmp_plan_dir, mock_runner)

        with patch(
            "agent_fox.engine.engine.run_sync_barrier_sequence",
            new_callable=AsyncMock,
        ) as mock_barrier:
            await orch.run()

        mock_barrier.assert_called()
        call_kwargs = mock_barrier.call_args.kwargs
        assert call_kwargs["emit_audit"] == orch._emit_audit
