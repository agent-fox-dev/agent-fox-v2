"""Property-based tests for archetype mode infrastructure.

Test Spec: TS-97-P1 through TS-97-P6
Requirements: 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5, 97-REQ-2.2,
              97-REQ-3.3, 97-REQ-4.1, 97-REQ-4.2, 97-REQ-4.3, 97-REQ-4.4,
              97-REQ-5.2
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


pytestmark = pytest.mark.property


# ---------------------------------------------------------------------------
# Helpers / Strategies
# ---------------------------------------------------------------------------

_VALID_TIERS = ["SIMPLE", "STANDARD", "ADVANCED"]
_VALID_INJECTIONS = [None, "auto_pre", "auto_post", "auto_mid"]
_VALID_THINKING_MODES = ["disabled", "enabled", "adaptive"]


def _mode_config_strategy():  # type: ignore[return]
    """Strategy that generates ModeConfig instances with arbitrary field combinations."""
    from hypothesis import strategies as st

    return st.fixed_dictionaries(
        {
            "templates": st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=20), max_size=3)),
            "injection": st.one_of(st.none(), st.sampled_from([v for v in _VALID_INJECTIONS if v is not None])),
            "allowlist": st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=10), max_size=5)),
            "model_tier": st.one_of(st.none(), st.sampled_from(_VALID_TIERS)),
            "max_turns": st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
            "thinking_mode": st.one_of(st.none(), st.sampled_from(_VALID_THINKING_MODES)),
            "thinking_budget": st.one_of(st.none(), st.integers(min_value=1000, max_value=100000)),
            "retry_predecessor": st.one_of(st.none(), st.booleans()),
        }
    )


def _archetype_entry_strategy():  # type: ignore[return]
    """Strategy that generates ArchetypeEntry base instances."""
    from hypothesis import strategies as st

    return st.fixed_dictionaries(
        {
            "name": st.text(alphabet=st.characters(whitelist_categories=("L",)), min_size=1, max_size=20),
            "templates": st.lists(st.text(min_size=1, max_size=20), max_size=3),
            "default_model_tier": st.sampled_from(_VALID_TIERS),
            "injection": st.one_of(st.none(), st.sampled_from([v for v in _VALID_INJECTIONS if v is not None])),
            "task_assignable": st.booleans(),
            "retry_predecessor": st.booleans(),
            "default_allowlist": st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=10), max_size=5)),
            "default_max_turns": st.integers(min_value=1, max_value=500),
            "default_thinking_mode": st.sampled_from(_VALID_THINKING_MODES),
            "default_thinking_budget": st.integers(min_value=1000, max_value=100000),
        }
    )


# Mapping from ModeConfig field names to ArchetypeEntry field names
_MODE_TO_ENTRY_FIELD_MAP = {
    "templates": "templates",
    "injection": "injection",
    "allowlist": "default_allowlist",
    "model_tier": "default_model_tier",
    "max_turns": "default_max_turns",
    "thinking_mode": "default_thinking_mode",
    "thinking_budget": "default_thinking_budget",
    "retry_predecessor": "retry_predecessor",
}


# ---------------------------------------------------------------------------
# TS-97-P1: Mode Override Semantics
# Requirements: 97-REQ-1.3, 97-REQ-1.5
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestModeOverrideSemantics:
    """TS-97-P1: Non-None mode fields always override the base entry."""

    @given(base_params=_archetype_entry_strategy(), mode_params=_mode_config_strategy())
    @settings(max_examples=50)
    def test_non_none_mode_fields_override_base(self, base_params: dict, mode_params: dict) -> None:
        """For any non-None field in ModeConfig, resolved entry has that value."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        mode_cfg = ModeConfig(**mode_params)
        entry = ArchetypeEntry(**base_params, modes={"m": mode_cfg})
        resolved = resolve_effective_config(entry, "m")

        for mode_field, entry_field in _MODE_TO_ENTRY_FIELD_MAP.items():
            mode_val = getattr(mode_cfg, mode_field)
            if mode_val is not None:
                resolved_val = getattr(resolved, entry_field)
                assert resolved_val == mode_val, (
                    f"Field {mode_field!r} override: expected {mode_val!r}, got {resolved_val!r}"
                )


# ---------------------------------------------------------------------------
# TS-97-P2: Mode Inheritance Semantics
# Requirements: 97-REQ-1.5
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestModeInheritanceSemantics:
    """TS-97-P2: None mode fields inherit the base entry value."""

    @given(base_params=_archetype_entry_strategy(), mode_params=_mode_config_strategy())
    @settings(max_examples=50)
    def test_none_mode_fields_inherit_base(self, base_params: dict, mode_params: dict) -> None:
        """For any None field in ModeConfig, resolved entry has the base value."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        mode_cfg = ModeConfig(**mode_params)
        entry = ArchetypeEntry(**base_params, modes={"m": mode_cfg})
        resolved = resolve_effective_config(entry, "m")

        for mode_field, entry_field in _MODE_TO_ENTRY_FIELD_MAP.items():
            mode_val = getattr(mode_cfg, mode_field)
            if mode_val is None:
                base_val = getattr(entry, entry_field)
                resolved_val = getattr(resolved, entry_field)
                assert resolved_val == base_val, (
                    f"Field {mode_field!r} inheritance: expected base {base_val!r}, got {resolved_val!r}"
                )


# ---------------------------------------------------------------------------
# TS-97-P3: Null Mode Identity
# Requirements: 97-REQ-1.4, 97-REQ-4.E1
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestNullModeIdentity:
    """TS-97-P3: None mode always returns a value equivalent to the base entry."""

    @given(base_params=_archetype_entry_strategy())
    @settings(max_examples=50)
    def test_none_mode_preserves_all_base_fields(self, base_params: dict) -> None:
        """resolve_effective_config(entry, None) preserves all non-modes fields from base."""
        from agent_fox.archetypes import ArchetypeEntry, ModeConfig, resolve_effective_config

        entry = ArchetypeEntry(**base_params, modes={"m": ModeConfig(model_tier="SIMPLE")})
        resolved = resolve_effective_config(entry, None)

        # All non-modes fields should equal the base entry
        for entry_field in [
            "name",
            "templates",
            "default_model_tier",
            "injection",
            "task_assignable",
            "retry_predecessor",
            "default_allowlist",
            "default_max_turns",
            "default_thinking_mode",
            "default_thinking_budget",
        ]:
            base_val = getattr(entry, entry_field)
            resolved_val = getattr(resolved, entry_field)
            assert resolved_val == base_val, f"Field {entry_field!r}: expected {base_val!r}, got {resolved_val!r}"


# ---------------------------------------------------------------------------
# TS-97-P4: Resolution Priority Chain
# Requirements: 97-REQ-3.3, 97-REQ-4.1, 97-REQ-4.2, 97-REQ-4.3, 97-REQ-4.4
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestResolutionPriorityChain:
    """TS-97-P4: Config mode override > config archetype > registry mode > registry base."""

    @given(
        config_mode_tier=st.one_of(st.none(), st.sampled_from(_VALID_TIERS)),
        config_arch_tier=st.one_of(st.none(), st.sampled_from(_VALID_TIERS)),
        registry_mode_tier=st.one_of(st.none(), st.sampled_from(_VALID_TIERS)),
    )
    @settings(max_examples=50)
    def test_model_tier_priority_chain(
        self,
        config_mode_tier: str | None,
        config_arch_tier: str | None,
        registry_mode_tier: str | None,
    ) -> None:
        """Model tier resolution follows 4-tier priority chain."""

        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        registry_base_tier = "STANDARD"  # coder's default
        arch_name = "coder"
        mode_name = "test-mode"

        # Build config
        mode_overrides: dict = {}
        if config_mode_tier is not None:
            mode_overrides[mode_name] = PerArchetypeConfig(model_tier=config_mode_tier)

        arch_overrides: dict = {}
        if config_arch_tier is not None:
            arch_overrides[arch_name] = PerArchetypeConfig(
                model_tier=config_arch_tier,
                modes=mode_overrides if mode_overrides else {},
            )
        elif mode_overrides:
            arch_overrides[arch_name] = PerArchetypeConfig(modes=mode_overrides)

        config = AgentFoxConfig(archetypes=ArchetypesConfig(overrides=arch_overrides))

        # Determine expected result
        mode_in_arch = arch_name in arch_overrides and mode_name in arch_overrides[arch_name].modes
        if config_mode_tier is not None and mode_in_arch:
            expected = config_mode_tier
        elif config_arch_tier is not None:
            expected = config_arch_tier
        else:
            expected = registry_base_tier

        result = resolve_model_tier(config, arch_name, mode=mode_name)
        assert result == expected, (
            f"Priority chain failed: config_mode={config_mode_tier!r}, "
            f"config_arch={config_arch_tier!r}, expected={expected!r}, got={result!r}"
        )


# ---------------------------------------------------------------------------
# TS-97-P5: Empty Allowlist Blocks All Bash
# Requirement: 97-REQ-5.2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestEmptyAllowlistBlocksAll:
    """TS-97-P5: An empty allowlist blocks every possible command."""

    @given(
        cmd=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="- _/"),
            min_size=1,
            max_size=30,
        )
    )
    @settings(max_examples=50)
    def test_empty_allowlist_blocks_any_command(self, cmd: str) -> None:
        """Every non-empty command is blocked when allowlist is empty."""
        from agent_fox.core.config import SecurityConfig
        from agent_fox.security.security import make_pre_tool_use_hook

        # Strip to ensure non-empty, add a prefix to ensure it's a valid command name
        safe_cmd = "mycmd_" + cmd.strip()
        if not safe_cmd.strip():
            return  # skip empty

        hook = make_pre_tool_use_hook(SecurityConfig(bash_allowlist=[]))
        result = hook(tool_name="Bash", tool_input={"command": safe_cmd})
        assert result["decision"] == "block", f"Expected block for command {safe_cmd!r}, got {result['decision']!r}"


# ---------------------------------------------------------------------------
# TS-97-P6: Serialization Round-Trip
# Requirement: 97-REQ-2.2
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestSerializationRoundTrip:
    """TS-97-P6: Node mode survives serialization round-trip."""

    @given(
        mode=st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
                min_size=1,
                max_size=30,
            ),
        )
    )
    @settings(max_examples=50)
    def test_mode_survives_roundtrip(self, mode: str | None) -> None:
        """For any mode (None or string), serialize then deserialize preserves mode."""
        from agent_fox.graph.persistence import _node_from_dict, _serialize
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0",
            spec_name="s",
            group_number=0,
            title="t",
            optional=False,
            mode=mode,
        )
        serialized = _serialize(node)
        deserialized = _node_from_dict(serialized)
        assert deserialized.mode == mode, f"Round-trip failed: expected mode {mode!r}, got {deserialized.mode!r}"
