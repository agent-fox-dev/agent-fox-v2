"""Unit tests for spec 63: plan always rebuilds, dead code removed.

These tests verify that:
- Cache-related functions are removed from agent_fox.cli.plan
- PlanMetadata no longer has specs_hash or config_hash fields
- Old plan.json files containing those fields still load without error

Test Spec: TS-63-5, TS-63-6, TS-63-E1
Requirements: 63-REQ-3.1, 63-REQ-3.2, 63-REQ-3.E1
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import agent_fox.cli.plan as plan_mod
from agent_fox.graph.persistence import load_plan
from agent_fox.graph.types import PlanMetadata


class TestDeadFunctionsRemoved:
    """TS-63-5: Cache-related functions removed from the plan module."""

    def test_compute_specs_hash_not_in_module(self) -> None:
        """_compute_specs_hash must not exist in agent_fox.cli.plan (63-REQ-3.1)."""
        assert not hasattr(plan_mod, "_compute_specs_hash"), (
            "_compute_specs_hash still exists in plan module — remove it (63-REQ-3.1)"
        )

    def test_compute_config_hash_not_in_module(self) -> None:
        """_compute_config_hash must not exist in agent_fox.cli.plan (63-REQ-3.1)."""
        assert not hasattr(plan_mod, "_compute_config_hash"), (
            "_compute_config_hash still exists in plan module — remove it (63-REQ-3.1)"
        )

    def test_cache_matches_request_not_in_module(self) -> None:
        """_cache_matches_request must not exist in agent_fox.cli.plan (63-REQ-3.1)."""
        assert not hasattr(plan_mod, "_cache_matches_request"), (
            "_cache_matches_request still exists in plan module — remove it (63-REQ-3.1)"
        )


class TestPlanMetadataFieldsRemoved:
    """TS-63-6: PlanMetadata no longer exposes specs_hash or config_hash."""

    def test_specs_hash_field_not_in_plan_metadata(self) -> None:
        """PlanMetadata must not declare a specs_hash field (63-REQ-3.2)."""
        field_names = {f.name for f in dataclasses.fields(PlanMetadata)}
        assert "specs_hash" not in field_names, "specs_hash is still a field on PlanMetadata — remove it (63-REQ-3.2)"

    def test_config_hash_field_not_in_plan_metadata(self) -> None:
        """PlanMetadata must not declare a config_hash field (63-REQ-3.2)."""
        field_names = {f.name for f in dataclasses.fields(PlanMetadata)}
        assert "config_hash" not in field_names, "config_hash is still a field on PlanMetadata — remove it (63-REQ-3.2)"


def _write_old_plan_json(plan_path: Path, *, specs_hash: str, config_hash: str) -> None:
    """Write a plan.json in the legacy format that includes hash fields in metadata."""
    data = {
        "nodes": {
            "old_spec:1": {
                "id": "old_spec:1",
                "spec_name": "old_spec",
                "group_number": 1,
                "title": "Old task group",
                "optional": False,
                "status": "pending",
                "subtask_count": 1,
                "body": "",
                "archetype": "coder",
                "instances": 1,
            }
        },
        "edges": [],
        "order": ["old_spec:1"],
        "metadata": {
            "created_at": "2025-01-01T00:00:00",
            "fast_mode": False,
            "filtered_spec": None,
            "version": "0.0.1",
            "specs_hash": specs_hash,
            "config_hash": config_hash,
        },
    }
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestOldPlanJsonBackwardCompatibility:
    """TS-63-E1: Old plan.json with legacy hash fields loads without error."""

    def test_old_plan_loads_without_error(self, tmp_path: Path) -> None:
        """load_plan() succeeds on plan.json that contains legacy hash fields."""
        plan_path = tmp_path / "plan.json"
        _write_old_plan_json(plan_path, specs_hash="abc123", config_hash="def456")

        graph = load_plan(plan_path)

        assert graph is not None

    def test_loaded_metadata_has_no_specs_hash_attribute(self, tmp_path: Path) -> None:
        """Loaded PlanMetadata does not expose specs_hash attribute (63-REQ-3.2)."""
        plan_path = tmp_path / "plan.json"
        _write_old_plan_json(plan_path, specs_hash="abc123", config_hash="def456")

        graph = load_plan(plan_path)

        assert graph is not None
        assert not hasattr(graph.metadata, "specs_hash"), (
            "specs_hash attribute still present on loaded PlanMetadata — "
            "remove the field from PlanMetadata (63-REQ-3.2)"
        )

    def test_loaded_metadata_has_no_config_hash_attribute(self, tmp_path: Path) -> None:
        """Loaded PlanMetadata does not expose config_hash attribute (63-REQ-3.2)."""
        plan_path = tmp_path / "plan.json"
        _write_old_plan_json(plan_path, specs_hash="abc123", config_hash="def456")

        graph = load_plan(plan_path)

        assert graph is not None
        assert not hasattr(graph.metadata, "config_hash"), (
            "config_hash attribute still present on loaded PlanMetadata — "
            "remove the field from PlanMetadata (63-REQ-3.2)"
        )
