"""Unit tests for engine.review_parser module.

Tests JSON extraction from archetype output text, typed parsing functions,
and robustness with various input formats including markdown fences,
bare arrays, and multiple arrays.

Test Spec: TS-53-6, TS-53-7, TS-53-E2
Requirements: 53-REQ-4.1, 53-REQ-4.2, 53-REQ-4.E1
"""

from __future__ import annotations

import logging

import pytest

# NOTE: agent_fox.engine.review_parser does not exist yet.
# All tests in this file will fail with ImportError until Task Group 2
# creates the module.
from agent_fox.engine.review_parser import (
    extract_json_array,
    parse_drift_findings,
    parse_review_findings,
    parse_verification_results,
)

# ---------------------------------------------------------------------------
# TS-53-6: extract_json_array – basic extraction
# ---------------------------------------------------------------------------


class TestExtractJsonArrayBasic:
    """TS-53-6: extract_json_array extracts valid JSON arrays from text."""

    def test_bare_array_returned(self) -> None:
        """Extracts a bare JSON array directly in the text."""
        result = extract_json_array('[{"severity": "minor"}]')
        assert result == [{"severity": "minor"}]

    def test_json_from_markdown_json_fences(self) -> None:
        """TS-53-6: Extracts JSON array from ```json ... ``` code fences."""
        text = 'Some text\n```json\n[{"severity": "minor"}]\n```\nMore text'
        result = extract_json_array(text)
        assert result == [{"severity": "minor"}]

    def test_json_from_plain_fences(self) -> None:
        """Extracts JSON array from plain ``` ... ``` fences (no json label)."""
        text = '```\n[{"severity": "minor"}]\n```'
        result = extract_json_array(text)
        assert result == [{"severity": "minor"}]

    def test_array_surrounded_by_prose(self) -> None:
        """Extracts JSON array embedded in surrounding prose."""
        text = (
            "Here are the findings:\n"
            '[{"severity": "major", "description": "Missing null check"}]\n'
            "End of review."
        )
        result = extract_json_array(text)
        assert result == [{"severity": "major", "description": "Missing null check"}]

    def test_empty_array_is_valid(self) -> None:
        """An empty JSON array [] is returned as an empty list."""
        result = extract_json_array("[]")
        assert result == []

    def test_array_with_multiple_objects(self) -> None:
        """Returns a list with all objects from the array."""
        text = '[{"severity": "major"}, {"severity": "minor"}]'
        result = extract_json_array(text)
        assert result is not None
        assert len(result) == 2
        assert result[0]["severity"] == "major"
        assert result[1]["severity"] == "minor"


class TestExtractJsonArrayReturnsNone:
    """extract_json_array returns None when no valid JSON array is present."""

    def test_plain_prose_returns_none(self) -> None:
        """Returns None when output contains no JSON at all."""
        result = extract_json_array("This is just prose with no JSON")
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        """Returns None for empty input string."""
        result = extract_json_array("")
        assert result is None

    def test_invalid_json_in_brackets_returns_none(self) -> None:
        """Returns None when brackets found but content is not valid JSON."""
        result = extract_json_array("[not valid json {at all]")
        assert result is None

    def test_json_object_not_array_returns_none(self) -> None:
        """Returns None when JSON is a dict (not an array)."""
        result = extract_json_array('{"key": "value"}')
        assert result is None

    def test_json_string_not_array_returns_none(self) -> None:
        """Returns None when JSON is a plain string."""
        result = extract_json_array('"just a string"')
        assert result is None


# ---------------------------------------------------------------------------
# TS-53-E2: Multiple JSON arrays – first valid one is used
# ---------------------------------------------------------------------------


class TestExtractJsonArrayMultipleArrays:
    """TS-53-E2: When output contains multiple JSON arrays, first valid is used."""

    def test_multiple_arrays_returns_first(self) -> None:
        """TS-53-E2: Returns the first valid JSON array found."""
        result = extract_json_array('[{"a": 1}] some text [{"b": 2}]')
        assert result == [{"a": 1}]

    def test_invalid_first_bracket_fallback(self) -> None:
        """Falls back to markdown fences if bracket-match yields invalid JSON."""
        # First bracket group is invalid JSON; fences contain valid JSON
        text = '[not json here] text\n```json\n[{"valid": true}]\n```'
        result = extract_json_array(text)
        assert result is not None
        assert len(result) == 1


# ---------------------------------------------------------------------------
# TS-53-7: parse_review_findings – field validation and skipping
# ---------------------------------------------------------------------------


class TestParseReviewFindings:
    """TS-53-7: parse_review_findings parses dicts and skips invalid entries."""

    def test_valid_finding_parsed(self) -> None:
        """Valid finding dict is parsed into a ReviewFinding with all fields."""
        json_objects = [
            {
                "severity": "major",
                "description": "Missing null check",
                "requirement_ref": "03-REQ-1.1",
            },
        ]
        result = parse_review_findings(json_objects, "03_api", 2, "skeptic_03_2")
        assert len(result) == 1
        assert result[0].severity == "major"
        assert result[0].description == "Missing null check"
        assert result[0].requirement_ref == "03-REQ-1.1"
        assert result[0].spec_name == "03_api"
        assert result[0].task_group == 2
        assert result[0].session_id == "skeptic_03_2"

    def test_invalid_fields_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TS-53-7: Objects missing required fields are skipped; warning logged."""
        json_objects: list[dict] = [
            {"severity": "major", "description": "ok"},  # valid
            {"severity": "minor"},  # missing description → skipped
        ]
        with caplog.at_level(logging.WARNING):
            result = parse_review_findings(json_objects, "03_api", 2, "sess")

        assert len(result) == 1
        assert result[0].description == "ok"

        warning_text = " ".join(r.message for r in caplog.records)
        assert any(
            word in warning_text.lower()
            for word in ("missing", "skip", "required", "invalid")
        )

    def test_empty_input_returns_empty(self) -> None:
        """Empty input list returns an empty result list."""
        result = parse_review_findings([], "03_api", 2, "sess")
        assert result == []

    def test_id_assigned_to_each_finding(self) -> None:
        """Each parsed finding receives a non-empty UUID id."""
        json_objects = [{"severity": "major", "description": "issue"}]
        result = parse_review_findings(json_objects, "03_api", 2, "sess")
        assert len(result) == 1
        assert result[0].id  # non-empty

    def test_multiple_valid_findings_all_parsed(self) -> None:
        """Multiple valid findings are all parsed correctly."""
        json_objects = [
            {"severity": "critical", "description": "Critical bug"},
            {"severity": "minor", "description": "Nit"},
        ]
        result = parse_review_findings(json_objects, "spec", 1, "sess")
        assert len(result) == 2

    def test_non_dict_items_skipped(self) -> None:
        """Non-dict items in the input list are skipped."""
        json_objects: list = [
            "string_item",
            {"severity": "major", "description": "valid finding"},
        ]
        result = parse_review_findings(json_objects, "spec", 1, "sess")
        assert len(result) == 1

    def test_optional_requirement_ref_defaults_none(self) -> None:
        """requirement_ref is optional; defaults to None when absent."""
        json_objects = [{"severity": "minor", "description": "docstring issue"}]
        result = parse_review_findings(json_objects, "spec", 1, "sess")
        assert len(result) == 1
        assert result[0].requirement_ref is None


# ---------------------------------------------------------------------------
# parse_verification_results
# ---------------------------------------------------------------------------


class TestParseVerificationResults:
    """parse_verification_results parses VerificationResult instances."""

    def test_valid_verdict_parsed(self) -> None:
        """Valid verdict dict is parsed into a VerificationResult."""
        json_objects = [
            {
                "requirement_id": "03-REQ-1.1",
                "verdict": "PASS",
                "evidence": "All tests pass",
            },
        ]
        result = parse_verification_results(json_objects, "03_api", 2, "verifier_03_2")
        assert len(result) == 1
        assert result[0].requirement_id == "03-REQ-1.1"
        assert result[0].verdict == "PASS"
        assert result[0].evidence == "All tests pass"
        assert result[0].spec_name == "03_api"
        assert result[0].task_group == 2

    def test_missing_verdict_field_skipped(self) -> None:
        """Objects missing the verdict field are skipped."""
        json_objects = [{"requirement_id": "03-REQ-1.1"}]
        result = parse_verification_results(json_objects, "03_api", 2, "sess")
        assert len(result) == 0

    def test_missing_requirement_id_skipped(self) -> None:
        """Objects missing the requirement_id field are skipped."""
        json_objects = [{"verdict": "PASS"}]
        result = parse_verification_results(json_objects, "03_api", 2, "sess")
        assert len(result) == 0

    def test_invalid_verdict_value_skipped(self) -> None:
        """Objects with unrecognised verdict values are skipped."""
        json_objects = [{"requirement_id": "03-REQ-1.1", "verdict": "UNKNOWN"}]
        result = parse_verification_results(json_objects, "03_api", 2, "sess")
        assert len(result) == 0

    def test_fail_verdict_accepted(self) -> None:
        """FAIL verdict is valid and parsed correctly."""
        json_objects = [{"requirement_id": "03-REQ-2.1", "verdict": "FAIL"}]
        result = parse_verification_results(json_objects, "spec", 1, "sess")
        assert len(result) == 1
        assert result[0].verdict == "FAIL"

    def test_optional_evidence_defaults_none(self) -> None:
        """evidence field is optional; defaults to None."""
        json_objects = [{"requirement_id": "03-REQ-1.1", "verdict": "PASS"}]
        result = parse_verification_results(json_objects, "spec", 1, "sess")
        assert len(result) == 1
        assert result[0].evidence is None


# ---------------------------------------------------------------------------
# parse_drift_findings
# ---------------------------------------------------------------------------


class TestParseDriftFindings:
    """parse_drift_findings parses DriftFinding instances."""

    def test_valid_drift_finding_parsed(self) -> None:
        """Valid drift finding dict is parsed into a DriftFinding."""
        json_objects = [
            {
                "severity": "critical",
                "description": "API endpoint missing",
                "spec_ref": "03-REQ-2.1",
                "artifact_ref": "routes.py",
            },
        ]
        result = parse_drift_findings(json_objects, "03_api", 0, "oracle_03_0")
        assert len(result) == 1
        assert result[0].severity == "critical"
        assert result[0].description == "API endpoint missing"
        assert result[0].spec_ref == "03-REQ-2.1"
        assert result[0].artifact_ref == "routes.py"
        assert result[0].spec_name == "03_api"
        assert result[0].task_group == 0

    def test_missing_description_skipped(self) -> None:
        """Objects missing the description field are skipped."""
        json_objects = [{"severity": "critical"}]
        result = parse_drift_findings(json_objects, "03_api", 0, "sess")
        assert len(result) == 0

    def test_missing_severity_skipped(self) -> None:
        """Objects missing the severity field are skipped."""
        json_objects = [{"description": "Something is wrong"}]
        result = parse_drift_findings(json_objects, "03_api", 0, "sess")
        assert len(result) == 0

    def test_optional_refs_default_none(self) -> None:
        """spec_ref and artifact_ref are optional; default to None."""
        json_objects = [{"severity": "major", "description": "Drift detected"}]
        result = parse_drift_findings(json_objects, "spec", 0, "sess")
        assert len(result) == 1
        assert result[0].spec_ref is None
        assert result[0].artifact_ref is None

    def test_empty_input_returns_empty(self) -> None:
        """Empty input list returns an empty result list."""
        result = parse_drift_findings([], "spec", 0, "sess")
        assert result == []
