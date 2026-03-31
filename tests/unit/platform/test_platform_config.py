"""Tests for platform config overhaul — spec 65.

Test Spec: TS-65-1 through TS-65-6, TS-65-12 through TS-65-16,
           TS-65-17, TS-65-18, TS-65-E1 through TS-65-E5
Requirements: 65-REQ-1.*, 65-REQ-2.*, 65-REQ-4.*, 65-REQ-5.*,
              65-REQ-6.*, 65-REQ-7.*
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_fox.core.config import AgentFoxConfig, PlatformConfig
from agent_fox.core.config_gen import extract_schema, generate_config_template
from agent_fox.nightshift.platform_factory import create_platform
from agent_fox.platform.github import GitHubPlatform
from agent_fox.platform.protocol import PlatformProtocol

# ---------------------------------------------------------------------------
# TS-65-1: PlatformConfig has no auto_merge field
# ---------------------------------------------------------------------------


class TestPlatformConfigNoAutoMerge:
    """TS-65-1: PlatformConfig must not expose auto_merge.

    Requirement: 65-REQ-1.1
    """

    def test_no_auto_merge_field(self) -> None:
        """PlatformConfig() does not expose auto_merge attribute."""
        config = PlatformConfig()
        assert not hasattr(config, "auto_merge")


# ---------------------------------------------------------------------------
# TS-65-2: Old auto_merge key silently ignored
# ---------------------------------------------------------------------------


class TestPlatformConfigAutoMergeIgnored:
    """TS-65-2: Old auto_merge key in config is silently ignored.

    Requirement: 65-REQ-1.2
    """

    def test_old_auto_merge_ignored(self) -> None:
        """PlatformConfig(auto_merge=True) loads without error and ignores it."""
        config = PlatformConfig(type="github", auto_merge=True)
        assert config.type == "github"
        assert not hasattr(config, "auto_merge")


# ---------------------------------------------------------------------------
# TS-65-3: PlatformConfig exposes url field
# ---------------------------------------------------------------------------


class TestPlatformConfigUrlField:
    """TS-65-3: PlatformConfig exposes a url field of type str.

    Requirement: 65-REQ-2.1
    """

    def test_url_field(self) -> None:
        """PlatformConfig accepts and stores url field."""
        config = PlatformConfig(url="github.example.com")
        assert config.url == "github.example.com"


# ---------------------------------------------------------------------------
# TS-65-4: Default url for github and none types
# ---------------------------------------------------------------------------


class TestPlatformConfigUrlDefaults:
    """TS-65-4: Default url is empty string for both github and none types.

    Requirements: 65-REQ-2.2, 65-REQ-2.3
    """

    def test_github_url_default_empty(self) -> None:
        """PlatformConfig(type='github') defaults url to empty string."""
        config = PlatformConfig(type="github")
        assert config.url == ""

    def test_none_url_default_empty(self) -> None:
        """PlatformConfig(type='none') defaults url to empty string."""
        config = PlatformConfig(type="none")
        assert config.url == ""


# ---------------------------------------------------------------------------
# TS-65-5: API base URL resolves to api.github.com
# ---------------------------------------------------------------------------


class TestGitHubPlatformApiBaseGithubCom:
    """TS-65-5: url='github.com' resolves to https://api.github.com.

    Requirements: 65-REQ-2.4, 65-REQ-5.2
    """

    def test_api_base_github_com(self) -> None:
        """GitHubPlatform with url='github.com' uses https://api.github.com."""
        platform = GitHubPlatform(owner="o", repo="r", token="t", url="github.com")
        assert platform._api_base == "https://api.github.com"


# ---------------------------------------------------------------------------
# TS-65-6: API base URL resolves for GitHub Enterprise
# ---------------------------------------------------------------------------


class TestGitHubPlatformApiBaseGhe:
    """TS-65-6: Non-default url resolves to https://{url}/api/v3.

    Requirements: 65-REQ-2.5, 65-REQ-5.3
    """

    def test_api_base_ghe(self) -> None:
        """GitHubPlatform with GHE url uses https://{url}/api/v3."""
        platform = GitHubPlatform(
            owner="o", repo="r", token="t", url="github.example.com"
        )
        assert platform._api_base == "https://github.example.com/api/v3"


# ---------------------------------------------------------------------------
# TS-65-12: PlatformProtocol has no create_pr
# ---------------------------------------------------------------------------


class TestPlatformProtocolNoCreatePr:
    """TS-65-12: PlatformProtocol must not define create_pr.

    Requirement: 65-REQ-4.1
    """

    def test_protocol_no_create_pr(self) -> None:
        """PlatformProtocol does not have a create_pr method."""
        assert not hasattr(PlatformProtocol, "create_pr")


# ---------------------------------------------------------------------------
# TS-65-13: GitHubPlatform has no create_pr
# ---------------------------------------------------------------------------


class TestGitHubPlatformNoCreatePr:
    """TS-65-13: GitHubPlatform must not implement create_pr.

    Requirement: 65-REQ-4.2
    """

    def test_github_no_create_pr(self) -> None:
        """GitHubPlatform does not have a create_pr method."""
        assert not hasattr(GitHubPlatform, "create_pr")


# ---------------------------------------------------------------------------
# TS-65-14: GitHubPlatform has no _get_default_branch
# ---------------------------------------------------------------------------


class TestGitHubPlatformNoGetDefaultBranch:
    """TS-65-14: GitHubPlatform must not have _get_default_branch.

    Requirement: 65-REQ-4.3
    """

    def test_github_no_get_default_branch(self) -> None:
        """GitHubPlatform does not have a _get_default_branch method."""
        assert not hasattr(GitHubPlatform, "_get_default_branch")


# ---------------------------------------------------------------------------
# TS-65-15: GitHubPlatform accepts url parameter
# ---------------------------------------------------------------------------


class TestGitHubPlatformUrlParam:
    """TS-65-15: GitHubPlatform __init__ accepts a url parameter.

    Requirement: 65-REQ-5.1
    """

    def test_url_param_accepted(self) -> None:
        """GitHubPlatform(url=...) constructs without error."""
        platform = GitHubPlatform(
            owner="o", repo="r", token="t", url="github.example.com"
        )
        assert platform is not None


# ---------------------------------------------------------------------------
# TS-65-16: Platform factory passes url to GitHubPlatform
# ---------------------------------------------------------------------------


class TestCreatePlatformWiresUrl:
    """TS-65-16: create_platform passes url from config to GitHubPlatform.

    Requirement: 65-REQ-6.1
    """

    def test_factory_wires_url(self, tmp_path: Path) -> None:
        """create_platform wires PlatformConfig.url into GitHubPlatform."""

        class FakeConfig:
            class platform:
                type = "github"
                url = "github.example.com"

        with (
            patch.dict(os.environ, {"GITHUB_PAT": "test-token"}),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "https://github.com/owner/repo.git\n"

            platform = create_platform(FakeConfig(), tmp_path)

        assert isinstance(platform, GitHubPlatform)
        # The platform should store the url from config
        assert platform._url == "github.example.com"


# ---------------------------------------------------------------------------
# TS-65-17: Config template includes type and url
# ---------------------------------------------------------------------------


class TestConfigTemplateHasTypeAndUrl:
    """TS-65-17: Generated config template has type and url under [platform].

    Requirements: 65-REQ-7.1, 65-REQ-7.3
    """

    def test_template_has_type_and_url(self) -> None:
        """generate_config_template() output includes type and url."""
        template = generate_config_template(extract_schema(AgentFoxConfig))
        # Find the [platform] section
        assert "[platform]" in template
        # Both fields must appear
        assert "type" in template
        assert "url" in template


# ---------------------------------------------------------------------------
# TS-65-18: Config template excludes auto_merge
# ---------------------------------------------------------------------------


class TestConfigTemplateNoAutoMerge:
    """TS-65-18: Generated config template must not contain auto_merge.

    Requirement: 65-REQ-7.2
    """

    def test_template_no_auto_merge(self) -> None:
        """generate_config_template() output does not contain auto_merge."""
        template = generate_config_template(extract_schema(AgentFoxConfig))
        assert "auto_merge" not in template


# ---------------------------------------------------------------------------
# TS-65-E1: Unknown keys alongside auto_merge ignored
# ---------------------------------------------------------------------------


class TestPlatformConfigUnknownKeysIgnored:
    """TS-65-E1: Multiple unknown keys are all silently ignored.

    Requirement: 65-REQ-1.E1
    """

    def test_unknown_keys_ignored(self) -> None:
        """PlatformConfig ignores auto_merge and other arbitrary unknown keys."""
        config = PlatformConfig(type="github", auto_merge=True, foo="bar", baz=42)
        assert config.type == "github"
        assert not hasattr(config, "auto_merge")
        assert not hasattr(config, "foo")
        assert not hasattr(config, "baz")


# ---------------------------------------------------------------------------
# TS-65-E2: url set with type=none is accepted
# ---------------------------------------------------------------------------


class TestPlatformConfigUrlWithTypeNone:
    """TS-65-E2: url with type='none' loads without error.

    Requirement: 65-REQ-2.E1
    """

    def test_url_with_type_none(self) -> None:
        """PlatformConfig(type='none', url=...) loads successfully."""
        config = PlatformConfig(type="none", url="github.example.com")
        assert config.type == "none"
        assert config.url == "github.example.com"


# ---------------------------------------------------------------------------
# TS-65-E4: Empty url defaults to github.com behavior
# ---------------------------------------------------------------------------


class TestGitHubPlatformEmptyUrlDefault:
    """TS-65-E4: Empty url resolves to https://api.github.com.

    Requirement: 65-REQ-5.E1
    """

    def test_empty_url_defaults(self) -> None:
        """GitHubPlatform with url='' uses https://api.github.com."""
        platform = GitHubPlatform(owner="o", repo="r", token="t", url="")
        assert platform._api_base == "https://api.github.com"


# ---------------------------------------------------------------------------
# TS-65-E5: Missing GITHUB_PAT exits with code 1
# ---------------------------------------------------------------------------


class TestCreatePlatformMissingPat:
    """TS-65-E5: create_platform exits with code 1 if GITHUB_PAT is unset.

    Requirement: 65-REQ-6.E1
    """

    def test_missing_pat_exits(self, tmp_path: Path) -> None:
        """create_platform calls sys.exit(1) when GITHUB_PAT is missing."""

        class FakeConfig:
            class platform:
                type = "github"
                url = ""

        env_without_pat = {k: v for k, v in os.environ.items()}
        env_without_pat.pop("GITHUB_PAT", None)

        with (
            patch.dict(os.environ, env_without_pat, clear=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            create_platform(FakeConfig(), tmp_path)

        assert exc_info.value.code == 1
