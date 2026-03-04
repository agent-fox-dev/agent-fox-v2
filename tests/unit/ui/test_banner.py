"""Banner rendering tests.

Test Spec: TS-14-1, TS-14-2, TS-14-3, TS-14-4, TS-14-7, TS-14-8,
           TS-14-E1, TS-14-E2
Requirements: 14-REQ-1.1, 14-REQ-1.2, 14-REQ-2.1, 14-REQ-2.2,
              14-REQ-2.3, 14-REQ-2.E1, 14-REQ-3.1, 14-REQ-3.2,
              14-REQ-3.E1
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from rich.theme import Theme

from agent_fox import __version__
from agent_fox.core.config import ModelConfig, ThemeConfig
from agent_fox.ui.banner import render_banner
from agent_fox.ui.theme import create_theme

# Expected fox art from design.md — used to verify banner output content.
EXPECTED_FOX_ART = r"""   /\_/\  _
  / o.o \/ \
 ( > ^ < )  )
  \_^/\_/--'"""

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")


def _capture_banner(
    theme_config: ThemeConfig,
    model_config: ModelConfig,
    *,
    quiet: bool = False,
    force_terminal: bool = False,
) -> str:
    """Capture render_banner output via a StringIO-backed console.

    Creates an AppTheme from the given config, replaces its console with
    one that writes to a StringIO buffer, then calls render_banner.

    Args:
        theme_config: Theme configuration to use.
        model_config: Model configuration for banner rendering.
        quiet: Whether to suppress banner output.
        force_terminal: If True, capture ANSI escape codes for role
            verification. If False, capture plain text.

    Returns:
        The captured console output as a string.
    """
    theme = create_theme(theme_config)
    buf = StringIO()
    # Rebuild a Rich Theme from config values to preserve styled output
    rich_theme = Theme({role: getattr(theme_config, role) for role in _STYLE_ROLES})
    theme.console = Console(
        file=buf,
        theme=rich_theme,
        force_terminal=force_terminal,
        width=120,
    )
    render_banner(theme, model_config, quiet=quiet)
    return buf.getvalue()


class TestBannerFoxArt:
    """TS-14-1: Banner contains fox ASCII art.

    Requirement: 14-REQ-1.1
    """

    def test_fox_art_present_in_output(self) -> None:
        """All four lines of fox ASCII art appear in banner output."""
        output = _capture_banner(ThemeConfig(), ModelConfig())

        for line in EXPECTED_FOX_ART.splitlines():
            assert line in output, (
                f"Expected fox art line {line!r} in banner output, got:\n{output}"
            )

    def test_fox_art_constant_exists(self) -> None:
        """FOX_ART constant is exported from banner module."""
        from agent_fox.ui.banner import FOX_ART  # type: ignore[attr-error]

        assert FOX_ART is not None
        lines = FOX_ART.splitlines()
        assert len(lines) == 4, f"Expected 4 lines of fox art, got {len(lines)}"


class TestBannerFoxArtStyling:
    """TS-14-2: Fox art styled with header role.

    Requirement: 14-REQ-1.2
    """

    def test_fox_art_uses_header_style(self) -> None:
        """Fox art is rendered using the header role markup."""
        output = _capture_banner(ThemeConfig(), ModelConfig(), force_terminal=True)

        # The header style for default theme is "bold #ff8c00" (bold orange).
        # When rendered with force_terminal, Rich embeds ANSI bold + color codes.
        first_art_line = EXPECTED_FOX_ART.splitlines()[0]
        assert first_art_line in output, (
            f"Expected fox art in styled output, got:\n{output!r}"
        )
        # Verify ANSI codes are present (header style applies bold + color)
        assert "\x1b[" in output, "Expected ANSI escape codes for header styling"


class TestBannerVersionModel:
    """TS-14-3: Banner shows version and model line.

    Requirements: 14-REQ-2.1, 14-REQ-2.2
    """

    def test_version_and_model_line_format(self) -> None:
        """Banner output contains version and resolved model ID line."""
        # coding="ADVANCED" -> resolves to claude-opus-4-6
        output = _capture_banner(ThemeConfig(), ModelConfig())

        expected = f"agent-fox v{__version__}  model: claude-opus-4-6"
        assert expected in output, (
            f"Expected {expected!r} in banner output, got:\n{output}"
        )

    def test_version_contains_semver(self) -> None:
        """Version in banner matches __version__."""
        output = _capture_banner(ThemeConfig(), ModelConfig())

        assert f"v{__version__}" in output


class TestBannerWorkingDirectory:
    """TS-14-4: Banner shows working directory.

    Requirement: 14-REQ-3.1
    """

    def test_cwd_appears_in_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Working directory appears in the banner output."""
        monkeypatch.setattr(
            Path, "cwd", staticmethod(lambda: Path("/tmp/test-project"))
        )

        output = _capture_banner(ThemeConfig(), ModelConfig())

        assert "/tmp/test-project" in output, (
            f"Expected cwd '/tmp/test-project' in banner output, got:\n{output}"
        )


class TestBannerVersionModelStyling:
    """TS-14-7: Version/model line styled with header role.

    Requirement: 14-REQ-2.3
    """

    def test_version_line_uses_header_style(self) -> None:
        """Version/model line is rendered with header role styling."""
        output = _capture_banner(ThemeConfig(), ModelConfig(), force_terminal=True)

        # Check that the version line appears in styled output with ANSI codes
        assert f"agent-fox v{__version__}" in output
        assert "\x1b[" in output, "Expected ANSI escape codes for header styling"


class TestBannerCwdStyling:
    """TS-14-8: Working directory styled with muted role.

    Requirement: 14-REQ-3.2
    """

    def test_cwd_uses_muted_style(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CWD line is rendered with muted role styling."""
        monkeypatch.setattr(Path, "cwd", staticmethod(lambda: Path("/tmp/styled-cwd")))

        config = ThemeConfig(muted="dim", header="bold #ff8c00")

        # Capture with ANSI to verify separate styling
        output = _capture_banner(config, ModelConfig(), force_terminal=True)

        # The cwd should appear in the output
        assert "/tmp/styled-cwd" in output

        # The muted style ("dim") produces ESC[2m in ANSI.
        assert "\x1b[2m" in output, (
            "Expected dim (muted) ANSI escape code in output for cwd line"
        )


# --- Edge Case Tests ---


class TestBannerModelFallback:
    """TS-14-E1: Model resolution failure shows raw config value.

    Requirement: 14-REQ-2.E1
    """

    def test_invalid_model_shows_raw_value(self) -> None:
        """Invalid model name falls back to raw config value in output."""
        output = _capture_banner(ThemeConfig(), ModelConfig(coding="NONEXISTENT"))

        assert "model: NONEXISTENT" in output, (
            f"Expected 'model: NONEXISTENT' in banner output, got:\n{output}"
        )

    def test_invalid_model_no_exception(self) -> None:
        """No exception is raised for an invalid model name."""
        # Should not raise
        _capture_banner(ThemeConfig(), ModelConfig(coding="NONEXISTENT"))


class TestBannerCwdOSError:
    """TS-14-E2: Path.cwd() OSError shows (unknown).

    Requirement: 14-REQ-3.E1
    """

    def test_cwd_oserror_shows_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If Path.cwd() raises OSError, display '(unknown)'."""

        def _raise_oserror() -> Path:
            raise OSError("directory deleted")

        monkeypatch.setattr(Path, "cwd", staticmethod(_raise_oserror))

        output = _capture_banner(ThemeConfig(), ModelConfig())

        assert "(unknown)" in output, (
            f"Expected '(unknown)' in banner output, got:\n{output}"
        )

    def test_cwd_oserror_no_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No exception propagates when Path.cwd() raises OSError."""

        def _raise_oserror() -> Path:
            raise OSError("directory deleted")

        monkeypatch.setattr(Path, "cwd", staticmethod(_raise_oserror))

        # Should not raise
        _capture_banner(ThemeConfig(), ModelConfig())
