"""Tests for verification checklist injection into verifier context.

Verifies that assemble_context() includes the verification checklist
section when archetype is 'verifier' and omits it for other archetypes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import duckdb

from agent_fox.knowledge.migrations import run_migrations
from agent_fox.session.context import assemble_context


def _make_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    run_migrations(conn)
    return conn


def _setup_spec(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "10_my_spec"
    spec_dir.mkdir()
    (spec_dir / "requirements.md").write_text(
        "## Requirements\n\n**[10-REQ-1.1]** The system SHALL do X.\n",
        encoding="utf-8",
    )
    (spec_dir / "design.md").write_text("## Overview\n\nDesign doc.\n", encoding="utf-8")
    (spec_dir / "test_spec.md").write_text("## Test Cases\n\nTest spec.\n", encoding="utf-8")
    (spec_dir / "tasks.md").write_text(
        "- [x] 1. Write tests\n  - [x] 1.1 Unit tests\n  - [ ] 1.2 Integration tests\n",
        encoding="utf-8",
    )
    return spec_dir


class TestVerifierChecklistInjection:
    def test_verifier_context_includes_checklist(self, tmp_path: Path) -> None:
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        context = assemble_context(
            spec_dir,
            task_group=1,
            conn=conn,
            project_root=tmp_path,
            archetype="verifier",
        )
        assert "Verification Checklist" in context
        assert "Task Completion Audit" in context
        assert "1.1" in context
        assert "1.2" in context

    def test_coder_context_excludes_checklist(self, tmp_path: Path) -> None:
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        context = assemble_context(
            spec_dir,
            task_group=1,
            conn=conn,
            project_root=tmp_path,
            archetype="coder",
        )
        assert "Verification Checklist" not in context

    def test_no_archetype_excludes_checklist(self, tmp_path: Path) -> None:
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        context = assemble_context(
            spec_dir,
            task_group=1,
            conn=conn,
            project_root=tmp_path,
        )
        assert "Verification Checklist" not in context

    def test_checklist_includes_unchecked_warning(self, tmp_path: Path) -> None:
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        context = assemble_context(
            spec_dir,
            task_group=1,
            conn=conn,
            project_root=tmp_path,
            archetype="verifier",
        )
        assert "UNCHECKED" in context

    def test_checklist_includes_requirement_coverage(self, tmp_path: Path) -> None:
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        context = assemble_context(
            spec_dir,
            task_group=1,
            conn=conn,
            project_root=tmp_path,
            archetype="verifier",
        )
        assert "Requirement-to-Test Coverage" in context
        assert "10-REQ-1.1" in context

    def test_checklist_failure_does_not_crash(self, tmp_path: Path) -> None:
        """If checklist building fails, context assembly continues."""
        spec_dir = _setup_spec(tmp_path)
        conn = _make_conn()
        with patch(
            "agent_fox.spec.verification_checklist.build_verification_checklist",
            side_effect=RuntimeError("boom"),
        ):
            context = assemble_context(
                spec_dir,
                task_group=1,
                conn=conn,
                project_root=tmp_path,
                archetype="verifier",
            )
        assert "Verification Checklist" not in context
        assert "Requirements" in context
