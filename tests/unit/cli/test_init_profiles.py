"""Unit tests for the init --profiles CLI command (spec 99).

Covers: TS-99-6, TS-99-7, TS-99-E3
"""

from __future__ import annotations

from pathlib import Path


def test_init_creates_files(tmp_path: Path) -> None:
    """TS-99-6: init_profiles copies default profiles into project dir.

    Requirement: 99-REQ-3.1, 99-REQ-3.3
    """
    from agent_fox.cli.init import init_profiles

    paths = init_profiles(project_dir=tmp_path)

    assert len(paths) >= 4
    for name in ["coder", "reviewer", "verifier", "maintainer"]:
        dest = tmp_path / ".agent-fox" / "profiles" / f"{name}.md"
        assert dest.exists(), f"Profile {name}.md was not created"


def test_init_preserves_existing(tmp_path: Path) -> None:
    """TS-99-7: init_profiles skips files that already exist.

    Requirement: 99-REQ-3.2
    """
    from agent_fox.cli.init import init_profiles

    profiles_dir = tmp_path / ".agent-fox" / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "coder.md").write_text("MY CUSTOM CODER")

    paths = init_profiles(project_dir=tmp_path)

    # coder.md must NOT appear in the list of created paths
    assert "coder.md" not in [p.name for p in paths]
    # The pre-existing file content must be preserved
    assert (profiles_dir / "coder.md").read_text() == "MY CUSTOM CODER"


def test_init_creates_dirs(tmp_path: Path) -> None:
    """TS-99-E3: Init creates .agent-fox/profiles/ if the directory is absent.

    Requirement: 99-REQ-3.E1
    """
    from agent_fox.cli.init import init_profiles

    assert not (tmp_path / ".agent-fox").exists()

    init_profiles(project_dir=tmp_path)

    assert (tmp_path / ".agent-fox" / "profiles").is_dir()
