"""Tests for the verification checklist builder.

Verifies that the checklist correctly audits task completion, maps
requirements to test functions, and renders a structured markdown
document for verifier context injection.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from agent_fox.knowledge.migrations import run_migrations
from agent_fox.spec.verification_checklist import (
    RequirementMapping,
    SubtaskAuditEntry,
    VerificationChecklist,
    build_verification_checklist,
    render_checklist_markdown,
    scan_requirement_test_coverage,
)


def _make_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


def _write_tasks(spec_dir: Path, content: str) -> None:
    (spec_dir / "tasks.md").write_text(content, encoding="utf-8")


def _write_requirements(spec_dir: Path, content: str) -> None:
    (spec_dir / "requirements.md").write_text(content, encoding="utf-8")


class TestSubtaskAudit:
    def test_all_checked_returns_no_unchecked(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [x] 1. Write failing tests\n"
            "  - [x] 1.1 Write unit tests\n"
            "  - [x] 1.2 Write integration tests\n"
            "  - [x] 1.V Verify task group 1\n",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        unchecked = [e for e in checklist.task_audit if not e.checked]
        assert unchecked == []

    def test_unchecked_subtasks_flagged(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [ ] 1. Write failing tests\n"
            "  - [x] 1.1 Write unit tests\n"
            "  - [ ] 1.2 Write integration tests\n"
            "  - [ ] 1.V Verify task group 1\n",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        unchecked = [e for e in checklist.task_audit if not e.checked]
        assert len(unchecked) == 2
        ids = {e.subtask_id for e in unchecked}
        assert "1.2" in ids
        assert "1.V" in ids

    def test_erratum_covers_unchecked_subtask(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [ ] 1. Write failing tests\n"
            "  - [ ] 1.1 Skipped subtask\n",
        )
        conn = _make_conn()
        conn.execute(
            "INSERT INTO errata "
            "(id, spec_name, task_group, finding_summary, created_at) "
            "VALUES ('e1', '10_my_spec', '1', 'Documented deviation for 1.1', CURRENT_TIMESTAMP)",
        )
        checklist = build_verification_checklist(spec_dir, conn)
        assert checklist.has_errata is True

    def test_multiple_groups_audited(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [x] 1. Write failing tests\n"
            "  - [x] 1.1 Unit tests\n"
            "- [ ] 2. Implement\n"
            "  - [x] 2.1 Core logic\n"
            "  - [ ] 2.2 Edge cases\n",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        groups = {e.group_number for e in checklist.task_audit}
        assert 1 in groups
        assert 2 in groups

    def test_skipped_subtasks_excluded(self, tmp_path: Path) -> None:
        """Subtasks marked with [-] or [~] are intentionally skipped."""
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [-] 1. Partially done\n"
            "  - [x] 1.1 Done\n"
            "  - [-] 1.2 Skipped intentionally\n"
            "  - [~] 1.3 Not applicable\n",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        unchecked = [e for e in checklist.task_audit if not e.checked and not e.skipped]
        assert unchecked == []


class TestRequirementTestCoverage:
    def test_requirement_found_in_test_docstring(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_requirements(
            spec_dir,
            "## Requirements\n\n"
            "### Requirement 1: Core Feature\n"
            "**[10-REQ-1.1]** The system SHALL do X.\n",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_core.py").write_text(
            '"""Tests for core feature.\n\nRequirements: 10-REQ-1.1\n"""\n\n'
            "def test_core_does_x():\n    pass\n",
            encoding="utf-8",
        )
        mappings = scan_requirement_test_coverage(spec_dir, tests_dir)
        mapped = {m.requirement_id: m for m in mappings}
        assert "10-REQ-1.1" in mapped
        assert mapped["10-REQ-1.1"].covered is True

    def test_requirement_found_in_function_name(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_requirements(
            spec_dir,
            "## Requirements\n\n"
            "**[10-REQ-1.1]** The system SHALL do X.\n",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_feature.py").write_text(
            "def test_req_10_1_1_something():\n    pass\n",
            encoding="utf-8",
        )
        mappings = scan_requirement_test_coverage(spec_dir, tests_dir)
        mapped = {m.requirement_id: m for m in mappings}
        assert "10-REQ-1.1" in mapped
        assert mapped["10-REQ-1.1"].covered is True

    def test_unmapped_requirement_flagged(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_requirements(
            spec_dir,
            "## Requirements\n\n"
            "**[10-REQ-1.1]** The system SHALL do X.\n"
            "**[10-REQ-1.2]** The system SHALL do Y.\n",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_feature.py").write_text(
            "# Tests for 10-REQ-1.1\ndef test_x():\n    pass\n",
            encoding="utf-8",
        )
        mappings = scan_requirement_test_coverage(spec_dir, tests_dir)
        mapped = {m.requirement_id: m for m in mappings}
        assert mapped["10-REQ-1.1"].covered is True
        assert mapped["10-REQ-1.2"].covered is False

    def test_no_requirements_file(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        mappings = scan_requirement_test_coverage(spec_dir, tests_dir)
        assert mappings == []

    def test_no_tests_dir(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_requirements(
            spec_dir,
            "**[10-REQ-1.1]** The system SHALL do X.\n",
        )
        tests_dir = tmp_path / "nonexistent"
        mappings = scan_requirement_test_coverage(spec_dir, tests_dir)
        mapped = {m.requirement_id: m for m in mappings}
        assert mapped["10-REQ-1.1"].covered is False


class TestRenderChecklistMarkdown:
    def test_renders_task_audit_section(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [ ] 1. Write tests\n"
            "  - [x] 1.1 Unit tests\n"
            "  - [ ] 1.2 Integration tests\n",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        md = render_checklist_markdown(checklist)
        assert "## Verification Checklist" in md
        assert "Task Completion Audit" in md
        assert "1.1" in md
        assert "1.2" in md

    def test_renders_requirement_coverage(self, tmp_path: Path) -> None:
        checklist = VerificationChecklist(
            spec_name="10_my_spec",
            task_audit=[],
            requirement_coverage=[
                RequirementMapping("10-REQ-1.1", True, ["test_core.py"]),
                RequirementMapping("10-REQ-1.2", False, []),
            ],
            has_errata=False,
        )
        md = render_checklist_markdown(checklist)
        assert "Requirement-to-Test Coverage" in md
        assert "10-REQ-1.1" in md
        assert "10-REQ-1.2" in md
        assert "UNCOVERED" in md

    def test_renders_errata_notice(self, tmp_path: Path) -> None:
        checklist = VerificationChecklist(
            spec_name="10_my_spec",
            task_audit=[
                SubtaskAuditEntry(1, "1.1", "Do stuff", False, False),
            ],
            requirement_coverage=[],
            has_errata=True,
        )
        md = render_checklist_markdown(checklist)
        assert "errata" in md.lower()

    def test_empty_checklist_renders_cleanly(self) -> None:
        checklist = VerificationChecklist(
            spec_name="10_my_spec",
            task_audit=[],
            requirement_coverage=[],
            has_errata=False,
        )
        md = render_checklist_markdown(checklist)
        assert "## Verification Checklist" in md


class TestBuildVerificationChecklist:
    def test_full_checklist_integration(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        _write_tasks(
            spec_dir,
            "- [x] 1. Write failing tests\n"
            "  - [x] 1.1 Unit tests\n"
            "  - [x] 1.V Verify\n"
            "- [x] 2. Implement\n"
            "  - [x] 2.1 Core\n"
            "  - [x] 2.V Verify\n",
        )
        _write_requirements(
            spec_dir,
            "## Requirements\n\n"
            "**[10-REQ-1.1]** The system SHALL do X.\n",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_core.py").write_text(
            "# 10-REQ-1.1\ndef test_x():\n    pass\n",
            encoding="utf-8",
        )
        conn = _make_conn()
        checklist = build_verification_checklist(
            spec_dir, conn, tests_dir=tests_dir
        )
        assert checklist.spec_name == "10_my_spec"
        assert len(checklist.task_audit) > 0
        assert len(checklist.requirement_coverage) == 1
        assert checklist.requirement_coverage[0].covered is True

    def test_missing_tasks_file_returns_empty_audit(self, tmp_path: Path) -> None:
        spec_dir = tmp_path / "10_my_spec"
        spec_dir.mkdir()
        conn = _make_conn()
        checklist = build_verification_checklist(spec_dir, conn)
        assert checklist.task_audit == []
