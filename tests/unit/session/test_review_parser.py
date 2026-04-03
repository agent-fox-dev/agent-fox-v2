"""Unit tests for review_parser.py: JSON extraction and validation.

Test Spec: TS-27-3, TS-27-4, TS-27-5, TS-27-15, TS-27-16
Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2,
              27-REQ-8.1, 27-REQ-8.2, 27-REQ-9.1, 27-REQ-9.2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.session.review_parser import (
    parse_legacy_review_md,
    parse_legacy_verification_md,
    parse_review_output,
    parse_verification_output,
)


class TestParseSkepticJson:
    """TS-27-3: parse Skeptic JSON output."""

    def test_parse_skeptic_json(self) -> None:
        """Valid JSON with findings array is parsed correctly."""
        response = """
Here are my findings:

```json
{
  "findings": [
    {
      "severity": "critical",
      "description": "Missing error handling for null input",
      "requirement_ref": "05-REQ-1.1"
    },
    {
      "severity": "observation",
      "description": "Consider adding logging"
    }
  ]
}
```

That's all.
"""
        findings = parse_review_output(response, "test_spec", "1", "session-1")
        assert len(findings) == 2
        assert findings[0].severity == "critical"
        assert findings[0].description == "Missing error handling for null input"
        assert findings[0].requirement_ref == "05-REQ-1.1"
        assert findings[1].severity == "observation"
        assert findings[1].requirement_ref is None
        assert findings[0].spec_name == "test_spec"
        assert findings[0].task_group == "1"
        assert findings[0].session_id == "session-1"

    def test_parse_bare_array(self) -> None:
        """Bare JSON array of findings is parsed."""
        response = """
```json
[
  {"severity": "minor", "description": "Typo in docs"}
]
```
"""
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 1
        assert findings[0].severity == "minor"


class TestParseVerifierJson:
    """TS-27-4: parse Verifier JSON output."""

    def test_parse_verifier_json(self) -> None:
        """Valid JSON with verdicts array is parsed correctly."""
        response = """
```json
{
  "verdicts": [
    {
      "requirement_id": "05-REQ-1.1",
      "verdict": "PASS",
      "evidence": "Test passes"
    },
    {
      "requirement_id": "05-REQ-2.1",
      "verdict": "FAIL",
      "evidence": "Not implemented"
    }
  ]
}
```
"""
        verdicts = parse_verification_output(response, "test_spec", "1", "s1")
        assert len(verdicts) == 2
        assert verdicts[0].requirement_id == "05-REQ-1.1"
        assert verdicts[0].verdict == "PASS"
        assert verdicts[0].evidence == "Test passes"
        assert verdicts[1].verdict == "FAIL"


class TestValidateSchemaRejects:
    """TS-27-5: invalid JSON blocks are rejected."""

    def test_missing_severity_rejected(self) -> None:
        """Finding without severity is skipped."""
        response = '```json\n[{"description": "No severity"}]\n```'
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 0

    def test_missing_description_rejected(self) -> None:
        """Finding without description is skipped."""
        response = '```json\n[{"severity": "major"}]\n```'
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 0

    def test_missing_requirement_id_rejected(self) -> None:
        """Verdict without requirement_id is skipped."""
        response = '```json\n[{"verdict": "PASS"}]\n```'
        verdicts = parse_verification_output(response, "s", "1", "s1")
        assert len(verdicts) == 0

    def test_invalid_verdict_rejected(self) -> None:
        """Verdict with non-PASS/FAIL value is skipped."""
        response = '```json\n[{"requirement_id": "X", "verdict": "MAYBE"}]\n```'
        verdicts = parse_verification_output(response, "s", "1", "s1")
        assert len(verdicts) == 0


class TestNoValidJsonReturnsEmpty:
    """TS-27-E3: no valid JSON blocks in agent output."""

    def test_no_valid_json_returns_empty(self) -> None:
        """Returns empty list when no JSON blocks found."""
        response = "Just some plain text with no JSON."
        findings = parse_review_output(response, "s", "1", "s1")
        assert findings == []

    def test_invalid_json_returns_empty(self) -> None:
        """Returns empty list when JSON is malformed."""
        response = "```json\n{invalid json}\n```"
        findings = parse_review_output(response, "s", "1", "s1")
        assert findings == []


class TestUnknownSeverityNormalized:
    """TS-27-E4: unknown severity normalized to observation."""

    def test_unknown_severity_normalized(self) -> None:
        """Unknown severity value is normalized to 'observation'."""
        response = '```json\n[{"severity": "urgent", "description": "Something urgent"}]\n```'
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 1
        assert findings[0].severity == "observation"

    def test_case_insensitive_severity(self) -> None:
        """Severity matching is case-insensitive."""
        response = '```json\n[{"severity": "CRITICAL", "description": "Big problem"}]\n```'
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 1
        assert findings[0].severity == "critical"


class TestSkepticTemplateJson:
    """TS-27-15: Skeptic template instructs JSON output."""

    def test_skeptic_template_json(self) -> None:
        """Skeptic template contains JSON output instructions."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent / "agent_fox" / "_templates" / "prompts" / "skeptic.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert '"findings"' in content
        assert '"severity"' in content
        assert '"description"' in content
        assert "json" in content.lower()

    def test_skeptic_template_constraints(self) -> None:
        """Skeptic template retains read-only constraints."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent / "agent_fox" / "_templates" / "prompts" / "skeptic.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert "read-only" in content.lower() or "read only" in content.lower()


class TestVerifierTemplateJson:
    """TS-27-16: Verifier template instructs JSON output."""

    def test_verifier_template_json(self) -> None:
        """Verifier template contains JSON output instructions."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "agent_fox"
            / "_templates"
            / "prompts"
            / "verifier.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert '"verdicts"' in content
        assert '"requirement_id"' in content
        assert '"verdict"' in content
        assert "json" in content.lower()

    def test_verifier_template_constraints(self) -> None:
        """Verifier template retains verification process guidance."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "agent_fox"
            / "_templates"
            / "prompts"
            / "verifier.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert "PASS" in content
        assert "FAIL" in content


class TestJsonPreferredOverFile:
    """TS-27-E9 (partial): JSON output is preferred over file."""

    def test_json_preferred_over_file(self) -> None:
        """When both JSON and file content exist, JSON parsing works."""
        # The parser extracts JSON regardless of whether files exist
        response = """
I wrote review.md but here is the structured output:

```json
{"findings": [{"severity": "minor", "description": "Test issue"}]}
```
"""
        findings = parse_review_output(response, "s", "1", "s1")
        assert len(findings) == 1
        assert findings[0].severity == "minor"


class TestLegacyParsing:
    """TS-27-17, TS-27-18: Legacy markdown file parsing."""

    def test_legacy_review_migration(self) -> None:
        """Legacy review.md is parsed into findings."""
        content = """# Skeptic Review: test_spec

## Critical Findings
- [severity: critical] Missing error handling

## Major Findings
- [severity: major] Ambiguous requirement

## Observations
- [severity: observation] Consider adding logging

## Summary
1 critical, 1 major, 0 minor, 1 observation.
"""
        findings = parse_legacy_review_md(content, "test_spec", "1", "legacy")
        assert len(findings) == 3
        severities = [f.severity for f in findings]
        assert "critical" in severities
        assert "major" in severities
        assert "observation" in severities

    def test_legacy_verification_migration(self) -> None:
        """Legacy verification.md is parsed into verdicts."""
        content = """# Verification Report: test_spec

## Per-Requirement Assessment
| Requirement | Status | Notes |
|-------------|--------|-------|
| 05-REQ-1.1 | PASS | Tests pass |
| 05-REQ-2.1 | FAIL | Not implemented |

## Verdict: FAIL
"""
        verdicts = parse_legacy_verification_md(content, "test_spec", "1", "legacy")
        assert len(verdicts) == 2
        assert verdicts[0].requirement_id == "05-REQ-1.1"
        assert verdicts[0].verdict == "PASS"
        assert verdicts[1].verdict == "FAIL"
