"""Configuration tests for SDK feature adoption.

Test Spec: TS-56-1, TS-56-3, TS-56-5, TS-56-7, TS-56-8, TS-56-10,
           TS-56-12, TS-56-14, TS-56-E1, TS-56-E3, TS-56-E5, TS-56-E6
Requirements: 56-REQ-1.1, 56-REQ-1.3, 56-REQ-2.1, 56-REQ-2.3,
              56-REQ-3.1, 56-REQ-3.3, 56-REQ-4.1, 56-REQ-4.3,
              56-REQ-1.E1, 56-REQ-2.E2, 56-REQ-4.E1, 56-REQ-4.E2

AC-1, AC-2, AC-3: fallback_model migrated to [routing]; models.coding deprecated.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_fox.core.config import AgentFoxConfig, load_config

# ---------------------------------------------------------------------------
# TS-56-1: max_turns Config Parsing
# Requirement: 56-REQ-1.1
# ---------------------------------------------------------------------------


class TestMaxTurnsParsing:
    """Verify max_turns per archetype is parsed from config."""

    def test_max_turns_parsed_from_toml(self, tmp_path: Path) -> None:
        """TS-56-1: max_turns per archetype is parsed from config TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[archetypes.max_turns]\ncoder = 150\nreviewer = 30\n")
        config = load_config(path=config_file)
        assert config.archetypes.max_turns["coder"] == 150
        assert config.archetypes.max_turns["reviewer"] == 30

    def test_max_turns_empty_when_not_configured(self) -> None:
        """Default config has empty max_turns dict."""
        config = AgentFoxConfig()
        assert config.archetypes.max_turns == {}


# ---------------------------------------------------------------------------
# TS-56-3: max_turns Defaults Per Archetype
# Requirement: 56-REQ-1.3
# ---------------------------------------------------------------------------


class TestMaxTurnsDefaults:
    """Verify default max_turns values per archetype from registry."""

    def test_default_max_turns_per_archetype(self) -> None:
        """TS-56-3: Each archetype has the correct default_max_turns."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        expected = {
            "coder": 300,
            "reviewer": 80,
            "verifier": 120,
        }
        for archetype, turns in expected.items():
            entry = ARCHETYPE_REGISTRY[archetype]
            assert entry.default_max_turns == turns, (
                f"{archetype}: expected default_max_turns={turns}, got {entry.default_max_turns}"
            )


# ---------------------------------------------------------------------------
# TS-56-5: max_budget_usd Config Parsing
# Requirement: 56-REQ-2.1
# ---------------------------------------------------------------------------


class TestBudgetParsing:
    """Verify max_budget_usd is parsed from config."""

    def test_budget_parsed_from_toml(self, tmp_path: Path) -> None:
        """TS-56-5: max_budget_usd is parsed from config TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nmax_budget_usd = 5.0\n")
        config = load_config(path=config_file)
        assert config.orchestrator.max_budget_usd == 5.0


# ---------------------------------------------------------------------------
# TS-56-7: max_budget_usd Default
# Requirement: 56-REQ-2.3
# ---------------------------------------------------------------------------


class TestBudgetDefault:
    """Verify default max_budget_usd is 8.0."""

    def test_default_budget(self) -> None:
        """TS-56-7: Default max_budget_usd is 8.0."""
        config = AgentFoxConfig()
        assert config.orchestrator.max_budget_usd == 8.0


# ---------------------------------------------------------------------------
# TS-56-8: fallback_model Config Parsing
# Requirement: 56-REQ-3.1
# ---------------------------------------------------------------------------


class TestFallbackModelParsing:
    """Verify fallback_model is parsed from [routing] config (AC-1, AC-2)."""

    def test_fallback_model_parsed_from_routing_toml(self, tmp_path: Path) -> None:
        """AC-1/TS-56-8: fallback_model is parsed from [routing] section."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[routing]\nfallback_model = "claude-haiku-4-5"\n')
        config = load_config(path=config_file)
        assert config.routing.fallback_model == "claude-haiku-4-5"

    def test_fallback_model_legacy_models_section_still_parsed(self, tmp_path: Path) -> None:
        """Backward compat: [models] fallback_model still parses (but is not used by resolver)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[models]\nfallback_model = "claude-haiku-4-5"\n')
        config = load_config(path=config_file)
        # models.fallback_model is still stored but routing.fallback_model is the canonical source
        assert config.models.fallback_model == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# TS-56-10: fallback_model Default
# Requirement: 56-REQ-3.3
# ---------------------------------------------------------------------------


class TestFallbackModelDefault:
    """Verify default fallback_model is 'claude-sonnet-4-6' in [routing] (AC-1)."""

    def test_default_fallback_model_in_routing(self) -> None:
        """AC-1/TS-56-10: Default routing.fallback_model is 'claude-sonnet-4-6'."""
        config = AgentFoxConfig()
        assert config.routing.fallback_model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# AC-2: resolve_fallback_model reads from routing.fallback_model
# ---------------------------------------------------------------------------


class TestResolveFallbackModelReadsRouting:
    """Verify resolve_fallback_model uses config.routing.fallback_model (AC-2)."""

    def test_resolve_fallback_model_from_routing(self) -> None:
        """AC-2: resolve_fallback_model returns routing.fallback_model value."""
        from agent_fox.engine.sdk_params import resolve_fallback_model

        config = AgentFoxConfig(routing={"fallback_model": "claude-haiku-4-5"})
        assert resolve_fallback_model(config) == "claude-haiku-4-5"

    def test_resolve_fallback_model_default(self) -> None:
        """AC-2: resolve_fallback_model returns routing default when not overridden."""
        from agent_fox.engine.sdk_params import resolve_fallback_model

        config = AgentFoxConfig()
        assert resolve_fallback_model(config) == "claude-sonnet-4-6"

    def test_resolve_fallback_model_not_affected_by_models_section(self) -> None:
        """AC-2: Setting only models.fallback_model does not affect resolve_fallback_model."""
        from agent_fox.engine.sdk_params import resolve_fallback_model

        # routing.fallback_model is default; models.fallback_model is legacy
        config = AgentFoxConfig(
            routing={"fallback_model": "claude-sonnet-4-6"},
            models={"fallback_model": "claude-haiku-4-5"},
        )
        # The resolver reads from routing, not models
        assert resolve_fallback_model(config) == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# AC-3: models.coding deprecation warning
# ---------------------------------------------------------------------------


class TestModelsCodingDeprecationWarning:
    """Verify deprecation warning for [models] coding field (AC-3)."""

    def test_deprecation_warning_emitted_when_coding_non_default(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC-3: Loading config with models.coding != 'ADVANCED' emits a deprecation warning."""
        import logging

        config_file = tmp_path / "config.toml"
        config_file.write_text('[models]\ncoding = "STANDARD"\n')
        with caplog.at_level(logging.WARNING, logger="agent_fox.core.config"):
            load_config(path=config_file)
        warning_texts = " ".join(caplog.messages)
        assert "deprecated" in warning_texts.lower()
        assert "archetypes.overrides.coder" in warning_texts

    def test_no_deprecation_warning_when_coding_is_default(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC-3: No deprecation warning when models.coding is the default 'ADVANCED'."""
        import logging

        config_file = tmp_path / "config.toml"
        config_file.write_text('[models]\ncoding = "ADVANCED"\n')
        with caplog.at_level(logging.WARNING, logger="agent_fox.core.config"):
            load_config(path=config_file)
        # No deprecation warning for the default value
        assert not any("archetypes.overrides.coder" in m for m in caplog.messages)

    def test_archetypes_overrides_coder_takes_precedence_over_models_coding(
        self, tmp_path: Path
    ) -> None:
        """AC-3: archetypes.overrides.coder.model_tier takes precedence over models.coding."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[models]\ncoding = "STANDARD"\n'
            '[archetypes.overrides.coder]\nmodel_tier = "SIMPLE"\n'
        )
        config = load_config(path=config_file)
        assert resolve_model_tier(config, "coder") == "SIMPLE"


# ---------------------------------------------------------------------------
# TS-56-12: Thinking Config Parsing
# Requirement: 56-REQ-4.1
# ---------------------------------------------------------------------------


class TestThinkingParsing:
    """Verify thinking config per archetype is parsed."""

    def test_thinking_parsed_from_toml(self, tmp_path: Path) -> None:
        """TS-56-12: Thinking config per archetype is parsed from TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.thinking.coder]\nmode = "enabled"\nbudget_tokens = 20000\n')
        config = load_config(path=config_file)
        assert config.archetypes.thinking["coder"].mode == "enabled"
        assert config.archetypes.thinking["coder"].budget_tokens == 20000

    def test_thinking_empty_when_not_configured(self) -> None:
        """Default config has empty thinking dict."""
        config = AgentFoxConfig()
        assert config.archetypes.thinking == {}


# ---------------------------------------------------------------------------
# TS-56-14: Thinking Defaults
# Requirement: 56-REQ-4.3
# ---------------------------------------------------------------------------


class TestThinkingDefaults:
    """Verify coder defaults to adaptive thinking, others disabled."""

    def test_coder_default_thinking_adaptive(self) -> None:
        """TS-56-14: Coder defaults to adaptive thinking with 64000 budget."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        assert coder.default_thinking_mode == "adaptive"
        assert coder.default_thinking_budget == 64000

    def test_other_archetypes_default_thinking_disabled(self) -> None:
        """TS-56-14: Non-coder archetypes default to disabled thinking."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        for name in (
            "reviewer",
            "verifier",
        ):
            entry = ARCHETYPE_REGISTRY[name]
            assert entry.default_thinking_mode == "disabled", (
                f"{name}: expected default_thinking_mode='disabled', got {entry.default_thinking_mode}"
            )


# ---------------------------------------------------------------------------
# TS-56-E1: Negative max_turns Rejected
# Requirement: 56-REQ-1.E1
# ---------------------------------------------------------------------------


class TestNegativeMaxTurnsRejected:
    """Verify negative max_turns raises validation error."""

    def test_negative_max_turns_raises(self, tmp_path: Path) -> None:
        """TS-56-E1: Negative max_turns raises ValidationError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[archetypes.max_turns]\ncoder = -1\n")
        with pytest.raises((ValidationError, ValueError, Exception)):
            load_config(path=config_file)

    def test_negative_max_turns_direct(self) -> None:
        """TS-56-E1: Negative max_turns via direct construction raises."""
        with pytest.raises((ValidationError, ValueError, Exception)):
            AgentFoxConfig(
                archetypes={"max_turns": {"coder": -1}},  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# TS-56-E3: Negative Budget Rejected
# Requirement: 56-REQ-2.E2
# ---------------------------------------------------------------------------


class TestNegativeBudgetRejected:
    """Verify negative max_budget_usd raises validation error."""

    def test_negative_budget_raises(self, tmp_path: Path) -> None:
        """TS-56-E3: Negative max_budget_usd raises ValidationError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[orchestrator]\nmax_budget_usd = -1.0\n")
        with pytest.raises((ValidationError, ValueError, Exception)):
            load_config(path=config_file)


# ---------------------------------------------------------------------------
# TS-56-E5: Invalid Thinking Mode Rejected
# Requirement: 56-REQ-4.E1
# ---------------------------------------------------------------------------


class TestInvalidThinkingModeRejected:
    """Verify unrecognised thinking mode raises validation error."""

    def test_invalid_thinking_mode_raises(self, tmp_path: Path) -> None:
        """TS-56-E5: Invalid thinking mode raises ValidationError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.thinking.coder]\nmode = "turbo"\nbudget_tokens = 10000\n')
        with pytest.raises((ValidationError, ValueError, Exception)):
            load_config(path=config_file)


# ---------------------------------------------------------------------------
# TS-56-E6: Zero Budget Tokens With Enabled Mode Rejected
# Requirement: 56-REQ-4.E2
# ---------------------------------------------------------------------------


class TestZeroBudgetTokensEnabledRejected:
    """Verify budget_tokens=0 with mode=enabled raises error."""

    def test_zero_budget_tokens_enabled_raises(self, tmp_path: Path) -> None:
        """TS-56-E6: budget_tokens=0 with mode=enabled raises error."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.thinking.coder]\nmode = "enabled"\nbudget_tokens = 0\n')
        with pytest.raises((ValidationError, ValueError, Exception)):
            load_config(path=config_file)
