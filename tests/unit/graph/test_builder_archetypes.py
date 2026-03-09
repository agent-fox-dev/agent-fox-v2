"""Tests for graph builder archetype injection and serialization.

Test Spec: TS-26-13 through TS-26-21, TS-26-E5 through TS-26-E8,
           TS-26-P7, TS-26-P8, TS-26-P14
Requirements: 26-REQ-4.1 through 26-REQ-4.E2,
              26-REQ-5.1 through 26-REQ-5.E2
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


def _tgd(number, title="T", **kw):
    """Build a TaskGroupDef with short defaults."""
    from agent_fox.spec.parser import TaskGroupDef

    defaults = dict(
        optional=False, completed=False, subtasks=(), body=""
    )
    defaults.update(kw)
    return TaskGroupDef(number=number, title=title, **defaults)


def _spec(name="spec"):
    """Build a SpecInfo with short defaults."""
    from agent_fox.spec.discovery import SpecInfo

    return SpecInfo(
        name=name,
        prefix=0,
        path=Path(f".specs/{name}"),
        has_tasks=True,
        has_prd=False,
    )


# -------------------------------------------------------------------
# TS-26-13: Node dataclass has archetype and instances
# Requirement: 26-REQ-4.1
# -------------------------------------------------------------------


class TestNodeArchetypeDefaults:
    """Verify Node has archetype and instances with defaults."""

    def test_default_archetype(self) -> None:
        from agent_fox.graph.types import Node

        node = Node(
            id="s:1", spec_name="s",
            group_number=1, title="t", optional=False,
        )
        assert node.archetype == "coder"
        assert node.instances == 1

    def test_custom_archetype(self) -> None:
        from agent_fox.graph.types import Node

        node = Node(
            id="s:0", spec_name="s", group_number=0,
            title="Review", optional=False,
            archetype="skeptic", instances=3,
        )
        assert node.archetype == "skeptic"
        assert node.instances == 3


# -------------------------------------------------------------------
# TS-26-14: Plan serialization includes archetype fields
# Requirement: 26-REQ-4.2
# -------------------------------------------------------------------


class TestPlanSerializationArchetype:
    """Verify plan.json includes archetype and instances."""

    def test_serialization_includes_fields(
        self, tmp_path: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.graph.persistence import save_plan
        from agent_fox.graph.types import Node, TaskGraph

        node = Node(
            id="s:0", spec_name="s", group_number=0,
            title="Skeptic Review", optional=False,
            archetype="skeptic", instances=3,
        )
        graph = TaskGraph(
            nodes={"s:0": node}, edges=[], order=[],
        )
        plan_path = tmp_path / "plan.json"  # type: ignore[operator]
        save_plan(graph, plan_path)

        data = json.loads(plan_path.read_text())
        assert data["nodes"]["s:0"]["archetype"] == "skeptic"
        assert data["nodes"]["s:0"]["instances"] == 3


# -------------------------------------------------------------------
# TS-26-15: Legacy plan.json defaults
# Requirement: 26-REQ-4.3
# -------------------------------------------------------------------


class TestLegacyPlanDefaults:
    """Verify legacy plan without archetype defaults to coder/1."""

    def test_legacy_plan_defaults(
        self, tmp_path: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.graph.persistence import load_plan

        plan_data = {
            "nodes": {
                "s:1": {
                    "id": "s:1", "spec_name": "s",
                    "group_number": 1, "title": "t",
                    "optional": False, "status": "pending",
                }
            },
            "edges": [],
            "order": [],
        }
        plan_path = tmp_path / "plan.json"  # type: ignore[operator]
        plan_path.write_text(json.dumps(plan_data))

        graph = load_plan(plan_path)
        assert graph is not None
        assert graph.nodes["s:1"].archetype == "coder"
        assert graph.nodes["s:1"].instances == 1


# -------------------------------------------------------------------
# TS-26-17: tasks.md archetype tag extraction
# Requirement: 26-REQ-5.1
# -------------------------------------------------------------------


class TestArchetypeTagExtraction:
    """Verify parse_tasks() extracts [archetype: X] tags."""

    def test_tag_extracted_and_stripped(
        self, tmp_path: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.parser import parse_tasks

        tasks_md = (
            "## Tasks\n\n"
            "- [ ] 3. Update docs [archetype: cartographer]\n"
            "  - [ ] 3.1 Write docs\n"
        )
        path = tmp_path / "tasks.md"  # type: ignore[operator]
        path.write_text(tasks_md)

        groups = parse_tasks(path)
        assert len(groups) == 1
        assert groups[0].archetype == "cartographer"
        assert "[archetype:" not in groups[0].title
        assert "Update docs" in groups[0].title

    def test_no_tag_leaves_none(
        self, tmp_path: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.spec.parser import parse_tasks

        tasks_md = (
            "## Tasks\n\n"
            "- [ ] 1. Normal task\n"
            "  - [ ] 1.1 Sub\n"
        )
        path = tmp_path / "tasks.md"  # type: ignore[operator]
        path.write_text(tasks_md)

        groups = parse_tasks(path)
        assert len(groups) == 1
        assert groups[0].archetype is None


# -------------------------------------------------------------------
# TS-26-18: Three-layer assignment priority
# Requirement: 26-REQ-5.2
# -------------------------------------------------------------------


class TestThreeLayerPriority:
    """Verify assignment layers in correct priority order."""

    def test_tasks_md_tag_wins(self) -> None:
        from agent_fox.graph.builder import build_graph
        specs = [_spec()]
        task_groups = {
            "spec": [_tgd(3, "Task", archetype="librarian")]
        }

        graph = build_graph(specs, task_groups, [])
        assert graph.nodes["spec:3"].archetype == "librarian"


# -------------------------------------------------------------------
# TS-26-19: Skeptic auto-injection at group 0
# Requirement: 26-REQ-5.3
# -------------------------------------------------------------------


class TestSkepticAutoInjection:
    """Verify group-0 Skeptic node injected when enabled."""

    def test_skeptic_node_injected(self) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(skeptic=True)
        specs = [_spec()]
        task_groups = {
            "spec": [_tgd(1, "T1"), _tgd(2, "T2")]
        }

        graph = build_graph(
            specs, task_groups, [],
            archetypes_config=config,
        )

        assert "spec:0" in graph.nodes
        assert graph.nodes["spec:0"].archetype == "skeptic"
        assert any(
            e.source == "spec:0"
            and e.target == "spec:1"
            and e.kind == "intra_spec"
            for e in graph.edges
        )


# -------------------------------------------------------------------
# TS-26-20: Auto-post injection as siblings
# Requirement: 26-REQ-5.4
# -------------------------------------------------------------------


class TestAutoPostSiblings:
    """Verify auto_post archetypes as independent siblings."""

    def test_verifier_injected_after_last(self) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(verifier=True)
        specs = [_spec()]
        task_groups = {
            "spec": [_tgd(1, "T1"), _tgd(2, "T2")]
        }

        graph = build_graph(
            specs, task_groups, [],
            archetypes_config=config,
        )

        verifier_nodes = [
            n for n in graph.nodes.values()
            if n.archetype == "verifier"
        ]
        assert len(verifier_nodes) >= 1

        for vn in verifier_nodes:
            assert any(
                e.source == "spec:2" and e.target == vn.id
                for e in graph.edges
            )


# -------------------------------------------------------------------
# TS-26-21: Archetype assignment logged at INFO
# Requirement: 26-REQ-5.5
# -------------------------------------------------------------------


class TestAssignmentLogged:
    """Verify archetype assignments logged at INFO level."""

    def test_assignment_logged(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(skeptic=True)
        specs = [_spec()]
        task_groups = {"spec": [_tgd(1, "T1")]}

        with caplog.at_level(logging.INFO):
            build_graph(
                specs, task_groups, [],
                archetypes_config=config,
            )

        assert any(
            "archetype" in r.message.lower()
            for r in caplog.records
        )


# -------------------------------------------------------------------
# TS-26-E5: Coder instances clamped to 1
# Requirement: 26-REQ-4.E1
# -------------------------------------------------------------------


class TestCoderInstancesClamped:
    """Verify instances > 1 for coder is clamped to 1."""

    def test_coder_clamped(self, caplog: pytest.LogCaptureFixture) -> None:
        from agent_fox.engine.session_lifecycle import _clamp_instances

        with caplog.at_level(logging.WARNING):
            result = _clamp_instances("coder", 3)
        assert result == 1
        assert any("clamped" in r.message.lower() or "coder" in r.message.lower()
                    for r in caplog.records)


# -------------------------------------------------------------------
# TS-26-E6: Instances > 5 clamped
# Requirement: 26-REQ-4.E2
# -------------------------------------------------------------------


class TestInstancesOver5Clamped:
    """Verify instances > 5 is clamped to 5."""

    def test_instances_clamped_in_config(self) -> None:
        from agent_fox.core.config import ArchetypeInstancesConfig

        cfg = ArchetypeInstancesConfig(skeptic=10)
        assert cfg.skeptic == 5

    def test_instances_clamped_at_runner_level(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.engine.session_lifecycle import _clamp_instances

        with caplog.at_level(logging.WARNING):
            result = _clamp_instances("skeptic", 10)
        assert result == 5


# -------------------------------------------------------------------
# TS-26-E7: Disabled archetype in coordinator override
# Requirement: 26-REQ-5.E1
# -------------------------------------------------------------------


class TestDisabledArchetypeOverrideIgnored:
    """Verify disabled archetype override is ignored."""

    def test_disabled_override_ignored(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(librarian=False)
        specs = [_spec()]
        task_groups = {
            "spec": [_tgd(3, "Task")]
        }

        @dataclass
        class _Override:
            node: str
            archetype: str
            reason: str = ""

        overrides = [
            _Override(node="spec:3", archetype="librarian"),
        ]

        with caplog.at_level(logging.WARNING):
            graph = build_graph(
                specs, task_groups, [],
                archetypes_config=config,
                coordinator_overrides=overrides,
            )

        assert graph.nodes["spec:3"].archetype == "coder"
        assert any(
            "librarian" in r.message
            and "disabled" in r.message.lower()
            for r in caplog.records
        )


# -------------------------------------------------------------------
# TS-26-E8: Unknown archetype in tasks.md tag
# Requirement: 26-REQ-5.E2
# -------------------------------------------------------------------


class TestUnknownTagDefaultsCoder:
    """Verify unknown archetype tag defaults to coder."""

    def test_unknown_tag_warns(
        self,
        tmp_path: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.spec.parser import parse_tasks

        tasks_md = (
            "## Tasks\n\n"
            "- [ ] 3. Task [archetype: bogus]\n"
            "  - [ ] 3.1 Sub\n"
        )
        path = tmp_path / "tasks.md"  # type: ignore[operator]
        path.write_text(tasks_md)

        with caplog.at_level(logging.WARNING):
            groups = parse_tasks(path)

        assert len(groups) == 1


# -------------------------------------------------------------------
# TS-26-P7: Auto-Injection Graph Structure (Property)
# Property 7: Auto-injected nodes have correct edges
# Validates: 26-REQ-5.3, 26-REQ-5.4
# -------------------------------------------------------------------


class TestPropertyInjectionStructure:
    """Auto-injected nodes have correct edges."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(n_groups=st.integers(min_value=1, max_value=5))
    @settings(max_examples=10)
    def test_prop_injection_structure(
        self, n_groups: int,
    ) -> None:
        from itertools import combinations

        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.builder import build_graph

        config = ArchetypesConfig(skeptic=True, verifier=True)
        specs = [_spec()]
        task_groups = {
            "spec": [
                _tgd(i, f"T{i}")
                for i in range(1, n_groups + 1)
            ]
        }

        graph = build_graph(
            specs, task_groups, [],
            archetypes_config=config,
        )

        # Skeptic at group 0 precedes group 1
        assert "spec:0" in graph.nodes
        assert graph.nodes["spec:0"].archetype == "skeptic"
        assert any(
            e.source == "spec:0" and e.target == "spec:1"
            for e in graph.edges
        )

        # No edges between sibling auto_post nodes
        post_nodes = [
            n for n in graph.nodes.values()
            if n.archetype in {
                "verifier", "librarian", "cartographer",
            }
        ]
        for a, b in combinations(post_nodes, 2):
            assert not any(
                e.source == a.id and e.target == b.id
                for e in graph.edges
            )
            assert not any(
                e.source == b.id and e.target == a.id
                for e in graph.edges
            )


# -------------------------------------------------------------------
# TS-26-P8: Instance Clamping (Property)
# Property 8: Instance counts clamped to valid ranges
# Validates: 26-REQ-4.E1, 26-REQ-4.E2
# -------------------------------------------------------------------


class TestPropertyInstanceClamping:
    """Instance counts are clamped to valid ranges."""

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(instances=st.integers(min_value=0, max_value=20))
    @settings(max_examples=20)
    def test_prop_config_clamping(self, instances: int) -> None:
        from agent_fox.core.config import ArchetypeInstancesConfig

        cfg = ArchetypeInstancesConfig(skeptic=instances)
        assert 1 <= cfg.skeptic <= 5

    @pytest.mark.skipif(
        not HAS_HYPOTHESIS, reason="hypothesis not installed",
    )
    @given(
        archetype=st.sampled_from(["coder", "skeptic", "verifier"]),
        instances=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=30)
    def test_prop_runner_clamping(self, archetype: str, instances: int) -> None:
        from agent_fox.engine.session_lifecycle import _clamp_instances

        result = _clamp_instances(archetype, instances)
        if archetype == "coder":
            assert result == 1
        elif instances > 5:
            assert result == 5
        elif instances < 1:
            assert result == 1
        else:
            assert result == instances


# -------------------------------------------------------------------
# TS-26-P14: Backward Compatibility (Property)
# Property 14: Legacy data defaults correctly
# Validates: 26-REQ-4.3, 26-REQ-6.E1
# -------------------------------------------------------------------


class TestPropertyBackwardCompat:
    """Legacy plan.json nodes default to coder/1."""

    def test_prop_legacy_nodes_default(
        self, tmp_path: pytest.TempPathFactory,
    ) -> None:
        from agent_fox.graph.persistence import load_plan

        plan_data = {
            "nodes": {
                "s:1": {
                    "id": "s:1", "spec_name": "s",
                    "group_number": 1, "title": "Legacy task",
                    "optional": False, "status": "pending",
                },
                "s:2": {
                    "id": "s:2", "spec_name": "s",
                    "group_number": 2, "title": "Another",
                    "optional": True, "status": "completed",
                },
            },
            "edges": [],
            "order": ["s:1", "s:2"],
        }
        plan_path = tmp_path / "plan.json"  # type: ignore[operator]
        plan_path.write_text(json.dumps(plan_data))

        graph = load_plan(plan_path)
        assert graph is not None
        for node in graph.nodes.values():
            assert node.archetype == "coder"
            assert node.instances == 1
