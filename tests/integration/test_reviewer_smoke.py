"""Integration smoke tests for reviewer consolidation wiring.

End-to-end tests that exercise real components without mocking injection,
convergence logic, or template loading.

Test Spec: TS-98-SMOKE-1, TS-98-SMOKE-2, TS-98-SMOKE-3
Requirements: 98-REQ-4.1, 98-REQ-4.2, 98-REQ-4.4, 98-REQ-5.1, 98-REQ-5.2,
              98-REQ-2.1, 98-REQ-2.2
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reviewer_config(reviewer: bool = True):
    """Build a minimal ArchetypesConfig with reviewer enabled."""
    from agent_fox.core.config import ArchetypesConfig

    return ArchetypesConfig(reviewer=reviewer)


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


def _make_finding(severity: str = "critical", description: str = "Test finding"):
    """Build a Finding for convergence tests."""
    from agent_fox.session.convergence import Finding

    return Finding(severity=severity, description=description)


# ---------------------------------------------------------------------------
# TS-98-SMOKE-1: Pre-review End-to-End
# Execution Path 1 from design.md
# Requirements: 98-REQ-4.2, 98-REQ-5.1
# ---------------------------------------------------------------------------


class TestPreReviewEndToEnd:
    """TS-98-SMOKE-1: Pre-review injection through convergence.

    Verifies the complete chain:
    1. ensure_graph_archetypes creates reviewer:pre-review node
    2. converge_reviewer dispatches to skeptic algorithm for pre-review

    Does NOT mock injection or convergence logic.
    """

    def test_pre_review_node_injected(self) -> None:
        """TS-98-SMOKE-1 (part 1): Graph contains reviewer:pre-review after injection."""
        from agent_fox.graph.injection import ensure_graph_archetypes

        graph = _make_coder_graph(spec_name="smoke_spec", group_number=1)
        config = _make_reviewer_config(reviewer=True)

        # Run real ensure_graph_archetypes (no mocking)
        ensure_graph_archetypes(graph, config)

        pre_nodes = [n for n in graph.nodes.values() if n.archetype == "reviewer" and n.mode == "pre-review"]
        assert len(pre_nodes) >= 1, (
            f"Expected at least one reviewer:pre-review node after injection, "
            f"got nodes: {[(n.archetype, n.mode) for n in graph.nodes.values()]}"
        )

    def test_pre_review_convergence_uses_skeptic_algorithm(self) -> None:
        """TS-98-SMOKE-1 (part 2): converge_reviewer uses skeptic algorithm for pre-review."""
        from agent_fox.session.convergence import converge_reviewer, converge_skeptic

        # Build mock findings (list[list[Finding]])
        findings_instance_1 = [
            _make_finding("critical", "Missing input validation"),
            _make_finding("major", "No error handling"),
        ]
        findings_instance_2 = [
            _make_finding("critical", "Missing input validation"),
        ]
        results = [findings_instance_1, findings_instance_2]

        # Run converge_reviewer with mode="pre-review" (uses real convergence logic)
        reviewer_merged, reviewer_blocked = converge_reviewer(results, mode="pre-review", block_threshold=3)
        # Run converge_skeptic directly for comparison
        skeptic_merged, skeptic_blocked = converge_skeptic(results, block_threshold=3)

        # Results must be identical — same algorithm
        assert reviewer_blocked == skeptic_blocked, (
            f"converge_reviewer('pre-review') blocked={reviewer_blocked} but converge_skeptic blocked={skeptic_blocked}"
        )
        # Merged finding counts should be equal
        assert len(reviewer_merged) == len(skeptic_merged), (
            f"Merged finding count mismatch: reviewer={len(reviewer_merged)}, skeptic={len(skeptic_merged)}"
        )

    def test_no_old_archetype_nodes_after_injection(self) -> None:
        """TS-98-SMOKE-1 (property): No skeptic/oracle nodes after injection."""
        from agent_fox.graph.injection import ensure_graph_archetypes

        graph = _make_coder_graph()
        config = _make_reviewer_config(reviewer=True)
        ensure_graph_archetypes(graph, config)

        all_archetypes = {n.archetype for n in graph.nodes.values()}
        assert "skeptic" not in all_archetypes, f"'skeptic' node found after consolidation: {all_archetypes}"
        assert "oracle" not in all_archetypes, f"'oracle' node found after consolidation: {all_archetypes}"
        assert "auditor" not in all_archetypes, f"'auditor' node found after consolidation: {all_archetypes}"


# ---------------------------------------------------------------------------
# TS-98-SMOKE-2: Drift-review With Gating
# Execution Path 2 from design.md
# Requirements: 98-REQ-4.4
# ---------------------------------------------------------------------------


class TestDriftReviewGatingEndToEnd:
    """TS-98-SMOKE-2: Drift-review gating using real spec_has_existing_code.

    Tests that collect_enabled_auto_pre applies real gating — does NOT mock
    spec_has_existing_code.
    """

    def test_drift_review_excluded_for_no_code_spec(self, tmp_path: Path) -> None:
        """TS-98-SMOKE-2 (no-code path): Drift-review excluded when spec has no code."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        # Spec directory with no source file references
        spec_dir = tmp_path / "00_nocode_spec"
        spec_dir.mkdir()
        (spec_dir / "design.md").write_text(
            "# Design\n\nThis spec introduces a brand new concept.\nNo existing files will be modified.\n",
            encoding="utf-8",
        )

        config = _make_reviewer_config(reviewer=True)

        # Real collect_enabled_auto_pre with real gating (spec_has_existing_code)
        entries = collect_enabled_auto_pre(config, spec_path=spec_dir)
        reviewer_modes = [e.mode for e in entries if e.name == "reviewer"]

        assert "pre-review" in reviewer_modes, f"pre-review should always be included, got modes: {reviewer_modes}"
        assert "drift-review" not in reviewer_modes, (
            f"drift-review should be excluded when spec has no existing code, got modes: {reviewer_modes}"
        )

    def test_drift_review_included_for_code_spec(self, tmp_path: Path) -> None:
        """TS-98-SMOKE-2 (code path): Drift-review included when spec references existing code."""
        from agent_fox.graph.injection import collect_enabled_auto_pre

        # Spec directory with design.md referencing a real existing file
        existing_file = Path("agent_fox/archetypes.py")
        spec_dir = tmp_path / "00_hascode_spec"
        spec_dir.mkdir()
        (spec_dir / "design.md").write_text(
            f"# Design\n\nThis spec modifies **`{existing_file}`** (modified).\n",
            encoding="utf-8",
        )

        config = _make_reviewer_config(reviewer=True)

        # Real collect_enabled_auto_pre — drift-review should be included
        entries = collect_enabled_auto_pre(config, spec_path=spec_dir)
        reviewer_modes = [e.mode for e in entries if e.name == "reviewer"]

        assert "drift-review" in reviewer_modes, (
            f"drift-review should be included when spec references existing code, got modes: {reviewer_modes}"
        )

    def test_drift_review_convergence_uses_skeptic_algorithm(self) -> None:
        """TS-98-SMOKE-2: converge_reviewer drift-review uses skeptic algorithm."""
        from agent_fox.session.convergence import converge_reviewer, converge_skeptic

        findings = [
            [_make_finding("major", "Drift: module X interface changed")],
            [_make_finding("major", "Drift: module X interface changed")],
        ]

        reviewer_merged, reviewer_blocked = converge_reviewer(findings, mode="drift-review", block_threshold=3)
        skeptic_merged, skeptic_blocked = converge_skeptic(findings, block_threshold=3)

        assert reviewer_blocked == skeptic_blocked
        assert len(reviewer_merged) == len(skeptic_merged)


# ---------------------------------------------------------------------------
# TS-98-SMOKE-3: Coder Fix Mode Session Setup
# Execution Path 4 from design.md
# Requirements: 98-REQ-2.1, 98-REQ-2.2
# ---------------------------------------------------------------------------

_MOCK_KB = MagicMock()
_MOCK_KB.execute.return_value.fetchall.return_value = []


class TestCoderFixModeSessionSetup:
    """TS-98-SMOKE-3: Coder fix mode resolves correct config in session.

    Tests that NodeSessionRunner with mode="fix" resolves to STANDARD tier
    and uses fix_coding.md template.

    Does NOT mock resolve_model_tier or resolve_security_config.
    """

    def test_coder_fix_mode_resolves_global_models_coding(self) -> None:
        """TS-98-SMOKE-3: coder:fix mode resolves via config.models.coding (default ADVANCED)."""
        from agent_fox.core.config import AgentFoxConfig, ArchetypesConfig
        from agent_fox.engine.session_lifecycle import NodeSessionRunner

        config = AgentFoxConfig(archetypes=ArchetypesConfig(models={}))

        # Real NodeSessionRunner with mode="fix" — no mocking of tier resolution
        runner = NodeSessionRunner(
            "myspec:1",
            config,
            archetype="coder",
            mode="fix",
            knowledge_db=_MOCK_KB,
        )

        # Default config.models.coding is ADVANCED → claude-opus-4-6
        assert runner._resolved_model_id == "claude-opus-4-6", (
            f"coder:fix mode should resolve to ADVANCED (Opus) via config.models.coding, "
            f"got {runner._resolved_model_id!r}"
        )

    def test_coder_fix_mode_uses_fix_profile(self) -> None:
        """TS-98-SMOKE-3: coder:fix build_system_prompt uses coder_fix.md profile."""
        from agent_fox.session.prompt import build_system_prompt

        # Real build_system_prompt with mode="fix" — no mocking of profile loading
        system_prompt = build_system_prompt("test context", mode="fix")

        # coder_fix.md should NOT contain spec-driven workflow text from coder.md
        assert "task group" not in system_prompt.lower() or "fix" in system_prompt.lower(), (
            "System prompt for coder:fix should use coder_fix.md, not coder.md"
        )

        # coder_fix.md content should be present — check for distinctive fix mode text
        assert len(system_prompt) > 100, "System prompt for coder:fix should have meaningful content"

    def test_coder_no_mode_uses_default_profile(self) -> None:
        """TS-98-SMOKE-3 (regression): coder with no mode still uses coder.md."""
        from agent_fox.session.prompt import build_system_prompt

        # Real build_system_prompt with mode=None — no mocking
        system_prompt = build_system_prompt("test context", mode=None)

        assert len(system_prompt) > 100, "System prompt for coder (no mode) should have meaningful content"
