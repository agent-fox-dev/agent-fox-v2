"""Unit tests for steering document initialization (Spec 64).

Tests _ensure_steering_md(), _STEERING_PLACEHOLDER, and template references.

Test Spec: TS-64-1, TS-64-2, TS-64-3, TS-64-4, TS-64-9, TS-64-10, TS-64-11,
           TS-64-E1
Requirements: 64-REQ-1.1, 64-REQ-1.2, 64-REQ-1.3, 64-REQ-1.4, 64-REQ-1.E1,
              64-REQ-3.1, 64-REQ-3.2, 64-REQ-4.1, 64-REQ-4.2, 64-REQ-5.1
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# TS-64-1: Init creates steering file when absent
# Requirement: 64-REQ-1.1
# ---------------------------------------------------------------------------


class TestInitCreatesSteeringFile:
    """TS-64-1: _ensure_steering_md() creates the file when absent."""

    def test_returns_created(self, tmp_path: Path) -> None:
        """Return value is 'created' when file does not exist."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        result = _ensure_steering_md(tmp_path)
        assert result == "created"

    def test_file_exists_after_call(self, tmp_path: Path) -> None:
        """steering.md exists after _ensure_steering_md() is called."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        _ensure_steering_md(tmp_path)
        steering_path = tmp_path / ".specs" / "steering.md"
        assert steering_path.exists()

    def test_file_contains_sentinel(self, tmp_path: Path) -> None:
        """Created file contains the sentinel marker."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        _ensure_steering_md(tmp_path)
        content = (tmp_path / ".specs" / "steering.md").read_text()
        assert "<!-- steering:placeholder -->" in content


# ---------------------------------------------------------------------------
# TS-64-2: Init skips existing steering file
# Requirement: 64-REQ-1.2
# ---------------------------------------------------------------------------


class TestInitSkipsExistingSteeringFile:
    """TS-64-2: _ensure_steering_md() does not overwrite an existing file."""

    def test_returns_skipped(self, tmp_path: Path) -> None:
        """Return value is 'skipped' when file already exists."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        (specs_dir / "steering.md").write_text("my directives")

        result = _ensure_steering_md(tmp_path)
        assert result == "skipped"

    def test_file_content_unchanged(self, tmp_path: Path) -> None:
        """Existing file content is left unchanged."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()
        steering_path = specs_dir / "steering.md"
        steering_path.write_text("my directives")

        _ensure_steering_md(tmp_path)
        assert steering_path.read_text() == "my directives"


# ---------------------------------------------------------------------------
# TS-64-3: Placeholder contains sentinel and instructional comments
# Requirement: 64-REQ-1.3
# ---------------------------------------------------------------------------


class TestPlaceholderContainsSentinelAndComments:
    """TS-64-3: Placeholder content contains sentinel and HTML comments."""

    def test_placeholder_has_sentinel(self, tmp_path: Path) -> None:
        """Placeholder file contains the sentinel marker."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        _ensure_steering_md(tmp_path)
        content = (tmp_path / ".specs" / "steering.md").read_text()
        assert "<!-- steering:placeholder -->" in content

    def test_placeholder_has_html_comments(self, tmp_path: Path) -> None:
        """Placeholder file contains HTML comment blocks."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        _ensure_steering_md(tmp_path)
        content = (tmp_path / ".specs" / "steering.md").read_text()
        assert "<!--" in content

    def test_placeholder_treated_as_no_directives(self, tmp_path: Path) -> None:
        """load_steering() returns None for the placeholder file."""
        from agent_fox.workspace.init_project import _ensure_steering_md
        from agent_fox.session.prompt import load_steering

        _ensure_steering_md(tmp_path)
        result = load_steering(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# TS-64-4: Init creates .specs directory if needed
# Requirement: 64-REQ-1.4
# ---------------------------------------------------------------------------


class TestInitCreatesSpecsDirectory:
    """TS-64-4: _ensure_steering_md() creates .specs/ when absent."""

    def test_specs_dir_created(self, tmp_path: Path) -> None:
        """The .specs/ directory is created when absent."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        assert not (tmp_path / ".specs").exists()
        _ensure_steering_md(tmp_path)
        assert (tmp_path / ".specs").is_dir()

    def test_steering_md_created_inside_specs(self, tmp_path: Path) -> None:
        """steering.md is created inside the .specs/ directory."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        _ensure_steering_md(tmp_path)
        assert (tmp_path / ".specs" / "steering.md").exists()


# ---------------------------------------------------------------------------
# TS-64-9: Skill templates contain steering reference
# Requirements: 64-REQ-3.1, 64-REQ-3.2
# ---------------------------------------------------------------------------


class TestSkillTemplatesReferenceSteeringMd:
    """TS-64-9: Every bundled skill template references .specs/steering.md."""

    def test_skill_templates_reference_steering(self) -> None:
        """All skill templates contain a reference to .specs/steering.md."""
        templates_dir = Path(__file__).parents[3] / "agent_fox" / "_templates" / "skills"
        assert templates_dir.is_dir(), f"Skills directory not found: {templates_dir}"

        skill_files = [f for f in templates_dir.iterdir() if not f.name.startswith(".")]
        assert skill_files, "No skill templates found"

        missing = []
        for skill_file in skill_files:
            content = skill_file.read_text(encoding="utf-8")
            if ".specs/steering.md" not in content:
                missing.append(skill_file.name)

        assert not missing, f"Skill templates missing steering.md reference: {missing}"


# ---------------------------------------------------------------------------
# TS-64-10: AGENTS.md template contains steering reference
# Requirements: 64-REQ-4.1, 64-REQ-4.2
# ---------------------------------------------------------------------------


class TestAgentsMdTemplateReferencesSteeringMd:
    """TS-64-10: AGENTS.md template references steering.md in orientation section."""

    def test_agents_md_template_references_steering(self) -> None:
        """AGENTS.md template contains a reference to .specs/steering.md."""
        agents_md_path = Path(__file__).parents[3] / "agent_fox" / "_templates" / "agents_md.md"
        assert agents_md_path.exists(), f"agents_md.md not found at {agents_md_path}"
        content = agents_md_path.read_text(encoding="utf-8")
        assert ".specs/steering.md" in content

    def test_steering_reference_position_in_agents_md(self) -> None:
        """steering.md reference after README.md and before 'Explore the codebase'."""
        agents_md_path = Path(__file__).parents[3] / "agent_fox" / "_templates" / "agents_md.md"
        content = agents_md_path.read_text(encoding="utf-8")
        assert ".specs/steering.md" in content, "steering.md not referenced in agents_md.md"
        assert "README.md" in content, "README.md not in agents_md.md"
        assert "Explore the codebase" in content, "'Explore the codebase' not in agents_md.md"

        readme_pos = content.index("README.md")
        steering_pos = content.index(".specs/steering.md")
        explore_pos = content.index("Explore the codebase")
        assert readme_pos < steering_pos < explore_pos, (
            f"Expected README.md ({readme_pos}) < steering.md ({steering_pos}) < 'Explore the codebase' ({explore_pos})"
        )


# ---------------------------------------------------------------------------
# TS-64-11: Sentinel marker present in placeholder constant
# Requirement: 64-REQ-5.1
# ---------------------------------------------------------------------------


class TestSentinelMarkerInPlaceholderConstant:
    """TS-64-11: _STEERING_PLACEHOLDER constant contains the sentinel marker."""

    def test_sentinel_in_placeholder_constant(self) -> None:
        """The _STEERING_PLACEHOLDER constant contains the sentinel string."""
        from agent_fox.workspace.init_project import _STEERING_PLACEHOLDER

        assert "<!-- steering:placeholder -->" in _STEERING_PLACEHOLDER


# ---------------------------------------------------------------------------
# TS-64-E1: Permission error creating .specs directory
# Requirement: 64-REQ-1.E1
# ---------------------------------------------------------------------------


class TestPermissionErrorCreatingSpecsDir:
    """TS-64-E1: Init handles permission errors gracefully."""

    def test_returns_skipped_on_oserror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No exception raised when mkdir raises OSError; returns 'skipped'."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        original_mkdir = Path.mkdir

        def failing_mkdir(self, *args, **kwargs):
            if self == tmp_path / ".specs":
                raise OSError("permission denied")
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", failing_mkdir)

        with caplog.at_level(logging.WARNING):
            result = _ensure_steering_md(tmp_path)

        assert result == "skipped"

    def test_logs_warning_on_oserror(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A warning is logged when .specs/ cannot be created."""
        from agent_fox.workspace.init_project import _ensure_steering_md

        original_mkdir = Path.mkdir

        def failing_mkdir(self, *args, **kwargs):
            if self == tmp_path / ".specs":
                raise OSError("permission denied")
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", failing_mkdir)

        with caplog.at_level(logging.WARNING):
            _ensure_steering_md(tmp_path)

        assert any(record.levelno >= logging.WARNING for record in caplog.records), "Expected a warning to be logged"
