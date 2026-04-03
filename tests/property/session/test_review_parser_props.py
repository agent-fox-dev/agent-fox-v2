"""Property tests for review_parser: roundtrip fidelity, severity normalization.

Test Spec: TS-27-P2, TS-27-P5
Requirements: 27-REQ-3.1, 27-REQ-3.2, 27-REQ-3.3, 27-REQ-3.E2
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.knowledge.review_store import VALID_SEVERITIES
from agent_fox.session.review_parser import (
    parse_review_output,
    parse_verification_output,
)


@st.composite
def valid_finding_json(draw: st.DrawFn) -> dict:
    """Generate a valid finding JSON object."""
    severity = draw(st.sampled_from(list(VALID_SEVERITIES)))
    description = draw(
        st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
            ),
        )
    )
    result: dict = {"severity": severity, "description": description}
    if draw(st.booleans()):
        ref_alpha = st.characters(whitelist_categories=("L", "N", "P"))
        result["requirement_ref"] = draw(st.text(min_size=1, max_size=20, alphabet=ref_alpha))
    return result


@st.composite
def valid_verdict_json(draw: st.DrawFn) -> dict:
    """Generate a valid verdict JSON object."""
    req_id = draw(st.from_regex(r"[A-Z0-9]+-REQ-[0-9]+\.[0-9]+", fullmatch=True))
    verdict = draw(st.sampled_from(["PASS", "FAIL"]))
    result: dict = {"requirement_id": req_id, "verdict": verdict}
    if draw(st.booleans()):
        ev_alpha = st.characters(whitelist_categories=("L", "N", "P", "Z"))
        result["evidence"] = draw(st.text(min_size=1, max_size=100, alphabet=ev_alpha))
    return result


class TestParseRoundtripFidelity:
    """TS-27-P2: Property 2 — Parse-Roundtrip Fidelity.

    For any valid JSON output, parsed results match the JSON values.
    """

    @given(finding_data=valid_finding_json())
    @settings(max_examples=30)
    def test_finding_roundtrip(self, finding_data: dict) -> None:
        """Parsed finding matches original JSON data."""
        response = f"```json\n{json.dumps({'findings': [finding_data]})}\n```"
        findings = parse_review_output(response, "spec", "1", "session")
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == finding_data["severity"]
        assert f.description == finding_data["description"]
        assert f.requirement_ref == finding_data.get("requirement_ref")

    @given(verdict_data=valid_verdict_json())
    @settings(max_examples=30)
    def test_verdict_roundtrip(self, verdict_data: dict) -> None:
        """Parsed verdict matches original JSON data."""
        response = f"```json\n{json.dumps({'verdicts': [verdict_data]})}\n```"
        verdicts = parse_verification_output(response, "spec", "1", "session")
        assert len(verdicts) == 1
        v = verdicts[0]
        assert v.requirement_id == verdict_data["requirement_id"]
        assert v.verdict == verdict_data["verdict"]
        assert v.evidence == verdict_data.get("evidence")


class TestSeverityNormalization:
    """TS-27-P5: Property 5 — Severity Normalization.

    For any severity string, the result is in VALID_SEVERITIES.
    """

    @given(severity=st.text(min_size=1, max_size=50))
    @settings(max_examples=50)
    def test_severity_always_valid(self, severity: str) -> None:
        """Any severity string normalizes to a valid value."""
        # Build a JSON response with the arbitrary severity
        data = {"severity": severity, "description": "Test"}
        response = f"```json\n{json.dumps({'findings': [data]})}\n```"
        findings = parse_review_output(response, "spec", "1", "session")
        assert len(findings) == 1
        assert findings[0].severity in VALID_SEVERITIES
