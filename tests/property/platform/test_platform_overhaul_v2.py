"""Property tests for platform config overhaul — spec 65.

Test Spec: TS-65-P1 through TS-65-P6
Properties: Properties 1-6 from design.md
Requirements: 65-REQ-3.1, 65-REQ-3.2, 65-REQ-3.3, 65-REQ-3.4,
              65-REQ-2.4, 65-REQ-2.5, 65-REQ-5.2, 65-REQ-5.3, 65-REQ-5.E1,
              65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1, 65-REQ-6.1,
              65-REQ-7.1, 65-REQ-7.2
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, PlatformConfig
from agent_fox.core.config_gen import extract_schema, generate_config_template
from agent_fox.nightshift.platform_factory import create_platform
from agent_fox.platform.github import GitHubPlatform
from agent_fox.workspace import WorkspaceInfo
from agent_fox.workspace.harvest import post_harvest_integrate

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

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

        asyncio.get_event_loop().run_until_complete(run_test())


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
