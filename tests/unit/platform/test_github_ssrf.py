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

Acceptance criteria from issue #580 (DNS rebinding TOCTOU):
  580-AC-1: Transport re-validates resolved IP on every connection attempt
  580-AC-2: Construction still rejects immediately-restricted hostnames
  580-AC-3: Legitimate public-IP requests are not broken
  580-AC-4: All restricted categories caught at connection time
  580-AC-5: Construction-time DNS failure + connection-time restricted IP is caught

Requirements: 221-REQ-1.*, 221-REQ-2.*
"""

from __future__ import annotations

import socket
from unittest.mock import patch

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
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="169.254.169.254")


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
        platform = GitHubPlatform(owner="acme", repo="repo", token="tok", url="github.example.com")
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
        platform = GitHubPlatform(owner="acme", repo="repo", token="tok", url="github.com")
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
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="127.0.0.1:8080")


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
            platform = GitHubPlatform(owner="acme", repo="repo", token="tok", url="192.168.0.1")
            # If we get here, _api_base would be set to a bad value — fail.
            _ = platform._api_base

    def test_loopback_error_message_includes_ip(self) -> None:
        with pytest.raises(ConfigError, match="127.0.0.1"):
            GitHubPlatform(owner="acme", repo="repo", token="tok", url="127.0.0.1")


# ---------------------------------------------------------------------------
# AC-9 (issue #581): Reject unspecified, multicast, and reserved addresses
# ---------------------------------------------------------------------------


class TestRejectUnspecified:
    """AC-9a: Unspecified addresses (0.0.0.0 / ::) must be rejected."""

    def test_ipv4_unspecified_raises(self) -> None:
        with pytest.raises(ConfigError, match="0.0.0.0"):
            _validate_github_url("0.0.0.0")

    def test_ipv6_unspecified_raises(self) -> None:
        with pytest.raises(ConfigError):
            _validate_github_url("::")


class TestRejectMulticast:
    """AC-9b: Multicast addresses must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "224.0.0.1",  # IPv4 multicast (224.0.0.0/4)
            "239.255.255.255",  # IPv4 multicast upper bound
        ],
    )
    def test_ipv4_multicast_raises(self, url: str) -> None:
        with pytest.raises(ConfigError, match=url):
            _validate_github_url(url)

    def test_ipv6_multicast_raises(self) -> None:
        with pytest.raises(ConfigError):
            _validate_github_url("ff02::1")


class TestRejectReserved:
    """AC-9c: IANA reserved addresses must be rejected."""

    def test_ipv4_reserved_raises(self) -> None:
        with pytest.raises(ConfigError, match="240.0.0.1"):
            _validate_github_url("240.0.0.1")


# ---------------------------------------------------------------------------
# 580-AC-1 / 580-AC-4: DNS rebinding — transport re-validates at connect time
# ---------------------------------------------------------------------------

# Fake public IP returned at construction time.
_PUBLIC_IP_INFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]


def _make_rebinding_side_effect(
    restricted_ip: str,
) -> tuple[list[object], object]:
    """Return (first_result, subsequent_result) for a DNS rebinding scenario.

    First call (construction) returns a public IP.
    Subsequent calls (connection) return *restricted_ip*.
    """
    if ":" in restricted_ip:
        # IPv6
        subsequent = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (restricted_ip, 0, 0, 0))]
    else:
        subsequent = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (restricted_ip, 0))]

    call_count = 0

    def side_effect(host: str, port: object, *args: object, **kwargs: object) -> list[object]:
        nonlocal call_count
        call_count += 1
        return _PUBLIC_IP_INFO if call_count == 1 else subsequent

    return side_effect


class TestDnsRebindingGuard:
    """580-AC-1, 580-AC-4: DNS rebinding must be caught at connection time.

    A platform that was constructed successfully (hostname resolved to a
    public IP) must raise ConfigError before making any TCP connection if
    the hostname later resolves to a restricted address.
    """

    @pytest.mark.parametrize(
        "restricted_ip",
        [
            "127.0.0.1",  # loopback
            "10.0.0.1",  # private
            "169.254.169.254",  # link-local (IMDS)
            "::1",  # IPv6 loopback
            "0.0.0.0",  # unspecified
            "224.0.0.1",  # multicast
            "240.0.0.1",  # reserved
        ],
    )
    async def test_dns_rebinding_raises_config_error(self, restricted_ip: str) -> None:
        """580-AC-1 + 580-AC-4: ConfigError raised when DNS rebinds to a restricted IP."""
        side_effect = _make_rebinding_side_effect(restricted_ip)

        with patch("agent_fox.platform.github.socket.getaddrinfo", side_effect=side_effect):
            platform = GitHubPlatform(
                owner="owner",
                repo="repo",
                token="tok",
                url="my-ghe.example.com",
            )
            with pytest.raises(ConfigError):
                await platform.get_issue(1)

    # ---------------------------------------------------------------------------
    # 580-AC-5: Construction-time DNS failure + restricted IP at connect time
    # ---------------------------------------------------------------------------

    async def test_construction_dns_failure_then_restricted_at_connect(self) -> None:
        """580-AC-5: OSError during construction lets hostname through; restricted IP blocked at connect."""
        restricted = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        call_count = 0

        def side_effect(host: str, port: object, *args: object, **kwargs: object) -> list[object]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("DNS temporary failure")
            return restricted

        with patch("agent_fox.platform.github.socket.getaddrinfo", side_effect=side_effect):
            # Construction should succeed (DNS failure → allow through with warning).
            platform = GitHubPlatform(
                owner="owner",
                repo="repo",
                token="tok",
                url="my-ghe.example.com",
            )
            # Connection-time validation should catch the restricted IP.
            with pytest.raises(ConfigError):
                await platform.get_issue(1)
