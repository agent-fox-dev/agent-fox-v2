"""Tests for simplified PlatformConfig.

Test Spec: TS-19-16 (only type and auto_merge), TS-19-E10 (old fields ignored)
Requirements: 19-REQ-5.1, 19-REQ-5.2, 19-REQ-5.3, 19-REQ-5.E1
"""

from __future__ import annotations

from agent_fox.core.config import PlatformConfig

# ---------------------------------------------------------------------------
# TS-19-16: PlatformConfig Only Has Type and AutoMerge
# ---------------------------------------------------------------------------


class TestPlatformConfigSimplified:
    """TS-19-16: PlatformConfig accepts only type and auto_merge fields.

    Requirements: 19-REQ-5.1, 19-REQ-5.2, 19-REQ-5.3
    """

    def test_default_values(self) -> None:
        """PlatformConfig defaults to type='none', auto_merge=False."""
        config = PlatformConfig()
        assert config.type == "none"
        assert config.auto_merge is False

    def test_github_with_auto_merge(self) -> None:
        """PlatformConfig accepts type='github' with auto_merge=True."""
        config = PlatformConfig(type="github", auto_merge=True)
        assert config.type == "github"
        assert config.auto_merge is True

    def test_no_old_fields(self) -> None:
        """PlatformConfig does not have old fields like wait_for_ci."""
        config = PlatformConfig(type="github", auto_merge=True)
        assert not hasattr(config, "wait_for_ci")
        assert not hasattr(config, "wait_for_review")
        assert not hasattr(config, "ci_timeout")
        assert not hasattr(config, "pr_granularity")
        assert not hasattr(config, "labels")


# ---------------------------------------------------------------------------
# TS-19-E10: Config With Old Fields Parses OK
# ---------------------------------------------------------------------------


class TestPlatformConfigBackwardCompat:
    """TS-19-E10: Config with removed fields loads without error.

    Requirement: 19-REQ-5.E1
    """

    def test_old_fields_silently_ignored(self) -> None:
        """PlatformConfig ignores old fields without error."""
        config = PlatformConfig(
            **{
                "type": "github",
                "auto_merge": True,
                "wait_for_ci": True,
                "labels": ["bot"],
                "ci_timeout": 900,
                "pr_granularity": "session",
                "wait_for_review": True,
            }
        )
        assert config.type == "github"
        assert config.auto_merge is True
        assert not hasattr(config, "wait_for_ci")
        assert not hasattr(config, "labels")
