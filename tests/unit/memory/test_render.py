"""Tests for human-readable summary rendering.

Test Spec: TS-05-11 (markdown generation), TS-05-E7 (create docs dir),
           TS-05-E8 (empty knowledge base)
Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.E1, 05-REQ-6.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.memory.memory import write_facts
from agent_fox.memory.render import render_summary
from tests.unit.memory.conftest import make_fact


class TestRenderMarkdownByCategory:
    """TS-05-11: Render generates markdown organized by category.

    Requirements: 05-REQ-6.1, 05-REQ-6.2
    """

    def test_renders_sections_by_category(self, tmp_path: Path) -> None:
        """Verify output has section headings for each populated category."""
        memory_path = tmp_path / "memory.jsonl"
        output_path = tmp_path / "docs" / "memory.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        facts = [
            make_fact(
                id="g1",
                content="A gotcha about testing.",
                category="gotcha",
                spec_name="01_core_foundation",
                confidence="high",
            ),
            make_fact(
                id="p1",
                content="A useful pattern.",
                category="pattern",
                spec_name="02_planning_engine",
                confidence="medium",
            ),
        ]
        write_facts(facts, path=memory_path)

        render_summary(memory_path=memory_path, output_path=output_path)

        content = output_path.read_text()
        assert "## Gotchas" in content
        assert "## Patterns" in content

    def test_renders_fact_content_and_attribution(self, tmp_path: Path) -> None:
        """Verify each fact includes content, spec name, and confidence."""
        memory_path = tmp_path / "memory.jsonl"
        output_path = tmp_path / "docs" / "memory.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        facts = [
            make_fact(
                id="g1",
                content="A gotcha about testing.",
                category="gotcha",
                spec_name="01_core_foundation",
                confidence="high",
            ),
        ]
        write_facts(facts, path=memory_path)

        render_summary(memory_path=memory_path, output_path=output_path)

        content = output_path.read_text()
        assert "A gotcha about testing." in content
        assert "spec: 01_core_foundation" in content
        assert "confidence: high" in content


class TestRenderCreatesDocsDir:
    """TS-05-E7: Render creates docs directory.

    Requirement: 05-REQ-6.E1
    """

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Verify render creates the output directory if missing."""
        memory_path = tmp_path / "memory.jsonl"
        output_path = tmp_path / "docs" / "memory.md"

        # Ensure docs/ doesn't exist
        assert not output_path.parent.exists()

        # Write at least an empty memory to avoid file-not-found
        memory_path.write_text("")

        render_summary(memory_path=memory_path, output_path=output_path)

        assert output_path.exists()


class TestRenderEmptyKnowledgeBase:
    """TS-05-E8: Render with empty knowledge base.

    Requirement: 05-REQ-6.E2
    """

    def test_renders_no_facts_message(self, tmp_path: Path) -> None:
        """Verify render produces 'no facts' summary when KB is empty."""
        memory_path = tmp_path / "empty_memory.jsonl"
        output_path = tmp_path / "docs" / "memory.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Either don't create the file, or create it empty
        render_summary(memory_path=memory_path, output_path=output_path)

        content = output_path.read_text()
        assert "No facts have been recorded yet" in content

    def test_renders_no_facts_for_empty_file(self, tmp_path: Path) -> None:
        """Verify render produces 'no facts' for an empty JSONL file."""
        memory_path = tmp_path / "memory.jsonl"
        memory_path.write_text("")
        output_path = tmp_path / "docs" / "memory.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        render_summary(memory_path=memory_path, output_path=output_path)

        content = output_path.read_text()
        assert "No facts have been recorded yet" in content
