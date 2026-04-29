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


class TestAuditReviewProfile:
    """Verify reviewer_audit-review.md grades test design quality, not execution results."""

    def test_audit_review_profile_exists(self) -> None:
        """Audit-review profile template file exists."""
        template = _template_path("reviewer_audit-review.md")
        assert template.exists(), f"reviewer_audit-review.md not found at {template}"

    def test_audit_review_grades_design_not_execution(self) -> None:
        """Audit-review profile instructs grading design quality, not pass/fail status."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert "design quality" in content.lower(), (
            "Audit-review profile should instruct grading 'design quality'"
        )
        assert "not execution results" in content.lower() or "not pass/fail status" in content.lower(), (
            "Audit-review profile should explicitly state not to grade execution results"
        )

    def test_audit_review_has_anti_pattern_guidance(self) -> None:
        """Audit-review profile contains anti-pattern guidance against penalising failures."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert "anti-pattern" in content.lower(), (
            "Audit-review profile should contain anti-pattern guidance"
        )
        assert "INCORRECT" in content, (
            "Audit-review profile should show INCORRECT example of the anti-pattern"
        )
        assert "CORRECT" in content, (
            "Audit-review profile should show CORRECT example"
        )

    def test_audit_review_pass_verdict_ignores_execution_status(self) -> None:
        """PASS verdict definition mentions 'regardless of pass/fail status'."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert "regardless of" in content.lower(), (
            "PASS verdict should state it applies regardless of current pass/fail status"
        )

    def test_audit_review_weak_means_design_flaws(self) -> None:
        """WEAK verdict definition focuses on actual design flaws, not execution failures."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert "design flaws" in content.lower(), (
            "WEAK verdict should be defined as actual design flaws"
        )

    def test_audit_review_has_upstream_dependency_guidance(self) -> None:
        """Audit-review profile addresses multi-spec upstream dependency scenario."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert "upstream" in content.lower() or "other specs" in content.lower(), (
            "Audit-review profile should address tests failing due to unimplemented upstream specs"
        )

    def test_audit_review_has_json_output_format(self) -> None:
        """Audit-review profile specifies JSON output with required fields."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        assert '"audit"' in content
        assert '"ts_entry"' in content
        assert '"verdict"' in content
        assert '"overall_verdict"' in content

    def test_audit_review_identity_does_not_require_passing(self) -> None:
        """Identity section should not require tests to be 'passing'."""
        template = _template_path("reviewer_audit-review.md")
        content = template.read_text(encoding="utf-8")
        # Extract just the Identity section (up to ## Rules)
        identity_end = content.find("## Rules")
        identity_section = content[:identity_end] if identity_end > 0 else content[:200]
        assert "passing" not in identity_section.lower(), (
            "Identity section should not require 'passing' tests — "
            "the reviewer grades design quality, not execution results"
        )


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
