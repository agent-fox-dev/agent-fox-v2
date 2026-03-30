"""Configuration tests for SDK feature adoption.

Test Spec: TS-56-1, TS-56-3, TS-56-5, TS-56-7, TS-56-8, TS-56-10,
           TS-56-12, TS-56-14, TS-56-E1, TS-56-E3, TS-56-E5, TS-56-E6
Requirements: 56-REQ-1.1, 56-REQ-1.3, 56-REQ-2.1, 56-REQ-2.3,
              56-REQ-3.1, 56-REQ-3.3, 56-REQ-4.1, 56-REQ-4.3,
              56-REQ-1.E1, 56-REQ-2.E2, 56-REQ-4.E1, 56-REQ-4.E2
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
        config_file.write_text("[archetypes.max_turns]\ncoder = 150\noracle = 30\n")
        config = load_config(path=config_file)
        assert config.archetypes.max_turns["coder"] == 150
        assert config.archetypes.max_turns["oracle"] == 30

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
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        expected = {
            "coder": 200,
            "oracle": 50,
            "skeptic": 50,
            "verifier": 75,
            "auditor": 50,
            "librarian": 100,
            "cartographer": 100,
            "coordinator": 30,
        }
        for archetype, turns in expected.items():
            entry = ARCHETYPE_REGISTRY[archetype]
            assert entry.default_max_turns == turns, (
                f"{archetype}: expected default_max_turns={turns}, "
                f"got {entry.default_max_turns}"
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
    """Verify default max_budget_usd is 2.0."""

    def test_default_budget(self) -> None:
        """TS-56-7: Default max_budget_usd is 2.0."""
        config = AgentFoxConfig()
        assert config.orchestrator.max_budget_usd == 2.0


# ---------------------------------------------------------------------------
# TS-56-8: fallback_model Config Parsing
# Requirement: 56-REQ-3.1
# ---------------------------------------------------------------------------


class TestFallbackModelParsing:
    """Verify fallback_model is parsed from config."""

    def test_fallback_model_parsed_from_toml(self, tmp_path: Path) -> None:
        """TS-56-8: fallback_model is parsed from config TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[models]\nfallback_model = "claude-haiku-4-5"\n')
        config = load_config(path=config_file)
        assert config.models.fallback_model == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# TS-56-10: fallback_model Default
# Requirement: 56-REQ-3.3
# ---------------------------------------------------------------------------


class TestFallbackModelDefault:
    """Verify default fallback_model is 'claude-sonnet-4-6'."""

    def test_default_fallback_model(self) -> None:
        """TS-56-10: Default fallback_model is 'claude-sonnet-4-6'."""
        config = AgentFoxConfig()
        assert config.models.fallback_model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# TS-56-12: Thinking Config Parsing
# Requirement: 56-REQ-4.1
# ---------------------------------------------------------------------------


class TestThinkingParsing:
    """Verify thinking config per archetype is parsed."""

    def test_thinking_parsed_from_toml(self, tmp_path: Path) -> None:
        """TS-56-12: Thinking config per archetype is parsed from TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[archetypes.thinking.coder]\nmode = "enabled"\nbudget_tokens = 20000\n'
        )
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
        """TS-56-14: Coder defaults to adaptive thinking with 10000 budget."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        assert coder.default_thinking_mode == "adaptive"
        assert coder.default_thinking_budget == 10000

    def test_other_archetypes_default_thinking_disabled(self) -> None:
        """TS-56-14: Non-coder archetypes default to disabled thinking."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        for name in (
            "oracle",
            "skeptic",
            "verifier",
            "auditor",
            "librarian",
            "cartographer",
            "coordinator",
        ):
            entry = ARCHETYPE_REGISTRY[name]
            assert entry.default_thinking_mode == "disabled", (
                f"{name}: expected default_thinking_mode='disabled', "
                f"got {entry.default_thinking_mode}"
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
        config_file.write_text(
            '[archetypes.thinking.coder]\nmode = "turbo"\nbudget_tokens = 10000\n'
        )
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
        config_file.write_text(
            '[archetypes.thinking.coder]\nmode = "enabled"\nbudget_tokens = 0\n'
        )
        with pytest.raises((ValidationError, ValueError, Exception)):
            load_config(path=config_file)
