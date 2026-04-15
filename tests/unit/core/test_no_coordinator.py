"""Tests asserting coordinator removal from core modules and templates.

Test Spec: TS-62-3, TS-62-8, TS-62-E1
Requirements: 62-REQ-2.1, 62-REQ-6.1, 62-REQ-6.E1
"""

from __future__ import annotations

from pathlib import Path

# -------------------------------------------------------------------
# TS-62-3: Coordinator Template Deleted
# Requirement: 62-REQ-2.1
# -------------------------------------------------------------------


class TestCoordinatorTemplateDeleted:
    """TS-62-3: Verify coordinator is not a registered archetype."""

    def test_coordinator_not_in_registry(self) -> None:
        """coordinator must not appear in the archetype registry."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "coordinator" not in ARCHETYPE_REGISTRY, (
            "coordinator should have been removed from the archetype registry"
        )


# -------------------------------------------------------------------
# TS-62-8: ModelConfig Has No Coordinator Field
# Requirement: 62-REQ-6.1
# -------------------------------------------------------------------


class TestModelConfigNoCoordinatorField:
    """TS-62-8: Verify ModelConfig does not have a coordinator field."""

    def test_model_config_no_coordinator_field(self) -> None:
        """ModelConfig must not declare a 'coordinator' field."""
        from agent_fox.core.config import ModelConfig

        assert "coordinator" not in ModelConfig.model_fields, (
            "ModelConfig still has a 'coordinator' field; it should be removed"
        )


# -------------------------------------------------------------------
# TS-62-E1: Config With Coordinator Field Loads Successfully
# Requirement: 62-REQ-6.E1
# -------------------------------------------------------------------


class TestConfigWithCoordinatorFieldLoadsOk:
    """TS-62-E1: TOML config with coordinator field loads without error."""

    def test_config_with_coordinator_loads_ok(self, tmp_path: Path) -> None:
        """A config file with coordinator under [models] loads successfully."""
        from agent_fox.core.config import load_config

        config_file = tmp_path / "config.toml"
        config_file.write_text('[models]\ncoordinator = "STANDARD"\n')

        from agent_fox.core.config import ModelConfig

        # Must not raise
        load_config(path=config_file)

        # The coordinator field must be silently ignored (not present on model)
        assert "coordinator" not in ModelConfig.model_fields, "coordinator should be silently ignored by ModelConfig"
