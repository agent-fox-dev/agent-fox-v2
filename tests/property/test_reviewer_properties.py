"""Property-based tests for reviewer consolidation correctness.

Covers:
- Mode-archetype mapping correctness (TS-98-P1)
- Convergence dispatch routing (TS-98-P2)
- Injection consistency (TS-98-P3)
- Verifier single-instance invariant (TS-98-P4)
- Coder fix mode equivalence (TS-98-P5)
- Old names rejected from registry (TS-98-P6)

Test Spec: TS-98-P1 through TS-98-P6
Requirements: 98-REQ-1.1 through 98-REQ-1.5, 98-REQ-2.1, 98-REQ-2.2,
              98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3,
              98-REQ-6.2, 98-REQ-7.1
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


pytestmark = pytest.mark.property


# ---------------------------------------------------------------------------
# TS-98-P1: Mode-Archetype Mapping
# Requirements: 98-REQ-1.1 through 98-REQ-1.5
# ---------------------------------------------------------------------------

# Expected config values per reviewer mode:
# (allowlist_must_contain, injection, model_tier)
_REVIEWER_MODE_EXPECTATIONS = {
    "pre-review": ([], "auto_pre", "STANDARD"),
    "drift-review": (["ls", "cat", "git", "grep", "find", "head", "tail", "wc"], "auto_pre", "STANDARD"),
    "audit-review": (["ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv"], "auto_mid", "STANDARD"),
    "fix-review": (["ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv", "make"], None, "ADVANCED"),
}


class TestModeArchetypeMapping:
    """TS-98-P1: Every reviewer mode resolves to correct injection, allowlist, tier."""

    @pytest.mark.parametrize("mode", list(_REVIEWER_MODE_EXPECTATIONS.keys()))
    def test_mode_mapping(self, mode: str) -> None:
        """For each reviewer mode, resolved config has the expected injection/allowlist/tier."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        assert "reviewer" in ARCHETYPE_REGISTRY, "reviewer not in ARCHETYPE_REGISTRY — consolidation not implemented"
        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, mode)

        expected_cmds, expected_injection, expected_tier = _REVIEWER_MODE_EXPECTATIONS[mode]

        # Check model tier
        assert cfg.default_model_tier == expected_tier, (
            f"mode={mode!r}: expected tier {expected_tier!r}, got {cfg.default_model_tier!r}"
        )

        # Check injection
        assert cfg.injection == expected_injection, (
            f"mode={mode!r}: expected injection {expected_injection!r}, got {cfg.injection!r}"
        )

        # Check allowlist contains expected commands
        if mode == "pre-review":
            # pre-review must have empty allowlist
            assert cfg.default_allowlist == [], (
                f"mode=pre-review: allowlist should be empty, got {cfg.default_allowlist}"
            )
        else:
            assert cfg.default_allowlist is not None, f"mode={mode!r}: allowlist should not be None"
            for cmd in expected_cmds:
                assert cmd in cfg.default_allowlist, (
                    f"mode={mode!r}: '{cmd}' missing from allowlist {cfg.default_allowlist}"
                )

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(mode=st.sampled_from(list(_REVIEWER_MODE_EXPECTATIONS.keys())))
    @settings(max_examples=20)
    def test_mode_mapping_property(self, mode: str) -> None:
        """Property: any valid reviewer mode resolves to the correct config."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        assert "reviewer" in ARCHETYPE_REGISTRY
        entry = ARCHETYPE_REGISTRY["reviewer"]
        cfg = resolve_effective_config(entry, mode)

        expected_cmds, expected_injection, expected_tier = _REVIEWER_MODE_EXPECTATIONS[mode]
        assert cfg.default_model_tier == expected_tier
        assert cfg.injection == expected_injection


# ---------------------------------------------------------------------------
# TS-98-P2: Convergence Dispatch Correctness
# Requirements: 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3
# ---------------------------------------------------------------------------


def _make_findings(n: int, severity: str = "critical", base_desc: str = "Issue") -> list:
    """Build a list of Finding objects."""
    from agent_fox.session.convergence import Finding

    return [Finding(severity=severity, description=f"{base_desc} {i}") for i in range(n)]


def _make_audit_result(verdict: str = "PASS"):
    """Build a minimal AuditResult."""
    from agent_fox.session.convergence import AuditEntry, AuditResult

    entry = AuditEntry(
        ts_entry="TS-1",
        test_functions=["test_foo"],
        verdict=verdict,
        notes=None,
    )
    return AuditResult(entries=[entry], overall_verdict=verdict, summary="ok")


class TestConvergenceDispatchCorrectness:
    """TS-98-P2: converge_reviewer routes to correct algorithm by mode."""

    @pytest.mark.parametrize("mode", ["pre-review", "drift-review"])
    def test_pre_drift_dispatch_to_skeptic(self, mode: str) -> None:
        """pre-review and drift-review route to converge_skeptic."""
        from agent_fox.session.convergence import (
            converge_reviewer,  # type: ignore[attr-defined]
            converge_skeptic,
        )

        results = [
            [_make_findings(1, "critical", "Issue")[0]],
            [_make_findings(1, "major", "Other")[0]],
        ]
        result = converge_reviewer(results, mode=mode, block_threshold=5)
        expected = converge_skeptic(results, block_threshold=5)
        assert result == expected, f"mode={mode!r}: expected {expected}, got {result}"

    def test_audit_dispatch_to_auditor(self) -> None:
        """audit-review routes to converge_auditor."""
        from agent_fox.session.convergence import (
            AuditResult,
            converge_auditor,
            converge_reviewer,  # type: ignore[attr-defined]
        )

        audit_results = [_make_audit_result("PASS"), _make_audit_result("FAIL")]
        result = converge_reviewer(audit_results, mode="audit-review")
        expected = converge_auditor(audit_results)

        assert isinstance(result, AuditResult)
        assert result.overall_verdict == expected.overall_verdict

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(mode=st.sampled_from(["pre-review", "drift-review"]))
    @settings(max_examples=20)
    def test_skeptic_modes_always_match(self, mode: str) -> None:
        """Property: any skeptic-routed mode produces same result as converge_skeptic."""
        from agent_fox.session.convergence import (
            converge_reviewer,  # type: ignore[attr-defined]
            converge_skeptic,
        )

        results: list = []
        result = converge_reviewer(results, mode=mode, block_threshold=3)
        expected = converge_skeptic(results, block_threshold=3)
        assert result == expected


# ---------------------------------------------------------------------------
# TS-98-P3: Injection Consistency
# Requirements: 98-REQ-4.2, 98-REQ-4.3, 98-REQ-7.1
# ---------------------------------------------------------------------------


class TestInjectionConsistency:
    """TS-98-P3: Injected nodes never use old archetype names."""

    def _build_graph_and_inject(self):
        """Build a minimal task graph and inject archetypes."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import ensure_graph_archetypes
        from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

        node = Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Test",
            optional=False,
            archetype="coder",
        )
        graph = TaskGraph(
            nodes={"spec:1": node},
            edges=[],
            order=["spec:1"],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )
        # Pass ArchetypesConfig directly (ensure_graph_archetypes expects archetypes_config)
        config = ArchetypesConfig(reviewer=True)
        ensure_graph_archetypes(graph, config)
        return graph

    def test_injection_consistency(self) -> None:
        """TS-98-P3: After injection, no node has old archetype names."""
        graph = self._build_graph_and_inject()
        old_names = {"skeptic", "oracle", "auditor"}
        for node in graph.nodes.values():
            assert node.archetype not in old_names, (
                f"Node {node.id!r} has old archetype {node.archetype!r} — "
                "should have been replaced by reviewer with mode"
            )

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(enabled=st.booleans())
    @settings(max_examples=10)
    def test_no_old_archetypes_any_config(self, enabled: bool) -> None:
        """Property: For any reviewer enable state, old archetype names never appear."""
        from agent_fox.core.config import ArchetypesConfig
        from agent_fox.graph.injection import ensure_graph_archetypes
        from agent_fox.graph.types import Node, PlanMetadata, TaskGraph

        node = Node(
            id="spec:1",
            spec_name="spec",
            group_number=1,
            title="Test",
            optional=False,
            archetype="coder",
        )
        graph = TaskGraph(
            nodes={"spec:1": node},
            edges=[],
            order=["spec:1"],
            metadata=PlanMetadata(created_at="2026-01-01T00:00:00"),
        )
        # Pass ArchetypesConfig directly (ensure_graph_archetypes expects archetypes_config)
        config = ArchetypesConfig(reviewer=enabled)
        ensure_graph_archetypes(graph, config)

        old_names = {"skeptic", "oracle", "auditor"}
        for n in graph.nodes.values():
            assert n.archetype not in old_names, (
                f"Node {n.id!r} has old archetype {n.archetype!r} (reviewer_enabled={enabled})"
            )


# ---------------------------------------------------------------------------
# TS-98-P4: Verifier Single-Instance Invariant
# Requirement: 98-REQ-6.2
# ---------------------------------------------------------------------------


class TestVerifierSingleInstanceInvariant:
    """TS-98-P4: Verifier always resolves to 1 instance after clamping."""

    @pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 100])
    def test_verifier_single(self, n: int) -> None:
        """clamp_instances('verifier', n) always returns 1."""
        from agent_fox.engine.sdk_params import clamp_instances

        result = clamp_instances("verifier", n)
        assert result == 1, f"clamp_instances('verifier', {n}) should return 1, got {result}"

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(n=st.integers(min_value=1, max_value=100))
    @settings(max_examples=30)
    def test_verifier_single_property(self, n: int) -> None:
        """Property: for any n in 1..100, clamp_instances('verifier', n) == 1."""
        from agent_fox.engine.sdk_params import clamp_instances

        assert clamp_instances("verifier", n) == 1, f"clamp_instances('verifier', {n}) should always return 1"


# ---------------------------------------------------------------------------
# TS-98-P5: Coder Fix Mode Equivalence
# Requirements: 98-REQ-2.1, 98-REQ-2.2
# ---------------------------------------------------------------------------


class TestCoderFixModeEquivalence:
    """TS-98-P5: Coder fix mode config matches former fix_coder baseline."""

    def test_coder_fix_equiv(self) -> None:
        """Coder:fix resolved config matches former fix_coder archetype spec."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY, resolve_effective_config

        entry = ARCHETYPE_REGISTRY["coder"]
        assert "fix" in entry.modes, f"coder must have 'fix' mode, got {set(entry.modes.keys())}"
        cfg = resolve_effective_config(entry, "fix")

        # Matches former fix_coder archetype configuration
        assert cfg.default_model_tier == "STANDARD", (
            f"coder:fix tier should be STANDARD, got {cfg.default_model_tier!r}"
        )
        assert cfg.default_max_turns == 300, f"coder:fix max_turns should be 300, got {cfg.default_max_turns}"
        assert cfg.default_thinking_mode == "adaptive", (
            f"coder:fix thinking_mode should be 'adaptive', got {cfg.default_thinking_mode!r}"
        )
        assert cfg.default_thinking_budget == 64000, (
            f"coder:fix thinking_budget should be 64000, got {cfg.default_thinking_budget}"
        )


# ---------------------------------------------------------------------------
# TS-98-P6: Old Names Rejected
# Requirement: 98-REQ-7.1
# ---------------------------------------------------------------------------


class TestOldNamesRejected:
    """TS-98-P6: No old archetype name appears in ARCHETYPE_REGISTRY."""

    @pytest.mark.parametrize(
        "name",
        ["skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"],
    )
    def test_old_names_gone(self, name: str) -> None:
        """For each old name, it must not be in ARCHETYPE_REGISTRY."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert name not in ARCHETYPE_REGISTRY, (
            f"'{name}' should have been removed from ARCHETYPE_REGISTRY during reviewer consolidation (98-REQ-7.1)"
        )

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(name=st.sampled_from(["skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder"]))
    @settings(max_examples=10)
    def test_old_names_rejected_property(self, name: str) -> None:
        """Property: any old archetype name is absent from registry."""
        from agent_fox.archetypes import ARCHETYPE_REGISTRY

        assert name not in ARCHETYPE_REGISTRY, f"'{name}' found in ARCHETYPE_REGISTRY — should be removed"
