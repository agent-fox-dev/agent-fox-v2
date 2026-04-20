"""Property tests asserting coordinator is absent from all archetype collections.

Test Spec: TS-62-P1, TS-62-P2
Requirements: 62-REQ-1.1, 62-REQ-5.1, 62-REQ-6.E1

Updated after legacy template path removal (issue #342).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# -------------------------------------------------------------------
# TS-62-P1: No Coordinator in Any Archetype Collection
# Property 1 from design.md
# Validates: 62-REQ-1.1, 62-REQ-5.1
# -------------------------------------------------------------------


class TestNoCoordinatorInAnyCollection:
    """TS-62-P1: Coordinator absent from all archetype collections."""

    def test_no_coordinator_in_registry(self) -> None:
        """ARCHETYPE_REGISTRY must not contain 'coordinator'."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert "coordinator" not in set(ARCHETYPE_REGISTRY.keys())

    def test_no_coordinator_in_known_archetypes(self) -> None:
        """Parser's _KNOWN_ARCHETYPES must not contain 'coordinator'."""
        from agent_fox.spec.parser import _KNOWN_ARCHETYPES

        assert "coordinator" not in _KNOWN_ARCHETYPES

    def test_no_coordinator_in_any_collection(self) -> None:
        """Coordinator absent from every archetype enumeration simultaneously."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY
        from agent_fox.spec.parser import _KNOWN_ARCHETYPES

        all_collections = [
            set(ARCHETYPE_REGISTRY.keys()),
            _KNOWN_ARCHETYPES,
        ]
        for collection in all_collections:
            assert "coordinator" not in collection, f"'coordinator' found in collection: {collection}"


# -------------------------------------------------------------------
# TS-62-P2: Config Tolerance for Extra Model Fields
# Property 6 from design.md
# Validates: 62-REQ-6.E1
# -------------------------------------------------------------------


class TestConfigToleranceExtraModelFields:
    """TS-62-P2: Any TOML config with extra [models] fields loads without error."""

    @pytest.mark.parametrize(
        "field_name",
        ["coordinator", "planner", "reviewer", "analyzer"],
    )
    def test_config_tolerance_extra_model_fields(self, tmp_path: Path, field_name: str) -> None:
        """Config with extra [models] field loads and the field is not present."""
        from agent_fox.core.config import load_config

        config_file = tmp_path / f"config_{field_name}.toml"
        config_file.write_text(f'[models]\n{field_name} = "STANDARD"\n')

        from agent_fox.core.config import ModelConfig

        # Must not raise
        load_config(path=config_file)

        # Extra field must be silently ignored (not present on model class)
        assert field_name not in ModelConfig.model_fields, (
            f"Extra field '{field_name}' should be silently ignored by ModelConfig"
        )
