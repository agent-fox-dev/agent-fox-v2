"""Tests asserting coordinator removal from the graph builder.

Test Spec: TS-62-4, TS-62-5, TS-62-9
Requirements: 62-REQ-3.1, 62-REQ-3.2, 62-REQ-3.3
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_fox.spec.parser import TaskGroupDef


def _tgd(number: int, title: str = "Task", **kw: Any) -> TaskGroupDef:
    """Build a TaskGroupDef with short defaults."""
    from agent_fox.spec.parser import TaskGroupDef

    defaults: dict[str, Any] = dict(optional=False, completed=False, subtasks=(), body="")
    defaults.update(kw)
    return TaskGroupDef(number=number, title=title, **defaults)


def _spec(name: str = "spec"):
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
# TS-62-4: build_graph Rejects coordinator_overrides
# Requirement: 62-REQ-3.1
# -------------------------------------------------------------------


class TestBuildGraphNoCoordinatorOverridesParam:
    """TS-62-4: Verify build_graph() has no coordinator_overrides parameter."""

    def test_build_graph_no_coordinator_overrides_param(self) -> None:
        """build_graph signature must not include 'coordinator_overrides'."""
        from agent_fox.graph.builder import build_graph

        sig = inspect.signature(build_graph)
        assert "coordinator_overrides" not in sig.parameters


# -------------------------------------------------------------------
# TS-62-5: _apply_coordinator_overrides Removed
# Requirement: 62-REQ-3.2
# -------------------------------------------------------------------


class TestApplyCoordinatorOverridesRemoved:
    """TS-62-5: Verify _apply_coordinator_overrides does not exist on builder."""

    def test_apply_coordinator_overrides_removed(self) -> None:
        """The builder module must not expose _apply_coordinator_overrides."""
        import agent_fox.graph.builder as builder_mod

        assert not hasattr(builder_mod, "_apply_coordinator_overrides")


# -------------------------------------------------------------------
# TS-62-9: Two-Layer Archetype Assignment
# Requirement: 62-REQ-3.3
# -------------------------------------------------------------------


class TestTwoLayerArchetypeAssignment:
    """TS-62-9: Verify build_graph applies tasks.md tags directly after defaults."""

    def test_two_layer_archetype_assignment(self) -> None:
        """Tagged task group gets archetype from tasks.md with no coordinator layer."""
        from agent_fox.graph.builder import build_graph

        spec = _spec("myspec")
        group1 = _tgd(1, title="Write tests")
        group2 = _tgd(2, title="Implement [archetype: verifier]", archetype="verifier")

        graph = build_graph(
            specs=[spec],
            task_groups={"myspec": [group1, group2]},
            cross_deps=[],
        )

        node_id = "myspec:2"
        assert node_id in graph.nodes, f"Expected node '{node_id}' in graph"
        assert graph.nodes[node_id].archetype == "verifier", (
            f"Expected archetype 'verifier' but got '{graph.nodes[node_id].archetype}'"
        )
