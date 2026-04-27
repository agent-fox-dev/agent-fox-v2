"""Tests for SIGINT/shutdown session-outcome persistence.

Verifies that interrupted parallel sessions always produce session_outcomes
rows so the database is consistent after a SIGINT-interrupted run.

Issue: #536 — SIGINT/transport handling
Requirements: 536-AC-1, 536-AC-2, 536-AC-3, 536-AC-4
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_fox.engine.engine import Orchestrator
from agent_fox.engine.parallel import ParallelRunner
from agent_fox.engine.state import ExecutionState, RunStatus, SessionRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slow_factory(delay: float = 10.0):
    """Return a session runner factory whose sessions take *delay* seconds."""

    class _SlowRunner:
        async def execute(
            self,
            node_id: str,
            attempt: int,
            previous_error: str | None = None,
        ) -> SessionRecord:
            await asyncio.sleep(delay)
            return SessionRecord(
                node_id=node_id,
                attempt=attempt,
                status="completed",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                duration_ms=0,
                error_message=None,
                timestamp="2026-01-01T00:00:00Z",
            )

    return lambda nid, **kw: _SlowRunner()


def _make_minimal_state() -> ExecutionState:
    """Return a minimal ExecutionState that can be mutated by _shutdown()."""
    return ExecutionState(
        node_states={},
        run_status=RunStatus.RUNNING,
        total_sessions=0,
        total_cost=0.0,
        session_history=[],
        blocked_reasons={},
        plan_hash="",
    )


# ---------------------------------------------------------------------------
# 536-AC-3: _shutdown() calls result_handler.process() for cancelled tasks
# ---------------------------------------------------------------------------


class TestShutdownPersistsInterruptedRecords:
    """536-AC-3: _shutdown() persists failure records for all cancelled tasks.

    Mocks result_handler.process() and verifies it is called once per
    in-flight task that was cancelled by _shutdown().
    """

    @pytest.mark.asyncio
    async def test_shutdown_calls_process_for_each_cancelled_task(self) -> None:
        """_shutdown() calls result_handler.process() once per cancelled task.

        Two tasks are in-flight when _shutdown() is called. After it
        completes, result_handler.process() must have been called exactly
        twice — once per interrupted session.
        """
        runner = ParallelRunner(
            session_runner_factory=_slow_factory(delay=10.0),
            max_parallelism=4,
            inter_session_delay=0,
        )

        task_a = asyncio.create_task(
            runner.execute_one("spec:1", 1, None),
            name="parallel-spec:1",
        )
        task_b = asyncio.create_task(
            runner.execute_one("spec:2", 1, None),
            name="parallel-spec:2",
        )
        runner.track_tasks([task_a, task_b])

        mock_result_handler = MagicMock()
        state = _make_minimal_state()

        # Build a minimal self-like namespace that _shutdown() needs.
        # _graph_sync=None tells the logging block to skip summary.
        fake_self = SimpleNamespace(
            _dispatch_mgr=SimpleNamespace(parallel_runner=runner),
            _result_handler=mock_result_handler,
            _graph_sync=None,
        )

        await Orchestrator._shutdown(
            fake_self,  # type: ignore[arg-type]
            state,
            attempt_tracker={"spec:1": 2, "spec:2": 1},
            error_tracker={},
        )

        # result_handler.process() must have been called once per cancelled task
        assert mock_result_handler.process.call_count == 2

    @pytest.mark.asyncio
    async def test_shutdown_uses_attempt_tracker_for_attempt_number(self) -> None:
        """_shutdown() uses attempt_tracker values rather than the default=1."""
        runner = ParallelRunner(
            session_runner_factory=_slow_factory(delay=10.0),
            max_parallelism=4,
            inter_session_delay=0,
        )

        task = asyncio.create_task(
            runner.execute_one("spec:1", 3, None),
            name="parallel-spec:1",
        )
        runner.track_tasks([task])

        mock_result_handler = MagicMock()
        state = _make_minimal_state()

        fake_self = SimpleNamespace(
            _dispatch_mgr=SimpleNamespace(parallel_runner=runner),
            _result_handler=mock_result_handler,
            _graph_sync=None,
        )

        await Orchestrator._shutdown(
            fake_self,  # type: ignore[arg-type]
            state,
            attempt_tracker={"spec:1": 3},
            error_tracker={},
        )

        assert mock_result_handler.process.call_count == 1
        # The record passed to process() should use the tracker's attempt (3)
        call_args = mock_result_handler.process.call_args
        record: SessionRecord = call_args[0][0]
        assert record.attempt == 3

    @pytest.mark.asyncio
    async def test_shutdown_sets_run_status_interrupted(self) -> None:
        """_shutdown() always sets state.run_status = INTERRUPTED."""
        runner = ParallelRunner(
            session_runner_factory=_slow_factory(delay=0.0),
            max_parallelism=4,
            inter_session_delay=0,
        )

        state = _make_minimal_state()
        assert state.run_status == RunStatus.RUNNING

        fake_self = SimpleNamespace(
            _dispatch_mgr=SimpleNamespace(parallel_runner=runner),
            _result_handler=None,
            _graph_sync=None,
        )

        await Orchestrator._shutdown(fake_self, state)  # type: ignore[arg-type]

        assert state.run_status == RunStatus.INTERRUPTED

    @pytest.mark.asyncio
    async def test_shutdown_no_tasks_process_not_called(self) -> None:
        """_shutdown() does not call process() when no tasks are in flight."""
        runner = ParallelRunner(
            session_runner_factory=_slow_factory(),
            max_parallelism=4,
            inter_session_delay=0,
        )
        # No tasks tracked

        mock_result_handler = MagicMock()
        state = _make_minimal_state()

        fake_self = SimpleNamespace(
            _dispatch_mgr=SimpleNamespace(parallel_runner=runner),
            _result_handler=mock_result_handler,
            _graph_sync=None,
        )

        await Orchestrator._shutdown(fake_self, state)  # type: ignore[arg-type]

        assert mock_result_handler.process.call_count == 0

    @pytest.mark.asyncio
    async def test_shutdown_with_no_result_handler_does_not_crash(self) -> None:
        """_shutdown() is safe when _result_handler is None (no DB connection)."""
        runner = ParallelRunner(
            session_runner_factory=_slow_factory(delay=10.0),
            max_parallelism=4,
            inter_session_delay=0,
        )

        task = asyncio.create_task(
            runner.execute_one("spec:1", 1, None),
            name="parallel-spec:1",
        )
        runner.track_tasks([task])

        state = _make_minimal_state()
        fake_self = SimpleNamespace(
            _dispatch_mgr=SimpleNamespace(parallel_runner=runner),
            _result_handler=None,
            _graph_sync=None,
        )

        # Should not raise even without a result handler
        await Orchestrator._shutdown(fake_self, state)  # type: ignore[arg-type]
        assert state.run_status == RunStatus.INTERRUPTED


# ---------------------------------------------------------------------------
# 536-AC-4: Double-SIGINT (SystemExit) does not bypass run()'s finally block
# ---------------------------------------------------------------------------


class TestDoubleSignintSystemExit:
    """536-AC-4: run()'s finally block executes _complete_run even on SystemExit.

    When a second SIGINT fires while _shutdown() is executing (e.g., inside
    cancel_all()'s asyncio.gather()), the signal handler raises SystemExit(1).
    Python guarantees that 'finally' executes for BaseException subclasses, so
    _complete_run must be called before the process exits.
    """

    @pytest.mark.asyncio
    async def test_finally_calls_complete_run_when_system_exit_from_shutdown(
        self,
    ) -> None:
        """_complete_run is invoked in run()'s finally block even when _shutdown raises SystemExit(1)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from agent_fox.engine.engine import Orchestrator

        state = _make_minimal_state()

        # Build a minimal mock Orchestrator instance.  We avoid spec=Orchestrator
        # because _signal and other instance attributes are set in __init__, not
        # the class body, so the spec would reject them.
        mock_self = MagicMock()
        mock_self._init_run.return_value = (state, {}, {})
        mock_self._finalize_run = AsyncMock()
        mock_self._signal.interrupted = True  # Enter _shutdown path immediately
        mock_self._graph = None  # _sync_plan_statuses returns early
        mock_self._graph_sync = None  # Skip audit cleanup + issue summaries
        mock_self._platform = None  # Skip issue summary posting
        mock_self._knowledge_db_conn = MagicMock()  # Non-None so _complete_run is called
        mock_self._run_id = "test-run-id-ac4"
        mock_self._is_parallel = False

        # _shutdown raises SystemExit(1), simulating the double-SIGINT handler
        # (engine.py: raise SystemExit(1)) firing while cancel_all() is awaiting
        # in-flight tasks.
        async def _shutdown_raises(*args: object, **kwargs: object) -> None:
            raise SystemExit(1)

        mock_self._shutdown = _shutdown_raises

        with patch("agent_fox.engine.engine.emit_audit_event"):
            with pytest.raises(SystemExit) as exc_info:
                await Orchestrator.run(mock_self)

        assert exc_info.value.code == 1, "SystemExit must propagate with code 1"
        mock_self._finalize_run.assert_called_once()
