"""Tests for GitHubPlatform timeout and retry behaviour.

Acceptance criteria: AC-1 through AC-5 from issue #313.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import _GITHUB_TIMEOUT, _MAX_RETRIES, GitHubPlatform

_TARGET = "agent_fox.platform.github.httpx.AsyncClient"
_SLEEP_TARGET = "agent_fox.platform.github.asyncio.sleep"


def _json_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = ""
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def _make_client(get=None, post=None, patch=None, delete=None) -> AsyncMock:
    """Build a mock client that works as an async context manager."""
    client = AsyncMock()
    if get is not None:
        client.get = get
    if post is not None:
        client.post = post
    if patch is not None:
        client.patch = patch
    if delete is not None:
        client.delete = delete
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# AC-1: Explicit timeout on every AsyncClient instantiation
# ---------------------------------------------------------------------------


class TestExplicitTimeout:
    """AC-1: AsyncClient is always created with an explicit timeout >= 15s."""

    @pytest.mark.asyncio
    async def test_list_issues_by_label_uses_explicit_timeout(self) -> None:
        """httpx.AsyncClient is instantiated with a timeout argument."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        resp = _json_response(200, [])

        client = _make_client(get=AsyncMock(return_value=resp))

        with patch(_TARGET, return_value=client) as mock_cls:
            await platform.list_issues_by_label("label")

        # Verify the class was called with a timeout kwarg
        assert mock_cls.called
        _, kwargs = mock_cls.call_args
        assert "timeout" in kwargs, "httpx.AsyncClient must be called with timeout="
        timeout = kwargs["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect >= 15.0, "connect timeout must be >= 15 seconds"

    @pytest.mark.asyncio
    async def test_search_issues_uses_explicit_timeout(self) -> None:
        """search_issues uses timeout on AsyncClient."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        resp = _json_response(200, {"items": []})
        client = _make_client(get=AsyncMock(return_value=resp))

        with patch(_TARGET, return_value=client) as mock_cls:
            await platform.search_issues("prefix")

        _, kwargs = mock_cls.call_args
        assert "timeout" in kwargs

    @pytest.mark.asyncio
    async def test_create_issue_uses_explicit_timeout(self) -> None:
        """create_issue uses timeout on AsyncClient."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        resp = _json_response(
            201, {"number": 1, "title": "t", "html_url": "http://x"}
        )
        client = _make_client(post=AsyncMock(return_value=resp))

        with patch(_TARGET, return_value=client) as mock_cls:
            await platform.create_issue("title", "body")

        _, kwargs = mock_cls.call_args
        assert "timeout" in kwargs

    @pytest.mark.asyncio
    async def test_timeout_connect_value(self) -> None:
        """_GITHUB_TIMEOUT has connect >= 15s (spec minimum)."""
        assert _GITHUB_TIMEOUT.connect is not None
        assert _GITHUB_TIMEOUT.connect >= 15.0


# ---------------------------------------------------------------------------
# AC-2: Retry on transient errors succeeds on second attempt
# ---------------------------------------------------------------------------


class TestRetrySuccess:
    """AC-2: list_issues_by_label retries ConnectTimeout and returns on success."""

    @pytest.mark.asyncio
    async def test_retries_connect_timeout_and_succeeds(self) -> None:
        """First call raises ConnectTimeout; second returns 200 successfully."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(
            200,
            [{"number": 1, "title": "Issue", "html_url": "http://x", "body": ""}],
        )

        # Raise on first call, succeed on second
        mock_get = AsyncMock(
            side_effect=[
                httpx.ConnectTimeout("timeout"),
                success_resp,
            ]
        )
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock) as mock_sleep:
                results = await platform.list_issues_by_label("label")

        assert len(results) == 1
        assert results[0].number == 1
        # Verify sleep was called (backoff between attempts)
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_connect_error_and_succeeds(self) -> None:
        """ConnectError triggers retry; method returns on second attempt."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200, [])

        mock_get = AsyncMock(
            side_effect=[
                httpx.ConnectError("refused"),
                success_resp,
            ]
        )
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                results = await platform.list_issues_by_label("label")

        assert results == []
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_read_timeout_and_succeeds(self) -> None:
        """ReadTimeout triggers retry; method returns on second attempt."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200, [])

        mock_get = AsyncMock(
            side_effect=[
                httpx.ReadTimeout("read timeout"),
                success_resp,
            ]
        )
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                results = await platform.list_issues_by_label("label")

        assert results == []
        assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# AC-3: Retry exhaustion re-raises the original exception
# ---------------------------------------------------------------------------


class TestRetryExhaustion:
    """AC-3: After all retries are exhausted, the original exception propagates."""

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_connect_timeout(self) -> None:
        """ConnectTimeout is re-raised after _MAX_RETRIES attempts."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_get = AsyncMock(side_effect=httpx.ConnectTimeout("always fails"))
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                with pytest.raises(httpx.ConnectTimeout):
                    await platform.list_issues_by_label("label")

        assert mock_get.call_count == _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_exhausted_retries_correct_attempt_count(self) -> None:
        """Exactly _MAX_RETRIES attempts are made before giving up."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        call_count = 0

        async def always_fails(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("always fails")

        client = _make_client(get=AsyncMock(side_effect=always_fails))

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                with pytest.raises(httpx.ConnectError):
                    await platform.list_issues_by_label("label")

        assert call_count == _MAX_RETRIES


# ---------------------------------------------------------------------------
# AC-4: All other HTTP methods also use the shared retry mechanism
# ---------------------------------------------------------------------------


class TestAllMethodsUseRetry:
    """AC-4: Retry applies to all GitHubPlatform HTTP methods."""

    @pytest.mark.asyncio
    async def test_search_issues_retries_on_connect_timeout(self) -> None:
        """search_issues retries on ConnectTimeout."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200, {"items": []})

        mock_get = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t/o"), success_resp]
        )
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                results = await platform.search_issues("prefix")

        assert results == []
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_create_issue_retries_on_connect_timeout(self) -> None:
        """create_issue retries on ConnectTimeout."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(
            201, {"number": 5, "title": "t", "html_url": "http://x"}
        )

        mock_post = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t/o"), success_resp]
        )
        client = _make_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                result = await platform.create_issue("title", "body")

        assert result.number == 5
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_close_issue_retries_on_connect_timeout(self) -> None:
        """close_issue retries on ConnectTimeout."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200)

        mock_patch = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t/o"), success_resp]
        )
        client = _make_client(patch=mock_patch)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                await platform.close_issue(42)

        assert mock_patch.call_count == 2

    @pytest.mark.asyncio
    async def test_assign_label_retries_on_connect_timeout(self) -> None:
        """assign_label retries on ConnectTimeout."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200)

        mock_post = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t/o"), success_resp]
        )
        client = _make_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                await platform.assign_label(1, "label")

        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_remove_label_retries_on_connect_timeout(self) -> None:
        """remove_label retries on ConnectTimeout."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        success_resp = _json_response(200)

        mock_delete = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t/o"), success_resp]
        )
        client = _make_client(delete=mock_delete)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock):
                await platform.remove_label(1, "label")

        assert mock_delete.call_count == 2


# ---------------------------------------------------------------------------
# AC-5: Non-retryable HTTP errors are not retried
# ---------------------------------------------------------------------------


class TestNonRetryableErrors:
    """AC-5: HTTP-level errors (4xx, 5xx) are not retried — exactly one attempt."""

    @pytest.mark.asyncio
    async def test_401_not_retried_raises_integration_error(self) -> None:
        """A 401 response raises IntegrationError after exactly one attempt."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        mock_get = AsyncMock(return_value=mock_resp)
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(IntegrationError):
                    await platform.list_issues_by_label("label")

        # Exactly one attempt — no retry for HTTP errors
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_404_not_retried(self) -> None:
        """A 404 response raises IntegrationError after exactly one attempt."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        mock_get = AsyncMock(return_value=mock_resp)
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(IntegrationError):
                    await platform.list_issues_by_label("label")

        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_500_not_retried(self) -> None:
        """A 500 response raises IntegrationError after exactly one attempt."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"

        mock_get = AsyncMock(return_value=mock_resp)
        client = _make_client(get=mock_get)

        with patch(_TARGET, return_value=client):
            with patch(_SLEEP_TARGET, new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(IntegrationError):
                    await platform.list_issues_by_label("label")

        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()
