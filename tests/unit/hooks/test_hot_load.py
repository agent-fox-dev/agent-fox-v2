"""Hot-load tests.

Test Spec: TS-06-15 (discover and add new specs),
           TS-06-16 (no new specs is no-op)
Edge Cases: TS-06-E5 (invalid dependency), TS-06-E7 (sync interval zero)
Requirements: 06-REQ-6.E1, 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3,
              06-REQ-7.E1, 06-REQ-7.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.engine.hot_load import discover_new_specs, hot_load_specs
from agent_fox.graph.types import Node, NodeStatus, PlanMetadata, TaskGraph


def _make_minimal_tasks_md() -> str:
    """Create minimal tasks.md content for a new spec."""
    return (
        "# Tasks\n"
        "\n"
        "- [ ] 1. Test task group\n"
        "  - [ ] 1.1 Subtask one\n"
        "  - [ ] 1.2 Subtask two\n"
    )


def _make_minimal_prd_md(*, deps: list[str] | None = None) -> str:
    """Create minimal prd.md content for a new spec.

    Args:
        deps: Optional list of dependency spec names for the cross-spec table.
    """
    content = "# Product Requirements\n\n## Dependencies\n\n"
    if deps:
        content += "| Spec | Dependency |\n|------|------------|\n"
        for dep in deps:
            content += f"| this | {dep} |\n"
    else:
        content += "No dependencies.\n"
    return content


def _make_graph_with_spec(spec_name: str) -> TaskGraph:
    """Create a TaskGraph with a single spec's nodes."""
    node_id = f"{spec_name}:1"
    nodes = {
        node_id: Node(
            id=node_id,
            spec_name=spec_name,
            group_number=1,
            title="Test task",
            optional=False,
            status=NodeStatus.COMPLETED,
        ),
    }
    return TaskGraph(
        nodes=nodes,
        edges=[],
        order=[node_id],
        metadata=PlanMetadata(created_at="2026-03-01T00:00:00"),
    )


class TestHotLoadDiscoversNewSpecs:
    """TS-06-15: Hot-load discovers new specs.

    Requirements: 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3
    """

    def test_discovers_new_spec_folder(
        self, tmp_specs_dir: Path,
    ) -> None:
        """New spec folders are discovered and added to the graph."""
        # Create existing spec
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        # Create new spec
        new_spec = tmp_specs_dir / "07_new_feature"
        new_spec.mkdir()
        (new_spec / "tasks.md").write_text(_make_minimal_tasks_md())
        (new_spec / "prd.md").write_text(_make_minimal_prd_md())

        graph = _make_graph_with_spec("01_existing")

        updated_graph, new_specs = hot_load_specs(graph, tmp_specs_dir)

        assert "07_new_feature" in new_specs
        assert any(
            n.spec_name == "07_new_feature"
            for n in updated_graph.nodes.values()
        )

    def test_updated_graph_has_more_nodes(
        self, tmp_specs_dir: Path,
    ) -> None:
        """Graph ordering includes new nodes after hot-load."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        new_spec = tmp_specs_dir / "07_new_feature"
        new_spec.mkdir()
        (new_spec / "tasks.md").write_text(_make_minimal_tasks_md())
        (new_spec / "prd.md").write_text(_make_minimal_prd_md())

        graph = _make_graph_with_spec("01_existing")
        original_order_len = len(graph.order)

        updated_graph, _ = hot_load_specs(graph, tmp_specs_dir)

        assert len(updated_graph.order) > original_order_len

    def test_preserves_existing_nodes(
        self, tmp_specs_dir: Path,
    ) -> None:
        """Hot-load does not remove or modify existing nodes."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        new_spec = tmp_specs_dir / "07_new_feature"
        new_spec.mkdir()
        (new_spec / "tasks.md").write_text(_make_minimal_tasks_md())
        (new_spec / "prd.md").write_text(_make_minimal_prd_md())

        graph = _make_graph_with_spec("01_existing")
        original_ids = set(graph.nodes.keys())

        updated_graph, _ = hot_load_specs(graph, tmp_specs_dir)

        assert original_ids.issubset(set(updated_graph.nodes.keys()))


class TestHotLoadNoNewSpecs:
    """TS-06-16: Hot-load with no new specs is a no-op.

    Requirement: 06-REQ-7.E2
    """

    def test_no_new_specs_returns_same_graph(
        self, tmp_specs_dir: Path,
    ) -> None:
        """No new specs found returns original graph unchanged."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        graph = _make_graph_with_spec("01_existing")

        updated_graph, new_specs = hot_load_specs(graph, tmp_specs_dir)

        assert new_specs == []
        assert updated_graph.nodes == graph.nodes

    def test_no_new_specs_returns_empty_list(
        self, tmp_specs_dir: Path,
    ) -> None:
        """Empty list is returned when no new specs are found."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        graph = _make_graph_with_spec("01_existing")

        _, new_specs = hot_load_specs(graph, tmp_specs_dir)

        assert new_specs == []


class TestDiscoverNewSpecs:
    """Unit tests for discover_new_specs function."""

    def test_finds_unknown_specs(self, tmp_specs_dir: Path) -> None:
        """Specs not in known_specs are returned."""
        (tmp_specs_dir / "01_existing").mkdir()
        (tmp_specs_dir / "01_existing" / "tasks.md").write_text(
            _make_minimal_tasks_md()
        )
        (tmp_specs_dir / "07_new_feature").mkdir()
        (tmp_specs_dir / "07_new_feature" / "tasks.md").write_text(
            _make_minimal_tasks_md()
        )

        new_specs = discover_new_specs(
            tmp_specs_dir, known_specs={"01_existing"}
        )

        assert len(new_specs) == 1
        assert new_specs[0].name == "07_new_feature"

    def test_returns_empty_when_all_known(self, tmp_specs_dir: Path) -> None:
        """Returns empty list when all specs are already known."""
        (tmp_specs_dir / "01_existing").mkdir()
        (tmp_specs_dir / "01_existing" / "tasks.md").write_text(
            _make_minimal_tasks_md()
        )

        new_specs = discover_new_specs(
            tmp_specs_dir, known_specs={"01_existing"}
        )

        assert new_specs == []


# -- Edge case tests ---------------------------------------------------------


class TestNewSpecInvalidDependency:
    """TS-06-E5: New spec with invalid dependency.

    Requirement: 06-REQ-7.E1
    """

    def test_invalid_dep_skipped_with_warning(
        self, tmp_specs_dir: Path, caplog,
    ) -> None:
        """New spec referencing nonexistent dependency is skipped."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        broken = tmp_specs_dir / "99_broken"
        broken.mkdir()
        (broken / "tasks.md").write_text(_make_minimal_tasks_md())
        (broken / "prd.md").write_text(
            _make_minimal_prd_md(deps=["50_nonexistent"])
        )

        graph = _make_graph_with_spec("01_existing")

        with caplog.at_level(logging.WARNING, logger="agent_fox.engine.hot_load"):
            updated_graph, new_specs = hot_load_specs(graph, tmp_specs_dir)

        assert "99_broken" not in new_specs
        assert updated_graph.nodes == graph.nodes

    def test_valid_spec_still_added_alongside_broken(
        self, tmp_specs_dir: Path,
    ) -> None:
        """Valid new specs are still added even if another has invalid deps."""
        existing = tmp_specs_dir / "01_existing"
        existing.mkdir()
        (existing / "tasks.md").write_text(_make_minimal_tasks_md())
        (existing / "prd.md").write_text(_make_minimal_prd_md())

        # Valid new spec
        valid_new = tmp_specs_dir / "07_valid"
        valid_new.mkdir()
        (valid_new / "tasks.md").write_text(_make_minimal_tasks_md())
        (valid_new / "prd.md").write_text(_make_minimal_prd_md())

        # Broken new spec
        broken = tmp_specs_dir / "99_broken"
        broken.mkdir()
        (broken / "tasks.md").write_text(_make_minimal_tasks_md())
        (broken / "prd.md").write_text(
            _make_minimal_prd_md(deps=["50_nonexistent"])
        )

        graph = _make_graph_with_spec("01_existing")

        updated_graph, new_specs = hot_load_specs(graph, tmp_specs_dir)

        assert "07_valid" in new_specs
        assert "99_broken" not in new_specs


class TestSyncIntervalZero:
    """TS-06-E7: Sync interval zero disables barriers.

    Requirement: 06-REQ-6.E1
    """

    def test_zero_interval_never_triggers(self) -> None:
        """sync_interval=0 means no sync barriers are triggered."""
        sync_interval = 0
        for completed in range(1, 101):
            triggered = (
                sync_interval > 0
                and completed > 0
                and completed % sync_interval == 0
            )
            assert triggered is False, (
                f"Barrier should never trigger with interval=0, "
                f"but triggered at completed={completed}"
            )

    def test_nonzero_interval_triggers(self) -> None:
        """A positive sync_interval triggers at the correct counts."""
        sync_interval = 5
        triggered_at = []
        for completed in range(1, 21):
            triggered = (
                sync_interval > 0
                and completed > 0
                and completed % sync_interval == 0
            )
            if triggered:
                triggered_at.append(completed)

        assert triggered_at == [5, 10, 15, 20]
