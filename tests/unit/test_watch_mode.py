"""Unit and edge-case tests for watch mode.

Test Spec: TS-70-1 through TS-70-18, TS-70-E1 through TS-70-E6
Requirements: 70-REQ-1.1 through 70-REQ-5.3
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.config import OrchestratorConfig
from agent_fox.engine.engine import Orchestrator
from agent_fox.knowledge.audit import AuditEvent, AuditEventType
from agent_fox.knowledge.sink import SinkDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DISCOVERY_METHOD = "_try_end_of_run_discovery"


class _CapturingSink:
    """Simple audit event sink for test assertions."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record_session_outcome(self, outcome: Any) -> None:
        pass

    def record_tool_call(self, call: Any) -> None:
        pass

    def record_tool_error(self, error: Any) -> None:
        pass

    def emit_audit_event(self, event: AuditEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass


def _write_empty_plan(plan_dir: Path) -> Path:
    """Write a plan.json with no tasks and return its path."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {},
        "edges": [],
        "order": [],
    }
    plan_path.write_text(json.dumps(plan, indent=2))
    return plan_path


def _write_single_node_plan(plan_dir: Path) -> Path:
    """Write a plan.json with a single node."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {
            "spec:1": {
                "id": "spec:1",
                "spec_name": "spec",
                "group_number": 1,
                "title": "Task 1",
                "optional": False,
                "status": "pending",
                "subtask_count": 0,
                "body": "",
                "archetype": "coder",
            }
        },
        "edges": [],
        "order": ["spec:1"],
    }
    plan_path.write_text(json.dumps(plan, indent=2))
    return plan_path


def _write_stalled_plan(plan_dir: Path) -> Path:
    """Write a plan.json where the node is blocked (stalled state)."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "plan.json"
    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {
            "spec:1": {
                "id": "spec:1",
                "spec_name": "spec",
                "group_number": 1,
                "title": "Task 1",
                "optional": False,
                "status": "blocked",
                "subtask_count": 0,
                "body": "",
                "archetype": "coder",
            }
        },
        "edges": [],
        "order": ["spec:1"],
    }
    plan_path.write_text(json.dumps(plan, indent=2))
    return plan_path


def _write_state_with_cost(state_path: Path, plan_data: dict[str, Any], total_cost: float) -> None:
    """Pre-write a state.jsonl file with a given total_cost."""
    plan_hash = hashlib.sha256(json.dumps(plan_data, sort_keys=True).encode()).hexdigest()[:16]
    state = {
        "plan_hash": plan_hash,
        "node_states": {},
        "session_history": [],
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost": total_cost,
        "total_sessions": 0,
        "started_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "run_status": "running",
    }
    state_path.write_text(json.dumps(state) + "\n")


def _make_orchestrator(
    tmp_path: Path,
    *,
    config: OrchestratorConfig | None = None,
    plan_path: Path | None = None,
    capturing_sink: _CapturingSink | None = None,
) -> tuple[Orchestrator, _CapturingSink]:
    """Create an Orchestrator with a capturing sink for event assertions."""
    plan_dir = tmp_path / ".agent-fox"
    if plan_path is None:
        plan_path = _write_empty_plan(plan_dir)
    state_path = plan_dir / "state.jsonl"

    sink = capturing_sink or _CapturingSink()
    sink_dispatcher = SinkDispatcher()
    sink_dispatcher.add(sink)  # type: ignore[arg-type]

    if config is None:
        config = OrchestratorConfig(parallel=1, inter_session_delay=0, hot_load=True)

    mock_outcome = MagicMock(
        status="completed",
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        duration_ms=0,
        error_message=None,
        spec_name="spec",
        task_group=1,
        archetype="coder",
    )

    orch = Orchestrator(
        config=config,
        plan_path=plan_path,
        state_path=state_path,
        session_runner_factory=lambda nid, **kw: MagicMock(execute=AsyncMock(return_value=mock_outcome)),
        sink_dispatcher=sink_dispatcher,
    )
    return orch, sink


def _watch_poll_events(sink: _CapturingSink) -> list[AuditEvent]:
    """Filter captured events to WATCH_POLL events only."""
    return [e for e in sink.events if e.event_type == AuditEventType.WATCH_POLL]


# ---------------------------------------------------------------------------
# TS-70-9: Watch interval default is 60
# TS-70-10: Watch interval clamped below 10
# TS-70-E5: Watch interval at exact minimum
# ---------------------------------------------------------------------------


class TestConfig:
    """Config field tests for watch_interval.

    Test Spec: TS-70-9, TS-70-10, TS-70-E5
    Requirements: 70-REQ-3.1, 70-REQ-3.2, 70-REQ-3.E1
    """

    def test_watch_interval_default_is_60(self) -> None:
        """TS-70-9: OrchestratorConfig.watch_interval defaults to 60."""
        config = OrchestratorConfig()
        assert config.watch_interval == 60  # noqa: PLR2004

    def test_watch_interval_clamped_below_10(self) -> None:
        """TS-70-10: watch_interval values below 10 are clamped to 10."""
        config5 = OrchestratorConfig(watch_interval=5)
        assert config5.watch_interval == 10  # noqa: PLR2004

        config1 = OrchestratorConfig(watch_interval=1)
        assert config1.watch_interval == 10  # noqa: PLR2004

    def test_watch_interval_at_exact_minimum(self) -> None:
        """TS-70-E5: watch_interval=10 is accepted without clamping."""
        config = OrchestratorConfig(watch_interval=10)
        assert config.watch_interval == 10  # noqa: PLR2004

    def test_watch_interval_above_minimum_not_clamped(self) -> None:
        """Values above minimum are preserved."""
        config = OrchestratorConfig(watch_interval=30)
        assert config.watch_interval == 30  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TS-70-18: WATCH_POLL in AuditEventType enum
# ---------------------------------------------------------------------------


class TestAuditEnum:
    """Audit event type enum tests.

    Test Spec: TS-70-18
    Requirements: 70-REQ-5.3
    """

    def test_watch_poll_enum_value(self) -> None:
        """TS-70-18: AuditEventType.WATCH_POLL == 'watch.poll'."""
        assert AuditEventType.WATCH_POLL == "watch.poll"

    def test_watch_poll_in_members(self) -> None:
        """TS-70-18: WATCH_POLL is a member of AuditEventType."""
        assert "WATCH_POLL" in AuditEventType.__members__


# ---------------------------------------------------------------------------
# TS-70-1: Watch flag activates watch loop
# TS-70-2: Watch disabled with hot_load=False
# ---------------------------------------------------------------------------


class TestWatchActivation:
    """Tests for watch mode activation.

    Test Spec: TS-70-1, TS-70-2
    Requirements: 70-REQ-1.1, 70-REQ-1.2
    """

    @pytest.mark.asyncio
    async def test_watch_mode_emits_watch_poll_event(self, tmp_path: Path) -> None:
        """TS-70-1: Watch mode emits WATCH_POLL when no tasks are ready."""
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await orch.run()

        events = _watch_poll_events(sink)
        assert len(events) >= 1, "Expected at least one WATCH_POLL audit event"

    @pytest.mark.asyncio
    async def test_hot_load_false_disables_watch(self, tmp_path: Path) -> None:
        """TS-70-2: Watch mode is skipped when hot_load=False."""
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=False,
        )
        orch, sink = _make_orchestrator(tmp_path, config=config)
        orch._watch = True  # type: ignore[attr-defined]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            state = await orch.run()

        assert state.run_status == "completed"
        events = _watch_poll_events(sink)
        assert len(events) == 0, "No WATCH_POLL events when hot_load=False"


# ---------------------------------------------------------------------------
# TS-70-4: Watch loop sleeps for watch_interval
# TS-70-5: Watch poll runs full barrier sequence
# TS-70-6: Watch loop resumes dispatch on new tasks
# TS-70-7: Watch loop re-enters on no tasks
# TS-70-8: Watch loop checks interruption before sleep
# ---------------------------------------------------------------------------


class TestWatchLoop:
    """Tests for watch loop behavior.

    Test Spec: TS-70-4, TS-70-5, TS-70-6, TS-70-7, TS-70-8
    Requirements: 70-REQ-2.1 through 70-REQ-2.5
    """

    @pytest.mark.asyncio
    async def test_watch_loop_sleeps_for_configured_interval(self, tmp_path: Path) -> None:
        """TS-70-4: Watch loop sleeps for watch_interval seconds."""
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            watch_interval=30,
        )
        orch, _ = _make_orchestrator(tmp_path, config=config)
        orch._watch = True  # type: ignore[attr-defined]

        sleep_args: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_args.append(seconds)
            orch._signal.interrupted = True

        async def fake_discovery(state: Any) -> bool:
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                await orch.run()

        assert len(sleep_args) >= 1, "asyncio.sleep must be called in watch loop"
        assert sleep_args[0] == 30  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_watch_poll_calls_end_of_run_discovery(self, tmp_path: Path) -> None:
        """TS-70-5: Each watch poll calls _try_end_of_run_discovery."""
        orch, _ = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:  # noqa: PLR2004
                orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await orch.run()

        assert poll_count >= 2, f"Expected >= 2 barrier calls, got {poll_count}"  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_watch_loop_resumes_on_new_tasks(self, tmp_path: Path) -> None:
        """TS-70-6: Watch loop exits and dispatch resumes when new tasks found.

        Mock discovery accounting for main loop offset:
        - Call 1 (main loop): returns False (enters watch gate)
        - Call 2 (watch poll 1): returns True (new tasks → watch returns None)
        - Call 3+ (main loop re-entry): set interrupted, return False
        """
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 2:  # noqa: PLR2004
                return True  # Watch poll finds tasks → watch loop returns None
            if poll_count >= 3:  # noqa: PLR2004
                orch._signal.interrupted = True  # Terminate after re-entry
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                state = await orch.run()

        assert poll_count >= 3  # noqa: PLR2004  # Main loop re-entered
        assert state.run_status == "interrupted"
        # Verify at least 1 WATCH_POLL event with new_tasks_found=True
        events = _watch_poll_events(sink)
        assert any(e.payload["new_tasks_found"] is True for e in events)

    @pytest.mark.asyncio
    async def test_watch_loop_continues_on_no_tasks(self, tmp_path: Path) -> None:
        """TS-70-7: Watch loop emits 3 WATCH_POLL events when polling 3 times."""
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:  # noqa: PLR2004
                orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                state = await orch.run()

        events = _watch_poll_events(sink)
        assert len(events) == 3  # noqa: PLR2004
        assert state.run_status == "interrupted"

    @pytest.mark.asyncio
    async def test_watch_loop_checks_interruption_before_sleep(self, tmp_path: Path) -> None:
        """TS-70-8: SIGINT before sleep prevents sleep from being called.

        The interrupt must be set via the discovery mock (not before run())
        so the main loop's interrupt check at line 507 does not catch it
        first. Setting it on call 1 (main loop discovery) causes the watch
        loop to see interrupted=True on entry.
        """
        orch, _ = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        sleep_called = False

        async def fake_sleep(seconds: float) -> None:
            nonlocal sleep_called
            sleep_called = True

        async def fake_discovery(state: Any) -> bool:
            orch._signal.interrupted = True  # Set during main loop discovery
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                state = await orch.run()

        assert not sleep_called, "sleep should NOT be called when interrupted"
        assert state.run_status == "interrupted"


# ---------------------------------------------------------------------------
# TS-70-12: Watch interval mutable via hot-reload
# ---------------------------------------------------------------------------


class TestConfigReload:
    """Tests for config hot-reload interaction with watch_interval.

    Test Spec: TS-70-12
    Requirements: 70-REQ-3.4
    """

    @pytest.mark.asyncio
    async def test_watch_interval_updated_mid_run(self, tmp_path: Path) -> None:
        """TS-70-12: Watch interval changes take effect on next sleep cycle.

        Config change must happen on mock call 2 (first watch poll), not
        call 1 (main loop), to ensure the first watch sleep uses the
        original interval.
        """
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            watch_interval=60,
        )
        orch, _ = _make_orchestrator(tmp_path, config=config)
        orch._watch = True  # type: ignore[attr-defined]

        sleep_args: list[float] = []
        poll_count = 0

        async def fake_sleep(seconds: float) -> None:
            sleep_args.append(seconds)
            if len(sleep_args) >= 2:  # noqa: PLR2004
                orch._signal.interrupted = True

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 2:  # noqa: PLR2004
                # First watch poll — simulate config hot-reload
                orch._config = orch._config.model_copy(update={"watch_interval": 20})
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                await orch.run()

        assert len(sleep_args) >= 2  # noqa: PLR2004
        assert sleep_args[0] == 60  # noqa: PLR2004
        assert sleep_args[1] == 20  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TS-70-13: Stall terminates in watch mode
# TS-70-14: Circuit breaker stops watch loop
# TS-70-15: SIGINT during watch sleep
# ---------------------------------------------------------------------------


class TestTermination:
    """Tests for watch mode termination conditions.

    Test Spec: TS-70-13, TS-70-14, TS-70-15
    Requirements: 70-REQ-4.1, 70-REQ-4.2, 70-REQ-4.3
    """

    @pytest.mark.asyncio
    async def test_stall_terminates_without_watch_poll(self, tmp_path: Path) -> None:
        """TS-70-13: Stalled graph terminates with STALLED, no WATCH_POLL."""
        plan_dir = tmp_path / ".agent-fox"
        plan_path = _write_stalled_plan(plan_dir)
        orch, sink = _make_orchestrator(tmp_path, plan_path=plan_path)
        orch._watch = True  # type: ignore[attr-defined]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            state = await orch.run()

        assert state.run_status == "stalled"
        events = _watch_poll_events(sink)
        assert len(events) == 0, "No WATCH_POLL events when run stalls"

    @pytest.mark.asyncio
    async def test_cost_limit_stops_watch_loop(self, tmp_path: Path) -> None:
        """TS-70-14: Cost limit trips circuit breaker and stops watch loop."""
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            max_cost=0.01,
        )
        orch, sink = _make_orchestrator(tmp_path, config=config)
        orch._watch = True  # type: ignore[attr-defined]

        plan_path = tmp_path / ".agent-fox" / "plan.json"
        state_path = tmp_path / ".agent-fox" / "state.jsonl"
        plan_data = json.loads(plan_path.read_text())
        _write_state_with_cost(state_path, plan_data, total_cost=0.01)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            final_state = await orch.run()

        assert final_state.run_status == "cost_limit"
        events = _watch_poll_events(sink)
        assert len(events) == 0, "No WATCH_POLL events when cost limit fires"

    @pytest.mark.asyncio
    async def test_sigint_during_watch_sleep_terminates_gracefully(self, tmp_path: Path) -> None:
        """TS-70-15: SIGINT during sleep causes graceful shutdown."""
        orch, _ = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        async def fake_sleep(seconds: float) -> None:
            orch._signal.interrupted = True

        async def fake_discovery(state: Any) -> bool:
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                state = await orch.run()

        assert state.run_status == "interrupted"


# ---------------------------------------------------------------------------
# TS-70-16: WATCH_POLL audit event emitted
# TS-70-17: WATCH_POLL payload contents
# ---------------------------------------------------------------------------


class TestAuditEvents:
    """Tests for WATCH_POLL audit event emission.

    Test Spec: TS-70-16, TS-70-17
    Requirements: 70-REQ-5.1, 70-REQ-5.2
    """

    @pytest.mark.asyncio
    async def test_watch_poll_event_emitted_each_cycle(self, tmp_path: Path) -> None:
        """TS-70-16: Two WATCH_POLL events emitted for two poll cycles."""
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:  # noqa: PLR2004
                orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await orch.run()

        events = _watch_poll_events(sink)
        assert len(events) == 2  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_watch_poll_payload_contents(self, tmp_path: Path) -> None:
        """TS-70-17: WATCH_POLL payload has poll_number and new_tasks_found.

        Mock must account for main loop discovery offset:
        - Call 1 (main loop): returns False
        - Call 2 (watch poll 1): returns False (no tasks)
        - Call 3 (watch poll 2): returns True (new tasks found)
        - Call 4+ (main loop re-entry): set interrupted, return False
        """
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 3:  # noqa: PLR2004
                return True  # Watch poll 2 finds tasks
            if poll_count >= 4:  # noqa: PLR2004
                orch._signal.interrupted = True  # Terminate after re-entry
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                final_state = await orch.run()

        assert final_state.run_status == "interrupted"
        events = _watch_poll_events(sink)
        assert len(events) >= 2  # noqa: PLR2004

        assert events[0].payload["poll_number"] == 1
        assert events[0].payload["new_tasks_found"] is False

        assert events[1].payload["poll_number"] == 2  # noqa: PLR2004
        assert events[1].payload["new_tasks_found"] is True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests.

    Test Spec: TS-70-E1, TS-70-E2, TS-70-E3, TS-70-E4, TS-70-E6
    Requirements: 70-REQ-1.E1, 70-REQ-1.E2, 70-REQ-2.E1, 70-REQ-2.E2, 70-REQ-4.E1
    """

    @pytest.mark.asyncio
    async def test_missing_plan_file_errors_normally_with_watch(self, tmp_path: Path) -> None:
        """TS-70-E1: Missing plan file raises PlanError even with watch=True."""
        from agent_fox.core.errors import PlanError

        plan_dir = tmp_path / ".agent-fox"
        plan_dir.mkdir(parents=True, exist_ok=True)
        nonexistent_plan = plan_dir / "plan.json"  # Does not exist
        state_path = plan_dir / "state.jsonl"

        orch = Orchestrator(
            config=OrchestratorConfig(parallel=1, inter_session_delay=0),
            plan_path=nonexistent_plan,
            state_path=state_path,
            session_runner_factory=lambda nid, **kw: MagicMock(),
        )
        orch._watch = True  # type: ignore[attr-defined]

        with pytest.raises(PlanError):
            await orch.run()

    @pytest.mark.asyncio
    async def test_empty_plan_enters_watch_loop(self, tmp_path: Path) -> None:
        """TS-70-E2: Empty plan with watch=True enters the watch loop.

        The interrupt must be set via the discovery mock (not before run())
        so the main loop's interrupt check at line 507 does not catch it
        first. Setting it on call 1 (main loop discovery) causes the watch
        loop to see interrupted=True on entry.
        """
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        async def fake_discovery(state: Any) -> bool:
            orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                state = await orch.run()

        events = _watch_poll_events(sink)
        assert len(events) >= 1, "Watch loop should be entered for empty plan"
        assert state.run_status == "interrupted"

    @pytest.mark.asyncio
    async def test_barrier_exception_does_not_stop_watch_loop(self, tmp_path: Path) -> None:
        """TS-70-E3: Barrier exceptions are logged but watch loop continues.

        The exception must be raised on mock call 2 (first watch poll), not
        call 1 (main loop) — the main loop does not catch
        _try_end_of_run_discovery exceptions the same way.
        """
        orch, sink = _make_orchestrator(tmp_path)
        orch._watch = True  # type: ignore[attr-defined]

        poll_count = 0

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                return False  # Main loop call → enters watch gate
            if poll_count == 2:  # noqa: PLR2004
                raise RuntimeError("Simulated barrier failure")
            # Call 3 (watch poll 2): set interrupted, return False
            orch._signal.interrupted = True
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await orch.run()

        events = _watch_poll_events(sink)
        # 3 events: poll 1 (exception→new_tasks_found=False), poll 2 (normal),
        # poll 3 (interrupt detected before sleep in step 1).
        assert len(events) == 3  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_watch_interval_updated_via_hot_reload(self, tmp_path: Path) -> None:
        """TS-70-E4: Config hot-reload updates interval used on next sleep.

        Config change must happen on mock call 2 (first watch poll), not
        call 1 (main loop), to ensure the first watch sleep uses the
        original interval.
        """
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            watch_interval=60,
        )
        orch, _ = _make_orchestrator(tmp_path, config=config)
        orch._watch = True  # type: ignore[attr-defined]

        sleep_args: list[float] = []
        poll_count = 0

        async def fake_sleep(seconds: float) -> None:
            sleep_args.append(seconds)
            if len(sleep_args) >= 2:  # noqa: PLR2004
                orch._signal.interrupted = True

        async def fake_discovery(state: Any) -> bool:
            nonlocal poll_count
            poll_count += 1
            if poll_count == 2:  # noqa: PLR2004
                # First watch poll — simulate config hot-reload
                orch._config = orch._config.model_copy(update={"watch_interval": 20})
            return False

        with patch.object(orch, _DISCOVERY_METHOD, side_effect=fake_discovery):
            with patch("asyncio.sleep", side_effect=fake_sleep):
                await orch.run()

        assert sleep_args[0] == 60  # noqa: PLR2004
        assert sleep_args[1] == 20  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_circuit_breaker_before_watch_loop_entry(self, tmp_path: Path) -> None:
        """TS-70-E6: Cost limit during dispatch prevents watch loop entry."""
        config = OrchestratorConfig(
            parallel=1,
            inter_session_delay=0,
            hot_load=True,
            max_cost=0.01,
        )
        plan_dir = tmp_path / ".agent-fox"
        plan_path = _write_single_node_plan(plan_dir)
        orch, sink = _make_orchestrator(tmp_path, config=config, plan_path=plan_path)
        orch._watch = True  # type: ignore[attr-defined]

        state_path = plan_dir / "state.jsonl"
        plan_data = json.loads(plan_path.read_text())
        _write_state_with_cost(state_path, plan_data, total_cost=0.01)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            final_state = await orch.run()

        assert final_state.run_status == "cost_limit"
        events = _watch_poll_events(sink)
        assert len(events) == 0, "No WATCH_POLL events when circuit breaker fires"
