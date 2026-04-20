"""Unit tests for NightShiftConfig daemon framework extensions.

Test Spec: TS-85-22, TS-85-26, TS-85-E13, TS-85-E14, TS-85-E15
Requirements: 85-REQ-8.1, 85-REQ-8.E2, 85-REQ-9.1, 85-REQ-9.E1, 85-REQ-9.E2
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-85-26: NightShiftConfig new fields defaults
# Requirement: 85-REQ-9.1
# ---------------------------------------------------------------------------


class TestNightShiftConfigNewDefaults:
    """Verify new config fields have correct defaults."""

    def test_spec_interval_default(self) -> None:
        """spec_interval defaults to 300."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.spec_interval == 300

    def test_enabled_streams_default(self) -> None:
        """enabled_streams defaults to all three streams."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.enabled_streams == ["specs", "fixes", "hunts"]

    def test_merge_strategy_default(self) -> None:
        """merge_strategy defaults to 'direct'."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.merge_strategy == "direct"


# ---------------------------------------------------------------------------
# TS-85-22: Direct merge strategy (default)
# Requirement: 85-REQ-8.1
# ---------------------------------------------------------------------------


class TestDirectMergeStrategy:
    """Verify merge_strategy='direct' is the default."""

    def test_default_is_direct(self) -> None:
        """Default NightShiftConfig has merge_strategy='direct'."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig()
        assert config.merge_strategy == "direct"


# ---------------------------------------------------------------------------
# TS-85-E13: Unknown merge_strategy falls back to direct
# Requirement: 85-REQ-8.E2
# ---------------------------------------------------------------------------


class TestUnknownMergeStrategy:
    """Verify unknown merge_strategy defaults to 'direct'."""

    def test_unknown_strategy_fallback(self) -> None:
        """resolve_merge_strategy returns 'direct' for unknown values."""
        from agent_fox.nightshift.daemon import resolve_merge_strategy

        effective = resolve_merge_strategy("unknown")
        assert effective == "direct"


# ---------------------------------------------------------------------------
# TS-85-E14: spec_interval clamped to minimum
# Requirement: 85-REQ-9.E1
# ---------------------------------------------------------------------------


class TestSpecIntervalClamping:
    """Verify spec_interval below 10 is clamped to 10."""

    def test_spec_interval_clamped(self) -> None:
        """spec_interval of 5 is clamped to 10."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig(spec_interval=5)
        assert config.spec_interval == 10

    def test_spec_interval_at_boundary(self) -> None:
        """spec_interval of 10 is not changed."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig(spec_interval=10)
        assert config.spec_interval == 10


# ---------------------------------------------------------------------------
# TS-85-E15: Empty enabled_streams = all enabled
# Requirement: 85-REQ-9.E2
# ---------------------------------------------------------------------------


class TestEmptyEnabledStreams:
    """Verify empty enabled_streams list defaults to all streams."""

    def test_empty_list_means_all(self) -> None:
        """Empty enabled_streams treated as all enabled."""
        from agent_fox.core.config import NightShiftConfig

        config = NightShiftConfig(enabled_streams=[])
        assert config.enabled_streams == ["specs", "fixes", "hunts"]
