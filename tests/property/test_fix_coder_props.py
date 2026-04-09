"""Property-based tests for the fix_coder archetype.

Test Spec: TS-88-P1, TS-88-P2, TS-88-P3
Requirements: 88-REQ-1.2, 88-REQ-1.E1, 88-REQ-2.1, 88-REQ-2.2, 88-REQ-2.3,
              88-REQ-4.1, 88-REQ-4.2
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


# ---------------------------------------------------------------------------
# TS-88-P1: Template isolation under interpolation
# Requirements: 88-REQ-1.2, 88-REQ-1.E1
# ---------------------------------------------------------------------------


class TestTemplateIsolation:
    """TS-88-P1: For any spec_name, interpolated fix_coding.md has no .specs/."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        spec_name=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
        )
    )
    @settings(max_examples=50)
    def test_prop_no_specs_after_interpolation(self, spec_name: str) -> None:
        """For any spec_name, the interpolated template never contains '.specs/'."""
        from agent_fox.session.prompt import _interpolate, _load_template

        template = _load_template("fix_coding.md")
        variables = {
            "spec_name": spec_name,
            "task_group": "0",
            "number": spec_name,
            "specification": spec_name,
        }
        result = _interpolate(template, variables)
        assert ".specs/" not in result, (
            f"Interpolated template contains '.specs/' with spec_name={spec_name!r}"
        )

    def test_raw_template_no_specs_reference(self) -> None:
        """The raw template does not contain '.specs/' before interpolation."""
        from agent_fox.session.prompt import _load_template

        template = _load_template("fix_coding.md")
        assert ".specs/" not in template

    def test_no_specs_with_adversarial_spec_name(self) -> None:
        """Even with spec_name='.specs/malicious', raw template has no .specs/."""
        from agent_fox.session.prompt import _load_template

        template = _load_template("fix_coding.md")
        # The raw template itself must not contain .specs/
        assert ".specs/" not in template


# ---------------------------------------------------------------------------
# TS-88-P2: Registry parity between fix_coder and coder
# Requirements: 88-REQ-2.1, 88-REQ-2.2, 88-REQ-2.3
# ---------------------------------------------------------------------------


class TestRegistryParity:
    """TS-88-P2: fix_coder has same numeric defaults as coder but different template."""

    def test_fix_coder_template_is_fix_coding_md(self) -> None:
        """fix_coder.templates == ['fix_coding.md']."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.templates == ["fix_coding.md"]

    def test_fix_coder_template_differs_from_coder(self) -> None:
        """fix_coder.templates is different from coder.templates."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.templates != coder.templates

    def test_fix_coder_not_task_assignable(self) -> None:
        """fix_coder.task_assignable is False."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.task_assignable is False

    def test_model_tier_parity(self) -> None:
        """fix_coder.default_model_tier equals coder.default_model_tier."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_model_tier == coder.default_model_tier

    def test_max_turns_parity(self) -> None:
        """fix_coder.default_max_turns equals coder.default_max_turns."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_max_turns == coder.default_max_turns

    def test_thinking_mode_parity(self) -> None:
        """fix_coder.default_thinking_mode equals coder.default_thinking_mode."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_thinking_mode == coder.default_thinking_mode

    def test_thinking_budget_parity(self) -> None:
        """fix_coder.default_thinking_budget equals coder.default_thinking_budget."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        coder = ARCHETYPE_REGISTRY["coder"]
        fix_coder = ARCHETYPE_REGISTRY["fix_coder"]
        assert fix_coder.default_thinking_budget == coder.default_thinking_budget


# ---------------------------------------------------------------------------
# TS-88-P3: SDK parameter parity without overrides
# Requirements: 88-REQ-4.1, 88-REQ-4.2
# ---------------------------------------------------------------------------


class TestSdkParameterParity:
    """TS-88-P3: Without config overrides, fix_coder resolves same params as coder."""

    def _default_config(self) -> object:
        """Build a default AgentFoxConfig with no archetype overrides."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig

        return AgentFoxConfig(archetypes=ArchetypesConfig())

    def test_resolve_model_tier_parity(self) -> None:
        """resolve_model_tier returns same value for fix_coder and coder."""
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = self._default_config()
        coder_tier = resolve_model_tier(config, "coder")
        fix_coder_tier = resolve_model_tier(config, "fix_coder")
        assert fix_coder_tier == coder_tier, (
            f"resolve_model_tier: fix_coder={fix_coder_tier!r}, coder={coder_tier!r}"
        )

    def test_resolve_max_turns_parity(self) -> None:
        """resolve_max_turns returns same value for fix_coder and coder."""
        from agent_fox.engine.sdk_params import resolve_max_turns

        config = self._default_config()
        coder_turns = resolve_max_turns(config, "coder")
        fix_coder_turns = resolve_max_turns(config, "fix_coder")
        assert fix_coder_turns == coder_turns, (
            f"resolve_max_turns: fix_coder={fix_coder_turns!r}, coder={coder_turns!r}"
        )

    def test_resolve_thinking_parity(self) -> None:
        """resolve_thinking returns same value for fix_coder and coder."""
        from agent_fox.engine.sdk_params import resolve_thinking

        config = self._default_config()
        coder_thinking = resolve_thinking(config, "coder")
        fix_coder_thinking = resolve_thinking(config, "fix_coder")
        assert fix_coder_thinking == coder_thinking, (
            f"resolve_thinking: fix_coder={fix_coder_thinking!r}, coder={coder_thinking!r}"
        )

    def test_fix_coder_override_independent_of_coder(self) -> None:
        """A fix_coder-specific override does not affect coder resolution."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        # Override only fix_coder's model tier
        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"fix_coder": PerArchetypeConfig(model_tier="ADVANCED")}
            )
        )
        coder_tier = resolve_model_tier(config, "coder")
        fix_coder_tier = resolve_model_tier(config, "fix_coder")

        # fix_coder should use the override (ADVANCED)
        assert fix_coder_tier == "ADVANCED", (
            f"fix_coder override not applied: got {fix_coder_tier!r}"
        )
        # coder should still use its registry default (STANDARD)
        assert coder_tier == "STANDARD", (
            f"coder was affected by fix_coder override: got {coder_tier!r}"
        )

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @pytest.mark.property
    @given(
        tier=st.sampled_from(["SIMPLE", "STANDARD", "ADVANCED"]),
    )
    @settings(max_examples=20)
    def test_prop_fix_coder_override_independent(self, tier: str) -> None:
        """For any tier override on fix_coder, coder resolution is unaffected."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig, PerArchetypeConfig
        from agent_fox.engine.sdk_params import resolve_model_tier

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                overrides={"fix_coder": PerArchetypeConfig(model_tier=tier)}
            )
        )
        # Coder should always be STANDARD (its registry default)
        coder_tier = resolve_model_tier(config, "coder")
        assert coder_tier == "STANDARD", (
            f"coder tier was affected by fix_coder override: got {coder_tier!r}"
        )
        # fix_coder should use the override
        fix_coder_tier = resolve_model_tier(config, "fix_coder")
        assert fix_coder_tier == tier, (
            f"fix_coder tier {fix_coder_tier!r} != override {tier!r}"
        )
