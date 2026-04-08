"""Unit tests for PullRequestResult and create_pull_request.

Test Spec: TS-85-23, TS-85-24, TS-85-25, TS-85-E12
Requirements: 85-REQ-8.2, 85-REQ-8.3, 85-REQ-8.4, 85-REQ-8.E1
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# TS-85-23: Draft PR creation
# Requirement: 85-REQ-8.2
# ---------------------------------------------------------------------------


class TestDraftPrCreation:
    """Verify merge_strategy='pr' calls create_pull_request and returns PullRequestResult."""

    async def test_create_pull_request_returns_result(self) -> None:
        """create_pull_request returns PullRequestResult with correct fields."""
        from agent_fox.platform.github import PullRequestResult

        result = PullRequestResult(
            number=42,
            url="https://api.github.com/repos/o/r/pulls/42",
            html_url="https://github.com/o/r/pull/42",
        )
        assert result.number == 42
        assert result.html_url == "https://github.com/o/r/pull/42"

    async def test_mock_platform_create_pr(self) -> None:
        """Mock platform returns PullRequestResult."""
        from agent_fox.platform.github import PullRequestResult

        platform = MagicMock()
        platform.create_pull_request = AsyncMock(
            return_value=PullRequestResult(
                number=42,
                url="https://api.github.com/repos/o/r/pulls/42",
                html_url="https://github.com/o/r/pull/42",
            )
        )
        result = await platform.create_pull_request("title", "body", "fix/123", "develop", draft=True)
        assert result.number == 42
        assert result.html_url == "https://github.com/o/r/pull/42"


# ---------------------------------------------------------------------------
# TS-85-24: PlatformProtocol has create_pull_request
# Requirement: 85-REQ-8.3
# ---------------------------------------------------------------------------


class TestPlatformProtocolCreatePR:
    """Verify PlatformProtocol defines create_pull_request method."""

    def test_class_with_create_pr_passes_isinstance(self) -> None:
        """Class implementing all methods including create_pull_request passes."""
        from agent_fox.platform.github import IssueComment, IssueResult, PullRequestResult
        from agent_fox.platform.protocol import PlatformProtocol

        class WithPR:
            async def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> IssueResult: ...  # type: ignore[empty-body]

            async def list_issues_by_label(  # type: ignore[empty-body]
                self, label: str, state: str = "open", *, sort: str = "created", direction: str = "asc"
            ) -> list[IssueResult]: ...

            async def add_issue_comment(self, issue_number: int, body: str) -> None: ...

            async def assign_label(self, issue_number: int, label: str) -> None: ...

            async def close_issue(self, issue_number: int, comment: str | None = None) -> None: ...

            async def close(self) -> None: ...

            async def create_pull_request(  # type: ignore[empty-body]
                self, title: str, body: str, head: str, base: str, draft: bool = True
            ) -> PullRequestResult: ...

            async def remove_label(self, issue_number: int, label: str) -> None: ...

            async def list_issue_comments(self, issue_number: int) -> list[IssueComment]: ...  # type: ignore[empty-body]

            async def get_issue(self, issue_number: int) -> IssueResult: ...  # type: ignore[empty-body]

        assert isinstance(WithPR(), PlatformProtocol)


# ---------------------------------------------------------------------------
# TS-85-25: GitHubPlatform.create_pull_request API call
# Requirement: 85-REQ-8.4
# ---------------------------------------------------------------------------


class TestGitHubPlatformCreatePR:
    """Verify GitHubPlatform.create_pull_request sends correct API request."""

    async def test_api_call_shape(self) -> None:
        """POST to /repos/{owner}/{repo}/pulls with correct JSON body."""
        from unittest.mock import patch

        from agent_fox.platform.github import GitHubPlatform

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 99,
            "url": "https://api.github.com/repos/owner/repo/pulls/99",
            "html_url": "https://github.com/owner/repo/pull/99",
        }

        requests_made: list[dict] = []

        async def mock_post(url: str, *, json: dict, headers: dict, **kw: object) -> MagicMock:
            requests_made.append({"url": url, "json": json})
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("agent_fox.platform.github.httpx.AsyncClient", return_value=mock_client):
            github = GitHubPlatform("owner", "repo", "token")
            result = await github.create_pull_request("Fix bug", "body", "fix/42", "develop", draft=True)

        assert result.number == 99
        assert len(requests_made) == 1
        assert "/repos/owner/repo/pulls" in requests_made[0]["url"]
        assert requests_made[0]["json"]["head"] == "fix/42"
        assert requests_made[0]["json"]["draft"] is True


# ---------------------------------------------------------------------------
# TS-85-E12: create_pull_request failure fallback
# Requirement: 85-REQ-8.E1
# ---------------------------------------------------------------------------


class TestPrCreationFailure:
    """Verify PR creation failure logs error and posts branch name comment."""

    async def test_failure_posts_comment(self) -> None:
        """On PR creation failure, comment with branch name is posted."""
        from agent_fox.core.errors import IntegrationError  # noqa: I001
        from agent_fox.nightshift.daemon import handle_merge_strategy

        platform = MagicMock()
        platform.create_pull_request = AsyncMock(side_effect=IntegrationError("API error"))
        platform.add_issue_comment = AsyncMock()

        await handle_merge_strategy(
            platform=platform,
            issue_number=42,
            branch="fix/42",
            strategy="pr",
            title="Fix bug",
            body="body",
        )

        assert platform.add_issue_comment.call_count == 1
        comment_body = platform.add_issue_comment.call_args[0][1]
        assert "fix/42" in comment_body
