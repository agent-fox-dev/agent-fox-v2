"""Tests for routing configuration.

Test Spec: TS-30-20, TS-30-21, TS-30-22, TS-30-E9, TS-30-P9
Requirements: 30-REQ-5.1, 30-REQ-5.2, 30-REQ-5.3, 30-REQ-5.E1, 30-REQ-5.E2
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import RoutingConfig, load_config
from agent_fox.core.errors import ConfigError
from agent_fox.core.models import ModelTier


class TestRoutingDefaults:
    """TS-30-20: Routing config defaults."""

    def test_routing_defaults(self, minimal_config_toml: Path) -> None:
        """TS-30-20: Verify default config values when [routing] absent.

        Requirement: 30-REQ-5.1, 30-REQ-5.E1
        """
        config = load_config(minimal_config_toml)
        assert config.routing.retries_before_escalation == 1

    def test_routing_defaults_no_file(self) -> None:
        """Verify defaults when no config file exists.

        Requirement: 30-REQ-5.E1
        """
        config = load_config(None)
        assert config.routing.retries_before_escalation == 1


class TestRoutingClamping:
    """TS-30-21: Routing config clamping."""

    def test_routing_clamping(self, extreme_routing_config_toml: Path) -> None:
        """TS-30-21: Verify out-of-range values are clamped.

        Requirement: 30-REQ-5.2
        """
        config = load_config(extreme_routing_config_toml)
        assert config.routing.retries_before_escalation == 3  # clamped from 10


class TestArchetypeCeiling:
    """TS-30-22: Archetype model override acts as tier ceiling."""

    def test_archetype_ceiling(self, archetype_ceiling_config_toml: Path) -> None:
        """TS-30-22: Config override sets tier ceiling.

        Requirement: 30-REQ-5.3
        """
        config = load_config(archetype_ceiling_config_toml)
        ceiling_str = config.archetypes.models.get("coder")
        assert ceiling_str == "STANDARD"

        ceiling = ModelTier(ceiling_str)
        assert ceiling == ModelTier.STANDARD

        # Verify the escalation ladder respects this ceiling
        from agent_fox.routing.escalation import EscalationLadder

        ladder = EscalationLadder(ModelTier.SIMPLE, ceiling, retries_before_escalation=1)
        ladder.record_failure()
        ladder.record_failure()  # escalate to STANDARD
        assert ladder.current_tier == ModelTier.STANDARD
        ladder.record_failure()
        ladder.record_failure()  # exhausted at STANDARD
        assert ladder.is_exhausted is True


class TestInvalidRoutingType:
    """TS-30-E9: Invalid routing config type raises ConfigError."""

    def test_invalid_routing_type(self, bad_type_routing_config_toml: Path) -> None:
        """TS-30-E9: String where int expected raises ConfigError.

        Requirement: 30-REQ-5.E2
        """
        with pytest.raises(ConfigError):
            load_config(bad_type_routing_config_toml)


class TestP9ConfigClamping:
    """TS-30-P9: Configuration clamping property."""

    @pytest.mark.property
    @given(retries=st.integers(min_value=-10, max_value=100))
    @settings(max_examples=50)
    def test_p9_config_clamping(self, retries: int) -> None:
        """TS-30-P9: Routing config retries clamped to valid range.

        Requirement: 30-REQ-5.1, 30-REQ-5.2
        """
        config = RoutingConfig(retries_before_escalation=retries)
        assert 0 <= config.retries_before_escalation <= 3
