"""Property tests for transient audit reports.

Test Spec: TS-92-P1 through TS-92-P4
Requirements: 92-REQ-1.1, 92-REQ-1.3, 92-REQ-2.1, 92-REQ-3.1, 92-REQ-3.E1,
              92-REQ-4.1, 92-REQ-4.2, 92-REQ-4.E1
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from string import ascii_lowercase, digits

import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

from agent_fox.session.convergence import AuditResult

_SPEC_NAME_ALPHABET = ascii_lowercase + digits + "_"

_spec_name_strategy = st.text(
    alphabet=_SPEC_NAME_ALPHABET,
    min_size=3,
    max_size=40,
)

_non_pass_verdict_strategy = st.sampled_from(["FAIL", "WEAK"])


# ---------------------------------------------------------------------------
# TS-92-P1: Output location for arbitrary spec names
# Property 1 from design.md
# Validates: 92-REQ-1.1, 92-REQ-1.3
# ---------------------------------------------------------------------------


class TestOutputLocationInvariant:
    """For any valid spec name and non-PASS verdict, report at .agent-fox/audit/."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        spec_name=_spec_name_strategy,
        verdict=_non_pass_verdict_strategy,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_output_location_invariant(self, spec_name: str, verdict: str) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            spec_dir = project_root / ".specs" / spec_name
            spec_dir.mkdir(parents=True, exist_ok=True)

            result = AuditResult(
                entries=[],
                overall_verdict=verdict,
                summary="test",
            )
            persist_auditor_results(spec_dir, result)

            audit_path = project_root / ".agent-fox" / "audit" / f"audit_{spec_name}.md"
            assert audit_path.exists(), f"Expected audit file at {audit_path} for spec_name={spec_name!r}"
            assert not (spec_dir / "audit.md").exists(), f"Expected NO audit.md in spec_dir for spec_name={spec_name!r}"


# ---------------------------------------------------------------------------
# TS-92-P2: PASS always deletes
# Property 2 from design.md
# Validates: 92-REQ-3.1, 92-REQ-3.E1
# ---------------------------------------------------------------------------


class TestPassAlwaysDeletes:
    """For any spec name, after PASS verdict, no audit file remains."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        spec_name=_spec_name_strategy,
        pre_existing=st.booleans(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_pass_always_deletes(self, spec_name: str, pre_existing: bool) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            spec_dir = project_root / ".specs" / spec_name
            spec_dir.mkdir(parents=True, exist_ok=True)

            audit_dir = project_root / ".agent-fox" / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            audit_path = audit_dir / f"audit_{spec_name}.md"

            if pre_existing:
                audit_path.write_text("old report")

            pass_result = AuditResult(
                entries=[],
                overall_verdict="PASS",
                summary="ok",
            )
            persist_auditor_results(spec_dir, pass_result)

            assert not audit_path.exists(), (
                f"Expected no audit file after PASS for spec_name={spec_name!r}, pre_existing={pre_existing}"
            )


# ---------------------------------------------------------------------------
# TS-92-P3: Cleanup only deletes matching specs
# Property 3 from design.md
# Validates: 92-REQ-4.1, 92-REQ-4.2, 92-REQ-4.E1
# ---------------------------------------------------------------------------


class TestCleanupOnlyDeletesMatching:
    """Cleanup deletes exactly the files for completed specs."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(
        all_specs=st.sets(_spec_name_strategy, min_size=1, max_size=5),
        data=st.data(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_cleanup_only_deletes_matching(self, all_specs: set[str], data: st.DataObject) -> None:
        from agent_fox.session.auditor_output import cleanup_completed_spec_audits

        all_specs_list = sorted(all_specs)
        completed: set[str] = data.draw(st.sets(st.sampled_from(all_specs_list), max_size=len(all_specs_list)))

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            audit_dir = project_root / ".agent-fox" / "audit"
            audit_dir.mkdir(parents=True)

            for spec in all_specs:
                (audit_dir / f"audit_{spec}.md").write_text("report")

            cleanup_completed_spec_audits(project_root, completed)

            for spec in completed:
                assert not (audit_dir / f"audit_{spec}.md").exists(), (
                    f"Expected {spec} audit file deleted (in completed set)"
                )
            for spec in all_specs - completed:
                assert (audit_dir / f"audit_{spec}.md").exists(), (
                    f"Expected {spec} audit file intact (not in completed set)"
                )


# ---------------------------------------------------------------------------
# TS-92-P4: Overwrite produces single file with latest content
# Property 4 from design.md
# Validates: 92-REQ-2.1
# ---------------------------------------------------------------------------


class TestOverwriteIdempotency:
    """Multiple writes for the same spec leave exactly one file with latest content."""

    @pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
    @given(n=st.integers(min_value=1, max_value=5))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_overwrite_idempotency(self, n: int) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            spec_name = "05_foo"
            spec_dir = project_root / ".specs" / spec_name
            spec_dir.mkdir(parents=True)

            result = AuditResult(
                entries=[],
                overall_verdict="FAIL",
                summary="failing",
            )

            for i in range(1, n + 1):
                persist_auditor_results(spec_dir, result, attempt=i)

            audit_dir = project_root / ".agent-fox" / "audit"
            files = list(audit_dir.glob(f"audit_{spec_name}*.md"))
            assert len(files) == 1, f"Expected 1 audit file after {n} writes, got {len(files)}"
            assert f"**Attempt:** {n}" in files[0].read_text(), f"Expected attempt {n} in file content"
