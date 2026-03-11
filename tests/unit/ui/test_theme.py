"""Theme system tests.

Test Spec: TS-01-12 (playful toggle), TS-01-E6 (invalid color fallback)
Requirements: 01-REQ-7.1, 01-REQ-7.3, 01-REQ-7.4, 01-REQ-7.E1
"""

from __future__ import annotations

from agent_fox.core.config import ThemeConfig
from agent_fox.ui.display import AppTheme, create_theme


class TestThemePlayfulToggle:
    """TS-01-12: Theme playful mode toggle."""

    def test_playful_and_neutral_differ(self) -> None:
        """Playful and non-playful modes return different messages."""
        playful_theme = create_theme(ThemeConfig(playful=True))
        neutral_theme = create_theme(ThemeConfig(playful=False))

        playful_msg = playful_theme.playful("task_complete")
        neutral_msg = neutral_theme.playful("task_complete")

        assert playful_msg != neutral_msg

    def test_playful_message_non_empty(self) -> None:
        """Playful mode returns a non-empty message."""
        theme = create_theme(ThemeConfig(playful=True))

        msg = theme.playful("task_complete")

        assert len(msg) > 0

    def test_neutral_message_non_empty(self) -> None:
        """Neutral mode returns a non-empty message."""
        theme = create_theme(ThemeConfig(playful=False))

        msg = theme.playful("task_complete")

        assert len(msg) > 0

    def test_theme_has_color_roles(self) -> None:
        """Theme exposes all required color roles."""
        theme = create_theme(ThemeConfig())

        assert isinstance(theme, AppTheme)
        # Theme should be able to style text with each role
        for role in ("header", "success", "error", "warning", "info", "tool", "muted"):
            styled = theme.styled("test", role)
            assert isinstance(styled, str)


class TestThemeInvalidColor:
    """TS-01-E6: Invalid Rich style falls back to default."""

    def test_invalid_style_creates_theme(self) -> None:
        """Theme is created without error even with invalid style value."""
        theme = create_theme(ThemeConfig(header="not_a_valid_style"))

        assert theme is not None
        assert isinstance(theme, AppTheme)

    def test_invalid_style_still_functions(self) -> None:
        """Theme with invalid style can still render output."""
        theme = create_theme(ThemeConfig(header="not_a_valid_style"))

        # Should not raise — falls back to default
        theme.header("test text")
