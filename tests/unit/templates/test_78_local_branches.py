"""Tests for local-only feature branch template content — spec 78.

Test Spec: TS-78-4 through TS-78-8
Requirements: 78-REQ-2.1, 78-REQ-2.2, 78-REQ-2.3, 78-REQ-3.1, 78-REQ-3.2
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve template paths relative to this file
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[3]
_AGENTS_MD_TEMPLATE = _REPO_ROOT / "agent_fox" / "_templates" / "agents_md.md"
_AF_SPEC_TEMPLATE = _REPO_ROOT / "agent_fox" / "_templates" / "skills" / "af-spec"


# ---------------------------------------------------------------------------
# TS-78-4: agents_md.md has no "pushed to `origin`"
# ---------------------------------------------------------------------------


class TestAgentsMdNoPushedToOrigin:
    """TS-78-4: agents_md.md must not tell agents to push feature branches to origin.

    Requirement: 78-REQ-2.1
    """

    def test_no_pushed_to_origin(self) -> None:
        """The phrase 'pushed to `origin`' must not appear in agents_md.md."""
        content = _AGENTS_MD_TEMPLATE.read_text()
        assert "pushed to `origin`" not in content


# ---------------------------------------------------------------------------
# TS-78-5: agents_md.md has no "push the feature branch"
# ---------------------------------------------------------------------------


class TestAgentsMdNoPushFeatureBranch:
    """TS-78-5: agents_md.md must not instruct agents to push feature branches.

    Requirement: 78-REQ-2.2
    """

    def test_no_push_feature_branch(self) -> None:
        """The phrase 'push the feature branch' must not appear in agents_md.md."""
        content = _AGENTS_MD_TEMPLATE.read_text()
        assert "push the feature branch" not in content


# ---------------------------------------------------------------------------
# TS-78-6: agents_md.md describes local-only feature branches
# ---------------------------------------------------------------------------


class TestAgentsMdLocalOnlyGuidance:
    """TS-78-6: agents_md.md must contain guidance that feature branches are local-only.

    Requirement: 78-REQ-2.3
    """

    def test_local_only_guidance(self) -> None:
        """The template must contain 'local-only' or 'local only'."""
        content = _AGENTS_MD_TEMPLATE.read_text().lower()
        assert "local-only" in content or "local only" in content


# ---------------------------------------------------------------------------
# TS-78-7: af-spec template has no "pushed to remote" in Definition of Done
# ---------------------------------------------------------------------------


class TestAfSpecNoPushedToRemote:
    """TS-78-7: af-spec must not reference pushing to remote in Definition of Done.

    Requirement: 78-REQ-3.1
    """

    def test_no_pushed_to_remote(self) -> None:
        """The phrase 'pushed to remote' must not appear in af-spec."""
        content = _AF_SPEC_TEMPLATE.read_text()
        assert "pushed to remote" not in content


# ---------------------------------------------------------------------------
# TS-78-8: af-spec git-flow line has no "-> push"
# ---------------------------------------------------------------------------


class TestAfSpecNoFeatureBranchPushInGitFlow:
    """TS-78-8: af-spec git-flow comment must not instruct pushing feature branches.

    Requirement: 78-REQ-3.2
    """

    def test_no_push_in_git_flow(self) -> None:
        """The git-flow line in af-spec must not contain '-> push'."""
        content = _AF_SPEC_TEMPLATE.read_text()
        for line in content.splitlines():
            if "git-flow" in line.lower() or "feature branch from develop" in line:
                assert "-> push" not in line, f"git-flow line still contains '-> push': {line!r}"
