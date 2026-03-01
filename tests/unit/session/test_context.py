"""Context assembly tests.

Test Spec: TS-03-4 (spec documents), TS-03-5 (memory facts),
           TS-03-E4 (missing spec file)
Requirements: 03-REQ-4.1 through 03-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.session.context import assemble_context


class TestContextAssemblySpecDocs:
    """TS-03-4: Context assembly includes spec documents."""

    def test_includes_requirements_content(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Assembled context includes requirements.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2)
        assert "REQ content here" in ctx

    def test_includes_design_content(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Assembled context includes design.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2)
        assert "Design content here" in ctx

    def test_includes_tasks_content(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Assembled context includes tasks.md content."""
        ctx = assemble_context(tmp_spec_dir, task_group=2)
        assert "Task content here" in ctx

    def test_has_section_headers(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Assembled context has section headers separating documents."""
        ctx = assemble_context(tmp_spec_dir, task_group=2)
        # Should have some kind of header/separator for each document
        # The exact format is implementation-defined, but each section
        # should be clearly delineated
        assert ctx.count("#") >= 1 or ctx.count("---") >= 1


class TestContextAssemblyMemoryFacts:
    """TS-03-5: Context assembly includes memory facts."""

    def test_includes_memory_facts(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Memory facts appear in the assembled context."""
        ctx = assemble_context(
            tmp_spec_dir, task_group=1,
            memory_facts=["Fact 1", "Fact 2"],
        )
        assert "Fact 1" in ctx
        assert "Fact 2" in ctx

    def test_memory_facts_in_labeled_section(
        self, tmp_spec_dir: Path,
    ) -> None:
        """Memory facts appear in a clearly labeled section."""
        ctx = assemble_context(
            tmp_spec_dir, task_group=1,
            memory_facts=["Important fact"],
        )
        # The memory section should have some label
        lower_ctx = ctx.lower()
        assert "memory" in lower_ctx or "fact" in lower_ctx


class TestContextAssemblyMissingFile:
    """TS-03-E4: Context assembly with missing spec file."""

    def test_missing_file_does_not_raise(self, tmp_path: Path) -> None:
        """A missing spec file is skipped without error."""
        spec_dir = tmp_path / "specs" / "partial"
        spec_dir.mkdir(parents=True)
        # Only create requirements.md, skip design.md and tasks.md
        (spec_dir / "requirements.md").write_text("REQ content\n")

        ctx = assemble_context(spec_dir, task_group=1)
        assert "REQ content" in ctx

    def test_returns_nonempty_with_partial_files(
        self, tmp_path: Path,
    ) -> None:
        """Context is non-empty even when some files are missing."""
        spec_dir = tmp_path / "specs" / "partial"
        spec_dir.mkdir(parents=True)
        (spec_dir / "requirements.md").write_text("REQ content\n")

        ctx = assemble_context(spec_dir, task_group=1)
        assert len(ctx) > 0
