"""Unit tests for review archetype prompt template format instructions.

Tests that review archetype prompt templates (skeptic, verifier, auditor,
oracle) contain strict format enforcement instructions, a CRITICAL REMINDERS
section, and a negative example of incorrect formatting.

Test Spec: TS-74-1, TS-74-2, TS-74-3, TS-74-4, TS-74-5, TS-74-6
Requirements: 74-REQ-1.1, 74-REQ-1.2, 74-REQ-1.3, 74-REQ-1.4,
              74-REQ-1.5, 74-REQ-1.6
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Path to prompt template files
_TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "agent_fox" / "_templates" / "prompts"

_REVIEW_TEMPLATES = [
    ("skeptic", _TEMPLATE_DIR / "skeptic.md"),
    ("verifier", _TEMPLATE_DIR / "verifier.md"),
    ("auditor", _TEMPLATE_DIR / "auditor.md"),
    ("oracle", _TEMPLATE_DIR / "oracle.md"),
]


class TestSkepticPromptFormatInstructions:
    """TS-74-1: Skeptic prompt contains strict format instructions."""

    def test_contains_no_markdown_fences_instruction(self) -> None:
        """74-REQ-1.1: Skeptic template instructs output without markdown fences."""
        content = (_TEMPLATE_DIR / "skeptic.md").read_text()
        assert "no markdown fences" in content.lower(), (
            "Skeptic template must instruct to output without markdown fences"
        )

    def test_contains_exact_field_names_instruction(self) -> None:
        """74-REQ-1.1: Skeptic template instructs use of exact field names."""
        content = (_TEMPLATE_DIR / "skeptic.md").read_text()
        assert "exact field names" in content.lower() or "exactly the field names" in content.lower(), (
            "Skeptic template must instruct use of exact field names from the schema"
        )


class TestVerifierPromptFormatInstructions:
    """TS-74-2: Verifier prompt contains strict format instructions."""

    def test_contains_no_markdown_fences_instruction(self) -> None:
        """74-REQ-1.2: Verifier template instructs output without markdown fences."""
        content = (_TEMPLATE_DIR / "verifier.md").read_text()
        assert "no markdown fences" in content.lower(), (
            "Verifier template must instruct to output without markdown fences"
        )

    def test_contains_exact_field_names_instruction(self) -> None:
        """74-REQ-1.2: Verifier template instructs use of exact field names."""
        content = (_TEMPLATE_DIR / "verifier.md").read_text()
        assert "exact field names" in content.lower() or "exactly the field names" in content.lower(), (
            "Verifier template must instruct use of exact field names from the schema"
        )


class TestAuditorPromptFormatInstructions:
    """TS-74-3: Auditor prompt contains strict format instructions."""

    def test_contains_no_markdown_fences_instruction(self) -> None:
        """74-REQ-1.3: Auditor template instructs output without markdown fences."""
        content = (_TEMPLATE_DIR / "auditor.md").read_text()
        assert "no markdown fences" in content.lower(), (
            "Auditor template must instruct to output without markdown fences"
        )

    def test_contains_exact_field_names_instruction(self) -> None:
        """74-REQ-1.3: Auditor template instructs use of exact field names."""
        content = (_TEMPLATE_DIR / "auditor.md").read_text()
        assert "exact field names" in content.lower() or "exactly the field names" in content.lower(), (
            "Auditor template must instruct use of exact field names from the schema"
        )


class TestOraclePromptFormatInstructions:
    """TS-74-4: Oracle prompt contains strict format instructions."""

    def test_contains_no_markdown_fences_instruction(self) -> None:
        """74-REQ-1.4: Oracle template instructs output without markdown fences."""
        content = (_TEMPLATE_DIR / "oracle.md").read_text()
        assert "no markdown fences" in content.lower(), (
            "Oracle template must instruct to output without markdown fences"
        )

    def test_contains_exact_field_names_instruction(self) -> None:
        """74-REQ-1.4: Oracle template instructs use of exact field names."""
        content = (_TEMPLATE_DIR / "oracle.md").read_text()
        assert "exact field names" in content.lower() or "exactly the field names" in content.lower(), (
            "Oracle template must instruct use of exact field names from the schema"
        )


class TestCriticalRemindersSection:
    """TS-74-5: Review archetype templates end with a CRITICAL REMINDERS section."""

    @pytest.mark.parametrize("name,path", _REVIEW_TEMPLATES)
    def test_contains_critical_section(self, name: str, path: Path) -> None:
        """74-REQ-1.5: Template contains a CRITICAL section."""
        content = path.read_text()
        assert "CRITICAL" in content, f"{name} template must contain a CRITICAL section repeating format constraints"

    @pytest.mark.parametrize("name,path", _REVIEW_TEMPLATES)
    def test_critical_section_after_output_format(self, name: str, path: Path) -> None:
        """74-REQ-1.5: CRITICAL section appears after the OUTPUT FORMAT section."""
        content = path.read_text()
        assert "OUTPUT FORMAT" in content, f"{name} template must have an OUTPUT FORMAT section"
        assert "CRITICAL" in content, f"{name} template must have a CRITICAL section"
        output_idx = content.index("OUTPUT FORMAT")
        critical_idx = content.index("CRITICAL")
        assert critical_idx > output_idx, (
            f"{name} template: CRITICAL section must appear after OUTPUT FORMAT "
            f"(CRITICAL at {critical_idx}, OUTPUT FORMAT at {output_idx})"
        )


class TestNegativeExample:
    """TS-74-6: Review archetype templates include a negative formatting example."""

    @pytest.mark.parametrize("name,path", _REVIEW_TEMPLATES)
    def test_contains_negative_example_marker(self, name: str, path: Path) -> None:
        """74-REQ-1.6: Template contains a negative example of incorrect formatting."""
        content = path.read_text()
        negative_markers = ["WRONG", "INCORRECT", "DO NOT"]
        assert any(marker in content for marker in negative_markers), (
            f"{name} template must contain a negative example marker "
            f"(one of: {negative_markers!r}) showing incorrect formatting"
        )
