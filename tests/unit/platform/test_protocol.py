"""Tests for Platform protocol definition and structural conformance.

Updated for spec 19 (Git and Platform Overhaul): the protocol now has only
``create_pr``.  Old methods (wait_for_ci, wait_for_review, merge_pr) and
NullPlatform have been removed.

Requirements: 19-REQ-6.2
"""

from __future__ import annotations

import inspect

from agent_fox.platform.github import GitHubPlatform
from agent_fox.platform.protocol import Platform


class TestPlatformProtocolMethods:
    """Platform protocol defines only create_pr.

    Requirement: 19-REQ-6.2
    """

    def test_has_create_pr_method(self) -> None:
        """Platform protocol has a create_pr method."""
        assert hasattr(Platform, "create_pr")

    def test_create_pr_is_coroutine(self) -> None:
        """create_pr is an async method."""
        assert inspect.iscoroutinefunction(Platform.create_pr)

    def test_create_pr_signature(self) -> None:
        """create_pr accepts branch, title, body (no labels)."""
        sig = inspect.signature(Platform.create_pr)
        params = list(sig.parameters.keys())
        assert "branch" in params
        assert "title" in params
        assert "body" in params
        # labels parameter was removed in spec 19
        assert "labels" not in params

    def test_no_wait_for_ci(self) -> None:
        """Platform protocol no longer has wait_for_ci."""
        assert not hasattr(Platform, "wait_for_ci")

    def test_no_wait_for_review(self) -> None:
        """Platform protocol no longer has wait_for_review."""
        assert not hasattr(Platform, "wait_for_review")

    def test_no_merge_pr(self) -> None:
        """Platform protocol no longer has merge_pr."""
        assert not hasattr(Platform, "merge_pr")


class TestGitHubPlatformSatisfiesProtocol:
    """GitHubPlatform satisfies the simplified Platform protocol.

    Requirement: 19-REQ-4.1
    """

    def test_github_platform_is_instance_of_platform(self) -> None:
        """GitHubPlatform passes isinstance check against Platform."""
        gh = GitHubPlatform(owner="o", repo="r", token="t")
        assert isinstance(gh, Platform)
