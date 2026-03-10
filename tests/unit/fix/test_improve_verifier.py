"""Verifier verdict tests.

Test Spec: TS-31-14, TS-31-15, TS-31-16
Requirements: 31-REQ-6.2, 31-REQ-6.E2
"""

from __future__ import annotations

import json

import pytest

from agent_fox.fix.improve import parse_verifier_verdict


class TestParseVerifierVerdict:
    """TS-31-14, TS-31-15, TS-31-16: Verifier verdict parsing."""

    def test_pass_verdict(self) -> None:
        """TS-31-14: PASS verdict parsed correctly."""
        pass_json = json.dumps(
            {
                "quality_gates": "PASS",
                "improvement_valid": True,
                "verdict": "PASS",
                "evidence": "All tests pass. 3 files simplified.",
            }
        )

        verdict = parse_verifier_verdict(pass_json)

        assert verdict.verdict == "PASS"
        assert verdict.improvement_valid is True
        assert verdict.quality_gates == "PASS"

    def test_fail_verdict(self) -> None:
        """TS-31-15: FAIL verdict parsed correctly."""
        fail_json = json.dumps(
            {
                "quality_gates": "PASS",
                "improvement_valid": False,
                "verdict": "FAIL",
                "evidence": "Public API changed in module.py",
            }
        )

        verdict = parse_verifier_verdict(fail_json)

        assert verdict.verdict == "FAIL"
        assert verdict.improvement_valid is False

    def test_invalid_json(self) -> None:
        """TS-31-16: Invalid JSON raises ValueError."""
        with pytest.raises(ValueError):
            parse_verifier_verdict("not json")
