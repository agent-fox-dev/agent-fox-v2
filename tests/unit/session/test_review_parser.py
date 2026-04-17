"""Unit tests for review_parser.py: JSON extraction and validation.

Test Spec: TS-27-3, TS-27-4, TS-27-5, TS-27-15, TS-27-16
Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E1, 27-REQ-3.E2,
              27-REQ-8.1, 27-REQ-8.2, 27-REQ-9.1, 27-REQ-9.2,
              46-REQ-8.1
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.session.review_parser import (
    _classify_category,
    parse_auditor_output,
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

    def test_invalid_verdict_normalized_to_fail(self) -> None:
        """Verdict with non-PASS/FAIL value is normalized to FAIL (not skipped)."""
        response = '```json\n[{"requirement_id": "X", "verdict": "MAYBE"}]\n```'
        verdicts = parse_verification_output(response, "s", "1", "s1")
        assert len(verdicts) == 1
        assert verdicts[0].verdict == "FAIL"


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


class TestReviewerTemplateJson:
    """TS-27-15: Reviewer template instructs JSON output."""

    def test_reviewer_template_json(self) -> None:
        """Reviewer template contains JSON output instructions."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "agent_fox"
            / "_templates"
            / "profiles"
            / "reviewer.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert '"findings"' in content
        assert '"severity"' in content
        assert '"description"' in content
        assert "json" in content.lower()

    def test_reviewer_template_constraints(self) -> None:
        """Reviewer template retains read-only constraints."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "agent_fox"
            / "_templates"
            / "profiles"
            / "reviewer.md"
        )
        content = template_path.read_text(encoding="utf-8")
        assert "read-only" in content.lower() or "read only" in content.lower() or "do not" in content.lower()


class TestVerifierTemplateJson:
    """TS-27-16: Verifier template instructs JSON output."""

    def test_verifier_template_json(self) -> None:
        """Verifier template contains JSON output instructions."""
        template_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "agent_fox"
            / "_templates"
            / "profiles"
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
            / "profiles"
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


# ---------------------------------------------------------------------------
# parse_auditor_output: bare JSON fast path (issue #267)
# Requirements: 46-REQ-8.1
# ---------------------------------------------------------------------------


class TestParseAuditorOutputBareJson:
    """parse_auditor_output correctly handles bare JSON (no markdown fences).

    The auditor prompt instructs bare JSON output. The original regex-only
    approach failed on some well-formed responses. The fast-path json.loads
    call should handle these cases.
    """

    _VALID_AUDIT = {
        "audit": [
            {
                "ts_entry": "TS-05-1",
                "test_functions": ["tests/unit/test_foo.py::test_bar"],
                "verdict": "PASS",
                "notes": None,
            },
            {
                "ts_entry": "TS-05-2",
                "test_functions": [],
                "verdict": "MISSING",
                "notes": "No test found",
            },
        ],
        "overall_verdict": "FAIL",
        "summary": "1 MISSING entry found.",
    }

    def test_bare_json_parsed_correctly(self) -> None:
        """Bare JSON object (no fences, no prose) is parsed into AuditResult."""
        import json as _json

        response = _json.dumps(self._VALID_AUDIT)
        result = parse_auditor_output(response)

        assert result is not None
        assert result.overall_verdict == "FAIL"
        assert result.summary == "1 MISSING entry found."
        assert len(result.entries) == 2
        assert result.entries[0].ts_entry == "TS-05-1"
        assert result.entries[0].verdict == "PASS"
        assert result.entries[1].ts_entry == "TS-05-2"
        assert result.entries[1].verdict == "MISSING"

    def test_bare_json_with_nested_strings(self) -> None:
        """Bare JSON with nested brace characters in string values is parsed."""
        import json as _json

        audit = {
            "audit": [
                {
                    "ts_entry": "TS-01-1",
                    "test_functions": ["test_a"],
                    # notes contains { } characters that confuse naive regex
                    "verdict": "WEAK",
                    "notes": "Assertion uses `assert result == {'key': 'value'}` only",
                },
            ],
            "overall_verdict": "PASS",
            "summary": "Nested braces {handled} correctly.",
        }
        response = _json.dumps(audit)
        result = parse_auditor_output(response)

        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].verdict == "WEAK"
        assert "{'key': 'value'}" in (result.entries[0].notes or "")

    def test_fenced_json_still_parsed(self) -> None:
        """JSON wrapped in markdown fences is still parsed via fallback path."""
        import json as _json

        response = "```json\n" + _json.dumps(self._VALID_AUDIT) + "\n```"
        result = parse_auditor_output(response)

        assert result is not None
        assert result.overall_verdict == "FAIL"

    def test_json_with_surrounding_prose_parsed(self) -> None:
        """JSON embedded in prose (with fences) is parsed via fallback path."""
        import json as _json

        response = (
            "Here is my analysis of the test suite.\n\n"
            "```json\n" + _json.dumps(self._VALID_AUDIT) + "\n```\n\n"
            "End of analysis."
        )
        result = parse_auditor_output(response)

        assert result is not None
        assert result.overall_verdict == "FAIL"

    def test_no_audit_key_returns_none(self) -> None:
        """JSON object without 'audit' key returns None."""
        response = '{"findings": [{"severity": "major", "description": "oops"}]}'
        result = parse_auditor_output(response)

        assert result is None

    def test_plain_prose_returns_none(self) -> None:
        """Plain text with no JSON returns None."""
        response = "I analyzed the tests and found several issues with coverage."
        result = parse_auditor_output(response)

        assert result is None

    def test_empty_audit_array(self) -> None:
        """Audit result with empty entries array is valid."""
        import json as _json

        audit = {
            "audit": [],
            "overall_verdict": "PASS",
            "summary": "All good.",
        }
        response = _json.dumps(audit)
        result = parse_auditor_output(response)

        assert result is not None
        assert result.overall_verdict == "PASS"
        assert len(result.entries) == 0


# ---------------------------------------------------------------------------
# Multi-category classification (issue #485)
# ---------------------------------------------------------------------------


class TestClassifyCategory:
    """_classify_category() returns the correct category for each keyword group."""

    def test_security_keywords_return_security(self) -> None:
        """Security keywords produce category='security'."""
        assert _classify_category("sql injection found in query builder") == "security"
        assert _classify_category("Path traversal in file upload handler") == "security"
        assert _classify_category("Remote code execution via deserialization") == "security"

    def test_correctness_keywords_return_correctness(self) -> None:
        """Correctness keywords produce category='correctness'."""
        assert _classify_category("Wrong behavior when input is empty") == "correctness"
        assert _classify_category("This is a logic error in the parser") == "correctness"
        assert _classify_category("Missing functionality: no retry on 429") == "correctness"

    def test_compatibility_keywords_return_compatibility(self) -> None:
        """Compatibility keywords produce category='compatibility'."""
        assert _classify_category("API mismatch between client and server") == "compatibility"
        assert _classify_category("Proto field disagreement in response") == "compatibility"
        assert _classify_category("Breaking change in the public interface") == "compatibility"

    def test_testing_keywords_return_testing(self) -> None:
        """Testing keywords produce category='testing'."""
        assert _classify_category("Missing test for error path") == "testing"
        assert _classify_category("No test coverage for edge cases") == "testing"
        assert _classify_category("The function is untested") == "testing"

    def test_configuration_keywords_return_configuration(self) -> None:
        """Configuration keywords produce category='configuration'."""
        assert _classify_category("Wrong port configured for service") == "configuration"
        assert _classify_category("Missing config for database connection") == "configuration"
        assert _classify_category("Misconfigured environment variable") == "configuration"

    def test_no_match_returns_none(self) -> None:
        """Descriptions with no recognized keywords return None."""
        assert _classify_category("The code looks fine overall") is None
        assert _classify_category("General observation about code style") is None

    def test_security_takes_priority_over_correctness(self) -> None:
        """Security is detected even when correctness keywords also appear."""
        result = _classify_category("Wrong behavior due to sql injection vulnerability")
        assert result == "security"

    def test_case_insensitive(self) -> None:
        """Keyword matching is case-insensitive."""
        assert _classify_category("MISSING TEST for this function") == "testing"
        assert _classify_category("SQL INJECTION risk") == "security"


class TestCategoryPopulatedInFindings:
    """parse_review_output() populates category on each ReviewFinding."""

    def test_security_finding_has_category(self) -> None:
        """Finding with security keyword has category='security'."""
        response = '{"findings": [{"severity": "critical", "description": "SQL injection in login form"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category == "security"

    def test_correctness_finding_has_category(self) -> None:
        """Finding with correctness keyword has category='correctness'."""
        response = '{"findings": [{"severity": "major", "description": "Wrong behavior when retrying"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category == "correctness"

    def test_testing_finding_has_category(self) -> None:
        """Finding with testing keyword has category='testing'."""
        response = '{"findings": [{"severity": "minor", "description": "Missing test for timeout path"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category == "testing"

    def test_compatibility_finding_has_category(self) -> None:
        """Finding with compatibility keyword has category='compatibility'."""
        response = '{"findings": [{"severity": "major", "description": "API mismatch in response schema"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category == "compatibility"

    def test_configuration_finding_has_category(self) -> None:
        """Finding with configuration keyword has category='configuration'."""
        response = '{"findings": [{"severity": "major", "description": "Wrong port in deployment config"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category == "configuration"

    def test_unclassified_finding_has_none_category(self) -> None:
        """Finding with no recognized keywords has category=None."""
        response = '{"findings": [{"severity": "observation", "description": "Consider renaming this variable"}]}'
        findings = parse_review_output(response, "s", "1", "sid")
        assert len(findings) == 1
        assert findings[0].category is None
