"""Tests for GitHubPlatform.create_label.

Test Spec: TS-358-1 through TS-358-5
Requirements: 358-REQ-1 through 358-REQ-5
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_fox.core.errors import IntegrationError
from agent_fox.platform.github import GitHubPlatform

_TARGET = "agent_fox.platform.github.httpx.AsyncClient"


def _mock_client(**method_responses: MagicMock) -> AsyncMock:
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
# TS-358-1: create_label sends POST to correct endpoint
# ---------------------------------------------------------------------------


class TestCreateLabelRequest:
    """Verify create_label sends a POST to the correct GitHub API endpoint."""

    async def test_sends_post_to_correct_endpoint(self) -> None:
        """TS-358-1: POST request sent to /repos/{owner}/{repo}/labels."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            201,
            {"id": 1, "name": "af:fix", "color": "12ec39", "description": "test"},
        )
        requests_made: list[tuple[str, Any]] = []

        async def mock_post(url, *, json=None, headers=None, **kw: Any) -> MagicMock:
            requests_made.append(("POST", url, json))
            return mock_resp

        client = _mock_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            await platform.create_label("af:fix", "12ec39", "Issues ready to be implemented")

        assert len(requests_made) == 1
        method, url, payload = requests_made[0]
        assert method == "POST"
        assert "/repos/org/repo/labels" in url
        assert payload["name"] == "af:fix"
        assert payload["color"] == "12ec39"
        assert payload["description"] == "Issues ready to be implemented"


# ---------------------------------------------------------------------------
# TS-358-2: create_label succeeds on 201
# ---------------------------------------------------------------------------


class TestCreateLabelSuccess:
    """Verify create_label succeeds on 201 response."""

    async def test_201_returns_none(self) -> None:
        """TS-358-2: No exception raised on 201 response."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            201,
            {"id": 1, "name": "af:hunt", "color": "0075ca", "description": ""},
        )
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            result = await platform.create_label("af:hunt", "0075ca")

        assert result is None


# ---------------------------------------------------------------------------
# TS-358-3: create_label is idempotent — 422 already_exists succeeds silently
# ---------------------------------------------------------------------------


class TestCreateLabelIdempotent:
    """Verify create_label treats 422 'already_exists' as success."""

    async def test_422_already_exists_succeeds_silently(self) -> None:
        """TS-358-3: No exception raised when label already exists (422)."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            422,
            {
                "message": "Validation Failed",
                "errors": [{"code": "already_exists"}],
            },
            text='{"message":"Validation Failed","errors":[{"code":"already_exists"}]}',
        )
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            # Must NOT raise — 422 already_exists is idempotent
            await platform.create_label("af:fix", "12ec39")

    async def test_422_other_error_raises(self) -> None:
        """TS-358-4: 422 with a different error code raises IntegrationError."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            422,
            {
                "message": "Validation Failed",
                "errors": [{"code": "invalid"}],
            },
            text='{"message":"Validation Failed","errors":[{"code":"invalid"}]}',
        )
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.create_label("bad-color", "ZZZZZZ")


# ---------------------------------------------------------------------------
# TS-358-4: create_label raises IntegrationError on server errors
# ---------------------------------------------------------------------------


class TestCreateLabelError:
    """Verify non-422 errors raise IntegrationError."""

    async def test_500_raises_integration_error(self) -> None:
        """TS-358-4: IntegrationError on 500."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(500, text="Internal Server Error")
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.create_label("af:fix", "12ec39")

    async def test_404_raises_integration_error(self) -> None:
        """TS-358-5: IntegrationError on 404 (e.g. repo not found)."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(404, text="Not Found")
        client = _mock_client(post=AsyncMock(return_value=mock_resp))

        with patch(_TARGET, return_value=client):
            with pytest.raises(IntegrationError):
                await platform.create_label("af:fix", "12ec39")


# ---------------------------------------------------------------------------
# TS-358-5: default description is empty string
# ---------------------------------------------------------------------------


class TestCreateLabelDefaults:
    """Verify create_label sends empty description when not provided."""

    async def test_default_description_is_empty(self) -> None:
        """TS-358-5: description defaults to empty string."""
        platform = GitHubPlatform(owner="org", repo="repo", token="tok")

        mock_resp = _json_response(
            201,
            {"id": 1, "name": "af:fix", "color": "12ec39", "description": ""},
        )
        payloads: list[dict] = []

        async def mock_post(url, *, json=None, headers=None, **kw: Any) -> MagicMock:
            payloads.append(json or {})
            return mock_resp

        client = _mock_client(post=mock_post)

        with patch(_TARGET, return_value=client):
            await platform.create_label("af:fix", "12ec39")

        assert payloads[0]["description"] == ""
