"""Unit tests for archetype model tier defaults.

Test Spec: TS-57-1 through TS-57-14, TS-57-E1 through TS-57-E3
Requirements: 57-REQ-1.1 through 57-REQ-3.E1, 57-REQ-4.1 through 57-REQ-4.3

Updated for spec 98 (reviewer consolidation):
- skeptic/oracle → reviewer (STANDARD base, fix-review mode = ADVANCED)
- verifier → STANDARD (was ADVANCED, per 98-REQ-6.1)
- auditor → reviewer:audit-review (STANDARD)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_fox.core.config import (
    AgentFoxConfig,
    ArchetypesConfig,
)
from agent_fox.core.errors import ConfigError
from agent_fox.core.models import ModelTier
from agent_fox.engine.session_lifecycle import NodeSessionRunner
from agent_fox.knowledge.db import KnowledgeDB

_MOCK_KB = MagicMock(spec=KnowledgeDB)


# ---------------------------------------------------------------------------
# TS-57-1/2 (updated): Reviewer base defaults to STANDARD
# Requirement: 57-REQ-1.1, 57-REQ-1.2 (updated by 98-REQ-1.1)
# ---------------------------------------------------------------------------


class TestReviewerDefaultStandard:
    """Verify reviewer archetype base defaults to STANDARD (was skeptic/oracle ADVANCED)."""

    def test_reviewer_default_tier_is_standard(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["reviewer"]
        assert entry.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-57-3 (updated): Verifier Default Tier Is STANDARD
# Requirement: 57-REQ-1.3 (updated by 98-REQ-6.1)
# ---------------------------------------------------------------------------


class TestVerifierDefaultStandard:
    """TS-57-3 (updated): Verify Verifier defaults to STANDARD (was ADVANCED)."""

    def test_verifier_default_tier_is_standard(self) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["verifier"]
        assert entry.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-57-4: Coder Default Tier Is STANDARD
# Requirement: 57-REQ-1.4
# ---------------------------------------------------------------------------


class TestCoderDefaultStandard:
    """TS-57-4: Verify Coder archetype defaults to STANDARD."""

    def test_coder_default_tier_is_standard(self) -> None:
        """ARCHETYPE_REGISTRY["coder"].default_model_tier must be STANDARD."""
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY["coder"]
        assert entry.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-57-5 (updated): All base archetypes default to STANDARD
# Requirement: 57-REQ-1.5 (updated by 98-REQ-1.1, 98-REQ-6.1)
# ---------------------------------------------------------------------------


class TestRemainingArchetypesStandard:
    """All base archetypes default to STANDARD tier."""

    @pytest.mark.parametrize("name", ["coder", "reviewer", "verifier"])
    def test_archetype_defaults_to_standard(self, name: str) -> None:
        from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

        entry = ARCHETYPE_REGISTRY[name]
        assert entry.default_model_tier == "STANDARD", (
            f"{name} should default to STANDARD, got {entry.default_model_tier!r}"
        )


# ---------------------------------------------------------------------------
# TS-57-6: Escalation Ladder Ceiling Is Always ADVANCED
# Requirement: 57-REQ-2.1
# Note: Tests using a Skeptic node. Currently Skeptic has STANDARD tier so
# the ceiling would be STANDARD before the fix.
# ---------------------------------------------------------------------------


def _write_plan(tmp_path: Path, archetype: str = "coder") -> Path:
    """Write a minimal plan.json for orchestrator tests."""
    plan = {
        "metadata": {
            "created_at": "2026-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.1.0",
        },
        "nodes": {
            "spec:1": {
                "id": "spec:1",
                "spec_name": "spec",
                "group_number": 1,
                "title": "Task 1",
                "optional": False,
                "status": "pending",
                "subtask_count": 0,
                "body": "",
                "archetype": archetype,
            }
        },
        "edges": [],
        "order": ["spec:1"],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    return plan_path


class TestCeilingAlwaysAdvanced:
    """TS-57-6: Ceiling is always ADVANCED regardless of archetype default tier."""

    @pytest.mark.asyncio
    async def test_ceiling_always_advanced_skeptic(self) -> None:
        """Skeptic node: ceiling must be ADVANCED even though default is STANDARD."""
        from agent_fox.engine.assessment import AssessmentManager

        mgr = AssessmentManager(
            retries_before_escalation=1,
        )

        await mgr.assess_node("spec:1", "skeptic")

        ladder = mgr.ladders["spec:1"]
        assert ladder._tier_ceiling == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-57-7: STANDARD Agent Escalates to ADVANCED
# Requirement: 57-REQ-2.2
# ---------------------------------------------------------------------------


class TestStandardEscalatesToAdvanced:
    """TS-57-7: A STANDARD-starting ladder escalates to ADVANCED after retries."""

    def test_standard_escalates_to_advanced(self) -> None:
        from agent_fox.routing.escalation import EscalationLadder

        ladder = EscalationLadder(
            starting_tier=ModelTier.STANDARD,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        ladder.record_failure()  # retry at STANDARD
        ladder.record_failure()  # exhausted STANDARD, escalate

        assert ladder.current_tier == ModelTier.ADVANCED
        assert ladder.is_exhausted is False


# ---------------------------------------------------------------------------
# TS-57-8: ADVANCED Agent Blocks After Exhaustion
# Requirement: 57-REQ-2.3
# ---------------------------------------------------------------------------


class TestAdvancedBlocksAfterExhaustion:
    """TS-57-8: An ADVANCED-starting ladder exhausts without escalation."""

    def test_advanced_blocks_after_exhaustion(self) -> None:
        from agent_fox.routing.escalation import EscalationLadder

        ladder = EscalationLadder(
            starting_tier=ModelTier.ADVANCED,
            tier_ceiling=ModelTier.ADVANCED,
            retries_before_escalation=1,
        )
        ladder.record_failure()  # retry at ADVANCED
        ladder.record_failure()  # exhausted, no higher tier

        assert ladder.is_exhausted is True
        assert ladder.current_tier == ModelTier.ADVANCED
        assert ladder.escalation_count == 0


# ---------------------------------------------------------------------------
# TS-57-9: Config Override Takes Precedence
# Requirement: 57-REQ-3.1
# ---------------------------------------------------------------------------


class TestConfigOverridePrecedence:
    """TS-57-9: Config override for an archetype takes precedence over registry."""

    def test_config_override_takes_precedence(self) -> None:
        """archetypes.models.coder = ADVANCED overrides STANDARD registry default."""
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"coder": "ADVANCED"}))
        runner = NodeSessionRunner("spec:1", config, knowledge_db=_MOCK_KB)
        # With override "ADVANCED", model should be Opus
        assert runner._resolved_model_id == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# TS-57-10: No Config Override Falls Back to Registry
# Requirement: 57-REQ-3.2
# ---------------------------------------------------------------------------


class TestNoOverrideUsesRegistry:
    """TS-57-10: Without config override, registry default is used."""

    def test_no_override_uses_registry_default(self) -> None:
        """Reviewer with no override should use registry default (STANDARD = Sonnet)."""
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={}))
        runner = NodeSessionRunner("spec:0", config, archetype="reviewer", knowledge_db=_MOCK_KB)
        assert runner._resolved_model_id == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# TS-57-11: Assessed Tier Overrides Everything
# Requirement: 57-REQ-3.3
# ---------------------------------------------------------------------------


class TestAssessedTierOverridesAll:
    """TS-57-11: assessed_tier overrides both config override and registry."""

    def test_assessed_tier_overrides_all(self) -> None:
        """assessed_tier=SIMPLE resolves to Haiku regardless of other config."""
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"coder": "ADVANCED"}))
        runner = NodeSessionRunner(
            "spec:1",
            config,
            archetype="coder",
            assessed_tier=ModelTier.SIMPLE,
            knowledge_db=_MOCK_KB,
        )
        assert runner._resolved_model_id == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# TS-57-E1: Unknown Archetype Falls Back to Coder
# Requirement: 57-REQ-1.E1
# ---------------------------------------------------------------------------


class TestUnknownArchetypeFallback:
    """TS-57-E1: Unknown archetype name falls back to Coder entry."""

    def test_unknown_archetype_returns_coder(self) -> None:
        from agent_fox.session.archetypes import get_archetype

        entry = get_archetype("unknown_archetype_xyz")
        assert entry.name == "coder"
        # After fix, coder defaults to STANDARD
        assert entry.default_model_tier == "STANDARD"


# ---------------------------------------------------------------------------
# TS-57-E2: Assessment Pipeline Failure Uses Default + ADVANCED Ceiling
# Requirement: 57-REQ-2.E1
# ---------------------------------------------------------------------------


class TestPipelineFailureFallback:
    """TS-57-E2: Failing pipeline uses archetype default as starting tier."""

    @pytest.mark.asyncio
    async def test_pipeline_failure_uses_default_with_advanced_ceiling(self) -> None:
        """Coder node without pipeline: starting=STANDARD (archetype default), ceiling=ADVANCED."""
        from agent_fox.engine.assessment import AssessmentManager

        mgr = AssessmentManager(
            retries_before_escalation=1,
        )

        await mgr.assess_node("spec:1", "coder")

        ladder = mgr.ladders["spec:1"]
        # starting_tier = coder.default (STANDARD), ceiling = ADVANCED (hardcoded)
        assert ladder.current_tier == ModelTier.STANDARD
        assert ladder._tier_ceiling == ModelTier.ADVANCED


# ---------------------------------------------------------------------------
# TS-57-E3: Invalid Config Tier Raises ConfigError
# Requirement: 57-REQ-3.E1
# ---------------------------------------------------------------------------


class TestInvalidConfigTierRaises:
    """TS-57-E3: Invalid tier name in config raises ConfigError."""

    def test_invalid_config_tier_raises_config_error(self) -> None:
        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={"coder": "INVALID_TIER"}))
        with pytest.raises(ConfigError):
            NodeSessionRunner("spec:1", config, archetype="coder", knowledge_db=_MOCK_KB)


# ---------------------------------------------------------------------------
# TS-57-12: Documentation Lists Default Tiers
# Requirement: 57-REQ-4.1
# ---------------------------------------------------------------------------


class TestDocsListDefaultTiers:
    """TS-57-12: archetypes.md lists default model tier for each archetype."""

    def test_docs_contain_advanced_and_standard(self) -> None:
        docs_path = Path("docs/archetypes.md")
        assert docs_path.exists(), "docs/archetypes.md must exist"
        content = docs_path.read_text()
        assert "ADVANCED" in content
        assert "STANDARD" in content

    def test_docs_show_reviewer_archetype(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        # Reviewer must appear in the docs
        assert "reviewer" in content.lower(), "reviewer not found in docs/archetypes.md"

    def test_docs_show_coder_as_standard(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        # Find the Coder section
        coder_idx = content.lower().find("## coder")
        assert coder_idx != -1, "## Coder section not found in docs"
        coder_section = content[coder_idx : coder_idx + 600]
        assert "STANDARD" in coder_section, "Expected STANDARD in Coder section of docs/archetypes.md"


# ---------------------------------------------------------------------------
# TS-57-13: Documentation Describes Config Override
# Requirement: 57-REQ-4.2
# ---------------------------------------------------------------------------


class TestDocsDescribeConfigOverride:
    """TS-57-13: archetypes.md explains how to override tiers via config.toml."""

    def test_docs_mention_models_config_key(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        assert "models" in content, "docs/archetypes.md must mention 'models' config key"

    def test_docs_mention_config(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        assert "config" in content.lower(), "docs/archetypes.md must mention config"


# ---------------------------------------------------------------------------
# TS-57-14: Documentation Explains Escalation
# Requirement: 57-REQ-4.3
# ---------------------------------------------------------------------------


class TestDocsExplainEscalation:
    """TS-57-14: archetypes.md explains retry-then-escalate behavior."""

    def test_docs_mention_escalation(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        assert "escalat" in content.lower(), "docs/archetypes.md must describe escalation behavior"

    def test_docs_mention_retry(self) -> None:
        docs_path = Path("docs/archetypes.md")
        content = docs_path.read_text()
        assert "retr" in content.lower(), "docs/archetypes.md must describe retry behavior (retry/retries)"
