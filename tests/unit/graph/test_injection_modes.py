"""Unit/integration tests for reviewer-mode injection logic.

Covers:
- collect_enabled_auto_pre returns reviewer mode entries (TS-98-8)
- ensure_graph_archetypes creates reviewer mode nodes (TS-98-9)
- Drift-review gating when spec has no existing code (TS-98-10)

Test Spec: TS-98-8, TS-98-9, TS-98-10
Requirements: 98-REQ-4.1, 98-REQ-4.2, 98-REQ-4.3, 98-REQ-4.4, 98-REQ-4.5,
              98-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coder_graph(spec_name: str = "myspec", group_number: int = 1):
    """Build a minimal TaskGraph with one coder node."""
    from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

    node = Node(
        id=f"{spec_name}:{group_number}",
        spec_name=spec_name,
        group_number=group_number,
        title="Test Task",
        optional=False,
        archetype="coder",
    )
    return TaskGraph(
        nodes={node.id: node},
        edges=[],
        order=[node.id],
        metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
    )


def _make_reviewer_config(reviewer: bool = True):
    """Build a minimal ArchetypesConfig with reviewer enabled/disabled."""
    from agent_fox.core.config import ArchetypesConfig

    return ArchetypesConfig(reviewer=reviewer)


# ---------------------------------------------------------------------------
# TS-98-8: collect_enabled_auto_pre Returns Reviewer Modes
# Requirements: 98-REQ-4.1, 98-REQ-4.5
# ---------------------------------------------------------------------------


class TestCollectEnabledAutoPreReviewerModes:
    """Verify auto_pre collection returns reviewer mode entries."""

    def test_auto_pre_reviewer_entries(self) -> None:
        """TS-98-8: collect_enabled_auto_pre returns reviewer entries with modes."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        config = _make_reviewer_config(reviewer=True)
        entries = collect_enabled_auto_pre(config)

        # Extract (name, mode) pairs
        try:
            names_and_modes = [(e.name, e.mode) for e in entries]
        except AttributeError as err:
            pytest.fail(
                f"ArchetypeEntry in injection.py lacks 'mode' field: {err}"
            )

        assert ("reviewer", "pre-review") in names_and_modes, (
            f"Expected ('reviewer', 'pre-review') in entries, got {names_and_modes}"
        )
        assert ("reviewer", "drift-review") in names_and_modes, (
            f"Expected ('reviewer', 'drift-review') in entries, got {names_and_modes}"
        )

    def test_no_old_archetype_names(self) -> None:
        """TS-98-8: collect_enabled_auto_pre returns no skeptic or oracle entries."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        config = _make_reviewer_config(reviewer=True)
        entries = collect_enabled_auto_pre(config)

        old_names = {e.name for e in entries}
        assert "skeptic" not in old_names, (
            f"'skeptic' should not be in auto_pre entries after consolidation, "
            f"got {old_names}"
        )
        assert "oracle" not in old_names, (
            f"'oracle' should not be in auto_pre entries after consolidation, "
            f"got {old_names}"
        )

    def test_reviewer_enable_check(self) -> None:
        """TS-98-8 (4.5): is_archetype_enabled checks archetypes.reviewer for all reviewer modes."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        # When reviewer=False, no reviewer entries returned
        config_off = _make_reviewer_config(reviewer=False)
        entries_off = collect_enabled_auto_pre(config_off)
        reviewer_names = [e.name for e in entries_off if e.name == "reviewer"]
        assert len(reviewer_names) == 0, (
            f"Expected no reviewer entries when reviewer=False, got {reviewer_names}"
        )


# ---------------------------------------------------------------------------
# TS-98-9: Injection Creates Reviewer Mode Nodes
# Requirements: 98-REQ-4.2, 98-REQ-4.3
# ---------------------------------------------------------------------------


class TestInjectReviewerModeNodes:
    """Verify ensure_graph_archetypes creates reviewer mode nodes."""

    def test_inject_reviewer_nodes(self) -> None:
        """TS-98-9: ensure_graph_archetypes creates reviewer:pre-review node."""
        from agent_fox.graph.injection import ensure_graph_archetypes

        graph = _make_coder_graph()
        # Pass ArchetypesConfig directly (that's what ensure_graph_archetypes expects)
        config = _make_reviewer_config(reviewer=True)
        ensure_graph_archetypes(graph, config)

        reviewer_nodes = [
            n for n in graph.nodes.values() if n.archetype == "reviewer"
        ]
        assert len(reviewer_nodes) >= 1, (
            f"Expected at least one reviewer node, got nodes: "
            f"{[(n.archetype, n.mode) for n in graph.nodes.values()]}"
        )

        modes = {n.mode for n in reviewer_nodes}
        assert "pre-review" in modes, (
            f"Expected 'pre-review' mode in reviewer nodes, got modes: {modes}"
        )

    def test_no_old_archetype_nodes(self) -> None:
        """TS-98-9: After injection, no nodes with archetype 'skeptic' or 'oracle'."""
        from agent_fox.graph.injection import ensure_graph_archetypes

        graph = _make_coder_graph()
        # Pass ArchetypesConfig directly (that's what ensure_graph_archetypes expects)
        config = _make_reviewer_config(reviewer=True)
        ensure_graph_archetypes(graph, config)

        all_archetypes = {n.archetype for n in graph.nodes.values()}
        assert "skeptic" not in all_archetypes, (
            f"'skeptic' should not appear as a node archetype after consolidation, "
            f"got archetypes: {all_archetypes}"
        )
        assert "oracle" not in all_archetypes, (
            f"'oracle' should not appear as a node archetype after consolidation, "
            f"got archetypes: {all_archetypes}"
        )


# ---------------------------------------------------------------------------
# TS-98-10: Drift-review Gating
# Requirement: 98-REQ-4.4
# ---------------------------------------------------------------------------


class TestDriftReviewGating:
    """Verify drift-review is skipped when spec has no existing code."""

    def test_drift_gating_no_code_spec(self, tmp_path: Path) -> None:
        """TS-98-10: collect_enabled_auto_pre skips drift-review for no-code spec."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        # Create a spec dir with a design.md that has no (modified) file references
        spec_dir = tmp_path / "00_nocode"
        spec_dir.mkdir()
        (spec_dir / "design.md").write_text(
            "# Design\n\nThis spec describes a new feature with no existing code.\n",
            encoding="utf-8",
        )

        config = _make_reviewer_config(reviewer=True)
        entries = collect_enabled_auto_pre(config, spec_path=spec_dir)

        reviewer_modes = []
        for e in entries:
            if e.name == "reviewer":
                try:
                    reviewer_modes.append(e.mode)
                except AttributeError:
                    pytest.fail("ArchetypeEntry lacks 'mode' field")

        assert "pre-review" in reviewer_modes, (
            f"pre-review should still be injected when spec has no code, "
            f"got modes: {reviewer_modes}"
        )
        assert "drift-review" not in reviewer_modes, (
            f"drift-review should be skipped when spec has no existing code, "
            f"got modes: {reviewer_modes}"
        )

    def test_drift_gating_has_code_spec(self, tmp_path: Path) -> None:
        """TS-98-10: collect_enabled_auto_pre includes drift-review when spec references code."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        # Create a spec dir with a design.md that references an existing file
        # Use injection.py as the existing file reference
        existing_file = Path("agent_fox/graph/injection.py")
        spec_dir = tmp_path / "00_hascode"
        spec_dir.mkdir()
        (spec_dir / "design.md").write_text(
            f"# Design\n\n**`{existing_file}`** (modified)\n",
            encoding="utf-8",
        )

        config = _make_reviewer_config(reviewer=True)
        entries = collect_enabled_auto_pre(config, spec_path=spec_dir)

        reviewer_modes = []
        for e in entries:
            if e.name == "reviewer":
                try:
                    reviewer_modes.append(e.mode)
                except AttributeError:
                    pytest.fail("ArchetypeEntry lacks 'mode' field")

        assert "drift-review" in reviewer_modes, (
            f"drift-review should be included when spec references existing code, "
            f"got modes: {reviewer_modes}"
        )
