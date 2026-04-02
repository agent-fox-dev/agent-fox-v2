"""Property-based tests for skill installation (Spec 47).

Requirements: 47-REQ-1.1, 47-REQ-1.2, 47-REQ-1.3, 47-REQ-2.1, 47-REQ-2.3,
              47-REQ-2.5, 47-REQ-3.1
Design Properties: 1 (Template Completeness), 2 (Installation Bijection),
                   5 (Count Accuracy)
Test Spec: TS-47-P1, TS-47-P2, TS-47-P3
"""

from __future__ import annotations

from pathlib import Path

import yaml

import agent_fox
from agent_fox.workspace.init_project import _install_skills

# Path to bundled skill templates
_SKILLS_DIR = Path(agent_fox.__file__).parent / "_templates" / "skills"


# ---------------------------------------------------------------------------
# TS-47-P1: Bundled templates have valid frontmatter
# ---------------------------------------------------------------------------


class TestBundledTemplatesHaveValidFrontmatter:
    """TS-47-P1: Every bundled skill template has valid YAML frontmatter.

    Property 1 from design.md — Template Completeness.
    Validates: 47-REQ-1.1, 47-REQ-1.2, 47-REQ-1.3
    """

    def test_all_templates_have_frontmatter(self) -> None:
        """Each template starts with --- and has name + description fields."""
        assert _SKILLS_DIR.exists(), f"Skills dir not found: {_SKILLS_DIR}"

        templates = [
            f
            for f in _SKILLS_DIR.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ]
        assert len(templates) > 0, "No bundled skill templates found"

        for template_path in templates:
            content = template_path.read_text(encoding="utf-8")

            # Must start with ---
            assert content.startswith("---"), (
                f"{template_path.name}: does not start with '---'"
            )

            # Extract frontmatter between first and second ---
            parts = content.split("---", 2)
            assert len(parts) >= 3, (
                f"{template_path.name}: missing closing '---' delimiter"
            )

            frontmatter_text = parts[1].strip()
            frontmatter = yaml.safe_load(frontmatter_text)
            assert isinstance(frontmatter, dict), (
                f"{template_path.name}: frontmatter is not a YAML mapping"
            )

            # name field must exist and match filename
            assert "name" in frontmatter, (
                f"{template_path.name}: missing 'name' field in frontmatter"
            )
            assert frontmatter["name"] == template_path.name, (
                f"{template_path.name}: name field '{frontmatter['name']}' "
                f"does not match filename"
            )

            # description field must exist
            assert "description" in frontmatter, (
                f"{template_path.name}: missing 'description' field in frontmatter"
            )


# ---------------------------------------------------------------------------
# TS-47-P2: Installation bijection
# ---------------------------------------------------------------------------


class TestInstallationBijection:
    """TS-47-P2: _install_skills() produces exactly one SKILL.md per template.

    Property 2 from design.md — Installation Bijection.
    Validates: 47-REQ-2.1, 47-REQ-2.3
    """

    def test_one_skill_per_template_byte_identical(self, tmp_path: Path) -> None:
        """Installed skill set matches template set, content byte-identical."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)

        skills_dir = project_root / ".claude" / "skills"
        templates = {
            f.name
            for f in _SKILLS_DIR.iterdir()
            if f.is_file() and not f.name.startswith(".")
        }
        installed = {d.name for d in skills_dir.iterdir() if d.is_dir()}

        assert installed == templates
        assert count == len(templates)

        for name in templates:
            installed_content = (skills_dir / name / "SKILL.md").read_bytes()
            template_content = (_SKILLS_DIR / name).read_bytes()
            assert installed_content == template_content, (
                f"Installed {name}/SKILL.md differs from template"
            )


# ---------------------------------------------------------------------------
# TS-47-P3: Count accuracy
# ---------------------------------------------------------------------------


class TestCountAccuracy:
    """TS-47-P3: Return value equals number of SKILL.md files written.

    Property 5 from design.md — Count Accuracy.
    Validates: 47-REQ-2.5, 47-REQ-3.1
    """

    def test_return_value_matches_files_written(self, tmp_path: Path) -> None:
        """Integer returned equals count of SKILL.md files under .claude/skills/."""
        project_root = tmp_path / "project"
        project_root.mkdir()

        count = _install_skills(project_root)

        skills_dir = project_root / ".claude" / "skills"
        written = sum(1 for d in skills_dir.iterdir() if (d / "SKILL.md").exists())
        assert count == written
