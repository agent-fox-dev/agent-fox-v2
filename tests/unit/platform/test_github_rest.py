"""Tests for GitHubPlatform REST API and parse_github_remote.

Test Spec: TS-19-13 (create_pr via REST), TS-19-14 (HTTPS parse),
           TS-19-15 (SSH parse), TS-19-E8 (API 401), TS-19-E9 (non-GitHub URL)
Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3, 19-REQ-4.4,
              19-REQ-4.E2, 19-REQ-4.E3, 19-REQ-4.E4
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform, parse_github_remote

# ---------------------------------------------------------------------------
# TS-19-13: GitHubPlatform create_pr Via REST API
# ---------------------------------------------------------------------------


class TestGitHubPlatformRestCreatePr:
    """TS-19-13: GitHubPlatform.create_pr posts to the GitHub REST API
    with correct auth and payload.

    Requirements: 19-REQ-4.1, 19-REQ-4.2, 19-REQ-4.3
    """

    async def test_creates_pr_and_returns_url(self) -> None:
        """create_pr POSTs to /repos/{owner}/{repo}/pulls with Bearer token."""
        platform = GitHubPlatform(owner="o", repo="r", token="tok")

        mock_response_repo = MagicMock()
        mock_response_repo.status_code = 200
        mock_response_repo.json.return_value = {"default_branch": "main"}

        mock_response_pr = MagicMock()
        mock_response_pr.status_code = 201
        mock_response_pr.json.return_value = {
            "html_url": "https://github.com/o/r/pull/1"
        }

        # Track actual requests
        requests_made: list[tuple[str, str, dict]] = []

        async def mock_request(method_unused, url=None, json=None, headers=None, **kw):
            # Handle both positional and keyword patterns
            return mock_response_repo

        mock_client = AsyncMock()

        async def mock_get(url, headers=None, **kw):
            requests_made.append(("GET", url, headers or {}))
            return mock_response_repo

        async def mock_post(url, json=None, headers=None, **kw):
            requests_made.append(("POST", url, headers or {}))
            return mock_response_pr

        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        target = "agent_fox.platform.github.httpx.AsyncClient"
        with patch(target, return_value=mock_client):
            result = await platform.create_pr("feature/test", "Test PR", "Desc")

        assert result == "https://github.com/o/r/pull/1"

        # Verify POST was to correct URL
        post_reqs = [r for r in requests_made if r[0] == "POST"]
        assert len(post_reqs) >= 1
        assert "https://api.github.com/repos/o/r/pulls" in post_reqs[0][1]

        # Verify Authorization header
        assert post_reqs[0][2].get("Authorization") == "Bearer tok"


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
# TS-19-E8: GitHub API Auth Error
# ---------------------------------------------------------------------------


class TestGitHubPlatformAuthError:
    """TS-19-E8: GitHub API 401 raises IntegrationError.

    Requirements: 19-REQ-4.E2, 19-REQ-4.E3
    """

    async def test_raises_on_401(self) -> None:
        """create_pr raises IntegrationError on 401."""
        platform = GitHubPlatform(owner="o", repo="r", token="bad")

        mock_response_repo = MagicMock()
        mock_response_repo.status_code = 200
        mock_response_repo.json.return_value = {"default_branch": "main"}

        mock_response_pr = MagicMock()
        mock_response_pr.status_code = 401
        mock_response_pr.text = "Bad credentials"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response_repo)
        mock_client.post = AsyncMock(return_value=mock_response_pr)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        target = "agent_fox.platform.github.httpx.AsyncClient"
        with patch(target, return_value=mock_client):
            with pytest.raises(IntegrationError, match="401"):
                await platform.create_pr("feature/test", "Test", "Body")

    async def test_raises_on_403(self) -> None:
        """create_pr raises IntegrationError on 403."""
        platform = GitHubPlatform(owner="o", repo="r", token="bad")

        mock_response_repo = MagicMock()
        mock_response_repo.status_code = 200
        mock_response_repo.json.return_value = {
            "default_branch": "main",
        }

        mock_response_pr = MagicMock()
        mock_response_pr.status_code = 403
        mock_response_pr.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response_repo)
        mock_client.post = AsyncMock(return_value=mock_response_pr)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        target = "agent_fox.platform.github.httpx.AsyncClient"
        with patch(target, return_value=mock_client):
            with pytest.raises(IntegrationError, match="403"):
                await platform.create_pr("feature/test", "Test", "Body")


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
# H3: Error Response Truncation
# ---------------------------------------------------------------------------


class TestErrorResponseTruncation:
    """H3: GitHub API error responses are truncated in exception messages."""

    async def test_long_error_text_is_truncated(self) -> None:
        """Error text longer than 500 chars is truncated in the exception."""
        platform = GitHubPlatform(owner="o", repo="r", token="tok")

        mock_response_repo = MagicMock()
        mock_response_repo.status_code = 200
        mock_response_repo.json.return_value = {"default_branch": "main"}

        mock_response_pr = MagicMock()
        mock_response_pr.status_code = 422
        mock_response_pr.text = "x" * 1000  # 1000-char response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response_repo)
        mock_client.post = AsyncMock(return_value=mock_response_pr)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        target = "agent_fox.platform.github.httpx.AsyncClient"
        with patch(target, return_value=mock_client):
            with pytest.raises(IntegrationError) as exc_info:
                await platform.create_pr("feature/test", "Test", "Body")

        # The error message should NOT contain the full 1000 chars
        error_msg = str(exc_info.value)
        assert len(error_msg) < 700  # reasonable bound with prefix text
        assert "..." in error_msg  # truncation marker

    async def test_short_error_text_not_truncated(self) -> None:
        """Error text shorter than 500 chars is preserved as-is."""
        platform = GitHubPlatform(owner="o", repo="r", token="tok")

        mock_response_repo = MagicMock()
        mock_response_repo.status_code = 200
        mock_response_repo.json.return_value = {"default_branch": "main"}

        mock_response_pr = MagicMock()
        mock_response_pr.status_code = 422
        mock_response_pr.text = "Short error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response_repo)
        mock_client.post = AsyncMock(return_value=mock_response_pr)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        target = "agent_fox.platform.github.httpx.AsyncClient"
        with patch(target, return_value=mock_client):
            with pytest.raises(IntegrationError, match="Short error"):
                await platform.create_pr("feature/test", "Test", "Body")
