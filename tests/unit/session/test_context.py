"""Context assembly tests.

Test Spec: TS-03-4 (spec documents), TS-03-5 (memory facts),
           TS-03-E4 (missing spec file),
           TS-15-1, TS-15-2, TS-15-E1 (test_spec.md inclusion)
Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pytest

from agent_fox.session.prompt import assemble_context


class TestContextAssemblySpecDocs:
    """TS-03-4: Context assembly includes spec documents."""

    def test_includes_requirements_content(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context includes requirements.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        assert "REQ content here" in ctx

    def test_includes_design_content(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context includes design.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        assert "Design content here" in ctx

    def test_includes_tasks_content(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context includes tasks.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        assert "Task content here" in ctx

    def test_has_section_headers(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context has section headers separating documents."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        # Should have some kind of header/separator for each document
        # The exact format is implementation-defined, but each section
        # should be clearly delineated
        assert ctx.count("#") >= 1 or ctx.count("---") >= 1


class TestContextAssemblyMemoryFacts:
    """TS-03-5: Context assembly includes memory facts."""

    def test_includes_memory_facts(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Memory facts appear in the assembled context."""
        ctx = assemble_context(
            tmp_spec_dir,
            task_group=1,
            memory_facts=["Fact 1", "Fact 2"],
            conn=knowledge_conn,
        )
        assert "Fact 1" in ctx
        assert "Fact 2" in ctx

    def test_memory_facts_in_labeled_section(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Memory facts appear in a clearly labeled section."""
        ctx = assemble_context(
            tmp_spec_dir,
            task_group=1,
            memory_facts=["Important fact"],
            conn=knowledge_conn,
        )
        # The memory section should have some label
        lower_ctx = ctx.lower()
        assert "memory" in lower_ctx or "fact" in lower_ctx


class TestContextAssemblyMissingFile:
    """TS-03-E4: Context assembly with missing spec file."""

    def test_missing_file_does_not_raise(self, tmp_path: Path, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """A missing spec file is skipped without error."""
        spec_dir = tmp_path / "specs" / "partial"
        spec_dir.mkdir(parents=True)
        # Only create requirements.md, skip design.md and tasks.md
        (spec_dir / "requirements.md").write_text("REQ content\n")

        ctx = assemble_context(spec_dir, task_group=1, conn=knowledge_conn)
        assert "REQ content" in ctx

    def test_returns_nonempty_with_partial_files(
        self,
        tmp_path: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Context is non-empty even when some files are missing."""
        spec_dir = tmp_path / "specs" / "partial"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("REQ content\n")

        ctx = assemble_context(spec_dir, task_group=1, conn=knowledge_conn)
        assert len(ctx) > 0


class TestContextIncludesTestSpec:
    """TS-15-1: Context assembly includes test_spec.md content.

    Requirement: 15-REQ-1.1
    """

    def test_context_includes_test_spec_content(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context includes test_spec.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        assert "Test spec content here" in ctx

    def test_context_has_test_specification_header(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """Assembled context includes the ## Test Specification header."""
        ctx = assemble_context(tmp_spec_dir, task_group=2, conn=knowledge_conn)
        assert "## Test Specification" in ctx


class TestTestSpecOrdering:
    """TS-15-2: test_spec.md appears after design and before tasks.

    Requirement: 15-REQ-1.2
    """

    def test_test_spec_between_design_and_tasks(
        self,
        tmp_spec_dir: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
    ) -> None:
        """## Test Specification appears after ## Design and before ## Tasks."""
        ctx = assemble_context(tmp_spec_dir, task_group=1, conn=knowledge_conn)
        design_pos = ctx.index("## Design")
        test_spec_pos = ctx.index("## Test Specification")
        tasks_pos = ctx.index("## Tasks")
        assert design_pos < test_spec_pos < tasks_pos


class TestMissingTestSpecFile:
    """TS-15-E1: Missing test_spec.md is skipped with a warning.

    Requirement: 15-REQ-1.E1
    """

    def test_missing_test_spec_does_not_raise(self, tmp_path: Path, knowledge_conn: duckdb.DuckDBPyConnection) -> None:
        """Context assembly succeeds when test_spec.md is absent."""
        spec_dir = tmp_path / "specs" / "no_test_spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("REQ content\n")
        (spec_dir / "design.md").write_text("Design content\n")
        (spec_dir / "tasks.md").write_text("Task content\n")

        # Should not raise
        ctx = assemble_context(spec_dir, task_group=1, conn=knowledge_conn)
        assert "## Test Specification" not in ctx

    def test_missing_test_spec_logs_warning(
        self,
        tmp_path: Path,
        knowledge_conn: duckdb.DuckDBPyConnection,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A warning is logged when test_spec.md is missing."""
        spec_dir = tmp_path / "specs" / "no_test_spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("REQ content\n")
        (spec_dir / "design.md").write_text("Design content\n")
        (spec_dir / "tasks.md").write_text("Task content\n")

        with caplog.at_level(logging.WARNING):
            assemble_context(spec_dir, task_group=1, conn=knowledge_conn)

        assert any("test_spec.md" in record.message for record in caplog.records)
