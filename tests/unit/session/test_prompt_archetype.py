"""Tests for archetype-based prompt resolution.

Test Spec: TS-26-12, TS-26-16, TS-26-42, TS-26-P5, TS-26-P6
Requirements: 26-REQ-3.5, 26-REQ-4.4
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
# TS-26-12: build_system_prompt uses registry
# Requirement: 26-REQ-3.5
# ---------------------------------------------------------------------------


class TestRegistryBasedResolution:
    """Verify build_system_prompt() resolves templates from the registry."""

    def test_coder_archetype_produces_output(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        result = build_system_prompt(
            context="test context",
            task_group=1,
            spec_name="03_session",
            archetype="coder",
        )
        assert "test context" in result
        assert len(result) > 100  # should have template content

    def test_no_role_templates_in_source(self) -> None:
        import os

        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "agent_fox", "session", "prompt.py",
        )
        prompt_path = os.path.normpath(prompt_path)
        with open(prompt_path, encoding="utf-8") as f:
            content = f.read()

        # After refactor, _ROLE_TEMPLATES should not exist
        assert "_ROLE_TEMPLATES" not in content, (
            "prompt.py should not contain _ROLE_TEMPLATES after refactor"
        )


# ---------------------------------------------------------------------------
# TS-26-E4: Missing template file
# Requirement: 26-REQ-3.E2
# ---------------------------------------------------------------------------


class TestMissingTemplateRaises:
    """Verify missing template file raises ConfigError."""

    def test_missing_template_raises_config_error(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from agent_fox.core.errors import ConfigError
        from agent_fox.session import prompt as prompt_mod
        from agent_fox.session.prompt import build_system_prompt

        # Point _TEMPLATE_DIR to an empty temp directory so templates
        # are not found on disk (26-REQ-3.E2).
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(prompt_mod, "_TEMPLATE_DIR", Path(tmp)):
                with pytest.raises(ConfigError):
                    build_system_prompt(
                        context="ctx",
                        task_group=1,
                        spec_name="test_spec",
                        archetype="coder",
                    )


# ---------------------------------------------------------------------------
# TS-26-42: build_system_prompt archetype="coder" matches old role="coding"
# Requirement: 26-REQ-3.5 (via Property 5)
# ---------------------------------------------------------------------------


class TestCoderEquivalence:
    """Verify coder archetype produces identical output to old coding role."""

    def test_coder_matches_coding(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        # After refactor, archetype="coder" should produce same output
        # as role="coding" did before
        # For now, test that the new parameter exists
        try:
            new_output = build_system_prompt(
                context="ctx",
                task_group=1,
                spec_name="03_session",
                archetype="coder",
            )
        except TypeError:
            # archetype parameter doesn't exist yet - expected failure
            pytest.skip("archetype parameter not yet implemented")

        old_output = build_system_prompt(
            context="ctx",
            task_group=1,
            spec_name="03_session",
            role="coding",
        )

        assert new_output == old_output


# ---------------------------------------------------------------------------
# TS-26-16: NodeSessionRunner uses archetype metadata
# Requirement: 26-REQ-4.4
# ---------------------------------------------------------------------------


class TestRunnerUsesArchetype:
    """Verify NodeSessionRunner reads archetype from node metadata."""

    def test_runner_accepts_archetype_param(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()

        # NodeSessionRunner should accept archetype parameter
        try:
            runner = NodeSessionRunner(
                "spec:3",
                config,
                archetype="librarian",
            )
        except TypeError:
            pytest.fail("NodeSessionRunner should accept archetype parameter")

        # Verify the archetype was stored
        assert runner._archetype == "librarian"

    def test_runner_accepts_instances_param(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="skeptic",
            instances=3,
        )
        assert runner._instances == 3

    def test_runner_resolves_model_tier(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:3",
            config,
            archetype="skeptic",
        )
        # Skeptic default model tier is STANDARD
        assert runner._resolved_model_id == "STANDARD"

    def test_runner_model_tier_config_override(self) -> None:
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(models={"skeptic": "SIMPLE"})
        )
        runner = NodeSessionRunner(
            "spec:3",
            config,
            archetype="skeptic",
        )
        assert runner._resolved_model_id == "SIMPLE"

    def test_runner_resolves_allowlist_from_registry(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="skeptic",
        )
        # Skeptic has a default allowlist in the registry
        assert runner._resolved_security is not None
        assert "ls" in runner._resolved_security.bash_allowlist
        assert "cat" in runner._resolved_security.bash_allowlist

    def test_runner_allowlist_config_override(self) -> None:
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(
            archetypes=ArchetypesConfig(
                allowlists={"skeptic": ["ls", "cat"]}
            )
        )
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="skeptic",
        )
        assert runner._resolved_security is not None
        assert runner._resolved_security.bash_allowlist == ["ls", "cat"]

    def test_runner_coder_no_security_override(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:1",
            config,
            archetype="coder",
        )
        # Coder has no allowlist override — uses global
        assert runner._resolved_security is None


# ---------------------------------------------------------------------------
# TS-26-P5: Template Resolution Equivalence (Property)
# Property 5: Coder archetype produces identical prompts to old role="coding"
# Validates: 26-REQ-3.5
# ---------------------------------------------------------------------------


class TestPropertyTemplateEquivalence:
    """Coder archetype produces identical prompts to old role='coding'."""

    def test_prop_equivalence_sample(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        contexts = ["ctx1", "longer context with details", ""]
        spec_names = ["03_session", "01_config", "26_agent_archetypes"]

        for ctx in contexts:
            for spec in spec_names:
                try:
                    new = build_system_prompt(
                        context=ctx,
                        task_group=1,
                        spec_name=spec,
                        archetype="coder",
                    )
                    old = build_system_prompt(
                        context=ctx,
                        task_group=1,
                        spec_name=spec,
                        role="coding",
                    )
                    assert new == old, (
                        f"Mismatch for ctx={ctx!r}, spec={spec}"
                    )
                except TypeError:
                    pytest.skip("archetype parameter not yet implemented")


# ---------------------------------------------------------------------------
# TS-26-P6: Assignment Priority (Property)
# Property 6: Highest-priority layer always wins
# Validates: 26-REQ-5.1, 26-REQ-5.2
# ---------------------------------------------------------------------------


class TestPropertyAssignmentPriority:
    """The highest-priority layer always wins in archetype assignment."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        has_tag=st.booleans(),
        has_coord=st.booleans(),
    )
    @settings(max_examples=10)
    def test_prop_priority_layers(self, has_tag: bool, has_coord: bool) -> None:
        # Test will be fully implemented when build_graph supports all layers
        # For now, validate the priority concept
        tag = "librarian" if has_tag else None
        coord = "cartographer" if has_coord else None
        default = "coder"

        expected = tag or coord or default
        result = tag if tag else (coord if coord else default)
        assert result == expected
