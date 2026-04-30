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


# ---------------------------------------------------------------------------
# Symlink rejection (issue #586, CWE-59)
# ---------------------------------------------------------------------------


def test_symlinked_project_profile_is_skipped(tmp_path: Path) -> None:
    """AC-1: load_profile() skips a project-level profile that is a symlink.

    A symlink pointing outside the repo must never be read; the function
    must fall through to the package-embedded fallback instead.
    """
    from agent_fox.session.profiles import load_profile

    # Create a sensitive file OUTSIDE the project tree.
    external_file = tmp_path / "external_secret.md"
    external_file.write_text("SECRET")

    profiles_dir = tmp_path / "project" / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    symlink = profiles_dir / "coder.md"
    symlink.symlink_to(external_file)

    project_dir = tmp_path / "project"
    result = load_profile("coder", project_dir=project_dir)

    assert "SECRET" not in result
    # Fell back to the package default, which has real content.
    assert len(result) > 0


def test_symlinked_project_profile_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-2: load_profile() emits a WARNING when it skips a symlinked candidate."""
    from agent_fox.session.profiles import load_profile

    external_file = tmp_path / "external.md"
    external_file.write_text("SENSITIVE")

    profiles_dir = tmp_path / "project" / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    symlink = profiles_dir / "coder.md"
    symlink.symlink_to(external_file)

    project_dir = tmp_path / "project"
    with caplog.at_level(logging.WARNING):
        load_profile("coder", project_dir=project_dir)

    warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("symlink" in msg.lower() for msg in warning_messages)
    assert any(str(symlink) in msg for msg in warning_messages)


def test_regular_project_profile_still_loads(tmp_path: Path) -> None:
    """AC-5 (profiles): Non-symlinked project profiles load correctly after the fix."""
    from agent_fox.session.profiles import load_profile

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder.md").write_text("custom-directive")

    result = load_profile("coder", project_dir=tmp_path)

    assert "custom-directive" in result


# ---------------------------------------------------------------------------
# Path traversal rejection (issue #585, CWE-22)
# ---------------------------------------------------------------------------


def test_load_profile_rejects_path_traversal_in_archetype() -> None:
    """AC-1: load_profile() raises ValueError for path traversal in archetype."""
    from agent_fox.session.profiles import load_profile

    with pytest.raises(ValueError, match="archetype"):
        load_profile("../../etc/passwd")


def test_load_profile_rejects_path_traversal_in_mode() -> None:
    """AC-2: load_profile() raises ValueError for path traversal in mode."""
    from agent_fox.session.profiles import load_profile

    with pytest.raises(ValueError, match="mode"):
        load_profile("coder", mode="../secret")


def test_has_custom_profile_rejects_path_traversal(tmp_path: Path) -> None:
    """AC-3: has_custom_profile() raises ValueError for path traversal in name."""
    from agent_fox.session.profiles import has_custom_profile

    with pytest.raises(ValueError, match="name"):
        has_custom_profile("../../etc", tmp_path)


def test_load_profile_safe_names_accepted() -> None:
    """AC-4: load_profile() accepts valid alphanumeric/hyphen/underscore names."""
    from agent_fox.session.profiles import load_profile

    # Should not raise — both are safe names.
    result = load_profile("coder", mode="fix")
    assert isinstance(result, str)
    assert len(result) > 0


def test_has_custom_profile_safe_name_accepted(tmp_path: Path) -> None:
    """AC-4: has_custom_profile() accepts a valid name without raising."""
    from agent_fox.session.profiles import has_custom_profile

    # Should not raise; returns a boolean.
    result = has_custom_profile("coder", tmp_path)
    assert isinstance(result, bool)
