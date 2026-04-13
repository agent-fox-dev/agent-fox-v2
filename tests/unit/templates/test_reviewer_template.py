"""Unit tests for the reviewer.md template file.

Covers:
- reviewer.md exists and contains mode-specific sections (TS-98-7)
- fix_coding.md is retained as a separate template (TS-98-7, 98-REQ-3.3)

Test Spec: TS-98-7
Requirements: 98-REQ-3.1, 98-REQ-3.2, 98-REQ-3.3
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Template directory helper
# ---------------------------------------------------------------------------


def _template_path(name: str) -> Path:
    """Return the absolute path to a template file."""
    import agent_fox

    package_root = Path(agent_fox.__file__).resolve().parent
    return package_root / "_templates" / "prompts" / name


# ---------------------------------------------------------------------------
# TS-98-7: Template File Exists With Mode Sections
# Requirements: 98-REQ-3.1, 98-REQ-3.2
# ---------------------------------------------------------------------------


class TestReviewerTemplate:
    """Verify reviewer.md template exists and contains all mode sections."""

    def test_reviewer_template_exists(self) -> None:
        """TS-98-7: reviewer.md template file exists."""
        template = _template_path("reviewer.md")
        assert template.exists(), (
            f"reviewer.md template not found at {template}. "
            "Create agent_fox/_templates/prompts/reviewer.md as required by 98-REQ-3.1"
        )

    def test_reviewer_template_has_pre_review_section(self) -> None:
        """TS-98-7: reviewer.md contains pre-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "pre-review" in content, (
            "reviewer.md should contain a 'pre-review' section (98-REQ-3.1)"
        )

    def test_reviewer_template_has_drift_review_section(self) -> None:
        """TS-98-7: reviewer.md contains drift-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "drift-review" in content, (
            "reviewer.md should contain a 'drift-review' section (98-REQ-3.1)"
        )

    def test_reviewer_template_has_audit_review_section(self) -> None:
        """TS-98-7: reviewer.md contains audit-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "audit-review" in content, (
            "reviewer.md should contain an 'audit-review' section (98-REQ-3.1)"
        )

    def test_reviewer_template_has_fix_review_section(self) -> None:
        """TS-98-7: reviewer.md contains fix-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "fix-review" in content, (
            "reviewer.md should contain a 'fix-review' section (98-REQ-3.1)"
        )

    def test_reviewer_template_all_modes(self) -> None:
        """TS-98-7: reviewer.md contains all 4 mode sections in one check."""
        template = _template_path("reviewer.md")
        assert template.exists(), (
            "reviewer.md does not exist — 98-REQ-3.1 not implemented"
        )
        content = template.read_text(encoding="utf-8").lower()
        for mode in ("pre-review", "drift-review", "audit-review", "fix-review"):
            assert mode in content, (
                f"reviewer.md missing '{mode}' section (98-REQ-3.1)"
            )


# ---------------------------------------------------------------------------
# TS-98-7 (98-REQ-3.3): fix_coding.md Retained
# Requirement: 98-REQ-3.3
# ---------------------------------------------------------------------------


class TestFixCodingTemplateRetained:
    """Verify fix_coding.md is retained as a separate template file."""

    def test_fix_coding_retained(self) -> None:
        """TS-98-7 (3.3): fix_coding.md template still exists separately."""
        template = _template_path("fix_coding.md")
        assert template.exists(), (
            f"fix_coding.md should be retained as a separate template at {template} "
            "(98-REQ-3.3)"
        )

    def test_fix_coding_not_merged_into_reviewer(self) -> None:
        """TS-98-7 (3.3): fix_coding.md content is separate from reviewer.md."""
        fix_template = _template_path("fix_coding.md")
        reviewer_template = _template_path("reviewer.md")
        if not fix_template.exists() or not reviewer_template.exists():
            pytest.skip("Templates not yet created")
        # Both files should be non-empty distinct files
        assert fix_template.is_file(), "fix_coding.md should be a regular file"
        assert reviewer_template.is_file(), "reviewer.md should be a regular file"
        assert fix_template.stat().st_size > 0, "fix_coding.md should not be empty"
        assert reviewer_template.stat().st_size > 0, "reviewer.md should not be empty"
