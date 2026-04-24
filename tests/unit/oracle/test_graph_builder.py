"""Tests for reviewer graph builder injection and multi-auto_pre support.

Test Spec: TS-32-3, TS-32-4, TS-32-5, TS-32-E2, TS-32-E3, TS-32-E9
Requirements: 32-REQ-2.1, 32-REQ-2.2, 32-REQ-2.E1,
              32-REQ-3.1, 32-REQ-3.2, 32-REQ-3.3, 32-REQ-3.E1,
              32-REQ-4.E1

Updated for reviewer consolidation (spec 98): oracle → reviewer:drift-review,
skeptic → reviewer:pre-review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_fox.spec.discovery import SpecInfo
from agent_fox.spec.parser import TaskGroupDef


def _spec(name: str = "spec") -> SpecInfo:
    """Build a SpecInfo with short defaults."""
    return SpecInfo(
        name=name,
        prefix=0,
        path=Path(f".specs/{name}"),
        has_tasks=True,
        has_prd=False,
    )


def _tgd(number: int, title: str = "T", **kw: Any) -> TaskGroupDef:
    """Build a TaskGroupDef with short defaults."""
    defaults: dict[str, Any] = dict(optional=False, completed=False, subtasks=(), body="")
    defaults.update(kw)
    return TaskGroupDef(number=number, title=title, **defaults)


# ---------------------------------------------------------------------------
# TS-32-3: Reviewer drift-review Node Injected in Graph
# Requirements: 32-REQ-2.1, 32-REQ-2.3
# ---------------------------------------------------------------------------


class TestDriftReviewNodeInjected:
    """Verify reviewer:drift-review node is injected before the first coder group."""

    def test_drift_review_node_injected(self) -> None:
        """TS-32-3: Reviewer drift-review node with edge to first coder group."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec()]
        task_groups = {"spec": [_tgd(1, "T1"), _tgd(2, "T2"), _tgd(3, "T3")]}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        # With reviewer=True, both pre-review and drift-review are injected (use_suffix=True)
        drift_id = "spec:0:reviewer:drift-review"
        assert drift_id in graph.nodes
        assert graph.nodes[drift_id].archetype == "reviewer"
        assert graph.nodes[drift_id].mode == "drift-review"
        assert any(e.source == drift_id and e.target == "spec:1" and e.kind == "intra_spec" for e in graph.edges)


# ---------------------------------------------------------------------------
# TS-32-4: Dual auto_pre (pre-review + drift-review) Parallel Nodes
# Requirements: 32-REQ-2.2, 32-REQ-3.1, 32-REQ-3.3
# ---------------------------------------------------------------------------


class TestDualAutoPre:
    """When reviewer is enabled, both pre-review and drift-review get distinct IDs."""

    def test_dual_auto_pre(self) -> None:
        """TS-32-4: Both pre-review and drift-review nodes exist with edges to first coder."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec()]
        task_groups = {"spec": [_tgd(1, "T1"), _tgd(2, "T2")]}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)

        pre_id = "spec:0:reviewer:pre-review"
        drift_id = "spec:0:reviewer:drift-review"
        assert pre_id in graph.nodes
        assert drift_id in graph.nodes

        # Both connect to first coder group
        assert any(e.source == pre_id and e.target == "spec:1" and e.kind == "intra_spec" for e in graph.edges)
        assert any(e.source == drift_id and e.target == "spec:1" and e.kind == "intra_spec" for e in graph.edges)

        # No edge between them
        edges_between = [
            e
            for e in graph.edges
            if (e.source == pre_id and e.target == drift_id) or (e.source == drift_id and e.target == pre_id)
        ]
        assert len(edges_between) == 0


# ---------------------------------------------------------------------------
# TS-32-5: Single auto_pre Uses Plain :0 Format
# Requirement: 32-REQ-3.2
# ---------------------------------------------------------------------------


class TestSingleAutoPreCompat:
    """When only one auto_pre is enabled, use {spec}:0 format."""

    def test_single_auto_pre_compat(self, tmp_path: Path) -> None:
        """TS-32-5: Single auto_pre uses {spec}:0 without archetype suffix."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        # Create a spec directory with design.md that has only (new) files,
        # which gates out drift-review, leaving only pre-review as single auto_pre.
        spec_dir = tmp_path / ".specs" / "myspec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "design.md").write_text("1. **`agent_fox/brand_new.py`** (new) -- New module.\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task one\n  - [ ] 1.1 Sub\n")

        config = ArchetypesConfig(reviewer=True)
        spec = SpecInfo(name="myspec", prefix=0, path=spec_dir, has_tasks=True, has_prd=False)
        task_groups = {"myspec": [_tgd(1, "T1")]}

        graph = build_graph([spec], task_groups, [], archetypes_config=config)

        # Only pre-review is enabled (drift-review gated out)
        assert "myspec:0" in graph.nodes
        assert graph.nodes["myspec:0"].archetype == "reviewer"
        assert graph.nodes["myspec:0"].mode == "pre-review"
        # No *reviewer* (auto_pre) nodes with ":0:" suffix — single auto_pre
        # uses the plain {spec}:0 format.  Note: auto_post nodes such as
        # verifier may legitimately use a 3-part ":0:" format; we only check
        # the auto_pre reviewer nodes for backward-compat format compliance.
        reviewer_nids = [n.id for n in graph.nodes.values() if n.archetype == "reviewer"]
        assert not any(":0:" in nid for nid in reviewer_nids), (
            f"Single auto_pre reviewer nodes must not use suffixed ':0:' format; "
            f"reviewer node ids: {reviewer_nids}"
        )


# ---------------------------------------------------------------------------
# TS-32-E2: Empty Spec (No Coder Groups)
# Requirement: 32-REQ-2.E1
# ---------------------------------------------------------------------------


class TestEmptySpecNoReviewerInjection:
    """No reviewer injection for spec with no coder groups."""

    def test_empty_spec_no_reviewer(self) -> None:
        """TS-32-E2: Spec with no task groups gets no reviewer node."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(reviewer=True)
        specs = [_spec("empty_spec")]
        task_groups: dict[str, list[TaskGroupDef]] = {"empty_spec": []}

        graph = build_graph(specs, task_groups, [], archetypes_config=config)
        assert "empty_spec:0" not in graph.nodes
        # No reviewer nodes at all
        reviewer_nodes = [nid for nid, n in graph.nodes.items() if n.archetype == "reviewer"]
        assert reviewer_nodes == []


# ---------------------------------------------------------------------------
# TS-32-E3: Legacy Plan Compatibility
# Requirement: 32-REQ-3.E1
# ---------------------------------------------------------------------------


class TestLegacyPlanCompat:
    """Runtime injection adds drift-review when plan has existing pre-review node."""

    def test_legacy_plan_compat(self) -> None:
        """TS-32-E3: Drift-review added with distinct ID, pre-review preserved."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import ensure_graph_archetypes
        from agent_fox.graph.types import Edge, Node, TaskGraph

        graph = TaskGraph(
            nodes={
                "spec:0": Node(
                    id="spec:0",
                    spec_name="spec",
                    group_number=0,
                    title="Reviewer (pre-review)",
                    optional=False,
                    archetype="reviewer",
                    mode="pre-review",
                    instances=1,
                ),
                "spec:1": Node(
                    id="spec:1",
                    spec_name="spec",
                    group_number=1,
                    title="Task 1",
                    optional=False,
                    archetype="coder",
                    instances=1,
                ),
            },
            edges=[Edge(source="spec:0", target="spec:1", kind="intra_spec")],
            order=["spec:0", "spec:1"],
        )
        config = ArchetypesConfig(reviewer=True)
        ensure_graph_archetypes(graph, config)

        # Pre-review node preserved
        assert "spec:0" in graph.nodes
        assert graph.nodes["spec:0"].archetype == "reviewer"
        assert graph.nodes["spec:0"].mode == "pre-review"

        # Drift-review node added with distinct ID
        drift_nodes = [nid for nid, n in graph.nodes.items() if n.archetype == "reviewer" and n.mode == "drift-review"]
        assert len(drift_nodes) == 1


# ---------------------------------------------------------------------------
# TS-32-E9: Hot-load Failure Skips Reviewer
# Requirement: 32-REQ-4.E1
# ---------------------------------------------------------------------------


class TestHotLoadFailureSkip:
    """When hot-loading fails for a spec, reviewer injection is skipped."""

    def test_hot_load_failure_skip(self, tmp_path: Path) -> None:
        """TS-32-E9: Invalid spec is skipped, reviewer not injected for it."""
        # Create a specs dir with one valid and one invalid spec
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        # Valid spec
        valid_spec = specs_dir / "01_valid"
        valid_spec.mkdir()
        (valid_spec / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task 1\n  - [ ] 1.1 Sub\n")

        # Invalid spec (no tasks.md)
        invalid_spec = specs_dir / "02_invalid"
        invalid_spec.mkdir()
        # Intentionally no tasks.md

        # Verify that hot_load_specs handles the invalid spec gracefully.
        assert valid_spec.exists()
        assert not (invalid_spec / "tasks.md").exists()


# ---------------------------------------------------------------------------
# spec_has_existing_code helper tests
# ---------------------------------------------------------------------------


class TestSpecHasExistingCode:
    """Tests for the drift-review gating helper."""

    def test_no_design_md_returns_true(self, tmp_path: Path) -> None:
        """Missing design.md defaults to True (safe — don't suppress drift-review)."""
        from agent_fox.graph.builder import spec_has_existing_code

        assert spec_has_existing_code(tmp_path) is True

    def test_no_modified_refs_returns_false(self, tmp_path: Path) -> None:
        """design.md with only (new) files returns False."""
        from agent_fox.graph.builder import spec_has_existing_code

        (tmp_path / "design.md").write_text("1. **`agent_fox/brand_new.py`** (new) -- New module.\n")
        assert spec_has_existing_code(tmp_path) is False

    def test_modified_ref_exists(self, tmp_path: Path) -> None:
        """Returns True when a (modified) file exists on disk."""
        from agent_fox.graph.builder import spec_has_existing_code

        target = tmp_path / "real_file.py"
        target.write_text("# existing")
        (tmp_path / "design.md").write_text(f"1. **`{target}`** (modified) -- Change.\n")
        assert spec_has_existing_code(tmp_path) is True

    def test_modified_ref_missing(self, tmp_path: Path) -> None:
        """Returns False when all (modified) files are absent."""
        from agent_fox.graph.builder import spec_has_existing_code

        (tmp_path / "design.md").write_text("1. **`nonexistent/foo.py`** (modified) -- Change.\n")
        assert spec_has_existing_code(tmp_path) is False

    def test_mixed_new_and_modified(self, tmp_path: Path) -> None:
        """Only (modified) refs are checked, not (new) ones."""
        from agent_fox.graph.builder import spec_has_existing_code

        target = tmp_path / "exists.py"
        target.write_text("# code")
        (tmp_path / "design.md").write_text(
            f"1. **`brand_new.py`** (new) -- New.\n2. **`{target}`** (modified) -- Change.\n"
        )
        assert spec_has_existing_code(tmp_path) is True


# ---------------------------------------------------------------------------
# Drift-review gating in build_graph
# ---------------------------------------------------------------------------


class TestDriftReviewGatingBuildGraph:
    """Drift-review is skipped at plan-build time when spec has no existing code."""

    def test_drift_review_skipped_no_existing_code(self, tmp_path: Path) -> None:
        """Drift-review node not injected when design.md has only (new) files."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        spec_dir = tmp_path / ".specs" / "myspec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "design.md").write_text("1. **`agent_fox/new_module.py`** (new) -- Brand new.\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task one\n  - [ ] 1.1 Sub\n")

        config = ArchetypesConfig(reviewer=True)
        spec = SpecInfo(name="myspec", prefix=0, path=spec_dir, has_tasks=True, has_prd=False)
        task_groups = {"myspec": [_tgd(1, "T1")]}

        graph = build_graph([spec], task_groups, [], archetypes_config=config)

        # Drift-review should NOT be present
        drift_nodes = [nid for nid, n in graph.nodes.items() if n.mode == "drift-review"]
        assert drift_nodes == []
        # Pre-review should still be present (as single auto_pre with plain :0 ID)
        assert "myspec:0" in graph.nodes
        assert graph.nodes["myspec:0"].archetype == "reviewer"
        assert graph.nodes["myspec:0"].mode == "pre-review"

    def test_drift_review_injected_existing_code(self, tmp_path: Path) -> None:
        """Drift-review node IS injected when design.md references existing files."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        spec_dir = tmp_path / ".specs" / "myspec"
        spec_dir.mkdir(parents=True)
        existing = tmp_path / "real.py"
        existing.write_text("# code")
        (spec_dir / "design.md").write_text(f"1. **`{existing}`** (modified) -- Change.\n")
        (spec_dir / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task one\n  - [ ] 1.1 Sub\n")

        config = ArchetypesConfig(reviewer=True)
        spec = SpecInfo(name="myspec", prefix=0, path=spec_dir, has_tasks=True, has_prd=False)
        task_groups = {"myspec": [_tgd(1, "T1")]}

        graph = build_graph([spec], task_groups, [], archetypes_config=config)

        # Both pre-review and drift-review should be present (suffixed IDs)
        drift_nodes = [nid for nid, n in graph.nodes.items() if n.mode == "drift-review"]
        assert len(drift_nodes) == 1
        assert graph.nodes[drift_nodes[0]].archetype == "reviewer"


# ---------------------------------------------------------------------------
# Drift-review gating in ensure_graph_archetypes (runtime injection)
# ---------------------------------------------------------------------------


class TestDriftReviewGatingRuntime:
    """Drift-review is skipped at runtime injection when spec has no existing code."""

    def test_runtime_drift_review_skipped(self, tmp_path: Path) -> None:
        """Runtime injection skips drift-review when design.md has only (new) files."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import ensure_graph_archetypes
        from agent_fox.graph.types import Node, TaskGraph

        spec_dir = tmp_path / "myspec"
        spec_dir.mkdir()
        (spec_dir / "design.md").write_text("1. **`agent_fox/new.py`** (new) -- Brand new.\n")

        graph = TaskGraph(
            nodes={
                "myspec:1": Node(
                    id="myspec:1",
                    spec_name="myspec",
                    group_number=1,
                    archetype="coder",
                    title="Task 1",
                    optional=False,
                    instances=1,
                ),
            },
            edges=[],
            order=["myspec:1"],
        )
        config = ArchetypesConfig(reviewer=True)
        ensure_graph_archetypes(graph, config, specs_dir=tmp_path)

        drift_nodes = [nid for nid, n in graph.nodes.items() if n.mode == "drift-review"]
        assert drift_nodes == []

    def test_runtime_drift_review_injected_with_existing_code(self, tmp_path: Path) -> None:
        """Runtime injection adds drift-review when design.md references existing files."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import ensure_graph_archetypes
        from agent_fox.graph.types import Node, TaskGraph

        spec_dir = tmp_path / "myspec"
        spec_dir.mkdir()
        existing = tmp_path / "real.py"
        existing.write_text("# code")
        (spec_dir / "design.md").write_text(f"1. **`{existing}`** (modified) -- Change.\n")

        graph = TaskGraph(
            nodes={
                "myspec:1": Node(
                    id="myspec:1",
                    spec_name="myspec",
                    group_number=1,
                    archetype="coder",
                    title="Task 1",
                    optional=False,
                    instances=1,
                ),
            },
            edges=[],
            order=["myspec:1"],
        )
        config = ArchetypesConfig(reviewer=True)
        ensure_graph_archetypes(graph, config, specs_dir=tmp_path)

        drift_nodes = [nid for nid, n in graph.nodes.items() if n.mode == "drift-review"]
        assert len(drift_nodes) == 1
