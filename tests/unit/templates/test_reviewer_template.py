"""Unit tests for the reviewer.md profile template file.

Covers:
- reviewer.md exists and contains mode-specific sections (TS-98-7)
- coder_fix.md profile exists (migrated from fix_coding.md, TS-98-7, 98-REQ-3.3)

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
    """Return the absolute path to a profile template file."""
    import agent_fox

    package_root = Path(agent_fox.__file__).resolve().parent
    return package_root / "_templates" / "profiles" / name


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
            "Create agent_fox/_templates/profiles/reviewer.md as required by 98-REQ-3.1"
        )

    def test_reviewer_template_has_pre_review_section(self) -> None:
        """TS-98-7: reviewer.md contains pre-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "pre-review" in content, "reviewer.md should contain a 'pre-review' section (98-REQ-3.1)"

    def test_reviewer_template_has_drift_review_section(self) -> None:
        """TS-98-7: reviewer.md contains drift-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "drift-review" in content, "reviewer.md should contain a 'drift-review' section (98-REQ-3.1)"

    def test_reviewer_template_has_audit_review_section(self) -> None:
        """TS-98-7: reviewer.md contains audit-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "audit-review" in content, "reviewer.md should contain an 'audit-review' section (98-REQ-3.1)"

    def test_reviewer_template_has_fix_review_section(self) -> None:
        """TS-98-7: reviewer.md contains fix-review mode section."""
        template = _template_path("reviewer.md")
        if not template.exists():
            pytest.skip("reviewer.md not yet created")
        content = template.read_text(encoding="utf-8").lower()
        assert "fix-review" in content, "reviewer.md should contain a 'fix-review' section (98-REQ-3.1)"

    def test_reviewer_template_all_modes(self) -> None:
        """TS-98-7: reviewer.md contains all 4 mode sections in one check."""
        template = _template_path("reviewer.md")
        assert template.exists(), "reviewer.md does not exist — 98-REQ-3.1 not implemented"
        content = template.read_text(encoding="utf-8").lower()
        for mode in ("pre-review", "drift-review", "audit-review", "fix-review"):
            assert mode in content, f"reviewer.md missing '{mode}' section (98-REQ-3.1)"


# ---------------------------------------------------------------------------
# TS-98-7 (98-REQ-3.3): coder_fix.md Profile Exists
# Requirement: 98-REQ-3.3 (migrated from fix_coding.md template to profile)
# ---------------------------------------------------------------------------


class TestFixCoderProfileRetained:
    """Verify coder_fix.md is available as a mode-specific profile."""

    def test_coder_fix_profile_exists(self) -> None:
        """TS-98-7 (3.3): coder_fix.md profile exists in profiles directory."""
        template = _template_path("coder_fix.md")
        assert template.exists(), f"coder_fix.md should exist at {template} (98-REQ-3.3)"

    def test_coder_fix_profile_separate_from_reviewer(self) -> None:
        """TS-98-7 (3.3): coder_fix.md content is separate from reviewer.md."""
        fix_profile = _template_path("coder_fix.md")
        reviewer_profile = _template_path("reviewer.md")
        if not fix_profile.exists() or not reviewer_profile.exists():
            pytest.skip("Profiles not yet created")
        assert fix_profile.is_file(), "coder_fix.md should be a regular file"
        assert reviewer_profile.is_file(), "reviewer.md should be a regular file"
        assert fix_profile.stat().st_size > 0, "coder_fix.md should not be empty"
        assert reviewer_profile.stat().st_size > 0, "reviewer.md should not be empty"
