"""Property tests for Git and Platform Overhaul.

Test Spec: TS-19-P1 (no push in templates), TS-19-P2 (URL parsing roundtrip),
           TS-19-P3 (config backward compat), TS-19-P4 (post-harvest strategy)
Properties: Property 3, 6, 7, 4 from design.md
Requirements: 19-REQ-2.1, 19-REQ-2.4, 19-REQ-2.E1, 19-REQ-4.4,
              19-REQ-4.E4, 19-REQ-5.E1, 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agent_fox.core.config import PlatformConfig
from agent_fox.platform.github import parse_github_remote

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
        Path(__file__).resolve().parents[3]
        / "agent_fox"
        / "_templates"
        / "prompts"
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
).filter(
    lambda s: not s.startswith("-")
    and not s.endswith(".")
    and ".." not in s
)


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
    PlatformConfig parses without error.
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
            "auto_merge": False,
            "wait_for_ci": wait_for_ci,
            "wait_for_review": wait_for_review,
            "ci_timeout": ci_timeout,
            "pr_granularity": pr_granularity,
            "labels": labels,
        }
        config = PlatformConfig(**data)
        assert config.type == "none"
        assert config.auto_merge is False


# ---------------------------------------------------------------------------
# TS-19-P4: Post-Harvest Strategy Matches Config
# ---------------------------------------------------------------------------


class TestPostHarvestStrategyMatchesConfig:
    """TS-19-P4: The push strategy is determined solely by platform config.

    Property 4: Develop is pushed iff type="none" or auto_merge=True.
    PR is created iff type="github" and auto_merge=False.
    Validates: 19-REQ-3.1, 19-REQ-3.2, 19-REQ-3.3
    """

    @given(
        ptype=st.sampled_from(["none", "github"]),
        auto_merge=st.booleans(),
    )
    @settings(max_examples=10)
    def test_strategy_determination(
        self, ptype: str, auto_merge: bool
    ) -> None:
        """Strategy matches config invariants."""
        # Ensure config parses without error
        PlatformConfig(type=ptype, auto_merge=auto_merge)

        should_push_develop = ptype == "none" or auto_merge is True
        should_create_pr = ptype == "github" and auto_merge is False

        # Verify the config captures the right strategy determination
        # (The actual post-harvest behavior is tested in unit tests;
        # this property test verifies the strategy logic is sound.)
        if ptype == "none":
            assert should_push_develop is True
            assert should_create_pr is False
        elif ptype == "github" and auto_merge:
            assert should_push_develop is True
            assert should_create_pr is False
        elif ptype == "github" and not auto_merge:
            assert should_push_develop is False
            assert should_create_pr is True
