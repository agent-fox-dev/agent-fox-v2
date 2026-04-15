"""Tests for GitHubPlatform issue REST API methods.

Test Spec: TS-28-1 through TS-28-6, TS-28-11, TS-28-E1 through TS-28-E3
Requirements: 28-REQ-1.*, 28-REQ-2.*, 28-REQ-3.*, 28-REQ-4.*
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform
from agent_fox.platform.protocol import IssueResult

# Helper to build a mock httpx.AsyncClient context manager
_TARGET = "agent_fox.platform.github.httpx.AsyncClient"


def _mock_client(**method_responses: MagicMock | Callable[..., Any]) -> AsyncMock:
    """Build a mock httpx.AsyncClient with specified method responses.

    Pass keyword arguments like get=mock_response or post=mock_response.
    Returns an AsyncMock that works as an async context manager.
    """
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
    json_data: dict | None = None,
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
# TS-28-1: search_issues Returns Matching Issues
# Requirements: 28-REQ-1.1, 28-REQ-1.2, 28-REQ-1.3
# ---------------------------------------------------------------------------


class TestSearchIssues:
    """Verify search_issues() calls the correct API endpoint and returns results."""

    @pytest.mark.asyncio
    async def test_returns_matching_issues(self) -> None:
        """search_issues returns list of IssueResult from API response."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            200,
            {
                "items": [
                    {
                        "number": 42,
                        "title": "[Skeptic Review] my_spec",
                        "html_url": "https://github.com/org/repo/issues/42",
                    },
                ],
            },
        )

        requests_made: list[tuple[str, dict]] = []

        async def mock_get(url, *, params=None, headers=None, **kw):
            requests_made.append((url, params or {}))
            return mock_resp

        client = _mock_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            results = await platform.search_issues("[Skeptic Review] my_spec")

        assert len(results) == 1
        assert results[0].number == 42
        assert results[0].title == "[Skeptic Review] my_spec"
        assert results[0].html_url == "https://github.com/org/repo/issues/42"
        assert isinstance(results[0], IssueResult)

        # Verify endpoint
        assert len(requests_made) == 1
        url, params = requests_made[0]
        assert "/search/issues" in url

        # Verify query contains required components (28-REQ-1.2)
        q = params.get("q", "")
        assert "repo:org/repo" in q
        assert "in:title" in q
        assert "[Skeptic Review] my_spec" in q
        assert "state:open" in q  # default state (28-REQ-1.3)
        assert "type:issue" in q

    @pytest.mark.asyncio
    async def test_state_parameter_passed(self) -> None:
        """search_issues passes custom state to query."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(200, {"items": []})
        requests_made: list[tuple[str, dict]] = []

        async def mock_get(url, *, params=None, headers=None, **kw):
            requests_made.append((url, params or {}))
            return mock_resp

        client = _mock_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            await platform.search_issues("prefix", state="closed")

        q = requests_made[0][1].get("q", "")
        assert "state:closed" in q


# ---------------------------------------------------------------------------
# TS-28-2: search_issues Empty Results
# Requirement: 28-REQ-1.E2
# ---------------------------------------------------------------------------


class TestSearchIssuesEmpty:
    """Verify search_issues() returns empty list when no matches."""

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(200, {"items": []})
        client = _mock_client(get=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            results = await platform.search_issues("nonexistent")

        assert results == []


# ---------------------------------------------------------------------------
# TS-28-3: create_issue Success
# Requirements: 28-REQ-2.1, 28-REQ-2.2
# ---------------------------------------------------------------------------


class TestCreateIssue:
    """Verify create_issue() POSTs and returns IssueResult."""

    @pytest.mark.asyncio
    async def test_creates_issue_and_returns_result(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            201,
            {
                "number": 1,
                "title": "[Skeptic Review] spec",
                "html_url": "https://github.com/org/repo/issues/1",
            },
        )

        requests_made: list[tuple[str, str, dict]] = []

        async def mock_post(url, *, json=None, headers=None, **kw):
            requests_made.append((url, "POST", json or {}))
            return mock_resp

        client = _mock_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            result = await platform.create_issue("[Skeptic Review] spec", "findings...")

        assert result.number == 1
        assert result.html_url == "https://github.com/org/repo/issues/1"
        assert isinstance(result, IssueResult)

        # Verify endpoint and payload
        assert len(requests_made) == 1
        url, method, payload = requests_made[0]
        assert url.endswith("/repos/org/repo/issues")
        assert payload["title"] == "[Skeptic Review] spec"
        assert payload["body"] == "findings..."


# ---------------------------------------------------------------------------
# TS-28-4: update_issue Success
# Requirement: 28-REQ-3.1
# ---------------------------------------------------------------------------


class TestUpdateIssue:
    """Verify update_issue() PATCHes the correct endpoint."""

    @pytest.mark.asyncio
    async def test_updates_issue_body(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(200)
        requests_made: list[tuple[str, dict]] = []

        async def mock_patch(url, *, json=None, headers=None, **kw):
            requests_made.append((url, json or {}))
            return mock_resp

        client = _mock_client(patch=mock_patch)

        with patch(_TARGET, return_value=client):
            await platform.update_issue(42, "updated findings")

        assert len(requests_made) == 1
        url, payload = requests_made[0]
        assert url.endswith("/repos/org/repo/issues/42")
        assert payload["body"] == "updated findings"


# ---------------------------------------------------------------------------
# TS-28-5: add_issue_comment Success
# Requirement: 28-REQ-3.2
# ---------------------------------------------------------------------------


class TestAddIssueComment:
    """Verify add_issue_comment() POSTs to comments endpoint."""

    @pytest.mark.asyncio
    async def test_adds_comment(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(201)
        requests_made: list[tuple[str, dict]] = []

        async def mock_post(url, *, json=None, headers=None, **kw):
            requests_made.append((url, json or {}))
            return mock_resp

        client = _mock_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            await platform.add_issue_comment(42, "Updated on re-run.")

        assert len(requests_made) == 1
        url, payload = requests_made[0]
        assert url.endswith("/repos/org/repo/issues/42/comments")
        assert payload["body"] == "Updated on re-run."


# ---------------------------------------------------------------------------
# TS-28-6: close_issue Success
# Requirement: 28-REQ-4.1
# ---------------------------------------------------------------------------


class TestCloseIssue:
    """Verify close_issue() patches state and optionally adds comment."""

    @pytest.mark.asyncio
    async def test_closes_with_comment(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        comment_resp = _json_response(201)
        close_resp = _json_response(200)
        requests_made: list[tuple[str, str, dict]] = []

        async def mock_post(url, *, json=None, headers=None, **kw):
            requests_made.append((url, "POST", json or {}))
            return comment_resp

        async def mock_patch(url, *, json=None, headers=None, **kw):
            requests_made.append((url, "PATCH", json or {}))
            return close_resp

        client = _mock_client(post=mock_post, patch=mock_patch)

        with patch(_TARGET, return_value=client):
            await platform.close_issue(42, comment="Closing: no findings on re-run.")

        # Should have comment POST and close PATCH
        post_reqs = [r for r in requests_made if r[1] == "POST"]
        patch_reqs = [r for r in requests_made if r[1] == "PATCH"]

        assert len(post_reqs) == 1
        assert post_reqs[0][0].endswith("/repos/org/repo/issues/42/comments")
        assert post_reqs[0][2]["body"] == "Closing: no findings on re-run."

        assert len(patch_reqs) == 1
        assert patch_reqs[0][2]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_closes_without_comment(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        close_resp = _json_response(200)
        requests_made: list[tuple[str, str, dict]] = []

        async def mock_patch(url, *, json=None, headers=None, **kw):
            requests_made.append((url, "PATCH", json or {}))
            return close_resp

        client = _mock_client(patch=mock_patch)

        with patch(_TARGET, return_value=client):
            await platform.close_issue(42)

        # Only PATCH, no POST for comment
        assert len(requests_made) == 1
        assert requests_made[0][1] == "PATCH"
        assert requests_made[0][2]["state"] == "closed"


# ---------------------------------------------------------------------------
# TS-28-11: Auth Headers Match create_pr
# Requirement: 28-REQ-1.1 (via Property 4)
# ---------------------------------------------------------------------------


class TestAuthHeadersConsistency:
    """Verify issue methods use the same auth headers as create_pr."""

    @pytest.mark.asyncio
    async def test_search_uses_correct_headers(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="test-token")

        mock_resp = _json_response(200, {"items": []})
        captured_headers: list[dict] = []

        async def mock_get(url, *, params=None, headers=None, **kw):
            captured_headers.append(headers or {})
            return mock_resp

        client = _mock_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            await platform.search_issues("prefix")

        assert len(captured_headers) == 1
        h = captured_headers[0]
        assert h["Authorization"] == "Bearer test-token"
        assert h["Accept"] == "application/vnd.github+json"
        assert h["X-GitHub-Api-Version"] == "2022-11-28"


# ---------------------------------------------------------------------------
# TS-28-E1: search_issues API Error
# Requirement: 28-REQ-1.E1
# ---------------------------------------------------------------------------


class TestSearchIssuesError:
    """Verify search_issues() raises IntegrationError on API error."""

    @pytest.mark.asyncio
    async def test_raises_on_403(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(403, text="forbidden")
        client = _mock_client(get=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError, match="403"):
                await platform.search_issues("prefix")


# ---------------------------------------------------------------------------
# TS-28-E2: create_issue API Error
# Requirement: 28-REQ-2.E1
# ---------------------------------------------------------------------------


class TestCreateIssueError:
    """Verify create_issue() raises IntegrationError on API error."""

    @pytest.mark.asyncio
    async def test_raises_on_422(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(422, text="validation failed")
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.create_issue("title", "body")


# ---------------------------------------------------------------------------
# TS-28-E3: update_issue / close_issue API Error
# Requirements: 28-REQ-3.E1, 28-REQ-4.E1
# ---------------------------------------------------------------------------


class TestUpdateIssueError:
    """Verify update_issue() raises IntegrationError on API error."""

    @pytest.mark.asyncio
    async def test_raises_on_404(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(404, text="not found")
        client = _mock_client(patch=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.update_issue(999, "body")


class TestCloseIssueError:
    """Verify close_issue() raises IntegrationError on API error."""

    @pytest.mark.asyncio
    async def test_raises_on_error(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(500, text="server error")
        client = _mock_client(patch=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.close_issue(42)


class TestAddIssueCommentError:
    """Verify add_issue_comment() raises IntegrationError on API error."""

    @pytest.mark.asyncio
    async def test_raises_on_error(self) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = _json_response(403, text="forbidden")
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.add_issue_comment(42, "comment")
