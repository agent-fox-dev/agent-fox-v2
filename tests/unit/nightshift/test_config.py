"""Unit tests for NightShiftConfig and NightShiftCategoryConfig.

Test Spec: TS-61-26, TS-61-27, TS-61-E12
Requirements: 61-REQ-9.1, 61-REQ-9.2, 61-REQ-9.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-61-26: NightShiftConfig defaults
# Requirement: 61-REQ-9.1
# ---------------------------------------------------------------------------


class TestNightShiftConfigDefaults:
    """Verify default config values."""

    def test_default_issue_check_interval(self) -> None:
        """issue_check_interval defaults to 900."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig()
        assert cfg.issue_check_interval == 900

    def test_default_hunt_scan_interval(self) -> None:
        """hunt_scan_interval defaults to 14400."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig()
        assert cfg.hunt_scan_interval == 14400


# ---------------------------------------------------------------------------
# TS-61-27: Category enable/disable config
# Requirement: 61-REQ-9.2
# ---------------------------------------------------------------------------


class TestCategoryConfig:
    """Verify category toggle configuration."""

    def test_all_categories_enabled_by_default(self) -> None:
        """All seven categories are enabled by default."""
        from agent_fox.nightshift.config import NightShiftCategoryConfig

        cfg = NightShiftCategoryConfig()
        assert cfg.dependency_freshness is True
        assert cfg.todo_fixme is True
        assert cfg.test_coverage is True
        assert cfg.deprecated_api is True
        assert cfg.linter_debt is True
        assert cfg.dead_code is True
        assert cfg.documentation_drift is True

    def test_disable_single_category(self) -> None:
        """Disabling dead_code leaves all others enabled."""
        from agent_fox.nightshift.config import (
            NightShiftCategoryConfig,
            NightShiftConfig,
        )

        cfg = NightShiftConfig(
            categories=NightShiftCategoryConfig(dead_code=False)
        )
        assert cfg.categories.dead_code is False
        assert cfg.categories.linter_debt is True
        assert cfg.categories.todo_fixme is True
        assert cfg.categories.dependency_freshness is True
        assert cfg.categories.test_coverage is True
        assert cfg.categories.deprecated_api is True
        assert cfg.categories.documentation_drift is True


# ---------------------------------------------------------------------------
# TS-61-E12: Interval clamped to minimum
# Requirement: 61-REQ-9.E1
# ---------------------------------------------------------------------------


class TestIntervalClamping:
    """Verify that intervals < 60s are clamped to 60."""

    def test_issue_check_interval_clamped(self) -> None:
        """issue_check_interval of 10 is clamped to 60."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig(issue_check_interval=10)
        assert cfg.issue_check_interval == 60

    def test_hunt_scan_interval_clamped(self) -> None:
        """hunt_scan_interval of 30 is clamped to 60."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig(hunt_scan_interval=30)
        assert cfg.hunt_scan_interval == 60

    def test_interval_at_boundary_not_clamped(self) -> None:
        """An interval of exactly 60 is not changed."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig(issue_check_interval=60)
        assert cfg.issue_check_interval == 60

    def test_interval_above_minimum_not_clamped(self) -> None:
        """An interval above 60 is not changed."""
        from agent_fox.nightshift.config import NightShiftConfig

        cfg = NightShiftConfig(issue_check_interval=120)
        assert cfg.issue_check_interval == 120
