"""Unit tests for ModeConfig dataclass and ArchetypeEntry.modes field.

Test Spec: TS-97-1, TS-97-2, TS-97-3, TS-97-4, TS-97-E1, TS-97-E2
Requirements: 97-REQ-1.1, 97-REQ-1.2, 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5,
              97-REQ-1.E1, 97-REQ-1.E2
"""

from __future__ import annotations

import logging

# ---------------------------------------------------------------------------
# TS-97-1: ModeConfig Dataclass Defaults
# Requirement: 97-REQ-1.1
# ---------------------------------------------------------------------------


class TestModeConfigDefaults:
    """Verify ModeConfig fields default to None."""

    def test_all_fields_default_to_none(self) -> None:
        """TS-97-1: All ModeConfig fields should default to None."""
        from agent_fox.archetypes import ModeConfig

        mc = ModeConfig()
        assert mc.templates is None
        assert mc.injection is None
        assert mc.allowlist is None
        assert mc.model_tier is None
        assert mc.max_turns is None
        assert mc.thinking_mode is None
        assert mc.thinking_budget is None
        assert mc.retry_predecessor is None

    def test_is_frozen(self) -> None:
        """ModeConfig should be a frozen dataclass."""
        import dataclasses

        from agent_fox.archetypes import ModeConfig

        mc = ModeConfig()
        assert dataclasses.is_dataclass(mc)
        # Frozen dataclasses raise FrozenInstanceError on assignment
        import pytest
        with pytest.raises((TypeError, AttributeError)):
            mc.model_tier = "SIMPLE"  # type: ignore[misc]

    def test_all_fields_can_be_set(self) -> None:
        """ModeConfig fields can be provided at construction."""
        from agent_fox.archetypes import ModeConfig

        mc = ModeConfig(
            templates=["custom.md"],
            injection="auto_pre",
            allowlist=["ls", "cat"],
            model_tier="SIMPLE",
            max_turns=50,
            thinking_mode="enabled",
            thinking_budget=8000,
            retry_predecessor=True,
        )
        assert mc.templates == ["custom.md"]
        assert mc.injection == "auto_pre"
        assert mc.allowlist == ["ls", "cat"]
        assert mc.model_tier == "SIMPLE"
        assert mc.max_turns == 50
        assert mc.thinking_mode == "enabled"
        assert mc.thinking_budget == 8000
        assert mc.retry_predecessor is True

    def test_empty_allowlist_is_allowed(self) -> None:
        """ModeConfig should accept an empty list for allowlist."""
        from agent_fox.archetypes import ModeConfig

        mc = ModeConfig(allowlist=[])
        assert mc.allowlist == []


# ---------------------------------------------------------------------------
# TS-97-2: ArchetypeEntry Modes Field
# Requirement: 97-REQ-1.2
# ---------------------------------------------------------------------------


class TestArchetypeEntryModesField:
    """Verify ArchetypeEntry has a modes dict defaulting to empty."""

    def test_modes_field_defaults_to_empty_dict(self) -> None:
        """TS-97-2: ArchetypeEntry.modes should default to empty dict."""
        from agent_fox.archetypes import ArchetypeEntry

        entry = ArchetypeEntry(name="test")
        assert entry.modes == {}
        assert isinstance(entry.modes, dict)

    def test_modes_can_be_set_with_mode_configs(self) -> None:
        """ArchetypeEntry.modes accepts a dict of ModeConfig instances."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig

        entry = ArchetypeEntry(
            name="test",
            modes={"fast": ModeConfig(model_tier="SIMPLE", max_turns=50)},
        )
        assert "fast" in entry.modes
        assert entry.modes["fast"].model_tier == "SIMPLE"
        assert entry.modes["fast"].max_turns == 50

    def test_entry_is_frozen(self) -> None:
        """ArchetypeEntry with modes field should remain a frozen dataclass."""
        import pytest

        from agent_fox.archetypes import ArchetypeEntry
        entry = ArchetypeEntry(name="test")
        with pytest.raises((TypeError, AttributeError)):
            entry.modes = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-97-3: resolve_effective_config With Valid Mode
# Requirements: 97-REQ-1.3, 97-REQ-1.5
# ---------------------------------------------------------------------------


class TestResolveEffectiveConfigValidMode:
    """Verify mode overrides are applied and non-overridden fields are inherited."""

    def test_mode_overrides_model_tier_and_max_turns(self) -> None:
        """TS-97-3: Non-None ModeConfig fields override the base entry."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            templates=["base.md"],
            default_model_tier="STANDARD",
            default_max_turns=200,
            modes={"fast": ModeConfig(model_tier="SIMPLE", max_turns=50)},
        )
        result = resolve_effective_config(entry, "fast")
        assert result.default_model_tier == "SIMPLE"
        assert result.default_max_turns == 50
        # Non-overridden field is inherited
        assert result.templates == ["base.md"]

    def test_mode_overrides_templates(self) -> None:
        """Overriding templates replaces the base templates list."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            templates=["base.md"],
            modes={"custom": ModeConfig(templates=["custom.md"])},
        )
        result = resolve_effective_config(entry, "custom")
        assert result.templates == ["custom.md"]

    def test_mode_overrides_allowlist(self) -> None:
        """Overriding allowlist with empty list gives empty allowlist."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            default_allowlist=["ls", "cat"],
            modes={"no-shell": ModeConfig(allowlist=[])},
        )
        result = resolve_effective_config(entry, "no-shell")
        assert result.default_allowlist == []

    def test_mode_overrides_injection(self) -> None:
        """Overriding injection replaces the base injection value."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            injection=None,
            modes={"pre": ModeConfig(injection="auto_pre")},
        )
        result = resolve_effective_config(entry, "pre")
        assert result.injection == "auto_pre"

    def test_mode_overrides_thinking(self) -> None:
        """Overriding thinking_mode and thinking_budget applies correctly."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            default_thinking_mode="disabled",
            default_thinking_budget=10000,
            modes={"think": ModeConfig(thinking_mode="enabled", thinking_budget=32000)},
        )
        result = resolve_effective_config(entry, "think")
        assert result.default_thinking_mode == "enabled"
        assert result.default_thinking_budget == 32000

    def test_mode_overrides_retry_predecessor(self) -> None:
        """Overriding retry_predecessor applies correctly."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            retry_predecessor=False,
            modes={"retry": ModeConfig(retry_predecessor=True)},
        )
        result = resolve_effective_config(entry, "retry")
        assert result.retry_predecessor is True

    def test_partial_override_inherits_rest(self) -> None:
        """When only some fields are overridden, others come from the base."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            templates=["base.md"],
            default_model_tier="STANDARD",
            default_max_turns=200,
            default_thinking_mode="disabled",
            injection="auto_post",
            retry_predecessor=False,
            modes={"partial": ModeConfig(model_tier="SIMPLE")},
        )
        result = resolve_effective_config(entry, "partial")
        # Override applied
        assert result.default_model_tier == "SIMPLE"
        # Everything else inherited
        assert result.templates == ["base.md"]
        assert result.default_max_turns == 200
        assert result.default_thinking_mode == "disabled"
        assert result.injection == "auto_post"
        assert result.retry_predecessor is False

    def test_result_is_archetype_entry(self) -> None:
        """resolve_effective_config returns an ArchetypeEntry instance."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            modes={"fast": ModeConfig(model_tier="SIMPLE")},
        )
        result = resolve_effective_config(entry, "fast")
        assert isinstance(result, ArchetypeEntry)


# ---------------------------------------------------------------------------
# TS-97-4: resolve_effective_config With None Mode
# Requirement: 97-REQ-1.4
# ---------------------------------------------------------------------------


class TestResolveEffectiveConfigNoneMode:
    """Verify None mode returns base entry unchanged."""

    def test_none_mode_returns_base_unchanged(self) -> None:
        """TS-97-4: mode=None returns the base entry with same field values."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            default_model_tier="ADVANCED",
            modes={"fast": ModeConfig(model_tier="SIMPLE")},
        )
        result = resolve_effective_config(entry, None)
        assert result.default_model_tier == "ADVANCED"

    def test_none_mode_preserves_name(self) -> None:
        """None mode preserves the entry name."""
        from agent_fox.archetypes import ArchetypeEntry, resolve_effective_config

        entry = ArchetypeEntry(name="my_archetype")
        result = resolve_effective_config(entry, None)
        assert result.name == "my_archetype"

    def test_none_mode_preserves_all_base_fields(self) -> None:
        """None mode preserves all base fields."""
        from agent_fox.archetypes import ArchetypeEntry, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            templates=["t.md"],
            default_model_tier="ADVANCED",
            default_max_turns=150,
            default_thinking_mode="adaptive",
            default_thinking_budget=20000,
            injection="auto_pre",
            retry_predecessor=True,
            default_allowlist=["ls"],
        )
        result = resolve_effective_config(entry, None)
        assert result.templates == ["t.md"]
        assert result.default_model_tier == "ADVANCED"
        assert result.default_max_turns == 150
        assert result.default_thinking_mode == "adaptive"
        assert result.default_thinking_budget == 20000
        assert result.injection == "auto_pre"
        assert result.retry_predecessor is True
        assert result.default_allowlist == ["ls"]


# ---------------------------------------------------------------------------
# TS-97-E1: Unknown Mode Fallback
# Requirement: 97-REQ-1.E1
# ---------------------------------------------------------------------------


class TestUnknownModeFallback:
    """Verify unknown mode falls back to base entry with warning."""

    def test_unknown_mode_returns_base_entry(self) -> None:
        """TS-97-E1: Unknown mode returns base entry unchanged."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(
            name="test",
            default_model_tier="STANDARD",
            modes={"fast": ModeConfig(model_tier="SIMPLE")},
        )
        result = resolve_effective_config(entry, "unknown_mode")
        assert result.default_model_tier == "STANDARD"

    def test_unknown_mode_logs_warning(self, caplog: object) -> None:
        """TS-97-E1: Unknown mode logs a warning."""
        import pytest

        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config
        entry = ArchetypeEntry(
            name="test",
            modes={"fast": ModeConfig(model_tier="SIMPLE")},
        )
        with pytest.warns(None):
            pass  # just to clear any previous warnings

        with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
            resolve_effective_config(entry, "unknown_mode")

        # Warning should mention the unknown mode
        warning_messages = [r.message for r in caplog.records]  # type: ignore[attr-defined]
        assert any("unknown_mode" in str(m) for m in warning_messages)


# ---------------------------------------------------------------------------
# TS-97-E2: Empty Modes Dict
# Requirement: 97-REQ-1.E2
# ---------------------------------------------------------------------------


class TestEmptyModesDict:
    """Verify empty modes dict treated as no modes — returns base entry."""

    def test_empty_modes_dict_returns_base(self) -> None:
        """TS-97-E2: Empty modes dict returns base entry for any mode arg."""
        from agent_fox.archetypes import ArchetypeEntry, resolve_effective_config

        entry = ArchetypeEntry(name="test", default_model_tier="STANDARD", modes={})
        result = resolve_effective_config(entry, "any_mode")
        assert result.default_model_tier == "STANDARD"
