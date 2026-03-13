"""Tests for oracle output parsing and DriftFinding dataclass.

Test Spec: TS-32-6, TS-32-7, TS-32-E4, TS-32-E5
Requirements: 32-REQ-6.1, 32-REQ-6.2, 32-REQ-6.3, 32-REQ-6.E1, 32-REQ-6.E2
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# TS-32-6: Parse Oracle Output - Valid JSON
# Requirements: 32-REQ-6.1, 32-REQ-6.2
# ---------------------------------------------------------------------------


class TestParseValidJson:
    """Verify parse_oracle_output extracts drift findings from valid JSON."""

    def test_parse_valid_json(self) -> None:
        """TS-32-6: Valid JSON with drift_findings array is parsed correctly."""
        from agent_fox.session.review_parser import parse_oracle_output

        response = (
            "```json\n"
            '{"drift_findings": ['
            '{"severity": "critical", "description": "File removed", '
            '"artifact_ref": "foo.py"}, '
            '{"severity": "minor", "description": "Function renamed", '
            '"spec_ref": "design.md"}'
            "]}\n"
            "```"
        )
        findings = parse_oracle_output(response, "spec_a", "0", "sess_1")

        assert len(findings) == 2
        assert findings[0].severity == "critical"
        assert findings[0].description == "File removed"
        assert findings[0].artifact_ref == "foo.py"
        assert findings[0].spec_ref is None
        assert findings[1].severity == "minor"
        assert findings[1].description == "Function renamed"
        assert findings[1].spec_ref == "design.md"

    def test_parse_bare_json(self) -> None:
        """Bare JSON object (no fenced block) is also parsed."""
        from agent_fox.session.review_parser import parse_oracle_output

        response = (
            "Here are my findings:\n"
            '{"drift_findings": ['
            '{"severity": "major", "description": "API changed"}'
            "]}"
        )
        findings = parse_oracle_output(response, "spec_b", "1", "sess_2")
        assert len(findings) == 1
        assert findings[0].severity == "major"
        assert findings[0].spec_name == "spec_b"
        assert findings[0].task_group == "1"
        assert findings[0].session_id == "sess_2"


# ---------------------------------------------------------------------------
# TS-32-7: DriftFinding Dataclass Fields
# Requirement: 32-REQ-6.3
# ---------------------------------------------------------------------------


class TestDriftFindingFields:
    """Verify DriftFinding has all required fields."""

    def test_drift_finding_fields(self) -> None:
        """TS-32-7: DriftFinding is frozen and has all fields."""
        from agent_fox.knowledge.review_store import DriftFinding

        f = DriftFinding(
            id="uuid-1",
            severity="critical",
            description="test drift",
            spec_ref="design.md",
            artifact_ref="foo.py",
            spec_name="spec_a",
            task_group="0",
            session_id="sess_1",
        )
        assert f.id == "uuid-1"
        assert f.severity == "critical"
        assert f.description == "test drift"
        assert f.spec_ref == "design.md"
        assert f.artifact_ref == "foo.py"
        assert f.spec_name == "spec_a"
        assert f.task_group == "0"
        assert f.session_id == "sess_1"
        assert f.superseded_by is None
        assert f.created_at is None

    def test_drift_finding_frozen(self) -> None:
        """DriftFinding is immutable (frozen dataclass)."""
        from agent_fox.knowledge.review_store import DriftFinding

        f = DriftFinding(
            id="uuid-1",
            severity="minor",
            description="test",
            spec_ref=None,
            artifact_ref=None,
            spec_name="s",
            task_group="0",
            session_id="x",
        )
        with pytest.raises(AttributeError):
            f.severity = "major"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TS-32-E4: No Valid JSON in Oracle Output
# Requirement: 32-REQ-6.E1
# ---------------------------------------------------------------------------


class TestNoJsonOutput:
    """Parser returns empty list for non-JSON output."""

    def test_no_json_output(self) -> None:
        """TS-32-E4: Plain text with no JSON returns empty list."""
        from agent_fox.session.review_parser import parse_oracle_output

        result = parse_oracle_output(
            "No drift found, everything looks good.",
            "spec",
            "0",
            "sess",
        )
        assert result == []


# ---------------------------------------------------------------------------
# TS-32-E5: Finding Missing Required Fields
# Requirement: 32-REQ-6.E2
# ---------------------------------------------------------------------------


class TestMissingFields:
    """Entries without severity or description are skipped."""

    def test_missing_fields(self) -> None:
        """TS-32-E5: Entry missing 'description' is skipped."""
        from agent_fox.session.review_parser import parse_oracle_output

        response = (
            '{"drift_findings": ['
            '{"severity": "major", "description": "ok"}, '
            '{"severity": "minor"}'
            "]}"
        )
        result = parse_oracle_output(response, "spec", "0", "sess")
        assert len(result) == 1
        assert result[0].description == "ok"

    def test_missing_severity(self) -> None:
        """Entry missing 'severity' is skipped."""
        from agent_fox.session.review_parser import parse_oracle_output

        response = '{"drift_findings": [{"description": "no severity field"}]}'
        result = parse_oracle_output(response, "spec", "0", "sess")
        assert len(result) == 0
