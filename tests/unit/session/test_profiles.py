"""Unit tests for archetype profile loading (spec 99).

Covers: TS-99-2, TS-99-3, TS-99-11, TS-99-12, TS-99-E2, TS-99-E6
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


def test_project_override(tmp_path: Path) -> None:
    """TS-99-2: Project profile replaces package default.

    Requirement: 99-REQ-1.2, 99-REQ-1.3
    """
    from agent_fox.session.profiles import load_profile

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder.md").write_text("CUSTOM CODER PROFILE")

    content = load_profile("coder", project_dir=tmp_path)

    assert content == "CUSTOM CODER PROFILE"
    assert "default" not in content.lower()


def test_default_fallback(tmp_path: Path) -> None:
    """TS-99-3: Fallback to package default when no project profile.

    Requirement: 99-REQ-1.2
    """
    from agent_fox.session.profiles import load_profile

    # tmp_path has no .agent-fox/profiles/coder.md
    content = load_profile("coder", project_dir=tmp_path)

    assert len(content) > 0
    assert "Identity" in content  # default profile has Identity section


def test_frontmatter_stripping(tmp_path: Path) -> None:
    """TS-99-11: YAML frontmatter is stripped from profiles.

    Requirement: 99-REQ-5.3
    """
    from agent_fox.session.profiles import load_profile

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "test_arch.md").write_text("---\nname: test\n---\n# Profile Content")

    content = load_profile("test_arch", project_dir=tmp_path)

    assert content.strip().startswith("# Profile Content")
    assert "---" not in content


def test_load_profile_signature() -> None:
    """TS-99-12: load_profile accepts archetype and optional project_dir.

    Requirement: 99-REQ-5.1, 99-REQ-5.2
    """
    from agent_fox.session.profiles import load_profile

    content = load_profile("coder", project_dir=None)

    assert isinstance(content, str)
    assert len(content) > 0


def test_missing_profile(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """TS-99-E2: Missing profile logs warning and returns empty string.

    Requirement: 99-REQ-1.E2
    """
    from agent_fox.session.profiles import load_profile

    with caplog.at_level(logging.WARNING):
        content = load_profile("nonexistent_archetype", project_dir=tmp_path)

    assert content == ""
    assert any("nonexistent_archetype" in record.message for record in caplog.records)


def test_none_project_dir() -> None:
    """TS-99-E6: None project_dir uses package default only.

    Requirement: 99-REQ-5.E1
    """
    from agent_fox.session.profiles import load_profile

    content = load_profile("coder", project_dir=None)

    assert len(content) > 0


# ---------------------------------------------------------------------------
# Mode-aware profile resolution (issue #342)
# ---------------------------------------------------------------------------


def test_mode_specific_profile_from_package() -> None:
    """Package-level mode-specific profile is loaded when mode is provided."""
    from agent_fox.session.profiles import load_profile

    content = load_profile("coder", mode="fix")

    assert len(content) > 0
    assert "nightshift" in content.lower()


def test_mode_specific_profile_project_override(tmp_path: Path) -> None:
    """Project-level mode-specific profile overrides package default."""
    from agent_fox.session.profiles import load_profile

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder_fix.md").write_text("CUSTOM FIX PROFILE")

    content = load_profile("coder", project_dir=tmp_path, mode="fix")

    assert content == "CUSTOM FIX PROFILE"


def test_mode_fallback_to_base_profile() -> None:
    """When mode-specific profile doesn't exist, falls back to base profile."""
    from agent_fox.session.profiles import load_profile

    # "nonexistent-mode" has no profile, should fall back to base coder profile
    content = load_profile("coder", mode="nonexistent-mode")

    assert len(content) > 0
    assert "Identity" in content  # base coder profile has Identity section


def test_mode_none_loads_base_profile() -> None:
    """mode=None loads the base profile, same as omitting mode."""
    from agent_fox.session.profiles import load_profile

    with_mode = load_profile("coder", mode=None)
    without_mode = load_profile("coder")

    assert with_mode == without_mode
