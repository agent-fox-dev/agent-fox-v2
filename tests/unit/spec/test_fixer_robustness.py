"""Unit tests for robustness auto-fix functions.

Tests for: fix_inconsistent_req_id_format, fix_missing_traceability_table,
fix_missing_coverage_matrix, fix_missing_definition_of_done,
fix_missing_error_table, fix_missing_correctness_properties.
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec.fixer import (
    fix_inconsistent_req_id_format,
    fix_missing_correctness_properties,
    fix_missing_coverage_matrix,
    fix_missing_definition_of_done,
    fix_missing_error_table,
    fix_missing_traceability_table,
)


class TestFixInconsistentReqIdFormat:
    """Verify bold-to-bracket ID conversion."""

    def test_converts_bold_to_bracket(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.md"
        req.write_text(
            "# Requirements\n\n"
            "### Requirement 1: Feature\n\n"
            "1. **05-REQ-1.1:** THE system SHALL do A.\n"
            "2. [05-REQ-1.2] THE system SHALL do B.\n"
            "3. **05-REQ-1.E1:** IF error, THEN THE system SHALL handle.\n"
        )
        results = fix_inconsistent_req_id_format("test", req)
        assert len(results) == 1
        assert results[0].rule == "inconsistent-req-id-format"

        text = req.read_text()
        assert "[05-REQ-1.1]" in text
        assert "**05-REQ-1.1:**" not in text
        assert "[05-REQ-1.2]" in text
        assert "[05-REQ-1.E1]" in text

    def test_no_bold_ids_returns_empty(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.md"
        req.write_text("# Requirements\n\n1. [05-REQ-1.1] THE system SHALL do A.\n")
        results = fix_inconsistent_req_id_format("test", req)
        assert len(results) == 0

    def test_count_in_description(self, tmp_path: Path) -> None:
        req = tmp_path / "requirements.md"
        req.write_text("1. **05-REQ-1.1:** A.\n2. **05-REQ-1.2:** B.\n")
        results = fix_inconsistent_req_id_format("test", req)
        assert "2" in results[0].description


class TestFixMissingTraceabilityTable:
    """Verify traceability table generation."""

    def test_appends_table_with_req_ids(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.md").write_text(
            "# Requirements\n\n1. [05-REQ-1.1] THE system SHALL do A.\n2. [05-REQ-1.2] THE system SHALL do B.\n"
        )
        (tmp_path / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Do stuff\n  - [ ] 1.1 Sub\n")
        results = fix_missing_traceability_table("test", tmp_path)
        assert len(results) == 1

        text = (tmp_path / "tasks.md").read_text()
        assert "## Traceability" in text
        assert "05-REQ-1.1" in text
        assert "05-REQ-1.2" in text

    def test_no_requirements_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.md").write_text("# Requirements\n")
        (tmp_path / "tasks.md").write_text("# Tasks\n")
        results = fix_missing_traceability_table("test", tmp_path)
        assert len(results) == 0


class TestFixMissingCoverageMatrix:
    """Verify coverage matrix generation."""

    def test_appends_matrix_with_req_ids(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.md").write_text("1. [05-REQ-1.1] THE system SHALL do A.\n")
        (tmp_path / "test_spec.md").write_text("# Test Spec\n\n### TS-05-1: Test A\n\n**Requirement:** 05-REQ-1.1\n")
        results = fix_missing_coverage_matrix("test", tmp_path)
        assert len(results) == 1

        text = (tmp_path / "test_spec.md").read_text()
        assert "## Coverage Matrix" in text
        assert "05-REQ-1.1" in text


class TestFixMissingDefinitionOfDone:
    """Verify DoD section appending."""

    def test_appends_dod_section(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Overview\n\nOverview.\n")

        results = fix_missing_definition_of_done("test", design)
        assert len(results) == 1

        text = design.read_text()
        assert "## Definition of Done" in text
        assert "All subtasks within the group are checked off" in text

    def test_skips_if_already_present(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Definition of Done\n\nAll done.\n")
        results = fix_missing_definition_of_done("test", design)
        assert len(results) == 0


class TestFixMissingErrorTable:
    """Verify error handling table appending."""

    def test_appends_error_table(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Overview\n\nOverview.\n")

        results = fix_missing_error_table("test", design)
        assert len(results) == 1

        text = design.read_text()
        assert "## Error Handling" in text
        assert "| Error Condition |" in text

    def test_skips_if_already_present(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Error Handling\n\n| A | B |\n|--|--|\n")
        results = fix_missing_error_table("test", design)
        assert len(results) == 0


class TestFixMissingCorrectnessProperties:
    """Verify correctness properties section appending."""

    def test_appends_properties_stub(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Overview\n\nOverview.\n")

        results = fix_missing_correctness_properties("test", design)
        assert len(results) == 1

        text = design.read_text()
        assert "## Correctness Properties" in text
        assert "### Property 1:" in text

    def test_skips_if_already_present(self, tmp_path: Path) -> None:
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Correctness Properties\n\n### Property 1: Test\n\nProp.\n")
        results = fix_missing_correctness_properties("test", design)
        assert len(results) == 0
