"""Tests for Verifier archetype behavior.

Test Spec: TS-26-37, TS-26-38
Requirements: 26-REQ-9.1, 26-REQ-9.2
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TS-26-37: Verifier produces verification.md
# Requirement: 26-REQ-9.1
# ---------------------------------------------------------------------------


class TestVerifierTemplate:
    """Verify Verifier template references per-requirement verdict and JSON output."""

    def test_template_has_verdict_and_assessment(self) -> None:
        import os

        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "agent_fox",
            "_templates",
            "profiles",
            "verifier.md",
        )
        template_path = os.path.normpath(template_path)

        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        assert "PASS" in content
        assert "FAIL" in content
        assert "verdicts" in content


# ---------------------------------------------------------------------------
# TS-26-38: Verifier files GitHub issue on FAIL
# Requirement: 26-REQ-9.2
# ---------------------------------------------------------------------------
