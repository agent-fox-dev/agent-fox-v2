"""Tests for profile template content — no push instructions.

Test Spec: TS-19-9 (coder.md profile)
Requirements: 19-REQ-2.4, 19-REQ-2.5

Updated after legacy template path removal (issue #342).
Profiles now live in _templates/profiles/ instead of _templates/prompts/.
"""

from __future__ import annotations

from pathlib import Path

# Resolve profiles directory relative to agent_fox package
_PROFILES_DIR = Path(__file__).resolve().parents[3] / "agent_fox" / "_templates" / "profiles"


# ---------------------------------------------------------------------------
# TS-19-9: coder.md Has No Push Instructions
# ---------------------------------------------------------------------------


class TestCoderProfile:
    """TS-19-9: The coder.md profile does not contain git push commands
    or push failure policy.

    Requirements: 19-REQ-2.4, 19-REQ-2.5
    """

    def test_no_git_push(self) -> None:
        """coder.md does not contain 'git push'."""
        content = (_PROFILES_DIR / "coder.md").read_text()
        assert "git push" not in content

    def test_no_push_failure_policy(self) -> None:
        """coder.md does not contain push failure/retry instructions."""
        content = (_PROFILES_DIR / "coder.md").read_text()
        assert "If push fails" not in content
