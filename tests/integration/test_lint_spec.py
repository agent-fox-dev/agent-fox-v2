"""Integration tests for the lint-specs CLI command.

Test Spec: TS-09-E1, TS-09-E2, TS-09-E4, TS-09-E5, TS-09-E6,
           TS-09-E7, TS-09-E8
Requirements: 09-REQ-1.E1, 09-REQ-9.1, 09-REQ-9.2, 09-REQ-9.3,
              09-REQ-9.4, 09-REQ-9.5, 09-REQ-6.1
Fixes: #118
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_fox.cli.app import main

# -- Fixtures ------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "specs"


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


def _create_spec_with_tasks(
    specs_dir: Path,
    name: str,
    *,
    all_completed: bool = False,
) -> Path:
    """Create a minimal spec directory with a tasks.md file.

    If all_completed is True, all task group checkboxes are [x].
    Otherwise, at least one is [ ].
    """
    spec_dir = specs_dir / name
    spec_dir.mkdir(exist_ok=True)
    for filename in ["prd.md", "requirements.md", "design.md", "test_spec.md"]:
        (spec_dir / filename).write_text(f"# {filename}\n")
    (spec_dir / "requirements.md").write_text(
        f"# Requirements\n\n## Introduction\n\nTest.\n\n## Glossary\n\nNone.\n\n"
        f"### Requirement 1: Thing\n\n"
        f"1. [{name[:2]}-REQ-1.1] THE system SHALL do thing.\n"
    )
    (spec_dir / "test_spec.md").write_text(
        f"# Test Spec\n\n**Requirement:** {name[:2]}-REQ-1.1\n\n"
        f"## Coverage Matrix\n\n"
        f"| Requirement | Test Spec Entry | Type |\n"
        f"|-------------|-----------------|------|\n"
        f"| {name[:2]}-REQ-1.1 | TS-{name[:2]}-1 | unit |\n"
    )
    (spec_dir / "design.md").write_text(
        "# Design\n\n## Overview\n\nTest.\n\n## Architecture\n\nNone.\n\n"
        "## Correctness Properties\n\n### Property 1: Test\n\nTest.\n\n"
        "## Error Handling\n\n| Error | Behavior | Requirement |\n"
        "|-------|----------|-------------|\n\n"
        "## Definition of Done\n\nDone.\n"
    )
    cb1 = "x" if all_completed else " "
    cb2 = "x" if all_completed else " "
    (spec_dir / "tasks.md").write_text(
        f"# Tasks\n\n## Traceability\n\n"
        f"| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |\n"
        f"|-------------|-----------------|---------------------|------------------|\n"
        f"| {name[:2]}-REQ-1.1 | TS-{name[:2]}-1 | 1.1 | test_thing |\n\n"
        f"## Tasks\n\n"
        f"- [{cb1}] 1. Write tests\n"
        f"  - [{cb1}] 1.1 Test thing\n"
        f"  - [{cb1}] 1.V Verify\n\n"
        f"- [{cb2}] 2. Implement\n"
        f"  - [{cb2}] 2.1 Do thing\n"
        f"  - [{cb2}] 2.V Verify\n"
    )
    return spec_dir


def _setup_project_with_specs(
    project_dir: Path,
    spec_fixtures: list[str],
) -> None:
    """Create a minimal project with selected fixture specs.

    Creates .agent-fox/config.toml and copies fixture spec directories
    into .specs/ with NN_ prefixes.
    """
    # Create config directory
    agent_fox_dir = project_dir / ".agent-fox"
    agent_fox_dir.mkdir(exist_ok=True)
    (agent_fox_dir / "config.toml").write_text("")

    # Create .specs/ directory and copy fixtures
    specs_dir = project_dir / ".specs"
    specs_dir.mkdir(exist_ok=True)

    for i, fixture_name in enumerate(spec_fixtures, start=1):
        src = FIXTURES_DIR / fixture_name
        dst = specs_dir / f"{i:02d}_{fixture_name}"
        if src.exists():
            shutil.copytree(src, dst)


# -- TS-09-E1: No specs directory ----------------------------------------------


class TestNoSpecsDirectory:
    """TS-09-E1: No specs directory.

    Requirements: 09-REQ-1.E1, 09-REQ-9.4
    Verify lint-specs reports error when .specs/ does not exist.
    """

    def test_exits_with_code_one(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """lint-specs exits with code 1 when no .specs/ directory."""
        # Create minimal project without .specs/
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "config.toml").write_text("")

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            assert result.exit_code == 1
        finally:
            os.chdir(original_dir)

    def test_output_indicates_no_specs(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """lint-specs output mentions no specifications found."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "config.toml").write_text("")

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            output_lower = result.output.lower()
            assert "no specifications" in output_lower or "error" in output_lower
        finally:
            os.chdir(original_dir)


# -- TS-09-E2: Empty specs directory -------------------------------------------


class TestEmptySpecsDirectory:
    """TS-09-E2: Empty specs directory.

    Requirements: 09-REQ-1.E1, 09-REQ-9.4
    Verify lint-specs reports error when .specs/ exists but is empty.
    """

    def test_exits_with_code_one(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """lint-specs exits with code 1 when .specs/ is empty."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "config.toml").write_text("")
        (tmp_path / ".specs").mkdir()

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            assert result.exit_code == 1
        finally:
            os.chdir(original_dir)


# -- TS-09-E4: JSON output format ---------------------------------------------


class TestJsonOutputFormat:
    """TS-09-E4: JSON output format.

    Requirements: 09-REQ-9.1, 09-REQ-9.3
    Verify --json produces valid JSON with correct structure.
    """

    def test_json_output_is_valid(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """--json produces valid JSON output."""
        _setup_project_with_specs(tmp_path, ["incomplete_spec"])

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs"])
            data = json.loads(result.output)
            assert "findings" in data
            assert "summary" in data
        finally:
            os.chdir(original_dir)

    def test_json_summary_counts_match(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """JSON summary total matches number of findings."""
        _setup_project_with_specs(tmp_path, ["incomplete_spec"])

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs"])
            data = json.loads(result.output)
            assert data["summary"]["total"] == len(data["findings"])
        finally:
            os.chdir(original_dir)


# -- TS-09-E6: Table output includes summary line -----------------------------


class TestTableOutputSummary:
    """TS-09-E6: Table output includes summary line.

    Requirements: 09-REQ-9.2
    Verify table output includes summary with severity counts.
    """

    def test_table_output_contains_error_text(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Table output contains 'error' severity text."""
        _setup_project_with_specs(tmp_path, ["incomplete_spec"])

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            assert "error" in result.output.lower()
        finally:
            os.chdir(original_dir)


# -- TS-09-E7: Exit code 0 when only warnings ---------------------------------


class TestExitCodeZeroWarningsOnly:
    """TS-09-E7: Exit code 0 when only warnings.

    Requirements: 09-REQ-9.4, 09-REQ-9.5
    Verify exit code is 0 when only Warning/Hint findings exist.
    """

    def test_warnings_only_exits_zero(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """lint-specs exits with code 0 when only warnings are present."""
        _setup_project_with_specs(tmp_path, ["warnings_only_spec"])

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            assert result.exit_code == 0
        finally:
            os.chdir(original_dir)


# -- TS-09-E8: Valid dependencies produce no findings --------------------------


class TestValidDependenciesIntegration:
    """TS-09-E8: Valid dependencies produce no findings.

    Requirements: 09-REQ-6.1
    Verify valid dependency references don't produce error findings.
    """

    def test_valid_deps_no_error_findings(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Valid dependency references produce no broken-dependency findings."""
        # Create a project with two specs: one that depends on the other
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir()
        (agent_fox_dir / "config.toml").write_text("")

        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir()

        # Create target spec (01_core_foundation) with all files
        target = specs_dir / "01_core_foundation"
        target.mkdir()
        for filename in [
            "prd.md",
            "requirements.md",
            "design.md",
            "test_spec.md",
            "tasks.md",
        ]:
            (target / filename).write_text(f"# {filename}\n")
        (target / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n  - [ ] 1.V Verify\n")
        (target / "requirements.md").write_text(
            "# Requirements\n\n### Requirement 1: Thing\n\n1. [01-REQ-1.1] Must do thing.\n"
        )
        (target / "test_spec.md").write_text("# Test Spec\n\n**Requirement:** 01-REQ-1.1\n")

        # Create referencing spec (02_dependent) with valid dep
        referencing = specs_dir / "02_dependent"
        referencing.mkdir()
        for filename in ["requirements.md", "design.md", "test_spec.md", "tasks.md"]:
            (referencing / filename).write_text(f"# {filename}\n")
        (referencing / "prd.md").write_text(
            "# PRD\n\n## Dependencies\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_dependent | 01_core_foundation | Types |\n"
        )
        (referencing / "tasks.md").write_text("# Tasks\n\n- [ ] 1. Task\n  - [ ] 1.1 Sub\n  - [ ] 1.V Verify\n")
        (referencing / "requirements.md").write_text(
            "# Requirements\n\n### Requirement 1: Feature\n\n1. [02-REQ-1.1] Must do feature.\n"
        )
        (referencing / "test_spec.md").write_text("# Test Spec\n\n**Requirement:** 02-REQ-1.1\n")

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs"])
            data = json.loads(result.output)
            broken_deps = [f for f in data["findings"] if f["rule"] == "broken-dependency"]
            assert len(broken_deps) == 0
        finally:
            os.chdir(original_dir)


# -- Issue #118: --all flag skips implemented specs ---------------------------


class TestAllFlagDefaultSkipsImplemented:
    """Issue #118: Default behavior skips fully-implemented specs.

    Verify that lint-specs only lints specs with incomplete tasks by default,
    and --all includes all specs.
    """

    def _setup_mixed_project(self, tmp_path: Path) -> None:
        """Create a project with one implemented and one incomplete spec."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir(exist_ok=True)
        (agent_fox_dir / "config.toml").write_text("")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(exist_ok=True)
        _create_spec_with_tasks(specs_dir, "01_done_spec", all_completed=True)
        _create_spec_with_tasks(specs_dir, "02_wip_spec", all_completed=False)

    def test_default_skips_implemented_spec(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Default lint-specs does not report findings for completed specs."""
        self._setup_mixed_project(tmp_path)
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs"])
            data = json.loads(result.output)
            spec_names = {f["spec_name"] for f in data["findings"]}
            assert "01_done_spec" not in spec_names
            assert "02_wip_spec" in spec_names
        finally:
            os.chdir(original_dir)

    def test_all_flag_includes_implemented_spec(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """--all includes findings for completed specs."""
        self._setup_mixed_project(tmp_path)
        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs", "--all"])
            data = json.loads(result.output)
            spec_names = {f["spec_name"] for f in data["findings"]}
            assert "01_done_spec" in spec_names
            assert "02_wip_spec" in spec_names
        finally:
            os.chdir(original_dir)

    def test_all_specs_implemented_shows_no_findings(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """When all specs are implemented, default lint reports no findings."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir(exist_ok=True)
        (agent_fox_dir / "config.toml").write_text("")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(exist_ok=True)
        _create_spec_with_tasks(specs_dir, "01_done", all_completed=True)

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["lint-specs"])
            assert "No findings" in result.output or result.exit_code == 0
        finally:
            os.chdir(original_dir)

    def test_archived_dep_not_flagged_as_broken(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Dependency on an archived spec does not produce broken-dependency."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir(exist_ok=True)
        (agent_fox_dir / "config.toml").write_text("")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(exist_ok=True)

        # Create an archived spec with tasks
        archive_dir = specs_dir / "archive"
        archive_dir.mkdir()
        archived = archive_dir / "01_archived_dep"
        archived.mkdir()
        for f in ["prd.md", "requirements.md", "design.md", "test_spec.md"]:
            (archived / f).write_text(f"# {f}\n")
        (archived / "tasks.md").write_text(
            "# Tasks\n\n- [x] 1. Task\n  - [x] 1.1 Sub\n  - [x] 1.V Verify\n"
        )

        # Create an active spec that depends on the archived one
        _create_spec_with_tasks(specs_dir, "02_active_spec", all_completed=False)
        (specs_dir / "02_active_spec" / "prd.md").write_text(
            "# PRD\n\n## Dependencies\n\n"
            "| This Spec | Depends On | What It Uses |\n"
            "|-----------|-----------|---------------|\n"
            "| 02_active_spec | 01_archived_dep | Archived types |\n"
        )

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = cli_runner.invoke(main, ["--json", "lint-specs"])
            data = json.loads(result.output)
            broken = [f for f in data["findings"] if f["rule"] == "broken-dependency"]
            assert len(broken) == 0, f"Unexpected broken-dependency findings: {broken}"
        finally:
            os.chdir(original_dir)

    def test_spec_without_tasks_md_is_linted(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """A spec without tasks.md is considered not implemented and is linted."""
        agent_fox_dir = tmp_path / ".agent-fox"
        agent_fox_dir.mkdir(exist_ok=True)
        (agent_fox_dir / "config.toml").write_text("")
        specs_dir = tmp_path / ".specs"
        specs_dir.mkdir(exist_ok=True)

        # Create a spec with no tasks.md
        spec_dir = specs_dir / "01_no_tasks"
        spec_dir.mkdir()
        (spec_dir / "prd.md").write_text("# PRD\n")
        (spec_dir / "requirements.md").write_text("# Requirements\n")

        original_dir = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Use table mode — JSON mode can have log warnings mixed in
            result = cli_runner.invoke(main, ["lint-specs"])
            assert "01_no_tasks" in result.output
        finally:
            os.chdir(original_dir)
