"""Unit tests for PerArchetypeConfig.modes field and TOML parsing.

Test Spec: TS-97-7, TS-97-8, TS-97-E4
Requirements: 97-REQ-3.1, 97-REQ-3.2, 97-REQ-3.E1
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-97-7: PerArchetypeConfig Modes Field
# Requirement: 97-REQ-3.1
# ---------------------------------------------------------------------------


class TestPerArchetypeConfigModesField:
    """Verify PerArchetypeConfig accepts nested modes dict."""

    def test_modes_field_defaults_to_empty_dict(self) -> None:
        """TS-97-7: PerArchetypeConfig.modes defaults to empty dict."""
        from agent_fox.core.config import PerArchetypeConfig

        pac = PerArchetypeConfig()
        assert pac.modes == {}
        assert isinstance(pac.modes, dict)

    def test_modes_accepts_nested_per_archetype_config(self) -> None:
        """TS-97-7: modes dict accepts PerArchetypeConfig values."""
        from agent_fox.core.config import PerArchetypeConfig

        pac = PerArchetypeConfig(
            model_tier="STANDARD",
            modes={"pre-review": PerArchetypeConfig(allowlist=[])},
        )
        assert "pre-review" in pac.modes
        assert pac.modes["pre-review"].allowlist == []

    def test_modes_nested_config_has_own_modes(self) -> None:
        """Nested PerArchetypeConfig in modes also has modes field."""
        from agent_fox.core.config import PerArchetypeConfig

        inner = PerArchetypeConfig(max_turns=60)
        pac = PerArchetypeConfig(modes={"m": inner})
        assert pac.modes["m"].max_turns == 60
        assert pac.modes["m"].modes == {}

    def test_modes_accepts_multiple_mode_entries(self) -> None:
        """modes dict accepts multiple named entries."""
        from agent_fox.core.config import PerArchetypeConfig

        pac = PerArchetypeConfig(
            modes={
                "pre-review": PerArchetypeConfig(allowlist=[], max_turns=60),
                "drift-review": PerArchetypeConfig(allowlist=["ls", "git"]),
            }
        )
        assert len(pac.modes) == 2
        assert pac.modes["pre-review"].max_turns == 60
        assert pac.modes["drift-review"].allowlist == ["ls", "git"]

    def test_mode_config_fields_are_optional(self) -> None:
        """Nested PerArchetypeConfig in modes has all optional fields."""
        from agent_fox.core.config import PerArchetypeConfig

        inner = PerArchetypeConfig()
        pac = PerArchetypeConfig(modes={"m": inner})
        assert pac.modes["m"].model_tier is None
        assert pac.modes["m"].max_turns is None
        assert pac.modes["m"].thinking_mode is None
        assert pac.modes["m"].thinking_budget is None
        assert pac.modes["m"].allowlist is None


# ---------------------------------------------------------------------------
# TS-97-8: TOML Config Parsing With Modes
# Requirement: 97-REQ-3.2
# ---------------------------------------------------------------------------


class TestTomlConfigParsingWithModes:
    """Verify TOML with nested mode sections parses correctly."""

    def _parse_toml_config(self, toml_str: str) -> object:
        """Helper to parse a TOML string into AgentFoxConfig."""
        import tomllib

        from agent_fox.core.config import AgentFoxConfig

        data = tomllib.loads(toml_str)
        return AgentFoxConfig.model_validate(data)

    def test_mode_section_parsed_into_modes_dict(self) -> None:
        """TS-97-8: [archetypes.overrides.reviewer.modes.pre-review] parses correctly."""
        toml_str = """
[archetypes.overrides.reviewer]
model_tier = "STANDARD"

[archetypes.overrides.reviewer.modes.pre-review]
max_turns = 60
"""
        config = self._parse_toml_config(toml_str)
        reviewer = config.archetypes.overrides["reviewer"]  # type: ignore[attr-defined]
        assert reviewer.model_tier == "STANDARD"
        pre = reviewer.modes["pre-review"]
        assert pre.max_turns == 60

    def test_mode_section_with_empty_allowlist(self) -> None:
        """TS-97-8: Empty allowlist in mode section parses to empty list."""
        toml_str = """
[archetypes.overrides.reviewer]
model_tier = "STANDARD"

[archetypes.overrides.reviewer.modes.pre-review]
allowlist = []
max_turns = 60
"""
        config = self._parse_toml_config(toml_str)
        reviewer = config.archetypes.overrides["reviewer"]  # type: ignore[attr-defined]
        pre = reviewer.modes["pre-review"]
        assert pre.allowlist == []
        assert pre.max_turns == 60

    def test_multiple_mode_sections(self) -> None:
        """Multiple mode sections under an archetype parse correctly."""
        toml_str = """
[archetypes.overrides.reviewer.modes.pre-review]
allowlist = []

[archetypes.overrides.reviewer.modes.drift-review]
allowlist = ["ls", "cat", "git"]
"""
        config = self._parse_toml_config(toml_str)
        reviewer = config.archetypes.overrides["reviewer"]  # type: ignore[attr-defined]
        assert reviewer.modes["pre-review"].allowlist == []
        assert reviewer.modes["drift-review"].allowlist == ["ls", "cat", "git"]

    def test_archetype_without_modes_has_empty_modes(self) -> None:
        """Archetype config without mode sections has empty modes dict."""
        toml_str = """
[archetypes.overrides.coder]
model_tier = "STANDARD"
"""
        config = self._parse_toml_config(toml_str)
        coder = config.archetypes.overrides["coder"]  # type: ignore[attr-defined]
        assert coder.modes == {}


# ---------------------------------------------------------------------------
# TS-97-E4: Config Missing Mode Section Fallback
# Requirement: 97-REQ-3.E1
# ---------------------------------------------------------------------------


class TestMissingModeSectionFallback:
    """Verify missing mode config section falls back to archetype level."""

    def test_resolve_max_turns_falls_back_to_archetype_level(self) -> None:
        """TS-97-E4: Missing mode section falls back to archetype-level max_turns."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(overrides={"reviewer": PerArchetypeConfig(max_turns=100, modes={})})
        )
        result = resolve_max_turns(config, "reviewer", mode="pre-review")
        assert result == 100

    def test_resolve_model_tier_falls_back_to_archetype_level(self) -> None:
        """TS-97-E4: Missing mode section falls back to archetype-level model_tier."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(overrides={"reviewer": PerArchetypeConfig(model_tier="ADVANCED", modes={})})
        )
        result = resolve_model_tier(config, "reviewer", mode="pre-review")
        assert result == "ADVANCED"
