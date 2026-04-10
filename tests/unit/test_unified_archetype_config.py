"""Unit tests for unified per-archetype configuration (issue #207).

Validates the new [archetypes.overrides.<name>] TOML table syntax and
resolution priority for model_tier, max_turns, thinking, and allowlist.

Requirements: 207-REQ-1, 207-REQ-2, 207-REQ-3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from agent_fox.core.config import (
    AgentFoxConfig,
    ArchetypesConfig,
    PerArchetypeConfig,
    load_config,
)
from agent_fox.engine.sdk_params import resolve_max_turns, resolve_thinking
from agent_fox.knowledge.db import KnowledgeDB

_MOCK_KB = MagicMock(spec=KnowledgeDB)


# ---------------------------------------------------------------------------
# PerArchetypeConfig — model validation
# ---------------------------------------------------------------------------


class TestPerArchetypeConfigParsing:
    """PerArchetypeConfig parses all fields correctly."""

    def test_all_fields_default_to_none(self) -> None:
        """Default PerArchetypeConfig has all fields as None."""
        cfg = PerArchetypeConfig()
        assert cfg.model_tier is None
        assert cfg.max_turns is None
        assert cfg.thinking_mode is None
        assert cfg.thinking_budget is None
        assert cfg.allowlist is None

    def test_model_tier_field(self) -> None:
        cfg = PerArchetypeConfig(model_tier="ADVANCED")
        assert cfg.model_tier == "ADVANCED"

    def test_max_turns_field(self) -> None:
        cfg = PerArchetypeConfig(max_turns=150)
        assert cfg.max_turns == 150

    def test_max_turns_zero_allowed(self) -> None:
        """0 means unlimited — should be accepted."""
        cfg = PerArchetypeConfig(max_turns=0)
        assert cfg.max_turns == 0

    def test_thinking_mode_enabled(self) -> None:
        cfg = PerArchetypeConfig(thinking_mode="enabled", thinking_budget=20000)
        assert cfg.thinking_mode == "enabled"
        assert cfg.thinking_budget == 20000

    def test_thinking_mode_adaptive(self) -> None:
        cfg = PerArchetypeConfig(thinking_mode="adaptive")
        assert cfg.thinking_mode == "adaptive"

    def test_thinking_mode_disabled(self) -> None:
        cfg = PerArchetypeConfig(thinking_mode="disabled")
        assert cfg.thinking_mode == "disabled"

    def test_allowlist_field(self) -> None:
        cfg = PerArchetypeConfig(allowlist=["git", "grep"])
        assert cfg.allowlist == ["git", "grep"]

    def test_negative_max_turns_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PerArchetypeConfig(max_turns=-1)

    def test_negative_thinking_budget_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PerArchetypeConfig(thinking_budget=-1)

    def test_invalid_thinking_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PerArchetypeConfig(thinking_mode="turbo")  # type: ignore[arg-type]

    def test_enabled_thinking_with_zero_budget_rejected(self) -> None:
        """thinking_mode=enabled requires thinking_budget > 0."""
        with pytest.raises((ValidationError, ValueError)):
            PerArchetypeConfig(thinking_mode="enabled", thinking_budget=0)


# ---------------------------------------------------------------------------
# TOML Parsing — [archetypes.overrides.<name>]
# ---------------------------------------------------------------------------


class TestOverridesTomlParsing:
    """[archetypes.overrides.<name>] parses correctly from TOML."""

    def test_single_override_parsed(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.overrides.coder]\nmodel_tier = "ADVANCED"\nmax_turns = 200\n')
        config = load_config(path=config_file)
        assert "coder" in config.archetypes.overrides
        coder = config.archetypes.overrides["coder"]
        assert coder.model_tier == "ADVANCED"
        assert coder.max_turns == 200

    def test_multiple_overrides_parsed(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[archetypes.overrides.coder]\n"
            'model_tier = "ADVANCED"\n'
            "max_turns = 200\n"
            "[archetypes.overrides.skeptic]\n"
            'model_tier = "STANDARD"\n'
            "max_turns = 50\n"
        )
        config = load_config(path=config_file)
        assert config.archetypes.overrides["coder"].model_tier == "ADVANCED"
        assert config.archetypes.overrides["skeptic"].model_tier == "STANDARD"
        assert config.archetypes.overrides["skeptic"].max_turns == 50

    def test_thinking_fields_parsed(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.overrides.coder]\nthinking_mode = "enabled"\nthinking_budget = 32000\n')
        config = load_config(path=config_file)
        coder = config.archetypes.overrides["coder"]
        assert coder.thinking_mode == "enabled"
        assert coder.thinking_budget == 32000

    def test_allowlist_field_parsed(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.overrides.skeptic]\nallowlist = ["ls", "cat", "git"]\n')
        config = load_config(path=config_file)
        assert config.archetypes.overrides["skeptic"].allowlist == ["ls", "cat", "git"]

    def test_overrides_empty_by_default(self) -> None:
        config = AgentFoxConfig()
        assert config.archetypes.overrides == {}

    def test_coexists_with_boolean_enables(self, tmp_path: Path) -> None:
        """overrides and boolean enable flags work together."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[archetypes]\ncoder = true\nskeptic = true\n[archetypes.overrides.coder]\nmodel_tier = "ADVANCED"\n'
        )
        config = load_config(path=config_file)
        assert config.archetypes.coder is True
        assert config.archetypes.overrides["coder"].model_tier == "ADVANCED"


# ---------------------------------------------------------------------------
# resolve_max_turns — priority: overrides > legacy > registry
# ---------------------------------------------------------------------------


class TestResolveMaxTurnsWithOverrides:
    """resolve_max_turns checks overrides first."""

    def test_override_takes_precedence_over_legacy_dict(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                max_turns={"coder": 100},  # legacy
                overrides={"coder": PerArchetypeConfig(max_turns=200)},  # new
            )
        )
        assert resolve_max_turns(config, "coder") == 200

    def test_override_takes_precedence_over_registry(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"skeptic": PerArchetypeConfig(max_turns=40)},
            )
        )
        assert resolve_max_turns(config, "skeptic") == 40

    def test_override_zero_means_unlimited(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"coder": PerArchetypeConfig(max_turns=0)},
            )
        )
        assert resolve_max_turns(config, "coder") is None

    def test_legacy_dict_used_when_no_override(self) -> None:
        config = AgentFoxConfig(archetypes=ArchetypesConfig(max_turns={"coder": 150}))
        assert resolve_max_turns(config, "coder") == 150

    def test_registry_default_used_when_neither(self) -> None:
        """No override and no legacy dict → registry default."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        config = AgentFoxConfig()
        expected = ARCHETYPE_REGISTRY["coder"].default_max_turns
        assert resolve_max_turns(config, "coder") == expected

    def test_override_none_max_turns_falls_through(self) -> None:
        """PerArchetypeConfig with max_turns=None falls through to legacy dict."""
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                max_turns={"coder": 100},
                overrides={"coder": PerArchetypeConfig(max_turns=None)},
            )
        )
        assert resolve_max_turns(config, "coder") == 100


# ---------------------------------------------------------------------------
# resolve_thinking — priority: overrides > legacy > registry
# ---------------------------------------------------------------------------


class TestResolveThinkingWithOverrides:
    """resolve_thinking checks overrides first."""

    def test_override_thinking_mode_enabled(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"skeptic": PerArchetypeConfig(thinking_mode="enabled", thinking_budget=16000)},
            )
        )
        result = resolve_thinking(config, "skeptic")
        assert result == {"type": "enabled", "budget_tokens": 16000}

    def test_override_thinking_mode_adaptive(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"verifier": PerArchetypeConfig(thinking_mode="adaptive")},
            )
        )
        result = resolve_thinking(config, "verifier")
        assert result is not None
        assert result["type"] == "adaptive"
        assert result["budget_tokens"] == 10000  # default budget

    def test_override_thinking_mode_disabled(self) -> None:
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"coder": PerArchetypeConfig(thinking_mode="disabled")},
            )
        )
        result = resolve_thinking(config, "coder")
        assert result is None

    def test_override_takes_precedence_over_legacy_thinking_dict(self) -> None:
        from agent_fox.core.config import ThinkingConfig

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                thinking={"coder": ThinkingConfig(mode="enabled", budget_tokens=5000)},
                overrides={"coder": PerArchetypeConfig(thinking_mode="disabled")},
            )
        )
        # Override wins → disabled
        result = resolve_thinking(config, "coder")
        assert result is None

    def test_legacy_thinking_dict_used_when_no_override(self) -> None:
        from agent_fox.core.config import ThinkingConfig

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                thinking={"skeptic": ThinkingConfig(mode="adaptive", budget_tokens=8000)},
            )
        )
        result = resolve_thinking(config, "skeptic")
        assert result == {"type": "adaptive", "budget_tokens": 8000}

    def test_override_none_thinking_mode_falls_through(self) -> None:
        """PerArchetypeConfig with thinking_mode=None falls through to legacy."""
        from agent_fox.core.config import ThinkingConfig

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                thinking={"coder": ThinkingConfig(mode="enabled", budget_tokens=5000)},
                overrides={"coder": PerArchetypeConfig(thinking_mode=None)},
            )
        )
        # thinking_mode is None in override → check legacy
        result = resolve_thinking(config, "coder")
        assert result == {"type": "enabled", "budget_tokens": 5000}


# ---------------------------------------------------------------------------
# _resolve_model_tier — priority: overrides > legacy > registry
# ---------------------------------------------------------------------------


class TestResolveModelTierWithOverrides:
    """NodeSessionRunner._resolve_model_tier checks overrides first."""

    def test_override_model_tier_takes_precedence(self) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                models={"coder": "STANDARD"},  # legacy
                overrides={"coder": PerArchetypeConfig(model_tier="ADVANCED")},  # new
            )
        )
        runner = NodeSessionRunner("spec:1", config, archetype="coder", knowledge_db=_MOCK_KB)
        # ADVANCED → claude-opus-4-6
        assert runner._resolved_model_id == "claude-opus-4-6"

    def test_override_standard_tier(self) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"skeptic": PerArchetypeConfig(model_tier="STANDARD")},
            )
        )
        runner = NodeSessionRunner("spec:0", config, archetype="skeptic", knowledge_db=_MOCK_KB)
        # STANDARD → claude-sonnet-4-6
        assert runner._resolved_model_id == "claude-sonnet-4-6"

    def test_legacy_models_dict_used_when_no_override(self) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"coder": "ADVANCED"}))
        runner = NodeSessionRunner("spec:1", config, archetype="coder", knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-opus-4-6"

    def test_override_none_model_tier_falls_through_to_legacy(self) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                models={"coder": "ADVANCED"},
                overrides={"coder": PerArchetypeConfig(model_tier=None)},
            )
        )
        runner = NodeSessionRunner("spec:1", config, archetype="coder", knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# _resolve_security_config — priority: overrides > legacy > registry
# ---------------------------------------------------------------------------


class TestResolveSecurityConfigWithOverrides:
    """resolve_security_config checks overrides first."""

    def test_override_allowlist_takes_precedence(self) -> None:
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                allowlists={"coder": ["ls"]},  # legacy
                overrides={"coder": PerArchetypeConfig(allowlist=["git", "grep"])},  # new
            )
        )
        sec = resolve_security_config(config, "coder")
        assert sec is not None
        assert sec.bash_allowlist == ["git", "grep"]

    def test_legacy_allowlist_used_when_no_override(self) -> None:
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(archetypes=ArchetypesConfig(allowlists={"coder": ["make", "uv"]}))
        sec = resolve_security_config(config, "coder")
        assert sec is not None
        assert sec.bash_allowlist == ["make", "uv"]

    def test_override_none_allowlist_falls_through_to_legacy(self) -> None:
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                allowlists={"coder": ["make"]},
                overrides={"coder": PerArchetypeConfig(allowlist=None)},
            )
        )
        sec = resolve_security_config(config, "coder")
        assert sec is not None
        assert sec.bash_allowlist == ["make"]

    def test_override_empty_allowlist_not_treated_as_none(self) -> None:
        """An explicit empty list [] is a valid allowlist (no commands allowed)."""
        from agent_fox.engine.sdk_params import resolve_security_config

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                allowlists={"coder": ["make"]},  # legacy
                overrides={"coder": PerArchetypeConfig(allowlist=[])},  # override with empty
            )
        )
        sec = resolve_security_config(config, "coder")
        assert sec is not None
        assert sec.bash_allowlist == []


# ---------------------------------------------------------------------------
# End-to-end TOML loading and resolution
# ---------------------------------------------------------------------------


class TestEndToEndTomlResolution:
    """Full path: TOML file → load_config → resolve functions."""

    def test_model_tier_from_toml_overrides_table(self, tmp_path: Path) -> None:
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.overrides.skeptic]\nmodel_tier = "STANDARD"\n')
        config = load_config(path=config_file)
        runner = NodeSessionRunner("spec:0", config, archetype="skeptic", knowledge_db=_MOCK_KB)
        # Registry default for skeptic is ADVANCED, but override is STANDARD → sonnet
        assert runner._resolved_model_id == "claude-sonnet-4-6"

    def test_max_turns_from_toml_overrides_table(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("[archetypes.overrides.coder]\nmax_turns = 50\n")
        config = load_config(path=config_file)
        assert resolve_max_turns(config, "coder") == 50

    def test_thinking_from_toml_overrides_table(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.overrides.verifier]\nthinking_mode = "enabled"\nthinking_budget = 8000\n')
        config = load_config(path=config_file)
        result = resolve_thinking(config, "verifier")
        assert result == {"type": "enabled", "budget_tokens": 8000}

    def test_backwards_compat_legacy_max_turns_dict(self, tmp_path: Path) -> None:
        """Old archetypes.max_turns dict style still works."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[archetypes.max_turns]\ncoder = 150\n")
        config = load_config(path=config_file)
        assert resolve_max_turns(config, "coder") == 150

    def test_backwards_compat_legacy_thinking_dict(self, tmp_path: Path) -> None:
        """Old archetypes.thinking dict style still works."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[archetypes.thinking.coder]\nmode = "enabled"\nbudget_tokens = 20000\n')
        config = load_config(path=config_file)
        result = resolve_thinking(config, "coder")
        assert result == {"type": "enabled", "budget_tokens": 20000}
