"""Property tests for banner rendering.

Test Spec: TS-14-P1, TS-14-P2, TS-14-P3, TS-14-P4, TS-14-P5
Properties: 1-5 from design.md
Requirements: 14-REQ-1.1, 14-REQ-2.1, 14-REQ-2.2, 14-REQ-2.E1,
              14-REQ-3.1, 14-REQ-4.2
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st
from rich.console import Console
from rich.theme import Theme

from agent_fox import __version__
from agent_fox.core.config import ModelConfig, ThemeConfig
from agent_fox.ui.display import create_theme, render_banner

# Expected fox art from design.md
EXPECTED_FOX_ART = r"""   /\_/\   _
  / o.o \/\ \
 ( > ^ < ) ) )
  \_^/\_/--'"""

_STYLE_ROLES = ("header", "success", "error", "warning", "info", "tool", "muted")

# Known valid model tier names and model IDs from the registry
_VALID_MODEL_NAMES = [
    "SIMPLE",
    "STANDARD",
    "ADVANCED",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]

# Expected resolved model IDs for each valid input
_MODEL_RESOLUTION: dict[str, str] = {
    "SIMPLE": "claude-haiku-4-5",
    "STANDARD": "claude-sonnet-4-6",
    "ADVANCED": "claude-opus-4-6",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-6": "claude-opus-4-6",
}


def _capture_banner(
    theme_config: ThemeConfig,
    model_config: ModelConfig,
    *,
    quiet: bool = False,
) -> str:
    """Capture render_banner output via a StringIO-backed console."""
    theme = create_theme(theme_config)
    buf = StringIO()
    rich_theme = Theme({role: getattr(theme_config, role) for role in _STYLE_ROLES})
    theme.console = Console(file=buf, theme=rich_theme, width=120)
    render_banner(theme, model_config, quiet=quiet)
    return buf.getvalue()


class TestFoxArtAlwaysPresent:
    """TS-14-P1: Fox art always present in banner output.

    Property 1: For any valid config with quiet=False, all four lines
    of FOX_ART appear in the output.
    """

    @given(playful=st.booleans())
    @settings(max_examples=10)
    def test_fox_art_present_for_any_playful_mode(self, playful: bool) -> None:
        """Fox art appears regardless of playful mode setting."""
        theme_config = ThemeConfig(playful=playful)
        output = _capture_banner(theme_config, ModelConfig())

        for line in EXPECTED_FOX_ART.splitlines():
            assert line in output, f"Fox art line {line!r} missing from output with playful={playful}"


class TestVersionLineAlwaysPresent:
    """TS-14-P2: Version + model line always present for valid models.

    Property 2: For any valid ModelConfig where coding is a known tier or
    model ID, the banner contains the correctly resolved version/model line.
    """

    @given(model_name=st.sampled_from(_VALID_MODEL_NAMES))
    @settings(max_examples=20)
    def test_version_model_line_for_valid_models(self, model_name: str) -> None:
        """Version/model line appears with correct resolved model ID."""
        model_config = ModelConfig(coding=model_name)
        with patch("agent_fox.ui.display._get_git_revision", return_value="abc1234"):
            output = _capture_banner(ThemeConfig(), model_config)

        resolved_id = _MODEL_RESOLUTION[model_name]
        expected = f"agent-fox v{__version__} (abc1234).  model: {resolved_id}"
        assert expected in output, f"Expected {expected!r} for coding={model_name!r}, got:\n{output}"


class TestModelFallbackNeverCrashes:
    """TS-14-P3: Model fallback never crashes.

    Property 3: For any arbitrary string as ModelConfig.coding,
    render_banner completes without exception and output contains
    'model:'.
    """

    @given(coding_name=st.text(min_size=0, max_size=50))
    @settings(max_examples=50)
    def test_arbitrary_model_name_never_crashes(self, coding_name: str) -> None:
        """Banner never raises, even with gibberish model names."""
        model_config = ModelConfig(coding=coding_name)
        # Should not raise
        output = _capture_banner(ThemeConfig(), model_config)
        assert "model:" in output


class TestQuietProducesNoOutput:
    """TS-14-P4: Quiet produces no output.

    Property 4: For any config combination, quiet=True produces empty output.
    """

    @given(
        playful=st.booleans(),
        coding=st.sampled_from(_VALID_MODEL_NAMES + ["NONEXISTENT", ""]),
    )
    @settings(max_examples=20)
    def test_quiet_always_produces_empty_output(self, playful: bool, coding: str) -> None:
        """quiet=True always results in empty output."""
        theme_config = ThemeConfig(playful=playful)
        model_config = ModelConfig(coding=coding)
        output = _capture_banner(theme_config, model_config, quiet=True)
        assert output == "", f"Expected empty output with quiet=True, got: {output!r}"


class TestCwdAlwaysPresent:
    """TS-14-P5: CWD always present in non-quiet output.

    Property 5: For any working directory path, banner output contains
    the cwd string.
    """

    @given(cwd_path=st.sampled_from(["/tmp/a", "/home/user/project", "/a/b/c/d", "/workspace"]))
    @settings(max_examples=10)
    def test_cwd_appears_for_any_path(self, cwd_path: str) -> None:
        """CWD string appears in banner for any working directory."""
        from unittest.mock import patch

        with patch.object(Path, "cwd", return_value=Path(cwd_path)):
            output = _capture_banner(ThemeConfig(), ModelConfig())
        assert cwd_path in output, f"Expected cwd {cwd_path!r} in output, got:\n{output}"
