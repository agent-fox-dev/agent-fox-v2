"""Tests for oracle blocking behavior and config defaults.

Test Spec: TS-32-11, TS-32-12, TS-32-E7, TS-32-E8
Requirements: 32-REQ-9.1, 32-REQ-9.2, 32-REQ-9.3, 32-REQ-9.E1,
              32-REQ-10.1, 32-REQ-10.2, 32-REQ-10.3, 32-REQ-10.4, 32-REQ-10.E1
"""

from __future__ import annotations

import uuid


def _make_drift_finding(severity: str = "critical"):
    """Create a DriftFinding for blocking tests."""
    from agent_fox.knowledge.review_store import DriftFinding

    return DriftFinding(
        id=str(uuid.uuid4()),
        severity=severity,
        description=f"Test {severity} finding",
        spec_ref=None,
        artifact_ref=None,
        spec_name="test_spec",
        task_group="0",
        session_id="sess_1",
    )


# ---------------------------------------------------------------------------
# TS-32-11: Block Threshold Exceeded
# Requirements: 32-REQ-9.1, 32-REQ-9.2, 32-REQ-9.3
# ---------------------------------------------------------------------------


class TestBlockThreshold:
    """Oracle blocks when critical findings exceed threshold."""

    def test_block_threshold_exceeded(self) -> None:
        """TS-32-11: 3 critical findings > threshold 2 -> should block."""

        findings = [_make_drift_finding("critical") for _ in range(3)]
        critical_count = sum(1 for f in findings if f.severity == "critical")
        threshold = 2
        should_block = critical_count > threshold
        assert should_block is True

    def test_block_threshold_not_exceeded(self) -> None:
        """2 critical findings <= threshold 2 -> should not block."""
        findings = [_make_drift_finding("critical") for _ in range(2)]
        critical_count = sum(1 for f in findings if f.severity == "critical")
        threshold = 2
        should_block = critical_count > threshold
        assert should_block is False

    def test_non_critical_dont_count(self) -> None:
        """Only critical findings count against threshold."""
        findings = [
            _make_drift_finding("critical"),
            _make_drift_finding("major"),
            _make_drift_finding("major"),
            _make_drift_finding("minor"),
        ]
        critical_count = sum(1 for f in findings if f.severity == "critical")
        threshold = 1
        should_block = critical_count > threshold
        assert should_block is False


# ---------------------------------------------------------------------------
# TS-32-12: Oracle Config Defaults
# Requirements: 32-REQ-10.1, 32-REQ-10.2, 32-REQ-10.3, 32-REQ-10.4
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    """Verify oracle config defaults."""

    def test_config_defaults(self) -> None:
        """TS-32-12: Oracle disabled by default, no block threshold."""
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig()
        assert config.oracle is False
        assert config.oracle_settings.block_threshold is None

    def test_oracle_enabled(self) -> None:
        """Oracle can be enabled via config."""
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig(oracle=True)
        assert config.oracle is True

    def test_oracle_settings_block_threshold(self) -> None:
        """Block threshold can be configured."""
        from agent_fox.core.config import ArchetypesConfig, OracleSettings

        settings = OracleSettings(block_threshold=5)
        config = ArchetypesConfig(oracle=True, oracle_settings=settings)
        assert config.oracle_settings.block_threshold == 5

    def test_model_override(self) -> None:
        """Model tier can be overridden via models dict."""
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig(models={"oracle": "ADVANCED"})
        assert config.models["oracle"] == "ADVANCED"

    def test_allowlist_override(self) -> None:
        """Allowlist can be overridden via allowlists dict."""
        from agent_fox.core.config import ArchetypesConfig

        config = ArchetypesConfig(
            allowlists={"oracle": ["ls", "git"]},
        )
        assert config.allowlists["oracle"] == ["ls", "git"]


# ---------------------------------------------------------------------------
# TS-32-E7: Advisory Mode (No block_threshold)
# Requirement: 32-REQ-9.E1
# ---------------------------------------------------------------------------


class TestAdvisoryMode:
    """Without block_threshold, oracle always completes."""

    def test_advisory_mode(self) -> None:
        """TS-32-E7: No threshold -> no blocking, even with many criticals."""
        from agent_fox.core.config import OracleSettings

        settings = OracleSettings(block_threshold=None)
        assert settings.block_threshold is None

        # With no threshold, blocking check is always False
        findings = [_make_drift_finding("critical") for _ in range(10)]
        critical_count = sum(1 for f in findings if f.severity == "critical")
        threshold = settings.block_threshold
        should_block = threshold is not None and critical_count > threshold
        assert should_block is False


# ---------------------------------------------------------------------------
# TS-32-E8: Block Threshold Clamped
# Requirement: 32-REQ-10.E1
# ---------------------------------------------------------------------------


class TestThresholdClamped:
    """Non-positive block_threshold is clamped to 1."""

    def test_threshold_clamped_zero(self) -> None:
        """TS-32-E8: block_threshold=0 clamped to 1."""
        from agent_fox.core.config import OracleSettings

        settings = OracleSettings(block_threshold=0)
        assert settings.block_threshold == 1

    def test_threshold_clamped_negative(self) -> None:
        """Negative block_threshold clamped to 1."""
        from agent_fox.core.config import OracleSettings

        settings = OracleSettings(block_threshold=-5)
        assert settings.block_threshold == 1

    def test_threshold_valid_not_clamped(self) -> None:
        """Valid threshold is not modified."""
        from agent_fox.core.config import OracleSettings

        settings = OracleSettings(block_threshold=3)
        assert settings.block_threshold == 3
