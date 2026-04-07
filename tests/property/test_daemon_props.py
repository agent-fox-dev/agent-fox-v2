"""Property tests for daemon framework.

Test Spec: TS-85-P1 through TS-85-P7
Properties: 1-7 from design.md
Requirements: 85-REQ-1.3, 85-REQ-1.4, 85-REQ-1.E1, 85-REQ-2.1,
              85-REQ-2.E1, 85-REQ-3.1, 85-REQ-3.2,
              85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1,
              85-REQ-6.1, 85-REQ-7.1, 85-REQ-7.E1,
              85-REQ-9.1, 85-REQ-9.E1
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_stream(
    name: str = "test",
    interval: int = 1,
    enabled: bool = True,
    fail: bool = False,
) -> MagicMock:
    """Create a mock WorkStream."""
    stream = MagicMock()
    stream.name = name
    stream.interval = interval
    stream.enabled = enabled
    if fail:
        stream.run_once = AsyncMock(side_effect=RuntimeError("test failure"))
    else:
        stream.run_once = AsyncMock()
    stream.shutdown = AsyncMock()
    return stream


def _make_config(enabled_streams: list[str] | None = None) -> MagicMock:
    config = MagicMock()
    ns = MagicMock()
    ns.enabled_streams = enabled_streams or ["specs", "fixes", "hunts", "spec_gen"]
    ns.merge_strategy = "direct"
    config.night_shift = ns
    return config


# ---------------------------------------------------------------------------
# TS-85-P1: PID mutual exclusion
# Property 1: check_pid_file returns ALIVE only for actually alive processes
# Validates: 85-REQ-2.1, 85-REQ-2.E1, 85-REQ-3.1, 85-REQ-3.2
# ---------------------------------------------------------------------------


class TestPidMutualExclusion:
    """PID file mechanism ensures at most one daemon runs at a time."""

    @given(pid=st.integers(min_value=1, max_value=2**31))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_pid_status_matches_process_liveness(self, pid: int, tmp_path: Path) -> None:
        """check_pid_file returns ALIVE for alive PIDs, STALE for dead ones."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file

        pid_path = tmp_path / f"daemon_{pid}.pid"
        pid_path.write_text(str(pid))
        status, read_pid = check_pid_file(pid_path)
        assert read_pid == pid

        # Determine if process is alive
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            # Process exists but we lack permission — treat as alive.
            alive = True
        except (OverflowError, OSError):
            # PID out of valid range — not alive.
            alive = False

        if alive:
            assert status == PidStatus.ALIVE
        else:
            assert status == PidStatus.STALE

    def test_write_then_check_returns_alive(self, tmp_path: Path) -> None:
        """write_pid_file + check_pid_file returns ALIVE for current process."""
        from agent_fox.nightshift.pid import PidStatus, check_pid_file, write_pid_file

        pid_path = tmp_path / "daemon.pid"
        write_pid_file(pid_path)
        status, pid = check_pid_file(pid_path)
        assert status == PidStatus.ALIVE
        assert pid == os.getpid()


# ---------------------------------------------------------------------------
# TS-85-P2: Cost monotonicity and limit
# Property 2: SharedBudget total cost is monotonically non-decreasing
# Validates: 85-REQ-5.1, 85-REQ-5.2, 85-REQ-5.E1
# ---------------------------------------------------------------------------


class TestCostMonotonicity:
    """SharedBudget total cost is monotonically non-decreasing."""

    @given(
        costs=st.lists(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False), max_size=20),
        max_cost=st.one_of(
            st.none(),
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=100)
    def test_cost_monotonicity_and_exceeded(
        self, costs: list[float], max_cost: float | None
    ) -> None:
        """total_cost equals sum of add_cost calls; exceeded triggers correctly."""
        from agent_fox.nightshift.daemon import SharedBudget

        budget = SharedBudget(max_cost=max_cost)
        running_total = 0.0
        for cost in costs:
            budget.add_cost(cost)
            running_total += cost
            assert abs(budget.total_cost - running_total) < 1e-9
            if max_cost is not None:
                assert budget.exceeded == (running_total >= max_cost)
            else:
                assert budget.exceeded is False


# ---------------------------------------------------------------------------
# TS-85-P3: Stream isolation
# Property 3: A failing stream never prevents other streams from running
# Validates: 85-REQ-1.4, 85-REQ-1.E1
# ---------------------------------------------------------------------------


class TestStreamIsolation:
    """A failing stream never prevents other streams from running."""

    @given(
        n=st.integers(min_value=2, max_value=5),
        fail_index=st.integers(min_value=0, max_value=4),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_failing_stream_does_not_block_others(
        self, n: int, fail_index: int, tmp_path: Path
    ) -> None:
        """Non-failing streams run even when one stream always fails."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        fail_index = fail_index % n
        streams = []
        for i in range(n):
            streams.append(_make_mock_stream(
                name=f"stream-{i}",
                fail=(i == fail_index),
            ))

        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(
            config, None, streams, budget, pid_path=tmp_path / "d.pid"
        )

        async def run_briefly() -> None:
            t = asyncio.create_task(runner.run())
            await asyncio.sleep(0.2)
            runner.request_shutdown()
            await t

        asyncio.get_event_loop().run_until_complete(run_briefly())

        for i, s in enumerate(streams):
            assert s.run_once.call_count >= 1, f"stream-{i} was not called"


# ---------------------------------------------------------------------------
# TS-85-P4: Shutdown completeness
# Property 4: Every registered stream's shutdown() is called
# Validates: 85-REQ-2.2, 85-REQ-2.4, 85-REQ-2.5
# ---------------------------------------------------------------------------


class TestShutdownCompleteness:
    """Every registered stream's shutdown() is called on graceful shutdown."""

    @given(n=st.integers(min_value=1, max_value=8))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_streams_shutdown(self, n: int, tmp_path: Path) -> None:
        """After run() returns, shutdown() called on all N streams."""
        from agent_fox.nightshift.daemon import DaemonRunner, SharedBudget

        streams = [_make_mock_stream(name=f"s-{i}") for i in range(n)]
        budget = SharedBudget(max_cost=None)
        config = _make_config()
        runner = DaemonRunner(
            config, None, streams, budget, pid_path=tmp_path / "d.pid"
        )
        runner.request_shutdown()

        async def run_and_check() -> None:
            await runner.run()

        asyncio.get_event_loop().run_until_complete(run_and_check())

        for i, s in enumerate(streams):
            assert s.shutdown.call_count == 1, f"stream s-{i} shutdown not called"


# ---------------------------------------------------------------------------
# TS-85-P5: Config interval clamping
# Property 5: Interval fields always >= their documented minimum
# Validates: 85-REQ-9.1, 85-REQ-9.E1
# ---------------------------------------------------------------------------


class TestConfigIntervalClamping:
    """Interval config fields are always >= their documented minimum."""

    @given(
        spec_interval=st.integers(min_value=-1000, max_value=10000),
        spec_gen_interval=st.integers(min_value=-1000, max_value=10000),
    )
    @settings(max_examples=100)
    def test_intervals_clamped(self, spec_interval: int, spec_gen_interval: int) -> None:
        """spec_interval >= 10 and spec_gen_interval >= 60 after validation."""
        from agent_fox.nightshift.config import NightShiftConfig

        config = NightShiftConfig(
            spec_interval=spec_interval,
            spec_gen_interval=spec_gen_interval,
        )
        assert config.spec_interval >= 10
        assert config.spec_gen_interval >= 60


# ---------------------------------------------------------------------------
# TS-85-P6: Platform degradation
# Property 6: With platform.type="none", only spec executor can be enabled
# Validates: 85-REQ-7.1, 85-REQ-7.E1
# ---------------------------------------------------------------------------


class TestPlatformDegradation:
    """With platform.type='none', only spec executor can be enabled."""

    @given(no_specs=st.booleans())
    @settings(max_examples=10)
    def test_platform_none_subset(self, no_specs: bool) -> None:
        """Enabled set is subset of {'spec-executor'} with platform none."""
        from agent_fox.nightshift.streams import build_streams

        config = MagicMock()
        config.platform.type = "none"
        ns = MagicMock()
        ns.enabled_streams = ["specs", "fixes", "hunts", "spec_gen"]
        ns.merge_strategy = "direct"
        ns.spec_interval = 60
        ns.spec_gen_interval = 300
        ns.issue_check_interval = 900
        ns.hunt_scan_interval = 14400
        config.night_shift = ns

        streams = build_streams(config, no_specs=no_specs)
        enabled_names = {s.name for s in streams if s.enabled}
        assert enabled_names.issubset({"spec-executor"})
        if no_specs:
            assert enabled_names == set()
        else:
            assert enabled_names == {"spec-executor"}


# ---------------------------------------------------------------------------
# TS-85-P7: Enabled stream filtering
# Property 7: Running streams = intersection of config-enabled and CLI-enabled
# Validates: 85-REQ-1.3, 85-REQ-6.1, 85-REQ-9.2
# ---------------------------------------------------------------------------

# Stream name mapping: config name -> stream name
_CONFIG_TO_STREAM = {
    "specs": "spec-executor",
    "fixes": "fix-pipeline",
    "hunts": "hunt-scan",
    "spec_gen": "spec-generator",
}
_STREAM_TO_CONFIG = {v: k for k, v in _CONFIG_TO_STREAM.items()}
_ALL_CONFIG_NAMES = list(_CONFIG_TO_STREAM.keys())


class TestEnabledStreamFiltering:
    """Running streams are the intersection of config-enabled and CLI-enabled."""

    @given(
        config_enabled=st.lists(
            st.sampled_from(_ALL_CONFIG_NAMES),
            min_size=0,
            max_size=4,
            unique=True,
        ),
        no_specs=st.booleans(),
        no_fixes=st.booleans(),
        no_hunts=st.booleans(),
        no_spec_gen=st.booleans(),
    )
    @settings(max_examples=50)
    def test_intersection(
        self,
        config_enabled: list[str],
        no_specs: bool,
        no_fixes: bool,
        no_hunts: bool,
        no_spec_gen: bool,
    ) -> None:
        """Running set = config-enabled ∩ CLI-enabled."""
        from agent_fox.nightshift.streams import build_streams

        config = MagicMock()
        config.platform.type = "github"
        ns = MagicMock()
        # Empty list means all enabled per 85-REQ-9.E2
        ns.enabled_streams = config_enabled if config_enabled else []
        ns.merge_strategy = "direct"
        ns.spec_interval = 60
        ns.spec_gen_interval = 300
        ns.issue_check_interval = 900
        ns.hunt_scan_interval = 14400
        config.night_shift = ns

        streams = build_streams(
            config,
            no_specs=no_specs,
            no_fixes=no_fixes,
            no_hunts=no_hunts,
            no_spec_gen=no_spec_gen,
        )

        cli_enabled = set()
        if not no_specs:
            cli_enabled.add("specs")
        if not no_fixes:
            cli_enabled.add("fixes")
        if not no_hunts:
            cli_enabled.add("hunts")
        if not no_spec_gen:
            cli_enabled.add("spec_gen")

        # Empty config_enabled means all enabled
        effective_config = set(config_enabled) if config_enabled else set(_ALL_CONFIG_NAMES)
        expected = effective_config & cli_enabled

        actual = {_STREAM_TO_CONFIG[s.name] for s in streams if s.enabled}
        assert actual == expected
