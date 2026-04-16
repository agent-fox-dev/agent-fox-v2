"""Unit tests for spec 63: plan always rebuilds, dead code removed.

These tests verify that:
- Cache-related functions are removed from agent_fox.cli.plan
- PlanMetadata no longer has specs_hash or config_hash fields
- DB-based persistence works correctly (replaces legacy plan.json tests)

Test Spec: TS-63-5, TS-63-6, TS-63-E1
Requirements: 63-REQ-3.1, 63-REQ-3.2, 63-REQ-3.E1
"""

from __future__ import annotations

import dataclasses

import duckdb

import agent_fox.cli.plan as plan_mod
from agent_fox.graph.persistence import load_plan, save_plan
from agent_fox.graph.types import Node, PlanMetadata, TaskGraph
from agent_fox.knowledge.migrations import run_migrations


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


def _save_old_plan_to_db(conn: duckdb.DuckDBPyConnection) -> None:
    """Save a plan to DuckDB that mimics what the old plan.json format contained."""
    graph = TaskGraph(
        nodes={
            "old_spec:1": Node(
                id="old_spec:1",
                spec_name="old_spec",
                group_number=1,
                title="Old task group",
                optional=False,
                subtask_count=1,
                body="",
                archetype="coder",
                instances=1,
            )
        },
        edges=[],
        order=["old_spec:1"],
        metadata=PlanMetadata(
            created_at="2025-01-01T00:00:00",
            fast_mode=False,
            filtered_spec=None,
            version="0.0.1",
        ),
    )
    save_plan(graph, conn)


class TestDBPlanPersistence:
    """TS-63-E1: DB-based plan persistence works correctly (replaces legacy plan.json tests)."""

    def test_plan_loads_from_db(self) -> None:
        """load_plan() succeeds on a plan saved to DuckDB."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)
        _save_old_plan_to_db(conn)

        graph = load_plan(conn)

        assert graph is not None
        conn.close()

    def test_loaded_metadata_has_no_specs_hash_attribute(self) -> None:
        """Loaded PlanMetadata does not expose specs_hash attribute (63-REQ-3.2)."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)
        _save_old_plan_to_db(conn)

        graph = load_plan(conn)

        assert graph is not None
        assert not hasattr(graph.metadata, "specs_hash"), (
            "specs_hash attribute still present on loaded PlanMetadata — "
            "remove the field from PlanMetadata (63-REQ-3.2)"
        )
        conn.close()

    def test_loaded_metadata_has_no_config_hash_attribute(self) -> None:
        """Loaded PlanMetadata does not expose config_hash attribute (63-REQ-3.2)."""
        conn = duckdb.connect(":memory:")
        run_migrations(conn)
        _save_old_plan_to_db(conn)

        graph = load_plan(conn)

        assert graph is not None
        assert not hasattr(graph.metadata, "config_hash"), (
            "config_hash attribute still present on loaded PlanMetadata — "
            "remove the field from PlanMetadata (63-REQ-3.2)"
        )
        conn.close()
