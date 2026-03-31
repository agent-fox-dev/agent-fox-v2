"""Property tests for Git and Platform Overhaul.

Spec 19 retained tests: TS-19-P1 (no push in templates),
    TS-19-P2 (URL parsing roundtrip), TS-19-P3 (config backward compat).
    TS-19-P4 (post-harvest strategy) removed — strategy no longer exists.

Spec 65 property tests: TS-65-P1 through TS-65-P6.

Requirements: 19-REQ-2.1, 19-REQ-2.4, 19-REQ-2.E1, 19-REQ-4.4,
              19-REQ-4.E4, 19-REQ-5.E1,
              65-REQ-3.1, 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4,
              65-REQ-2.4, 65-REQ-2.5, 65-REQ-5.2, 65-REQ-5.3, 65-REQ-5.E1,
              65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1, 65-REQ-6.1,
              65-REQ-7.1, 65-REQ-7.2
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, PlatformConfig
from agent_fox.core.config_gen import extract_schema, generate_config_template
from agent_fox.nightshift.platform_factory import create_platform
from agent_fox.platform.github import GitHubPlatform, parse_github_remote
from agent_fox.workspace import WorkspaceInfo
from agent_fox.workspace.harvest import post_harvest_integrate

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Strategy for GitHub-valid owner/repo names
_github_name = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-",
    ),
    min_size=1,
    max_size=39,
).filter(lambda s: not s.startswith("-") and not s.endswith("-"))

_github_repo = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_.",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: not s.startswith("-") and not s.endswith(".") and ".." not in s)

# Branch names: alphanumeric + /._- , 1-100 chars
_branch_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="/._-",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: not s.startswith("/") and not s.endswith("/"))

# Hostname-like strings: alphanumeric + .- , 1-253 chars
_hostname_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters=".-",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: len(s) > 0 and not s.startswith(".") and not s.endswith("."))

# Random string key names for config
_extra_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1,
    max_size=20,
).filter(lambda s: s not in {"type", "url"})


def _make_workspace(branch: str = "feature/test/1") -> WorkspaceInfo:
    return WorkspaceInfo(
        path=Path("/tmp/test-worktree"),
        branch=branch,
        spec_name="test_spec",
        task_group=1,
    )


# ---------------------------------------------------------------------------
# TS-19-P1: No Push Instructions In Any Template
# ---------------------------------------------------------------------------


class TestNoPushInstructionsInTemplates:
    """TS-19-P1: No template file contains git push instructions.

    Property 3: For any template file in _templates/prompts/,
    the content SHALL NOT contain 'git push'.
    Validates: 19-REQ-2.1, 19-REQ-2.4, 19-REQ-2.E1
    """

    _TEMPLATE_DIR = (
        Path(__file__).resolve().parents[3] / "agent_fox" / "_templates" / "prompts"
    )

    def test_no_push_in_any_template(self) -> None:
        """No template in _templates/prompts/ contains 'git push'."""
        for template_file in self._TEMPLATE_DIR.glob("*.md"):
            content = template_file.read_text()
            assert "git push" not in content, (
                f"{template_file.name} contains 'git push'"
            )


# ---------------------------------------------------------------------------
# TS-19-P2: Remote URL Parsing Roundtrip
# ---------------------------------------------------------------------------


class TestRemoteUrlParsingRoundtrip:
    """TS-19-P2: GitHub URLs parse correctly, non-GitHub URLs return None.

    Property 6: For any valid GitHub remote URL, parse_github_remote()
    returns the correct (owner, repo) tuple.
    Validates: 19-REQ-4.4, 19-REQ-4.E4
    """

    @given(owner=_github_name, repo=_github_repo)
    @settings(max_examples=100)
    def test_https_url_parses(self, owner: str, repo: str) -> None:
        """HTTPS GitHub URLs parse to (owner, repo)."""
        url = f"https://github.com/{owner}/{repo}.git"
        result = parse_github_remote(url)
        assert result == (owner, repo)

    @given(owner=_github_name, repo=_github_repo)
    @settings(max_examples=100)
    def test_ssh_url_parses(self, owner: str, repo: str) -> None:
        """SSH GitHub URLs parse to (owner, repo)."""
        url = f"git@github.com:{owner}/{repo}.git"
        result = parse_github_remote(url)
        assert result == (owner, repo)

    @given(
        host=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-.",
            ),
            min_size=3,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_non_github_url_returns_none(self, host: str) -> None:
        """Non-GitHub URLs return None."""
        assume("github.com" not in host)
        url = f"https://{host}/owner/repo.git"
        result = parse_github_remote(url)
        assert result is None


# ---------------------------------------------------------------------------
# TS-19-P3: Config Backward Compatibility
# ---------------------------------------------------------------------------


class TestConfigBackwardCompatibility:
    """TS-19-P3: Old config fields are silently ignored.

    Property 7: For any combination of old field names and values,
    PlatformConfig parses without error. auto_merge is excluded since
    it is now a silently-ignored unknown field (not a recognized field).
    Validates: 19-REQ-5.E1
    """

    @given(
        wait_for_ci=st.booleans(),
        wait_for_review=st.booleans(),
        ci_timeout=st.integers(min_value=0, max_value=10000),
        pr_granularity=st.sampled_from(["session", "spec", "group"]),
        labels=st.lists(st.text(max_size=20), max_size=5),
    )
    @settings(max_examples=50)
    def test_old_fields_ignored(
        self,
        wait_for_ci: bool,
        wait_for_review: bool,
        ci_timeout: int,
        pr_granularity: str,
        labels: list[str],
    ) -> None:
        """PlatformConfig ignores old fields without error."""
        data = {
            "type": "none",
            "wait_for_ci": wait_for_ci,
            "wait_for_review": wait_for_review,
            "ci_timeout": ci_timeout,
            "pr_granularity": pr_granularity,
            "labels": labels,
        }
        config = PlatformConfig(**data)
        assert config.type == "none"
        assert not hasattr(config, "wait_for_ci")
        assert not hasattr(config, "wait_for_review")
        assert not hasattr(config, "ci_timeout")
        assert not hasattr(config, "pr_granularity")
        assert not hasattr(config, "labels")


# ---------------------------------------------------------------------------
# TS-65-P1: Post-harvest always pushes both branches
# ---------------------------------------------------------------------------


class TestAlwaysPushesBoth:
    """TS-65-P1: For any workspace, post-harvest pushes both branches.

    Property 1: post_harvest_integrate always pushes feature branch (if exists)
    and calls _push_develop_if_pushable.
    Validates: 65-REQ-3.1, 65-REQ-3.2
    """

    @given(branch_name=_branch_strategy)
    @settings(max_examples=50)
    def test_always_pushes_both(self, branch_name: str) -> None:
        """For any branch name, post-harvest pushes both branches."""
        import asyncio

        workspace = _make_workspace(branch=branch_name)
        push_calls: list[str] = []

        async def mock_push(repo_root, branch, remote="origin"):
            push_calls.append(branch)
            return True

        async def run_test():
            with (
                patch(
                    "agent_fox.workspace.harvest.push_to_remote",
                    side_effect=mock_push,
                ),
                patch(
                    "agent_fox.workspace.harvest.local_branch_exists",
                    return_value=True,
                ),
                patch(
                    "agent_fox.workspace.harvest._push_develop_if_pushable",
                    new_callable=AsyncMock,
                ) as mock_push_develop,
            ):
                await post_harvest_integrate(
                    repo_root=Path("/tmp"),
                    workspace=workspace,
                )
                # Develop push must be attempted
                assert mock_push_develop.call_count == 1
                assert mock_push_develop.call_args[0][0] == Path("/tmp")

            # Feature branch push must be attempted
            assert branch_name in push_calls

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# TS-65-P2: Post-harvest never calls GitHub API
# ---------------------------------------------------------------------------


class TestNoGithubApiInPostHarvest:
    """TS-65-P2: post_harvest_integrate source has no GitHub API references.

    Property 2: Source code of post_harvest_integrate must not contain
    any GitHub API references.
    Validates: 65-REQ-3.3, 65-REQ-3.4
    """

    def test_no_github_api(self) -> None:
        """post_harvest_integrate source contains no GitHub API references."""
        source = inspect.getsource(post_harvest_integrate)
        assert "GitHubPlatform" not in source
        assert "httpx" not in source
        assert "parse_github_remote" not in source
        assert "GITHUB_PAT" not in source


# ---------------------------------------------------------------------------
# TS-65-P3: API URL resolution is deterministic
# ---------------------------------------------------------------------------


class TestUrlResolutionDeterministic:
    """TS-65-P3: URL resolution produces api.github.com for github.com/empty.

    Property 3: GitHubPlatform API base URL is deterministic.
    Validates: 65-REQ-2.4, 65-REQ-2.5, 65-REQ-5.2, 65-REQ-5.3, 65-REQ-5.E1
    """

    @given(url=_hostname_strategy)
    @settings(max_examples=100)
    def test_url_resolution(self, url: str) -> None:
        """URL resolution is deterministic: github.com/empty → api.github.com."""
        platform = GitHubPlatform(owner="o", repo="r", token="t", url=url)
        if url in ("github.com", ""):
            assert platform._api_base == "https://api.github.com"
        else:
            assert platform._api_base == f"https://{url}/api/v3"

    def test_empty_url_resolves_to_github(self) -> None:
        """Empty URL resolves to api.github.com."""
        platform = GitHubPlatform(owner="o", repo="r", token="t", url="")
        assert platform._api_base == "https://api.github.com"

    def test_github_com_resolves_to_api(self) -> None:
        """github.com resolves to https://api.github.com."""
        platform = GitHubPlatform(owner="o", repo="r", token="t", url="github.com")
        assert platform._api_base == "https://api.github.com"


# ---------------------------------------------------------------------------
# TS-65-P4: Unknown config keys silently ignored
# ---------------------------------------------------------------------------


class TestUnknownConfigKeysIgnored:
    """TS-65-P4: Arbitrary extra keys are silently dropped from PlatformConfig.

    Property 4: PlatformConfig always only exposes type and url.
    Validates: 65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1
    """

    @given(
        extra_keys=st.dictionaries(
            keys=_extra_key_strategy,
            values=st.text(max_size=50),
            max_size=10,
        )
    )
    @settings(max_examples=100)
    def test_unknown_keys_ignored(self, extra_keys: dict) -> None:
        """PlatformConfig ignores any extra keys; only type and url accessible."""
        data = {"type": "github", **extra_keys}
        config = PlatformConfig(**data)
        assert config.type == "github"
        for key in extra_keys:
            assert not hasattr(config, key)


# ---------------------------------------------------------------------------
# TS-65-P5: Platform factory wires url
# ---------------------------------------------------------------------------


class TestPlatformFactoryWiresUrl:
    """TS-65-P5: create_platform passes url from config to GitHubPlatform.

    Property 5: URL from config is wired through to the GitHubPlatform constructor.
    Validates: 65-REQ-6.1
    """

    @given(url=_hostname_strategy)
    @settings(max_examples=30)
    def test_factory_wires_url(self, url: str) -> None:
        """create_platform passes url to GitHubPlatform constructor."""

        class FakePlatformCfg:
            type = "github"

        class FakeConfig:
            platform = FakePlatformCfg()

        FakeConfig.platform.url = url

        with (
            patch.dict(os.environ, {"GITHUB_PAT": "test-token"}),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "https://github.com/owner/repo.git\n"

            platform = create_platform(FakeConfig(), Path("/tmp"))

        assert isinstance(platform, GitHubPlatform)
        expected_url = url if url else "github.com"
        assert platform._url == expected_url


# ---------------------------------------------------------------------------
# TS-65-P6: Config template schema correctness
# ---------------------------------------------------------------------------


class TestConfigTemplateSchemaCorrectness:
    """TS-65-P6: Generated template always includes type and url, never auto_merge.

    Property 6: generate_config_template output is always schema-correct.
    Validates: 65-REQ-7.1, 65-REQ-7.2
    """

    def test_template_schema(self) -> None:
        """Template always contains type and url, never auto_merge."""
        template = generate_config_template(extract_schema(AgentFoxConfig))
        assert "type" in template
        assert "url" in template
        assert "auto_merge" not in template
