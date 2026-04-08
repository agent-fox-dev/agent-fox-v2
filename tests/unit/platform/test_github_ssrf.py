"""Tests for SSRF protection in GitHubPlatform URL validation.

Acceptance criteria from issue #221:
  AC-1: Reject private IPv4 addresses
  AC-2: Reject loopback addresses
  AC-3: Reject link-local addresses (169.254.x.x)
  AC-4: Reject IPv6 loopback and link-local
  AC-5: Accept valid GitHub Enterprise hostnames
  AC-6: Accept 'github.com'
  AC-7: Reject IP addresses with port suffixes
  AC-8: Validation before _api_base is set; error message includes the IP

Requirements: 221-REQ-1.*, 221-REQ-2.*
"""

from __future__ import annotations

import pytest

from agent_fox.core.errors import ConfigError
from agent_fox.platform.github import GitHubPlatform, _validate_github_url

# ---------------------------------------------------------------------------
# AC-1: Reject private IPv4 addresses
# ---------------------------------------------------------------------------


class TestRejectPrivateIPv4:
    """AC-1: Private IPv4 ranges must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.1",
            "10.255.255.255",
            "192.168.0.0",
            "172.31.255.254",
        ],
    )
    def test_private_ipv4_raises(self, url: str) -> None:
        with pytest.raises(ConfigError, match=url):
            _validate_github_url(url)

    def test_private_ipv4_via_init(self) -> None:
        with pytest.raises(ConfigError):
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="10.0.0.1")


# ---------------------------------------------------------------------------
# AC-2: Reject loopback addresses
# ---------------------------------------------------------------------------


class TestRejectLoopback:
    """AC-2: Loopback addresses must be rejected."""

    @pytest.mark.parametrize("url", ["127.0.0.1", "127.0.0.2", "127.255.255.255"])
    def test_loopback_ipv4_raises(self, url: str) -> None:
        with pytest.raises(ConfigError, match=url):
            _validate_github_url(url)

    def test_loopback_via_init(self) -> None:
        with pytest.raises(ConfigError):
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="127.0.0.1")


# ---------------------------------------------------------------------------
# AC-3: Reject link-local addresses (169.254.x.x)
# ---------------------------------------------------------------------------


class TestRejectLinkLocal:
    """AC-3: Link-local addresses must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "169.254.169.254",  # IMDS endpoint
            "169.254.0.1",
            "169.254.255.255",
        ],
    )
    def test_link_local_ipv4_raises(self, url: str) -> None:
        with pytest.raises(ConfigError, match=url):
            _validate_github_url(url)

    def test_link_local_via_init(self) -> None:
        with pytest.raises(ConfigError):
            GitHubPlatform(
                owner="acme", repo="repo", token="tok", url="169.254.169.254"
            )


# ---------------------------------------------------------------------------
# AC-4: Reject IPv6 loopback and link-local
# ---------------------------------------------------------------------------


class TestRejectIPv6Restricted:
    """AC-4: IPv6 loopback and link-local must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "::1",  # loopback
            "fe80::1",  # link-local
            "fe80::dead:beef",  # link-local
        ],
    )
    def test_ipv6_restricted_raises(self, url: str) -> None:
        with pytest.raises(ConfigError, match=url.replace("::", r"\:\:")):
            _validate_github_url(url)


# ---------------------------------------------------------------------------
# AC-5: Accept valid GitHub Enterprise hostnames
# ---------------------------------------------------------------------------


class TestAcceptHostnames:
    """AC-5: Valid hostnames must be accepted and produce correct _api_base."""

    def test_hostname_accepted(self) -> None:
        _validate_github_url("github.example.com")  # must not raise

    def test_enterprise_api_base(self) -> None:
        platform = GitHubPlatform(
            owner="acme", repo="repo", token="tok", url="github.example.com"
        )
        assert platform._api_base == "https://github.example.com/api/v3"

    def test_arbitrary_hostname_accepted(self) -> None:
        _validate_github_url("my-ghe.corp.internal")  # must not raise


# ---------------------------------------------------------------------------
# AC-6: Accept 'github.com'
# ---------------------------------------------------------------------------


class TestAcceptGithubDotCom:
    """AC-6: 'github.com' must be accepted and produce api.github.com base."""

    def test_github_com_accepted(self) -> None:
        _validate_github_url("github.com")  # must not raise

    def test_github_com_api_base(self) -> None:
        platform = GitHubPlatform(owner="acme", repo="repo", token="tok")
        assert platform._api_base == "https://api.github.com"

    def test_github_com_explicit_url(self) -> None:
        platform = GitHubPlatform(
            owner="acme", repo="repo", token="tok", url="github.com"
        )
        assert platform._api_base == "https://api.github.com"


# ---------------------------------------------------------------------------
# AC-7: Reject IP addresses with port suffixes
# ---------------------------------------------------------------------------


class TestRejectIPWithPort:
    """AC-7: Restricted IPs with port suffixes must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "127.0.0.1:8080",
            "169.254.169.254:80",
            "192.168.1.1:443",
            "10.0.0.1:3000",
        ],
    )
    def test_ip_with_port_raises(self, url: str) -> None:
        with pytest.raises(ConfigError):
            _validate_github_url(url)

    def test_loopback_with_port_via_init(self) -> None:
        with pytest.raises(ConfigError):
            GitHubPlatform(
                owner="acme", repo="repo", token="tok", url="127.0.0.1:8080"
            )


# ---------------------------------------------------------------------------
# AC-8: Validation before _api_base is set; error message includes the IP
# ---------------------------------------------------------------------------


class TestValidationMessageAndOrdering:
    """AC-8: Error must occur before _api_base is set and include the URL."""

    def test_error_message_includes_url(self) -> None:
        url = "10.1.2.3"
        with pytest.raises(ConfigError, match=url):
            _validate_github_url(url)

    def test_api_base_not_set_on_error(self) -> None:
        """When validation raises, the platform object must not be created."""
        with pytest.raises(ConfigError):
            platform = GitHubPlatform(
                owner="acme", repo="repo", token="tok", url="192.168.0.1"
            )
            # If we get here, _api_base would be set to a bad value — fail.
            _ = platform._api_base

    def test_loopback_error_message_includes_ip(self) -> None:
        with pytest.raises(ConfigError, match="127.0.0.1"):
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="127.0.0.1")
