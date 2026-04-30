"""Unit tests for concrete stream implementations.

Test Spec: TS-85-18, TS-85-19, TS-85-20, TS-85-21, TS-85-28, TS-85-30,
           TS-85-E10, TS-85-E11, TS-85-E16
Requirements: 85-REQ-6.1, 85-REQ-6.2, 85-REQ-6.3, 85-REQ-7.1, 85-REQ-7.E1,
              85-REQ-10.1, 85-REQ-10.3, 85-REQ-10.E1
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    platform_type: str = "github",
    enabled_streams: list[str] | None = None,
) -> MagicMock:
    """Create a mock config."""
    config = MagicMock()
    config.platform.type = platform_type
    ns = MagicMock()
    ns.enabled_streams = enabled_streams or ["specs", "fixes", "hunts"]
    ns.spec_interval = 60
    ns.issue_check_interval = 900
    ns.hunt_scan_interval = 14400
    config.night_shift = ns
    return config


# ---------------------------------------------------------------------------
# TS-85-18: CLI --no-specs disables spec executor
# Requirement: 85-REQ-6.1
# ---------------------------------------------------------------------------


class TestCliNoFlags:
    """Verify --no-* flags disable corresponding streams."""

    def test_no_specs_disables_spec_executor(self) -> None:
        """--no-specs disables spec executor, others remain enabled."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config()
        streams = build_streams(config, no_specs=True, no_fixes=False, no_hunts=False)
        spec = next(s for s in streams if s.name == "spec-executor")
        fix = next(s for s in streams if s.name == "fix-pipeline")
        assert spec.enabled is False
        assert fix.enabled is True

    def test_no_fixes_disables_fix_pipeline(self) -> None:
        """--no-fixes disables fix pipeline."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config()
        streams = build_streams(config, no_specs=False, no_fixes=True, no_hunts=False)
        fix = next(s for s in streams if s.name == "fix-pipeline")
        assert fix.enabled is False

    def test_no_hunts_disables_hunt_scan(self) -> None:
        """--no-hunts disables hunt scan."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config()
        streams = build_streams(config, no_specs=False, no_fixes=False, no_hunts=True)
        hunt = next(s for s in streams if s.name == "hunt-scan")
        assert hunt.enabled is False


# ---------------------------------------------------------------------------
# TS-85-19: code --watch alias
# Requirement: 85-REQ-6.2
# ---------------------------------------------------------------------------


class TestCodeWatchAlias:
    """Verify code --watch runs only spec executor."""

    def test_watch_mode_only_spec_executor(self) -> None:
        """Watch mode enables only spec executor."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config()
        streams = build_streams(config, no_specs=False, no_fixes=True, no_hunts=True)
        enabled = [s for s in streams if s.enabled]
        assert len(enabled) == 1
        assert enabled[0].name == "spec-executor"


# ---------------------------------------------------------------------------
# TS-85-20: --auto flag labels hunt findings
# Requirement: 85-REQ-6.3
# ---------------------------------------------------------------------------


class TestAutoFlag:
    """Verify --auto flag is passed through to hunt scan stream."""

    def test_auto_fix_configured(self) -> None:
        """Hunt scan stream has auto_fix=True when --auto is passed."""
        from agent_fox.nightshift.streams import EngineWorkStream, build_streams

        config = _make_config()
        streams = build_streams(config, auto=True)
        hunt = next(s for s in streams if s.name == "hunt-scan")
        assert isinstance(hunt, EngineWorkStream)
        assert hunt.auto_fix is True


# ---------------------------------------------------------------------------
# TS-85-21: Platform none disables platform-dependent streams
# Requirement: 85-REQ-7.1
# ---------------------------------------------------------------------------


class TestPlatformDegradation:
    """Verify platform.type='none' disables platform-dependent streams."""

    def test_only_spec_executor_enabled(self) -> None:
        """Only spec executor enabled when platform is none."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config(platform_type="none")
        streams = build_streams(config)
        enabled_names = [s.name for s in streams if s.enabled]
        assert enabled_names == ["spec-executor"]


# ---------------------------------------------------------------------------
# TS-85-E10: All --no-* flags = idle loop
# Requirement: 85-REQ-6.E1
# ---------------------------------------------------------------------------


class TestAllFlagsDisabled:
    """Verify all --no-* flags results in no enabled streams."""

    def test_all_disabled(self) -> None:
        """All streams disabled when all --no-* flags set."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config()
        streams = build_streams(config, no_specs=True, no_fixes=True, no_hunts=True)
        enabled = [s for s in streams if s.enabled]
        assert len(enabled) == 0


# ---------------------------------------------------------------------------
# TS-85-E11: Platform none + no-specs = idle loop
# Requirement: 85-REQ-7.E1
# ---------------------------------------------------------------------------


class TestPlatformNoneNoSpecs:
    """Verify no-platform + no-specs = idle loop."""

    def test_all_disabled(self) -> None:
        """All streams disabled with platform none and --no-specs."""
        from agent_fox.nightshift.streams import build_streams

        config = _make_config(platform_type="none")
        streams = build_streams(config, no_specs=True)
        enabled = [s for s in streams if s.enabled]
        assert len(enabled) == 0


# ---------------------------------------------------------------------------
# TS-85-28: Spec executor discovers new specs
# Requirement: 85-REQ-10.1
# ---------------------------------------------------------------------------


class TestSpecExecutorDiscovery:
    """Verify spec executor calls discover_new_specs_gated."""

    async def test_discover_called(self) -> None:
        """discover_new_specs_gated called once during run_once."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecExecutorStream

        budget = SharedBudget(max_cost=None)
        mock_discover = AsyncMock(return_value=[])
        executor = SpecExecutorStream(
            config=_make_config(),
            budget=budget,
            discover_fn=mock_discover,
        )
        await executor.run_once()
        assert mock_discover.call_count == 1


# ---------------------------------------------------------------------------
# TS-85-30: Spec executor no-op when no specs found
# Requirement: 85-REQ-10.3
# ---------------------------------------------------------------------------


class TestSpecExecutorNoOp:
    """Verify spec executor returns without side effects when no specs found."""

    async def test_no_cost_when_no_specs(self) -> None:
        """Budget unchanged when no new specs discovered."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecExecutorStream

        budget = SharedBudget(max_cost=None)
        mock_discover = AsyncMock(return_value=[])
        executor = SpecExecutorStream(
            config=_make_config(),
            budget=budget,
            discover_fn=mock_discover,
        )
        await executor.run_once()
        assert budget.total_cost == 0.0


# ---------------------------------------------------------------------------
# TS-85-E16: Spec executor handles discovery error
# Requirement: 85-REQ-10.E1
# ---------------------------------------------------------------------------


class TestSpecExecutorDiscoveryError:
    """Verify spec executor logs error and returns on discovery failure."""

    async def test_discovery_error_no_raise(self) -> None:
        """run_once does not raise when discover_new_specs_gated fails."""
        from agent_fox.nightshift.daemon import SharedBudget
        from agent_fox.nightshift.streams import SpecExecutorStream

        budget = SharedBudget(max_cost=None)
        mock_discover = AsyncMock(side_effect=OSError("disk error"))
        executor = SpecExecutorStream(
            config=_make_config(),
            budget=budget,
            discover_fn=mock_discover,
        )
        await executor.run_once()  # should not raise
        assert budget.total_cost == 0.0
