"""Tests for GitHubPlatform REST API and parse_github_remote.

Test Spec: TS-19-14 (HTTPS parse), TS-19-15 (SSH parse),
           TS-19-E9 (non-GitHub URL)
Requirements: 19-REQ-4.4, 19-REQ-4.E4

Note: TS-19-13 (create_pr via REST), TS-19-E8 (API 401/403), and H3
(error response sanitization) have been removed — create_pr was removed
from GitHubPlatform in spec 65 (65-REQ-4.2).
"""

from __future__ import annotations

from agent_fox.platform.github import GitHubPlatform, parse_github_remote

# ---------------------------------------------------------------------------
# TS-19-14: parse_github_remote HTTPS
# ---------------------------------------------------------------------------


class TestParseGithubRemoteHTTPS:
    """TS-19-14: Parses owner/repo from HTTPS GitHub URL.

    Requirement: 19-REQ-4.4
    """

    def test_https_with_git_suffix(self) -> None:
        result = parse_github_remote("https://github.com/owner/repo.git")
        assert result == ("owner", "repo")

    def test_https_without_git_suffix(self) -> None:
        result = parse_github_remote("https://github.com/owner/repo")
        assert result == ("owner", "repo")


# ---------------------------------------------------------------------------
# TS-19-15: parse_github_remote SSH
# ---------------------------------------------------------------------------


class TestParseGithubRemoteSSH:
    """TS-19-15: Parses owner/repo from SSH GitHub URL.

    Requirement: 19-REQ-4.4
    """

    def test_ssh_format(self) -> None:
        result = parse_github_remote("git@github.com:owner/repo.git")
        assert result == ("owner", "repo")

    def test_ssh_without_git_suffix(self) -> None:
        result = parse_github_remote("git@github.com:owner/repo")
        assert result == ("owner", "repo")


# ---------------------------------------------------------------------------
# TS-19-E9: Non-GitHub Remote URL
# ---------------------------------------------------------------------------


class TestParseGithubRemoteNonGithub:
    """TS-19-E9: Non-GitHub remote URL returns None from parser.

    Requirement: 19-REQ-4.E4
    """

    def test_gitlab_returns_none(self) -> None:
        result = parse_github_remote("https://gitlab.com/owner/repo.git")
        assert result is None

    def test_bitbucket_returns_none(self) -> None:
        result = parse_github_remote("https://bitbucket.org/owner/repo.git")
        assert result is None

    def test_random_url_returns_none(self) -> None:
        result = parse_github_remote("https://example.com/foo/bar.git")
        assert result is None


# ---------------------------------------------------------------------------
# Regression test for issue #187: token must not leak in repr/str
# ---------------------------------------------------------------------------


class TestGitHubPlatformRepr:
    """Token must not appear in repr or str output.

    Regression test for issue #187: GitHub PAT stored as plain instance
    attribute may leak in tracebacks.
    """

    def test_repr_excludes_token(self) -> None:
        """repr() must not contain the token value."""
        platform = GitHubPlatform(owner="acme", repo="widgets", token="ghp_s3cret")
        result = repr(platform)
        assert "ghp_s3cret" not in result
        assert "acme" in result
        assert "widgets" in result

    def test_str_excludes_token(self) -> None:
        """str() must not contain the token value."""
        platform = GitHubPlatform(owner="acme", repo="widgets", token="ghp_s3cret")
        result = str(platform)
        assert "ghp_s3cret" not in result
