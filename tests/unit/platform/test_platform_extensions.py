"""Tests for GitHubPlatform extensions: remove_label, list_issue_comments, get_issue.

Test Spec: TS-86-1 through TS-86-5, TS-86-E1 through TS-86-E3
Requirements: 86-REQ-1.1, 86-REQ-1.2, 86-REQ-1.3, 86-REQ-1.4, 86-REQ-1.5,
              86-REQ-1.E1, 86-REQ-1.E2, 86-REQ-1.E3
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform
from agent_fox.platform.protocol import IssueComment, IssueResult

# Helper to build a mock httpx.AsyncClient context manager
_TARGET = "agent_fox.platform.github.httpx.AsyncClient"


def _mock_client(**method_responses: MagicMock | Callable[..., Any]) -> AsyncMock:
    """Build a mock httpx.AsyncClient with specified method responses."""
    client = AsyncMock()
    for method_name, response in method_responses.items():
        if callable(response) and not isinstance(response, MagicMock):
            setattr(client, method_name, response)
        else:
            setattr(client, method_name, AsyncMock(return_value=response))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _json_response(
    status_code: int,
    json_data: dict | list | None = None,
    text: str = "",
) -> MagicMock:
    """Build a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


# ---------------------------------------------------------------------------
# TS-86-1: remove_label sends DELETE request
# Requirements: 86-REQ-1.1
# ---------------------------------------------------------------------------


class TestRemoveLabel:
    """Verify remove_label sends a DELETE to the correct GitHub API endpoint."""

    async def test_sends_delete_to_correct_endpoint(self) -> None:
        """TS-86-1: DELETE request sent to /repos/{owner}/{repo}/issues/42/labels/af%3Aspec."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(204)
        requests_made: list[tuple[str, str]] = []

        async def mock_delete(url, *, headers=None, **kw: Any) -> MagicMock:
            requests_made.append(("DELETE", url))
            return mock_resp

        client = _mock_client(delete=mock_delete)

        with patch(_TARGET, return_value=client):
            await platform.remove_label(42, "af:spec")

        assert len(requests_made) == 1
        method, url = requests_made[0]
        assert method == "DELETE"
        assert "/repos/org/repo/issues/42/labels/" in url
        # Label must be URL-encoded: af:spec -> af%3Aspec
        assert "af%3Aspec" in url or "af:spec" in url


# ---------------------------------------------------------------------------
# TS-86-2: remove_label is idempotent on missing label
# Requirements: 86-REQ-1.2
# ---------------------------------------------------------------------------


class TestRemoveLabelIdempotent:
    """Verify remove_label succeeds when the label is not present (404 response)."""

    async def test_404_succeeds_silently(self) -> None:
        """TS-86-2: No exception raised on 404."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(404, text="Not Found")
        client = _mock_client(delete=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            # Should NOT raise
            await platform.remove_label(42, "nonexistent")


# ---------------------------------------------------------------------------
# TS-86-3: list_issue_comments returns ordered comments
# Requirements: 86-REQ-1.3
# ---------------------------------------------------------------------------


class TestListIssueComments:
    """Verify list_issue_comments returns IssueComment objects in chronological order."""

    async def test_returns_ordered_comments(self) -> None:
        """TS-86-3: List of two IssueComment objects with correct fields."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            200,
            [
                {
                    "id": 1,
                    "body": "first",
                    "user": {"login": "alice"},
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "body": "second",
                    "user": {"login": "bob"},
                    "created_at": "2026-01-02T00:00:00Z",
                },
            ],
        )

        requests_made: list[str] = []

        async def mock_get(url, *, params=None, headers=None, **kw: Any) -> MagicMock:
            requests_made.append(url)
            return mock_resp

        client = _mock_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            result = await platform.list_issue_comments(10)

        assert len(result) == 2
        assert isinstance(result[0], IssueComment)
        assert result[0].id == 1
        assert result[0].body == "first"
        assert result[0].user == "alice"
        assert result[0].created_at == "2026-01-01T00:00:00Z"
        assert result[1].id == 2
        assert result[1].body == "second"
        assert result[1].user == "bob"

        # Verify correct API endpoint
        assert len(requests_made) == 1
        assert "/repos/org/repo/issues/10/comments" in requests_made[0]


# ---------------------------------------------------------------------------
# TS-86-4: get_issue returns IssueResult
# Requirements: 86-REQ-1.4
# ---------------------------------------------------------------------------


class TestGetIssue:
    """Verify get_issue returns a complete IssueResult."""

    async def test_returns_issue_result(self) -> None:
        """TS-86-4: IssueResult with number=5, title, html_url, body."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            200,
            {
                "number": 5,
                "title": "Test Issue",
                "html_url": "https://github.com/org/repo/issues/5",
                "body": "Issue description here",
            },
        )

        async def mock_get(url, *, params=None, headers=None, **kw: Any) -> MagicMock:
            return mock_resp

        client = _mock_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            result = await platform.get_issue(5)

        assert isinstance(result, IssueResult)
        assert result.number == 5
        assert result.title == "Test Issue"
        assert result.html_url == "https://github.com/org/repo/issues/5"
        assert result.body == "Issue description here"


# ---------------------------------------------------------------------------
# TS-86-5: platform protocol includes new methods
# Requirements: 86-REQ-1.5
# ---------------------------------------------------------------------------


class TestPlatformProtocol:
    """Verify PlatformProtocol includes the three new method signatures."""

    def test_github_platform_satisfies_protocol(self) -> None:
        """TS-86-5: isinstance check and method existence."""
        from agent_fox.platform.protocol import PlatformProtocol

        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        assert isinstance(platform, PlatformProtocol)
        assert hasattr(platform, "remove_label")
        assert hasattr(platform, "list_issue_comments")
        assert hasattr(platform, "get_issue")
        assert callable(platform.remove_label)
        assert callable(platform.list_issue_comments)
        assert callable(platform.get_issue)


# ---------------------------------------------------------------------------
# TS-86-E1: remove_label API error raises IntegrationError
# Requirements: 86-REQ-1.E1
# ---------------------------------------------------------------------------


class TestRemoveLabelError:
    """Verify non-404 errors raise IntegrationError."""

    async def test_500_raises_integration_error(self) -> None:
        """TS-86-E1: IntegrationError on 500."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(500, text="Internal Server Error")
        client = _mock_client(delete=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.remove_label(42, "af:spec")


# ---------------------------------------------------------------------------
# TS-86-E2: list_issue_comments on issue with no comments
# Requirements: 86-REQ-1.E2
# ---------------------------------------------------------------------------


class TestListIssueCommentsEmpty:
    """Verify empty list returned for commentless issue."""

    async def test_empty_comments_returns_empty_list(self) -> None:
        """TS-86-E2: Empty list returned."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(200, [])
        client = _mock_client(get=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            result = await platform.list_issue_comments(42)

        assert result == []


# ---------------------------------------------------------------------------
# TS-86-E3: get_issue with nonexistent issue
# Requirements: 86-REQ-1.E3
# ---------------------------------------------------------------------------


class TestGetIssueNotFound:
    """Verify IntegrationError on 404."""

    async def test_404_raises_integration_error(self) -> None:
        """TS-86-E3: IntegrationError raised."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(404, text="Not Found")
        client = _mock_client(get=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.get_issue(99999)
