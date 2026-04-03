"""Unit tests for robustness validation rules (Phases 1, 3, 4).

Tests for: missing-ears-keyword, missing-correctness-properties,
missing-error-table, missing-definition-of-done, missing-coverage-matrix,
missing-traceability-table, inconsistent-req-id-format, untraced-test-spec,
untraced-property, orphan-error-ref, coverage-matrix-mismatch,
traceability-table-mismatch, missing-section, extra-section.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.validator import (
    check_coverage_matrix_completeness,
    check_design_completeness,
    check_inconsistent_req_id_format,
    check_missing_coverage_matrix,
    check_missing_ears_keyword,
    check_missing_traceability_table,
    check_orphan_error_refs,
    check_section_schema,
    check_traceability_table_completeness,
    check_untraced_properties,
    check_untraced_test_specs,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "specs"


# =============================================================================
# Phase 1: Completeness checks
# =============================================================================


class TestMissingEarsKeyword:
    """Verify check_missing_ears_keyword detects criteria without SHALL."""

    def test_detects_criterion_without_shall(self) -> None:
        fixture = FIXTURES_DIR / "no_ears_spec"
        findings = check_missing_ears_keyword("no_ears_spec", fixture)
        assert len(findings) == 1
        assert findings[0].rule == "missing-ears-keyword"
        assert "99-REQ-1.1" in findings[0].message

    def test_does_not_flag_criteria_with_shall(self) -> None:
        fixture = FIXTURES_DIR / "no_ears_spec"
        findings = check_missing_ears_keyword("no_ears_spec", fixture)
        # Only one finding — the criterion with SHALL (99-REQ-1.2) is clean
        flagged_ids = [f.message for f in findings]
        assert not any("99-REQ-1.2" in m for m in flagged_ids)

    def test_severity_is_warning(self) -> None:
        fixture = FIXTURES_DIR / "no_ears_spec"
        findings = check_missing_ears_keyword("no_ears_spec", fixture)
        for f in findings:
            assert f.severity == "warning"

    def test_clean_spec_produces_no_findings(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_missing_ears_keyword("robust_complete_spec", fixture)
        assert len(findings) == 0

    def test_includes_line_number(self) -> None:
        fixture = FIXTURES_DIR / "no_ears_spec"
        findings = check_missing_ears_keyword("no_ears_spec", fixture)
        for f in findings:
            assert f.line is not None

    def test_multiline_criterion_with_shall_on_continuation(self) -> None:
        """SHALL on a continuation line should not trigger a false positive."""
        fixture = FIXTURES_DIR / "multiline_ears_spec"
        findings = check_missing_ears_keyword("multiline_ears_spec", fixture)
        # Only 99-REQ-1.3 lacks SHALL — the two multi-line criteria are fine
        assert len(findings) == 1
        assert "99-REQ-1.3" in findings[0].message

    def test_multiline_does_not_flag_valid_criteria(self) -> None:
        fixture = FIXTURES_DIR / "multiline_ears_spec"
        findings = check_missing_ears_keyword("multiline_ears_spec", fixture)
        flagged_ids = [f.message for f in findings]
        assert not any("99-REQ-1.1" in m for m in flagged_ids)
        assert not any("99-REQ-1.2" in m for m in flagged_ids)


class TestDesignCompleteness:
    """Verify check_design_completeness detects missing design sections."""

    def test_minimal_design_triggers_all_three(self) -> None:
        fixture = FIXTURES_DIR / "warnings_only_spec"
        findings = check_design_completeness("warnings_only_spec", fixture)
        rules = {f.rule for f in findings}
        assert "missing-correctness-properties" in rules
        assert "missing-error-table" in rules
        assert "missing-definition-of-done" in rules

    def test_complete_design_no_findings(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_design_completeness("robust_complete_spec", fixture)
        assert len(findings) == 0

    def test_severity_is_warning(self) -> None:
        fixture = FIXTURES_DIR / "warnings_only_spec"
        findings = check_design_completeness("warnings_only_spec", fixture)
        for f in findings:
            assert f.severity == "warning"

    def test_detects_properties_heading_without_entries(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text(
            "# Design\n\n"
            "## Correctness Properties\n\n"
            "No properties defined yet.\n\n"
            "## Error Handling\n\n"
            "| Condition | Behavior | Req |\n"
            "|-----------|----------|-----|\n"
            "| Error | Handle | REQ |\n\n"
            "## Definition of Done\n\nAll tests pass.\n"
        )
        findings = check_design_completeness("test", tmp_path)
        rules = {f.rule for f in findings}
        assert "missing-correctness-properties" in rules
        assert "missing-error-table" not in rules
        assert "missing-definition-of-done" not in rules


class TestMissingCoverageMatrix:
    """Verify check_missing_coverage_matrix detects missing coverage matrix."""

    def test_missing_matrix_flagged(self) -> None:
        fixture = FIXTURES_DIR / "untraced_spec"
        findings = check_missing_coverage_matrix("untraced_spec", fixture)
        assert len(findings) == 1
        assert findings[0].rule == "missing-coverage-matrix"

    def test_present_matrix_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_missing_coverage_matrix("robust_complete_spec", fixture)
        assert len(findings) == 0


class TestMissingTraceabilityTable:
    """Verify check_missing_traceability_table detects missing traceability."""

    def test_missing_table_flagged(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.md"
        tasks.write_text("# Tasks\n\n- [ ] 1. Do stuff\n  - [ ] 1.1 Subtask\n")
        findings = check_missing_traceability_table("test", tmp_path)
        assert len(findings) == 1
        assert findings[0].rule == "missing-traceability-table"

    def test_present_table_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_missing_traceability_table("robust_complete_spec", fixture)
        assert len(findings) == 0


class TestInconsistentReqIdFormat:
    """Verify check_inconsistent_req_id_format detects mixed formats."""

    def test_mixed_format_flagged(self) -> None:
        fixture = FIXTURES_DIR / "mixed_format_spec"
        findings = check_inconsistent_req_id_format("mixed_format_spec", fixture)
        assert len(findings) == 1
        assert findings[0].rule == "inconsistent-req-id-format"
        assert findings[0].severity == "hint"

    def test_consistent_format_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_inconsistent_req_id_format("robust_complete_spec", fixture)
        assert len(findings) == 0


# =============================================================================
# Phase 3: Traceability chain checks
# =============================================================================


class TestUntracedTestSpecs:
    """Verify check_untraced_test_specs detects test entries not in tasks."""

    def test_detects_unreferenced_test_spec(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_untraced_test_specs("traceability_gaps_spec", fixture)
        # TS-99-3 and TS-99-P1 are not referenced in tasks.md
        unreferenced = {f.message.split()[3] for f in findings}
        assert "TS-99-3" in unreferenced
        assert "TS-99-P1" in unreferenced

    def test_severity_is_warning(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_untraced_test_specs("traceability_gaps_spec", fixture)
        for f in findings:
            assert f.severity == "warning"

    def test_fully_traced_produces_no_findings(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_untraced_test_specs("robust_complete_spec", fixture)
        assert len(findings) == 0


class TestUntracedProperties:
    """Verify check_untraced_properties detects properties without test entries."""

    def test_detects_missing_property_test(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_untraced_properties("99_traceability_gaps_spec", fixture)
        # Property 2 has no TS-99-P2 in test_spec.md
        assert len(findings) == 1
        assert "Property 2" in findings[0].message
        assert "TS-99-P2" in findings[0].message

    def test_all_properties_traced_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_untraced_properties("99_robust_complete_spec", fixture)
        assert len(findings) == 0


class TestOrphanErrorRefs:
    """Verify check_orphan_error_refs detects invalid req IDs in error table."""

    def test_detects_nonexistent_req_in_error_table(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_orphan_error_refs("traceability_gaps_spec", fixture)
        # 99-REQ-9.9 is in error table but not in requirements.md
        assert len(findings) == 1
        assert "99-REQ-9.9" in findings[0].message

    def test_valid_refs_produce_no_findings(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_orphan_error_refs("robust_complete_spec", fixture)
        assert len(findings) == 0


class TestCoverageMatrixCompleteness:
    """Verify check_coverage_matrix_completeness detects missing entries."""

    def test_detects_missing_requirement_in_matrix(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_coverage_matrix_completeness("traceability_gaps_spec", fixture)
        # 99-REQ-2.1 is in requirements.md but not in coverage matrix
        missing_ids = {f.message.split()[1] for f in findings}
        assert "99-REQ-2.1" in missing_ids

    def test_complete_matrix_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_coverage_matrix_completeness("robust_complete_spec", fixture)
        assert len(findings) == 0


class TestTraceabilityTableCompleteness:
    """Verify check_traceability_table_completeness detects missing entries."""

    def test_detects_missing_requirement_in_table(self) -> None:
        fixture = FIXTURES_DIR / "traceability_gaps_spec"
        findings = check_traceability_table_completeness("traceability_gaps_spec", fixture)
        # 99-REQ-1.2 and 99-REQ-2.1 are in requirements but not in traceability
        missing_ids = {f.message.split()[1] for f in findings}
        assert "99-REQ-1.2" in missing_ids
        assert "99-REQ-2.1" in missing_ids

    def test_complete_table_clean(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_traceability_table_completeness("robust_complete_spec", fixture)
        assert len(findings) == 0


# =============================================================================
# Phase 4: Section schema validation
# =============================================================================


class TestSectionSchema:
    """Verify check_section_schema detects missing and extra sections."""

    def test_complete_spec_no_missing_required(self) -> None:
        fixture = FIXTURES_DIR / "robust_complete_spec"
        findings = check_section_schema("robust_complete_spec", fixture)
        missing_required = [f for f in findings if f.rule == "missing-section" and f.severity == "warning"]
        assert len(missing_required) == 0

    def test_minimal_design_flags_missing_sections(self) -> None:
        fixture = FIXTURES_DIR / "warnings_only_spec"
        findings = check_section_schema("warnings_only_spec", fixture)
        missing = [f for f in findings if f.rule == "missing-section" and f.file == "design.md"]
        # Should flag multiple missing required sections
        assert len(missing) >= 3

    def test_extra_section_not_flagged(self, tmp_path: Path) -> None:
        """Domain-specific sections should not produce findings."""
        design = tmp_path / "design.md"
        design.write_text(
            "# Design\n\n"
            "## Overview\n\nOverview text.\n\n"
            "## Architecture\n\nArch text.\n\n"
            "## My Custom Section\n\nCustom content.\n\n"
            "## Correctness Properties\n\n"
            "### Property 1: Test\n\nProp.\n\n"
            "## Error Handling\n\n"
            "| A | B |\n|--|--|\n| x | y |\n\n"
            "## Definition of Done\n\nDone.\n"
        )
        findings = check_section_schema("test", tmp_path)
        extra = [f for f in findings if f.rule == "extra-section"]
        assert len(extra) == 0

    def test_missing_file_produces_no_findings(self) -> None:
        fixture = FIXTURES_DIR / "incomplete_spec"
        findings = check_section_schema("incomplete_spec", fixture)
        # design.md, requirements.md, test_spec.md don't exist — no schema findings
        design_findings = [f for f in findings if f.file == "design.md"]
        assert len(design_findings) == 0
