"""Tests for prompt template content — no push instructions.

Test Spec: TS-19-8 (git-flow.md), TS-19-9 (coding.md)
Requirements: 19-REQ-2.1, 19-REQ-2.2, 19-REQ-2.3, 19-REQ-2.4, 19-REQ-2.5
"""

from __future__ import annotations

from pathlib import Path

# Resolve template directory relative to agent_fox package
_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[3]
    / "agent_fox"
    / "_templates"
    / "prompts"
)


# ---------------------------------------------------------------------------
# TS-19-8: git-flow.md Has No Push Instructions
# ---------------------------------------------------------------------------


class TestGitFlowTemplate:
    """TS-19-8: The git-flow.md template does not contain git push commands.

    Requirements: 19-REQ-2.1, 19-REQ-2.2, 19-REQ-2.3
    """

    def test_no_git_push(self) -> None:
        """git-flow.md does not contain 'git push'."""
        content = (_TEMPLATE_DIR / "git-flow.md").read_text()
        assert "git push" not in content

    def test_no_pushed_to_reference(self) -> None:
        """git-flow.md does not contain 'pushed to' references."""
        content = (_TEMPLATE_DIR / "git-flow.md").read_text()
        assert "pushed to" not in content.lower()


# ---------------------------------------------------------------------------
# TS-19-9: coding.md Has No Push Instructions
# ---------------------------------------------------------------------------


class TestCodingTemplate:
    """TS-19-9: The coding.md template does not contain git push commands
    or push failure policy.

    Requirements: 19-REQ-2.4, 19-REQ-2.5
    """

    def test_no_git_push(self) -> None:
        """coding.md does not contain 'git push'."""
        content = (_TEMPLATE_DIR / "coding.md").read_text()
        assert "git push" not in content

    def test_no_push_failure_policy(self) -> None:
        """coding.md does not contain push failure/retry instructions."""
        content = (_TEMPLATE_DIR / "coding.md").read_text()
        assert "If push fails" not in content
