"""Property tests for spec-scoped reset (reset_spec).

Test Spec: TS-50-P1 through TS-50-P4
Properties: 1 (Spec Isolation), 2 (Complete Spec Coverage),
            4 (Preservation), 5 (Artifact Synchronization)
Requirements: 50-REQ-1.1, 50-REQ-1.2, 50-REQ-1.3, 50-REQ-1.5,
              50-REQ-1.6, 50-REQ-4.1, 50-REQ-4.2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.engine.reset import reset_spec
from agent_fox.engine.state import ExecutionState, SessionRecord

# -- Strategies ------------------------------------------------------------

SPEC_NAMES = ["alpha", "beta", "gamma", "delta", "epsilon"]
STATUSES = ["pending", "completed", "failed", "blocked", "in_progress"]
ARCHETYPES = ["coder", "skeptic", "auditor", "verifier", "oracle"]


@st.composite
def plan_with_multiple_specs(
    draw: st.DrawFn,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], str]:
    """Generate a plan with 2-5 specs, each with 1-5 nodes, random statuses.

    Returns (nodes_dict, node_states_dict, target_spec_name).
    """
    num_specs = draw(st.integers(min_value=2, max_value=4))
    specs = SPEC_NAMES[:num_specs]
    target_spec = draw(st.sampled_from(specs))

    nodes: dict[str, dict[str, Any]] = {}
    node_states: dict[str, str] = {}

    for spec in specs:
        num_nodes = draw(st.integers(min_value=1, max_value=4))
        for i in range(num_nodes):
            archetype = draw(st.sampled_from(ARCHETYPES))
            if archetype == "coder":
                nid = f"{spec}:{i + 1}"
            else:
                nid = f"{spec}:{i + 1}:{archetype}"

            nodes[nid] = {
                "spec_name": spec,
                "group_number": i + 1,
                "archetype": archetype,
            }
            node_states[nid] = draw(st.sampled_from(STATUSES))

    return nodes, node_states, target_spec


def _make_plan_json(nodes: dict[str, dict[str, Any]]) -> str:
    """Build a plan.json string from node definitions."""
    full_nodes: dict[str, Any] = {}
    for nid, props in nodes.items():
        parts = nid.split(":")
        spec_name = props.get("spec_name", parts[0])
        last = parts[1] if len(parts) > 1 else "1"
        group_number = int(last) if last.isdigit() else 0
        full_nodes[nid] = {
            "id": nid,
            "spec_name": spec_name,
            "group_number": props.get("group_number", group_number),
            "title": f"Task {nid}",
            "optional": False,
            "status": "pending",
            "subtask_count": 0,
            "body": "",
            "archetype": props.get("archetype", "coder"),
        }

    return json.dumps(
        {
            "metadata": {
                "created_at": "2026-01-01T00:00:00",
                "fast_mode": False,
                "filtered_spec": None,
                "version": "0.1.0",
            },
            "nodes": full_nodes,
            "edges": [],
            "order": list(nodes.keys()),
        },
        indent=2,
    )


def _setup_for_property(
    tmp_path: Path,
    nodes: dict[str, dict[str, Any]],
    node_states: dict[str, str],
    *,
    session_history: list[SessionRecord] | None = None,
    total_cost: float = 0.0,
    total_sessions: int = 0,
) -> tuple[ExecutionState, Path, Path, Path]:
    """Set up plan, state, worktrees dir and return (state, plan_path, wt_dir, repo)."""
    agent_dir = tmp_path / ".agent-fox"
    wt_dir = agent_dir / "worktrees"
    wt_dir.mkdir(parents=True, exist_ok=True)

    plan_path = agent_dir / "plan.json"
    plan_path.write_text(_make_plan_json(nodes))

    state = ExecutionState(
        plan_hash="abc123",
        node_states=node_states,
        session_history=session_history or [],
        total_cost=total_cost,
        total_sessions=total_sessions,
        started_at="2026-03-01T09:00:00Z",
        updated_at="2026-03-01T10:00:00Z",
    )

    # Create specs dirs with tasks.md for each spec
    specs_dir = tmp_path / ".specs"
    seen_specs: set[str] = set()
    for nid, props in nodes.items():
        spec = props.get("spec_name", nid.split(":")[0])
        if spec not in seen_specs:
            seen_specs.add(spec)
            spec_dir = specs_dir / spec
            spec_dir.mkdir(parents=True, exist_ok=True)
            # Build tasks.md with checkbox entries
            groups = set()
            for nid2, p2 in nodes.items():
                s2 = p2.get("spec_name", nid2.split(":")[0])
                if s2 == spec:
                    gn = p2.get("group_number", 1)
                    groups.add(gn)
            lines = []
            for g in sorted(groups):
                status = "[x]"  # Start as checked
                lines.append(f"- {status} {g}. Task group {g}")
            (spec_dir / "tasks.md").write_text("\n".join(lines) + "\n")

    return state, plan_path, wt_dir, tmp_path


# ---------------------------------------------------------------------------
# TS-50-P1: Spec Isolation
# Property 1: Only nodes from the target spec are modified.
# Validates: 50-REQ-1.1, 50-REQ-1.3
# ---------------------------------------------------------------------------


class TestSpecIsolation:
    """TS-50-P1: Only nodes from the target spec are modified."""

    @given(data=plan_with_multiple_specs())
    @settings(max_examples=30, deadline=None)
    def test_other_specs_unchanged(
        self,
        data: tuple[dict[str, dict[str, Any]], dict[str, str], str],
        tmp_path_factory: Any,
    ) -> None:
        """Nodes not in the target spec retain their original status."""
        nodes, node_states, target_spec = data
        tmp_path = tmp_path_factory.mktemp("iso")

        original_states = dict(node_states)
        state, plan_path, wt_dir, repo = _setup_for_property(tmp_path, nodes, node_states)
        mock_conn = MagicMock()

        with patch("agent_fox.engine.reset.load_state_from_db", return_value=state):
            reset_spec(target_spec, plan_path, wt_dir, repo, db_conn=mock_conn)

        for nid, orig_status in original_states.items():
            spec = nodes[nid].get("spec_name", nid.split(":")[0])
            if spec != target_spec:
                assert state.node_states[nid] == orig_status, (
                    f"Node {nid} (spec={spec}) changed from {orig_status} to {state.node_states[nid]}"
                )


# ---------------------------------------------------------------------------
# TS-50-P2: Complete Spec Coverage
# Property 2: Every node in the spec is reset regardless of archetype.
# Validates: 50-REQ-1.1, 50-REQ-1.2
# ---------------------------------------------------------------------------


class TestCompleteSpecCoverage:
    """TS-50-P2: Every node in the spec is reset regardless of archetype."""

    @given(data=plan_with_multiple_specs())
    @settings(max_examples=30, deadline=None)
    def test_all_spec_nodes_pending(
        self,
        data: tuple[dict[str, dict[str, Any]], dict[str, str], str],
        tmp_path_factory: Any,
    ) -> None:
        """After reset, all nodes with matching spec_name are pending."""
        nodes, node_states, target_spec = data
        tmp_path = tmp_path_factory.mktemp("cov")

        state, plan_path, wt_dir, repo = _setup_for_property(tmp_path, nodes, node_states)
        mock_conn = MagicMock()

        with patch("agent_fox.engine.reset.load_state_from_db", return_value=state):
            reset_spec(target_spec, plan_path, wt_dir, repo, db_conn=mock_conn)

        for nid, props in nodes.items():
            spec = props.get("spec_name", nid.split(":")[0])
            if spec == target_spec:
                assert state.node_states[nid] == "pending", (
                    f"Node {nid} (spec={spec}) should be pending but is {state.node_states[nid]}"
                )


# ---------------------------------------------------------------------------
# TS-50-P3: Preservation
# Property 4: Session history and counters are unchanged.
# Validates: 50-REQ-4.1, 50-REQ-4.2
# ---------------------------------------------------------------------------


class TestPreservation:
    """TS-50-P3: Session history and counters are unchanged."""

    @given(
        data=plan_with_multiple_specs(),
        num_sessions=st.integers(min_value=0, max_value=5),
        cost=st.floats(min_value=0.0, max_value=100.0),
    )
    @settings(max_examples=20, deadline=None)
    def test_history_and_cost_preserved(
        self,
        data: tuple[dict[str, dict[str, Any]], dict[str, str], str],
        num_sessions: int,
        cost: float,
        tmp_path_factory: Any,
    ) -> None:
        """Session history length and total_cost unchanged after reset."""
        nodes, node_states, target_spec = data
        tmp_path = tmp_path_factory.mktemp("pres")

        history = [
            SessionRecord(
                node_id=f"x:{i}",
                attempt=1,
                status="completed",
                input_tokens=100,
                output_tokens=50,
                cost=1.0,
                duration_ms=1000,
                error_message=None,
                timestamp="2026-03-01T10:00:00Z",
            )
            for i in range(num_sessions)
        ]

        state, plan_path, wt_dir, repo = _setup_for_property(
            tmp_path,
            nodes,
            node_states,
            session_history=history,
            total_cost=cost,
            total_sessions=num_sessions,
        )
        mock_conn = MagicMock()

        with patch("agent_fox.engine.reset.load_state_from_db", return_value=state):
            reset_spec(target_spec, plan_path, wt_dir, repo, db_conn=mock_conn)

        assert len(state.session_history) == num_sessions
        assert state.total_cost == cost
        assert state.total_sessions == num_sessions


# ---------------------------------------------------------------------------
# TS-50-P4: Artifact Synchronization
# Property 5: tasks.md and plan.json are consistent with state after reset.
# Validates: 50-REQ-1.5, 50-REQ-1.6
# ---------------------------------------------------------------------------


class TestArtifactSynchronization:
    """TS-50-P4: tasks.md and plan.json are consistent after reset."""

    @given(data=plan_with_multiple_specs())
    @settings(max_examples=20, deadline=None)
    def test_artifacts_reflect_pending(
        self,
        data: tuple[dict[str, dict[str, Any]], dict[str, str], str],
        tmp_path_factory: Any,
    ) -> None:
        """After reset, tasks.md has [ ] and plan.json has pending for spec."""
        nodes, node_states, target_spec = data
        tmp_path = tmp_path_factory.mktemp("sync")

        state, plan_path, wt_dir, repo = _setup_for_property(tmp_path, nodes, node_states)
        mock_conn = MagicMock()

        with patch("agent_fox.engine.reset.load_state_from_db", return_value=state):
            reset_spec(target_spec, plan_path, wt_dir, repo, db_conn=mock_conn)

        # Check plan.json
        plan_data = json.loads(plan_path.read_text())
        for nid, props in nodes.items():
            spec = props.get("spec_name", nid.split(":")[0])
            if spec == target_spec and nid in plan_data["nodes"]:
                assert plan_data["nodes"][nid]["status"] == "pending", f"Plan node {nid} should be pending"

        # Check tasks.md - no [x] or [-] for reset spec
        tasks_md = tmp_path / ".specs" / target_spec / "tasks.md"
        if tasks_md.exists():
            content = tasks_md.read_text()
            # Top-level checkboxes should not have [x] or [-]
            for line in content.split("\n"):
                if line.startswith("- ["):
                    assert "[x]" not in line, f"Found [x] in: {line}"
                    assert "[-]" not in line, f"Found [-] in: {line}"
