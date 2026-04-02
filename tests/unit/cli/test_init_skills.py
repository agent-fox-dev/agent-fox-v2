"""Unit tests for skill installation (Spec 47).

Tests the _install_skills() function in isolation.

Requirements: 47-REQ-1.E1, 47-REQ-2.E1, 47-REQ-2.E2
Test Spec: TS-47-E1, TS-47-E2, TS-47-E3
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-47-E1: Unreadable template skipped
# ---------------------------------------------------------------------------


class TestUnreadableTemplateSkipped:
    """TS-47-E1: An unreadable template file is skipped with a warning."""

    def test_unreadable_template_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """47-REQ-1.E1: Unreadable template is skipped; valid ones installed."""
        from agent_fox.workspace.init_project import _install_skills

        # Create a fake _SKILLS_DIR with one valid and one unreadable file
        fake_skills = tmp_path / "fake_skills"
        fake_skills.mkdir()

        valid = fake_skills / "af-valid"
        valid.write_text("---\nname: af-valid\ndescription: Valid.\n---\nContent")

        unreadable = fake_skills / "af-broken"
        unreadable.write_text("content")
        unreadable.chmod(0o000)

        import agent_fox.workspace.init_project as init_mod

        monkeypatch.setattr(init_mod, "_SKILLS_DIR", fake_skills)

        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)

        # Valid skill installed, broken one skipped
        assert count == 1
        assert (project_root / ".claude" / "skills" / "af-valid" / "SKILL.md").exists()
        assert not (
            project_root / ".claude" / "skills" / "af-broken" / "SKILL.md"
        ).exists()

        # Cleanup permissions so tmp_path can be removed
        unreadable.chmod(0o644)

    def test_unreadable_count_excludes_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """47-REQ-1.E1: Return count excludes skipped skills."""
        from agent_fox.workspace.init_project import _install_skills

        fake_skills = tmp_path / "fake_skills"
        fake_skills.mkdir()

        # Two valid, one unreadable
        (fake_skills / "af-one").write_text(
            "---\nname: af-one\ndescription: One.\n---\nContent"
        )
        (fake_skills / "af-two").write_text(
            "---\nname: af-two\ndescription: Two.\n---\nContent"
        )
        broken = fake_skills / "af-broken"
        broken.write_text("content")
        broken.chmod(0o000)

        import agent_fox.workspace.init_project as init_mod

        monkeypatch.setattr(init_mod, "_SKILLS_DIR", fake_skills)

        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)
        assert count == 2

        broken.chmod(0o644)


# ---------------------------------------------------------------------------
# TS-47-E2: Empty templates directory
# ---------------------------------------------------------------------------


class TestEmptyTemplatesDirectory:
    """TS-47-E2: Empty or missing _templates/skills/ returns 0."""

    def test_empty_skills_dir_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """47-REQ-2.E1: Empty templates directory returns 0 skills."""
        from agent_fox.workspace.init_project import _install_skills

        fake_skills = tmp_path / "empty_skills"
        fake_skills.mkdir()

        import agent_fox.workspace.init_project as init_mod

        monkeypatch.setattr(init_mod, "_SKILLS_DIR", fake_skills)

        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)
        assert count == 0

    def test_missing_skills_dir_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """47-REQ-2.E1: Missing templates directory returns 0 skills."""
        from agent_fox.workspace.init_project import _install_skills

        fake_skills = tmp_path / "nonexistent_skills"

        import agent_fox.workspace.init_project as init_mod

        monkeypatch.setattr(init_mod, "_SKILLS_DIR", fake_skills)

        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)
        assert count == 0


# ---------------------------------------------------------------------------
# TS-47-E3: Permission error creating skills directory
# ---------------------------------------------------------------------------


class TestPermissionErrorHandled:
    """TS-47-E3: Permission error creating .claude/skills/ is handled."""

    def test_permission_error_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """47-REQ-2.E2: Cannot create .claude/skills/ returns 0, no crash."""
        from agent_fox.workspace.init_project import _install_skills

        # Set up a valid skills dir with one template
        fake_skills = tmp_path / "fake_skills"
        fake_skills.mkdir()
        (fake_skills / "af-test").write_text(
            "---\nname: af-test\ndescription: Test.\n---\nContent"
        )

        import agent_fox.workspace.init_project as init_mod

        monkeypatch.setattr(init_mod, "_SKILLS_DIR", fake_skills)

        project_root = tmp_path / "project"
        project_root.mkdir()

        # Make .claude read-only so skills/ can't be created
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        claude_dir.chmod(0o444)

        count = _install_skills(project_root)
        assert count == 0

        # Cleanup permissions
        claude_dir.chmod(0o755)
