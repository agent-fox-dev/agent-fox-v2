"""Tests for transient audit report behavior.

Test Spec: TS-92-1 through TS-92-7, TS-92-E1 through TS-92-E5
Requirements: 92-REQ-1.1, 92-REQ-1.2, 92-REQ-1.3, 92-REQ-1.E1,
              92-REQ-2.1, 92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2,
              92-REQ-4.1, 92-REQ-4.2, 92-REQ-4.E1, 92-REQ-4.E2
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

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
# TS-92-1: Non-PASS report written to new location
# Requirement: 92-REQ-1.1
# ---------------------------------------------------------------------------


class TestNonPassWritesToNewLocation:
    """FAIL verdict writes report to .agent-fox/audit/audit_{spec_name}.md."""

    def test_non_pass_writes_to_new_location(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        result = _make_fail_result()
        persist_auditor_results(spec_dir, result)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
        assert audit_path.exists()
        assert "# Audit Report: 05_foo" in audit_path.read_text()
        assert not (spec_dir / "audit.md").exists()


# ---------------------------------------------------------------------------
# TS-92-2: Audit directory created automatically
# Requirement: 92-REQ-1.2
# ---------------------------------------------------------------------------


class TestAuditDirCreatedAutomatically:
    """Directory .agent-fox/audit/ is created when it does not exist."""

    def test_audit_dir_created_automatically(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_dir = tmp_path / ".agent-fox" / "audit"
        assert not audit_dir.exists()

        result = _make_fail_result()
        persist_auditor_results(spec_dir, result)

        assert audit_dir.is_dir()


# ---------------------------------------------------------------------------
# TS-92-3: No audit.md in spec directory
# Requirement: 92-REQ-1.3
# ---------------------------------------------------------------------------


class TestNoAuditInSpecDir:
    """After writing, no audit.md exists in the spec directory."""

    def test_no_audit_in_spec_dir(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "10_bar"
        spec_dir.mkdir(parents=True)

        result = AuditResult(
            entries=[],
            overall_verdict="WEAK",
            summary="Weak tests.",
        )
        persist_auditor_results(spec_dir, result)

        assert not (spec_dir / "audit.md").exists()


# ---------------------------------------------------------------------------
# TS-92-4: Overwrite existing report
# Requirement: 92-REQ-2.1
# ---------------------------------------------------------------------------


class TestOverwriteExistingReport:
    """A second audit run for the same spec overwrites the previous report."""

    def test_overwrite_existing_report(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
        result = _make_fail_result()

        persist_auditor_results(spec_dir, result, attempt=1)
        persist_auditor_results(spec_dir, result, attempt=2)

        content = audit_path.read_text()
        assert "**Attempt:** 2" in content
        assert "**Attempt:** 1" not in content


# ---------------------------------------------------------------------------
# TS-92-5: PASS verdict deletes existing report
# Requirement: 92-REQ-3.1
# ---------------------------------------------------------------------------


class TestPassDeletesExistingReport:
    """PASS verdict deletes the audit report and does not write a new one."""

    def test_pass_deletes_existing_report(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"

        # Write initial FAIL report
        persist_auditor_results(spec_dir, _make_fail_result())
        assert audit_path.exists()

        # PASS should delete the report
        persist_auditor_results(spec_dir, _make_pass_result())
        assert not audit_path.exists()


# ---------------------------------------------------------------------------
# TS-92-6: Cleanup deletes reports for completed specs
# Requirements: 92-REQ-4.1, 92-REQ-4.2
# ---------------------------------------------------------------------------


class TestCleanupCompletedSpecs:
    """cleanup_completed_spec_audits deletes completed specs' reports, leaves others."""

    def test_cleanup_completed_specs(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import cleanup_completed_spec_audits

        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)

        foo_path = audit_dir / "audit_05_foo.md"
        bar_path = audit_dir / "audit_10_bar.md"
        foo_path.write_text("report foo")
        bar_path.write_text("report bar")

        cleanup_completed_spec_audits(tmp_path, {"05_foo"})

        assert not foo_path.exists()
        assert bar_path.exists()


# ---------------------------------------------------------------------------
# TS-92-7: GraphSync.completed_spec_names
# Requirement: 92-REQ-4.1
# ---------------------------------------------------------------------------


class TestCompletedSpecNames:
    """completed_spec_names() returns only specs where all nodes are completed."""

    def test_completed_spec_names(self) -> None:
        from agent_fox.engine.graph_sync import GraphSync

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
        result = gs.completed_spec_names()

        assert result == {"05_foo"}


# ---------------------------------------------------------------------------
# TS-92-E1: Directory creation failure
# Requirement: 92-REQ-1.E1
# ---------------------------------------------------------------------------


class TestDirCreationFailure:
    """Filesystem error on directory creation is logged, not raised."""

    def test_dir_creation_failure(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)  # Must create BEFORE patching mkdir

        with caplog.at_level(logging.ERROR):
            with patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
                # Should not raise
                persist_auditor_results(spec_dir, _make_fail_result())

        assert any("error" in r.message.lower() or "failed" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-92-E2: PASS deletion when no file exists
# Requirement: 92-REQ-3.E1
# ---------------------------------------------------------------------------


class TestPassNoFileNoError:
    """PASS verdict with no existing file is a no-op."""

    def test_pass_no_file_no_error(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
        assert not audit_path.exists()

        # Should not raise
        persist_auditor_results(spec_dir, _make_pass_result())

        assert not audit_path.exists()


# ---------------------------------------------------------------------------
# TS-92-E3: PASS deletion filesystem error
# Requirement: 92-REQ-3.E2
# ---------------------------------------------------------------------------


class TestPassDeletionFilesystemError:
    """Filesystem error during PASS deletion is logged, not raised."""

    def test_pass_deletion_filesystem_error(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)
        audit_path = audit_dir / "audit_05_foo.md"
        audit_path.write_text("old report")

        with caplog.at_level(logging.ERROR):
            with patch("pathlib.Path.unlink", side_effect=OSError("denied")):
                # Should not raise
                persist_auditor_results(spec_dir, _make_pass_result())

        assert any("error" in r.message.lower() or "failed" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# TS-92-E4: Completion cleanup when no files exist
# Requirement: 92-REQ-4.E1
# ---------------------------------------------------------------------------


class TestCleanupNoFilesNoError:
    """Cleanup with no matching files is a no-op."""

    def test_cleanup_no_files_no_error(self, tmp_path: Path) -> None:
        from agent_fox.session.auditor_output import cleanup_completed_spec_audits

        # No files exist — should not raise
        cleanup_completed_spec_audits(tmp_path, {"05_foo"})


# ---------------------------------------------------------------------------
# TS-92-E5: Completion cleanup partial failure
# Requirement: 92-REQ-4.E2
# ---------------------------------------------------------------------------


class TestCleanupPartialFailure:
    """If deletion fails for one spec, remaining specs are still processed."""

    def test_cleanup_partial_failure(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from agent_fox.session.auditor_output import cleanup_completed_spec_audits

        audit_dir = tmp_path / ".agent-fox" / "audit"
        audit_dir.mkdir(parents=True)

        foo_path = audit_dir / "audit_05_foo.md"
        bar_path = audit_dir / "audit_10_bar.md"
        foo_path.write_text("report foo")
        bar_path.write_text("report bar")

        original_unlink = Path.unlink

        def fail_for_foo(self: Path, missing_ok: bool = False) -> None:
            if self.name == "audit_05_foo.md":
                raise OSError("denied")
            original_unlink(self, missing_ok=missing_ok)

        with caplog.at_level(logging.WARNING):
            with patch.object(Path, "unlink", fail_for_foo):
                cleanup_completed_spec_audits(tmp_path, {"05_foo", "10_bar"})

        # bar should be deleted despite foo's failure
        assert not bar_path.exists()

        # warning or error should be logged
        assert any(
            "warning" in r.levelname.lower() or "error" in r.message.lower() or "failed" in r.message.lower()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# Regression: persist_auditor_results uses explicit project_root (#355)
# ---------------------------------------------------------------------------


class TestProjectRootParameter:
    """Verify persist_auditor_results uses project_root instead of parent.parent."""

    def test_explicit_project_root(self, tmp_path: Path) -> None:
        """Regression for #355: project_root overrides spec_dir.parent.parent."""
        from agent_fox.session.auditor_output import persist_auditor_results

        # spec_dir is deeply nested — parent.parent would be wrong
        spec_dir = tmp_path / "some" / "deep" / "path" / "myspec"
        spec_dir.mkdir(parents=True)

        persist_auditor_results(spec_dir, _make_fail_result(), project_root=tmp_path)

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_myspec.md"
        assert audit_path.exists(), "audit report should be at project_root/.agent-fox/audit/"

    def test_fallback_to_parent_parent(self, tmp_path: Path) -> None:
        """Without project_root, falls back to spec_dir.parent.parent."""
        from agent_fox.session.auditor_output import persist_auditor_results

        spec_dir = tmp_path / ".specs" / "05_foo"
        spec_dir.mkdir(parents=True)

        persist_auditor_results(spec_dir, _make_fail_result())

        audit_path = tmp_path / ".agent-fox" / "audit" / "audit_05_foo.md"
        assert audit_path.exists(), "fallback should still work for standard .specs/ layout"
