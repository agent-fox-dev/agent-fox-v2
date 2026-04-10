"""Integration smoke tests for transient audit reports.

Test Spec: TS-92-SMOKE-1, TS-92-SMOKE-2
Requirements: 92-REQ-1.1, 92-REQ-1.3, 92-REQ-3.1, 92-REQ-4.1, 92-REQ-4.2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.session.convergence import AuditEntry, AuditResult


def _make_fail_result() -> AuditResult:
    return AuditResult(
        entries=[
            AuditEntry(
                ts_entry="TS-92-1",
                test_functions=[],
                verdict="FAIL",
                notes="Failing",
            )
        ],
        overall_verdict="FAIL",
        summary="Tests inadequate.",
    )


def _make_pass_result() -> AuditResult:
    return AuditResult(
        entries=[
            AuditEntry(
                ts_entry="TS-92-1",
                test_functions=["test_foo"],
                verdict="PASS",
                notes="All good",
            )
        ],
        overall_verdict="PASS",
        summary="All tests pass.",
    )


# ---------------------------------------------------------------------------
# TS-92-SMOKE-1: Full lifecycle — FAIL then PASS
# Execution Paths 1 + 2 from design.md
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Audit report appears on FAIL, disappears on PASS, never touches spec dir."""

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
        spec_audit_path = spec_dir / "audit.md"

        # Step 1: FAIL — report should appear at new location
        persist_auditor_results(spec_dir, _make_fail_result())
        assert audit_path.exists(), "Expected audit report at .agent-fox/audit/ after FAIL"
        assert not spec_audit_path.exists(), "Expected NO audit.md in spec directory after FAIL"

        # Step 2: PASS — report should disappear
        persist_auditor_results(spec_dir, _make_pass_result())
        assert not audit_path.exists(), "Expected audit report deleted from .agent-fox/audit/ after PASS"
        assert not spec_audit_path.exists(), "Expected NO audit.md in spec directory after PASS"


# ---------------------------------------------------------------------------
# TS-92-SMOKE-2: Completion cleanup end-to-end
# Execution Path 3 from design.md
# ---------------------------------------------------------------------------


class TestCompletionCleanup:
    """completed_spec_names feeds into cleanup_completed_spec_audits."""

    def test_completion_cleanup(self, tmp_path: Path) -> None:
        from agent_fox.engine.graph_sync import GraphSync
        from agent_fox.session.auditor_output import cleanup_completed_spec_audits

        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)

        foo_path = audit_dir / "audit_05_foo.md"
        bar_path = audit_dir / "audit_10_bar.md"
        foo_path.write_text("foo report")
        bar_path.write_text("bar report")

        # 05_foo: all nodes completed; 10_bar: one node still pending
        node_states = {
            "05_foo:1": "completed",
            "05_foo:2": "completed",
            "10_bar:1": "completed",
            "10_bar:2": "pending",
        }
        edges: dict[str, list[str]] = {
            "05_foo:1": [],
            "05_foo:2": ["05_foo:1"],
            "10_bar:1": [],
            "10_bar:2": ["10_bar:1"],
        }

        gs = GraphSync(node_states, edges)
        completed = gs.completed_spec_names()
        cleanup_completed_spec_audits(tmp_path, completed)

        assert not foo_path.exists(), "Expected 05_foo audit file deleted (all nodes completed)"
        assert bar_path.exists(), "Expected 10_bar audit file intact (has pending node)"
