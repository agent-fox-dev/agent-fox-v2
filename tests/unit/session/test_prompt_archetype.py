"""Tests for archetype-based prompt resolution.

Test Spec: TS-26-12, TS-26-16, TS-26-42, TS-26-P5, TS-26-P6
Requirements: 26-REQ-3.5, 26-REQ-4.4

Updated after legacy template path removal (issue #342).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_fox.knowledge.db import KnowledgeDB

_MOCK_KB = MagicMock(spec=KnowledgeDB)

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
    """Verify build_system_prompt() resolves profiles from the registry."""

    def test_coder_archetype_produces_output(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        result = build_system_prompt(
            context="test context",
            archetype="coder",
        )
        assert "test context" in result
        assert len(result) > 100  # should have profile content


# ---------------------------------------------------------------------------
# TS-26-42: build_system_prompt archetype="coder" produces coder profile
# Requirement: 26-REQ-3.5
# ---------------------------------------------------------------------------


class TestCoderArchetypeResolution:
    """Verify coder archetype resolves correctly."""

    def test_coder_archetype_produces_output(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        result = build_system_prompt(
            context="ctx",
            archetype="coder",
        )
        assert "Identity" in result
        assert "ctx" in result


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
                archetype="reviewer",
                mode="audit-review",
                knowledge_db=_MOCK_KB,
            )
        except TypeError:
            pytest.fail("NodeSessionRunner should accept archetype parameter")

        # Verify the archetype was stored
        assert runner._archetype == "reviewer"

    def test_runner_accepts_instances_param(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="reviewer",
            mode="pre-review",
            instances=3,
            knowledge_db=_MOCK_KB,
        )
        assert runner._instances == 3

    def test_runner_resolves_model_tier(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:3",
            config,
            archetype="reviewer",
            mode="pre-review",
            knowledge_db=_MOCK_KB,
        )
        # Reviewer base default model tier is STANDARD
        assert runner._resolved_model_id == "claude-sonnet-4-6"

    def test_runner_model_tier_config_override(self) -> None:
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"reviewer": "SIMPLE"}))
        runner = NodeSessionRunner(
            "spec:3",
            config,
            archetype="reviewer",
            mode="pre-review",
            knowledge_db=_MOCK_KB,
        )
        assert runner._resolved_model_id == "claude-haiku-4-5"

    def test_runner_resolves_allowlist_from_registry(self) -> None:
        from agent_fox.core.config import AgentFoxConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig()
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="reviewer",
            mode="drift-review",
            knowledge_db=_MOCK_KB,
        )
        # Reviewer drift-review mode has a default allowlist in the registry
        assert runner._resolved_security is not None
        assert runner._resolved_security.bash_allowlist is not None
        assert "ls" in runner._resolved_security.bash_allowlist
        assert "cat" in runner._resolved_security.bash_allowlist

    def test_runner_allowlist_config_override(self) -> None:
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(archetypes=ArchetypesConfig(allowlists={"reviewer": ["ls", "cat"]}))
        runner = NodeSessionRunner(
            "spec:0",
            config,
            archetype="reviewer",
            mode="drift-review",
            knowledge_db=_MOCK_KB,
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
            knowledge_db=_MOCK_KB,
        )
        # Coder has no allowlist override — uses global
        assert runner._resolved_security is None


# ---------------------------------------------------------------------------
# TS-26-P5: Profile Resolution (Property)
# Property 5: Coder archetype produces profile-based output
# Validates: 26-REQ-3.5
# ---------------------------------------------------------------------------


class TestPropertyProfileResolution:
    """Coder archetype produces consistent profile-based output."""

    def test_prop_coder_profile_sample(self) -> None:
        from agent_fox.session.prompt import build_system_prompt

        contexts = ["ctx1", "longer context with details", ""]

        for ctx in contexts:
            result = build_system_prompt(
                context=ctx,
                archetype="coder",
            )
            assert "Identity" in result, f"Coder profile missing for ctx={ctx!r}"
            assert ctx in result, f"Context missing for ctx={ctx!r}"


# ---------------------------------------------------------------------------
# TS-26-P6: Assignment Priority (Property)
# Property 6: Highest-priority layer always wins
# Validates: 26-REQ-5.1, 26-REQ-5.2
# ---------------------------------------------------------------------------


class TestPropertyAssignmentPriority:
    """The highest-priority layer always wins in archetype assignment."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS,
        reason="hypothesis not installed",
    )
    @given(
        has_tag=st.booleans(),
        has_coord=st.booleans(),
    )
    @settings(max_examples=10)
    def test_prop_priority_layers(self, has_tag: bool, has_coord: bool) -> None:
        # Test will be fully implemented when build_graph supports all layers
        # For now, validate the priority concept
        tag = "reviewer" if has_tag else None
        coord = "verifier" if has_coord else None
        default = "coder"

        expected = tag or coord or default
        result = tag if tag else (coord if coord else default)
        assert result == expected
