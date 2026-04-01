"""Unit tests for timeout-aware escalation configuration.

Test Spec: TS-75-16, TS-75-17, TS-75-18, TS-75-19, TS-75-20
Requirements: 75-REQ-4.1, 75-REQ-4.2, 75-REQ-4.3, 75-REQ-4.4,
              75-REQ-4.5, 75-REQ-4.6, 75-REQ-4.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-75-16: Config Default Values
# Requirements: 75-REQ-4.1, 75-REQ-4.2, 75-REQ-4.3
# ---------------------------------------------------------------------------


class TestRoutingConfigDefaults:
    """TS-75-16: RoutingConfig has correct default values for timeout fields."""

    def test_max_timeout_retries_default(self) -> None:
        """TS-75-16: max_timeout_retries defaults to 2."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.max_timeout_retries == 2

    def test_timeout_multiplier_default(self) -> None:
        """TS-75-16: timeout_multiplier defaults to 1.5."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.timeout_multiplier == 1.5

    def test_timeout_ceiling_factor_default(self) -> None:
        """TS-75-16: timeout_ceiling_factor defaults to 2.0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.timeout_ceiling_factor == 2.0

    def test_all_timeout_defaults_together(self) -> None:
        """TS-75-16: All three timeout fields have correct defaults."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.max_timeout_retries == 2
        assert config.timeout_multiplier == 1.5
        assert config.timeout_ceiling_factor == 2.0


# ---------------------------------------------------------------------------
# TS-75-17: Config Validation - Negative Retries
# Requirement: 75-REQ-4.4
# ---------------------------------------------------------------------------


class TestMaxTimeoutRetriesValidation:
    """TS-75-17: max_timeout_retries must be >= 0."""

    def test_negative_max_timeout_retries_clamped(self) -> None:
        """TS-75-17: max_timeout_retries=-1 is clamped or rejected to >= 0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(max_timeout_retries=-1)
        assert config.max_timeout_retries >= 0

    def test_zero_max_timeout_retries_allowed(self) -> None:
        """TS-75-17: max_timeout_retries=0 is a valid value."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(max_timeout_retries=0)
        assert config.max_timeout_retries == 0

    def test_positive_max_timeout_retries_preserved(self) -> None:
        """TS-75-17: max_timeout_retries=5 is preserved as-is."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(max_timeout_retries=5)
        assert config.max_timeout_retries == 5


# ---------------------------------------------------------------------------
# TS-75-18: Config Validation - Multiplier Below 1.0
# Requirement: 75-REQ-4.5
# ---------------------------------------------------------------------------


class TestTimeoutMultiplierValidation:
    """TS-75-18: timeout_multiplier must be >= 1.0."""

    def test_multiplier_below_one_clamped(self) -> None:
        """TS-75-18: timeout_multiplier=0.5 is clamped or rejected to >= 1.0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_multiplier=0.5)
        assert config.timeout_multiplier >= 1.0

    def test_multiplier_exactly_one_allowed(self) -> None:
        """TS-75-18: timeout_multiplier=1.0 is valid."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_multiplier=1.0)
        assert config.timeout_multiplier == 1.0

    def test_multiplier_above_one_preserved(self) -> None:
        """TS-75-18: timeout_multiplier=2.0 is preserved."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_multiplier=2.0)
        assert config.timeout_multiplier == 2.0

    def test_zero_multiplier_clamped(self) -> None:
        """TS-75-18: timeout_multiplier=0.0 is clamped to >= 1.0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_multiplier=0.0)
        assert config.timeout_multiplier >= 1.0


# ---------------------------------------------------------------------------
# TS-75-19: Config Validation - Ceiling Below 1.0
# Requirement: 75-REQ-4.6
# ---------------------------------------------------------------------------


class TestTimeoutCeilingFactorValidation:
    """TS-75-19: timeout_ceiling_factor must be >= 1.0."""

    def test_ceiling_below_one_clamped(self) -> None:
        """TS-75-19: timeout_ceiling_factor=0.8 is clamped or rejected to >= 1.0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_ceiling_factor=0.8)
        assert config.timeout_ceiling_factor >= 1.0

    def test_ceiling_exactly_one_allowed(self) -> None:
        """TS-75-19: timeout_ceiling_factor=1.0 is valid."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_ceiling_factor=1.0)
        assert config.timeout_ceiling_factor == 1.0

    def test_ceiling_above_one_preserved(self) -> None:
        """TS-75-19: timeout_ceiling_factor=3.0 is preserved."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_ceiling_factor=3.0)
        assert config.timeout_ceiling_factor == 3.0

    def test_zero_ceiling_clamped(self) -> None:
        """TS-75-19: timeout_ceiling_factor=0.0 is clamped to >= 1.0."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_ceiling_factor=0.0)
        assert config.timeout_ceiling_factor >= 1.0


# ---------------------------------------------------------------------------
# TS-75-20: Multiplier 1.0 No Extension
# Requirement: 75-REQ-4.E1
# ---------------------------------------------------------------------------


class TestMultiplierOneNoExtension:
    """TS-75-20: timeout_multiplier=1.0 means timeout params are not extended."""

    def test_multiplier_one_stored_correctly(self) -> None:
        """TS-75-20: timeout_multiplier=1.0 is stored without modification."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(timeout_multiplier=1.0)
        # When multiplier is 1.0, timeout extension is identity: ceil(x * 1.0) == x
        assert config.timeout_multiplier == 1.0

    def test_all_timeout_fields_configurable(self) -> None:
        """TS-75-20: All timeout fields can be configured together."""
        from agent_fox.core.config import RoutingConfig

        config = RoutingConfig(
            max_timeout_retries=3,
            timeout_multiplier=1.0,
            timeout_ceiling_factor=1.5,
        )
        assert config.max_timeout_retries == 3
        assert config.timeout_multiplier == 1.0
        assert config.timeout_ceiling_factor == 1.5
