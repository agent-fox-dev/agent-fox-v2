"""Unit tests for create_platform_safe() in platform_factory.

Test Spec: TS-108-12, TS-108-13, TS-108-14
Requirements: 108-REQ-5.1, 108-REQ-5.3
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# TS-108-12, TS-108-13, TS-108-14
# Requirements: 108-REQ-5.1, 108-REQ-5.3
# ---------------------------------------------------------------------------


class TestCreatePlatformSafe:
    """Tests for create_platform_safe() factory function."""

    def test_returns_none_when_platform_type_is_none(self, tmp_path: Path) -> None:
        """TS-108-12: create_platform_safe returns None when type is 'none'.

        Requirements: 108-REQ-5.3
        """
        from agent_fox.nightshift.platform_factory import create_platform_safe

        config = MagicMock()
        config.platform.type = "none"

        result = create_platform_safe(config, tmp_path)

        assert result is None

    def test_returns_none_when_github_pat_missing(self, tmp_path: Path) -> None:
        """TS-108-13: create_platform_safe returns None when GITHUB_PAT is missing.

        Requirements: 108-REQ-5.3
        """
        from agent_fox.nightshift.platform_factory import create_platform_safe

        config = MagicMock()
        config.platform.type = "github"

        with patch.dict("os.environ", {}, clear=True):
            # Ensure GITHUB_PAT is absent
            import os

            os.environ.pop("GITHUB_PAT", None)
            result = create_platform_safe(config, tmp_path)

        assert result is None

    def test_returns_github_platform_when_configured(self, tmp_path: Path) -> None:
        """TS-108-14: create_platform_safe returns GitHubPlatform when configured.

        Requirements: 108-REQ-5.1
        """
        from agent_fox.nightshift.platform_factory import create_platform_safe
        from agent_fox.platform.github import GitHubPlatform

        config = MagicMock()
        config.platform.type = "github"
        config.platform.url = "github.com"

        # Mock git remote to return a valid GitHub URL
        mock_git_result = MagicMock()
        mock_git_result.returncode = 0
        mock_git_result.stdout = "https://github.com/test-owner/test-repo.git"

        with (
            patch.dict("os.environ", {"GITHUB_PAT": "test-token"}),
            patch("subprocess.run", return_value=mock_git_result),
        ):
            result = create_platform_safe(config, tmp_path)

        assert result is not None
        assert isinstance(result, GitHubPlatform)
