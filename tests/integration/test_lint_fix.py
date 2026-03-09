"""Integration tests for lint-spec --fix CLI flag.

Test Spec: TS-20-14 (CLI integration)
Requirements: 20-REQ-6.1, #115
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import CliRunner

from agent_fox.cli.app import main


def _setup_project_with_coarse_dep(project_dir: Path) -> None:
    """Create a project with a spec that has a coarse dependency."""
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    specs_dir = project_dir / ".specs"
    specs_dir.mkdir()

    # Upstream spec
    spec1 = specs_dir / "01_alpha"
    spec1.mkdir()
    for f in ["prd.md", "requirements.md", "design.md", "test_spec.md"]:
        (spec1 / f).write_text(f"# {f}\n")
    (spec1 / "tasks.md").write_text(
        "# Tasks\n\n"
        "- [ ] 1. Task\n"
        "  - [ ] 1.1 Sub\n"
        "  - [ ] 1.V Verify task group 1\n"
        "\n"
        "- [ ] 2. Task 2\n"
        "  - [ ] 2.1 Sub\n"
        "  - [ ] 2.V Verify task group 2\n"
    )
    (spec1 / "requirements.md").write_text(
        "# Requirements\n\n### Requirement 1: Thing\n\n1. [01-REQ-1.1] Must do thing.\n"
    )
    (spec1 / "test_spec.md").write_text("# Test Spec\n\n**Requirement:** 01-REQ-1.1\n")

    # Downstream spec with coarse dependency
    spec2 = specs_dir / "02_beta"
    spec2.mkdir()
    for f in ["requirements.md", "design.md", "test_spec.md"]:
        (spec2 / f).write_text(f"# {f}\n")
    (spec2 / "prd.md").write_text(
        "# PRD\n\n## Dependencies\n\n"
        "| This Spec | Depends On | What It Uses |\n"
        "|-----------|-----------|---------------|\n"
        "| 02_beta | 01_alpha | Core types |\n"
    )
    (spec2 / "tasks.md").write_text(
        "# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n  - [ ] 1.V Verify task group 1\n"
    )
    (spec2 / "requirements.md").write_text(
        "# Requirements\n\n### Requirement 1: Feature\n\n"
        "1. [02-REQ-1.1] Must do feature.\n"
    )
    (spec2 / "test_spec.md").write_text("# Test Spec\n\n**Requirement:** 02-REQ-1.1\n")


class TestLintSpecFix:
    """Verify lint-spec --fix rewrites files and re-validates."""

    def test_fix_exits_zero(self, tmp_path: Path) -> None:
        """lint-spec --fix exits without errors after fixing."""
        _setup_project_with_coarse_dep(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(main, ["lint-spec", "--fix"])
            assert result.exit_code == 0, (
                f"Exit code {result.exit_code}, output:\n{result.output}"
            )
        finally:
            os.chdir(original_dir)

    def test_fix_rewrites_prd(self, tmp_path: Path) -> None:
        """lint-spec --fix rewrites the coarse dependency table."""
        _setup_project_with_coarse_dep(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            runner.invoke(main, ["lint-spec", "--fix"])
            prd_content = (tmp_path / ".specs" / "02_beta" / "prd.md").read_text()
            assert "From Group" in prd_content
            assert "This Spec" not in prd_content
        finally:
            os.chdir(original_dir)

    def test_fix_no_coarse_finding_after(self, tmp_path: Path) -> None:
        """After --fix, coarse-dependency finding should be gone."""
        _setup_project_with_coarse_dep(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(main, ["--json", "lint-spec", "--fix"])
            # Fix summary goes to stderr; JSON findings go to stdout.
            # In Click's test runner, both may appear in result.output.
            # Extract just the JSON portion.
            output = result.output
            json_start = output.index("{")
            json_str = output[json_start:]
            data = json.loads(json_str)
            coarse = [f for f in data["findings"] if f["rule"] == "coarse-dependency"]
            assert len(coarse) == 0
        finally:
            os.chdir(original_dir)


def _setup_project_with_mixed_ids(project_dir: Path) -> None:
    """Create a project with a spec that has mixed req ID formats."""
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    specs_dir = project_dir / ".specs"
    specs_dir.mkdir()

    spec = specs_dir / "01_feature"
    spec.mkdir()
    (spec / "prd.md").write_text("# PRD\n")
    (spec / "design.md").write_text("# Design\n")
    (spec / "test_spec.md").write_text("# Test Spec\n\n**Requirement:** 01-REQ-1.1\n")
    (spec / "tasks.md").write_text(
        "# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n  - [ ] 1.V Verify task group 1\n"
    )
    (spec / "requirements.md").write_text(
        "# Requirements\n\n### Requirement 1: Feature\n\n"
        "1. [01-REQ-1.1] THE system SHALL do A.\n"
        "2. **01-REQ-1.2:** THE system SHALL do B.\n"
    )


class TestLintSpecFixRobustness:
    """Verify lint-spec --fix handles new robustness rules."""

    def test_fix_converts_bold_ids_to_bracket(self, tmp_path: Path) -> None:
        """--fix converts bold req IDs to bracket format."""
        _setup_project_with_mixed_ids(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            runner.invoke(main, ["lint-spec", "--fix"])
            req_text = (
                tmp_path / ".specs" / "01_feature" / "requirements.md"
            ).read_text()
            assert "[01-REQ-1.2]" in req_text
            assert "**01-REQ-1.2:**" not in req_text
        finally:
            os.chdir(original_dir)

    def test_fix_appends_dod_and_error_table(self, tmp_path: Path) -> None:
        """--fix appends DoD and Error Handling to minimal design.md."""
        _setup_project_with_mixed_ids(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            runner.invoke(main, ["lint-spec", "--fix"])
            design_text = (tmp_path / ".specs" / "01_feature" / "design.md").read_text()
            assert "## Definition of Done" in design_text
            assert "## Error Handling" in design_text
            assert "## Correctness Properties" in design_text
        finally:
            os.chdir(original_dir)

    def test_fix_removes_robustness_findings(self, tmp_path: Path) -> None:
        """After --fix, robustness findings should be resolved."""
        _setup_project_with_mixed_ids(tmp_path)
        runner = CliRunner()
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(main, ["--json", "lint-spec", "--fix"])
            output = result.output
            json_start = output.index("{")
            json_str = output[json_start:]
            data = json.loads(json_str)
            fixed_rules = {
                "inconsistent-req-id-format",
                "missing-definition-of-done",
                "missing-error-table",
                "missing-correctness-properties",
            }
            remaining = [f for f in data["findings"] if f["rule"] in fixed_rules]
            assert len(remaining) == 0
        finally:
            os.chdir(original_dir)
