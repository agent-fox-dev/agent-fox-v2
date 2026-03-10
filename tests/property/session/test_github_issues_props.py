"""Property tests for GitHub issue REST API migration.

Test Spec: TS-28-P1 through TS-28-P5
Properties: 1 (no gh CLI refs), 2 (idempotency), 3 (graceful degradation),
            4 (auth consistency), 5 (search query correctness)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform, IssueResult
from agent_fox.session.github_issues import file_or_update_issue

_TARGET = "agent_fox.platform.github.httpx.AsyncClient"


# ---------------------------------------------------------------------------
# TS-28-P3: No gh CLI References
# Property 1: The module contains no subprocess or gh CLI references.
# Validates: 28-REQ-5.4
# ---------------------------------------------------------------------------


class TestNoGhCliRefs:
    """Source code of github_issues.py has no gh CLI references."""

    def test_no_subprocess_references(self) -> None:
        source_path = (
            Path(__file__).resolve().parents[3]
            / "agent_fox"
            / "session"
            / "github_issues.py"
        )
        content = source_path.read_text()
        assert "create_subprocess_exec" not in content
        assert "_run_gh_command" not in content


# ---------------------------------------------------------------------------
# TS-28-P1: Search-Before-Create Idempotency
# Property 2: Repeated calls produce at most one create and N-1 updates.
# Validates: 28-REQ-5.3
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Repeated calls produce at most one create per title prefix."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n", [1, 2, 3, 5, 10])
    async def test_at_most_one_create(self, n: int) -> None:
        """N calls with same title produce at most 1 create and N-1 updates."""
        created_issues: dict[str, IssueResult] = {}

        mock = AsyncMock()

        async def mock_search(title_prefix, state="open"):
            key = title_prefix
            if key in created_issues:
                return [created_issues[key]]
            return []

        async def mock_create(title, body):
            result = IssueResult(
                number=1,
                title=title,
                html_url="https://github.com/o/r/issues/1",
            )
            created_issues[title] = result
            return result

        mock.search_issues = mock_search
        mock.create_issue = mock_create
        mock.update_issue = AsyncMock()
        mock.add_issue_comment = AsyncMock()

        for i in range(n):
            await file_or_update_issue(
                "[Skeptic] spec", f"body {i}", platform=mock
            )

        # create_issue is called via mock_create, tracked by created_issues
        assert len(created_issues) <= 1

        if n > 1:
            assert mock.update_issue.call_count == n - 1


# ---------------------------------------------------------------------------
# TS-28-P2: Graceful Degradation
# Property 3: Function never raises regardless of platform state.
# Validates: 28-REQ-5.E1, 28-REQ-5.E2
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """file_or_update_issue never raises for any platform state."""

    @pytest.mark.asyncio
    async def test_platform_none(self) -> None:
        result = await file_or_update_issue(
            "[Skeptic] spec", "body", platform=None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_search_raises(self) -> None:
        mock = AsyncMock()
        mock.search_issues.side_effect = IntegrationError("search fail")
        result = await file_or_update_issue(
            "[Skeptic] spec", "body", platform=mock
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_create_raises(self) -> None:
        mock = AsyncMock()
        mock.search_issues.return_value = []
        mock.create_issue.side_effect = IntegrationError("create fail")
        result = await file_or_update_issue(
            "[Skeptic] spec", "body", platform=mock
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_raises(self) -> None:
        existing = IssueResult(
            number=42,
            title="[Skeptic] spec",
            html_url="https://github.com/o/r/issues/42",
        )
        mock = AsyncMock()
        mock.search_issues.return_value = [existing]
        mock.update_issue.side_effect = IntegrationError("update fail")
        result = await file_or_update_issue(
            "[Skeptic] spec", "body", platform=mock
        )
        assert result is None


# ---------------------------------------------------------------------------
# TS-28-P4: API Authentication Consistency
# Property 4: All issue methods use the same auth headers as create_pr.
# Validates: 28-REQ-1.1, 28-REQ-2.1, 28-REQ-3.1, 28-REQ-4.1
# ---------------------------------------------------------------------------


class TestAuthConsistency:
    """All issue methods use correct auth headers."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method_name,setup",
        [
            ("search_issues", {
                "args": ("prefix",),
                "resp_code": 200,
                "resp_json": {"items": []},
                "http_method": "get",
            }),
            ("create_issue", {
                "args": ("title", "body"),
                "resp_code": 201,
                "resp_json": {
                    "number": 1,
                    "title": "t",
                    "html_url": "u",
                },
                "http_method": "post",
            }),
            ("update_issue", {
                "args": (1, "body"),
                "resp_code": 200,
                "resp_json": None,
                "http_method": "patch",
            }),
            ("add_issue_comment", {
                "args": (1, "comment"),
                "resp_code": 201,
                "resp_json": None,
                "http_method": "post",
            }),
        ],
    )
    async def test_auth_headers_present(
        self, method_name: str, setup: dict
    ) -> None:
        platform = GitHubPlatform(owner="org", repo="repo", token="my-token")

        resp = MagicMock()
        resp.status_code = setup["resp_code"]
        resp.text = ""
        if setup["resp_json"] is not None:
            resp.json.return_value = setup["resp_json"]

        captured_headers: list[dict] = []

        async def capture_request(url, *, json=None, params=None, headers=None, **kw):
            captured_headers.append(headers or {})
            return resp

        client = AsyncMock()
        setattr(client, setup["http_method"], capture_request)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(_TARGET, return_value=client):
            method = getattr(platform, method_name)
            await method(*setup["args"])

        assert len(captured_headers) >= 1
        h = captured_headers[0]
        assert h["Authorization"] == "Bearer my-token"
        assert h["Accept"] == "application/vnd.github+json"
        assert h["X-GitHub-Api-Version"] == "2022-11-28"


# ---------------------------------------------------------------------------
# TS-28-P5: Search Query Correctness
# Property 5: Search query always contains required components.
# Validates: 28-REQ-1.2
# ---------------------------------------------------------------------------


class TestSearchQueryCorrectness:
    """Search query contains all required components."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "title_prefix,state",
        [
            ("[Skeptic Review] my_spec", "open"),
            ("[Verifier] other_spec", "closed"),
            ("simple-prefix", "open"),
        ],
    )
    async def test_query_components(
        self, title_prefix: str, state: str
    ) -> None:
        platform = GitHubPlatform(owner="myorg", repo="myrepo", token="tok")

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"items": []}

        captured_params: list[dict] = []

        async def mock_get(url, *, params=None, headers=None, **kw):
            captured_params.append(params or {})
            return resp

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(_TARGET, return_value=client):
            await platform.search_issues(title_prefix, state=state)

        assert len(captured_params) == 1
        q = captured_params[0].get("q", "")
        assert "repo:myorg/myrepo" in q
        assert "in:title" in q
        assert title_prefix in q
        assert f"state:{state}" in q
        assert "type:issue" in q
