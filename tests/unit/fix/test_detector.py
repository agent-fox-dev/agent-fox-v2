"""Detector tests.

Test Spec: TS-08-1 (pytest detection), TS-08-2 (ruff+mypy detection),
           TS-08-3 (npm test+lint detection), TS-08-4 (make test detection),
           TS-08-5 (cargo test detection)
Edge Cases: TS-08-E1 (no checks), TS-08-E2 (unparseable config)
Requirements: 08-REQ-1.1, 08-REQ-1.2, 08-REQ-1.3, 08-REQ-1.E1, 08-REQ-1.E2
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_fox.fix.detector import CheckCategory, detect_checks


class TestDetectPytestFromPyprojectToml:
    """TS-08-1: Detect pytest from pyproject.toml.

    Requirement: 08-REQ-1.1, 08-REQ-1.2
    """

    def test_detects_pytest_ini_options(self, tmp_project: Path) -> None:
        """Detector finds pytest when pyproject.toml has [tool.pytest.ini_options]."""
        pyproject = tmp_project / "pyproject.toml"
        pyproject.write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )

        checks = detect_checks(tmp_project)

        pytest_checks = [c for c in checks if c.name == "pytest"]
        assert len(pytest_checks) == 1
        assert pytest_checks[0].command == ["uv", "run", "pytest"]
        assert pytest_checks[0].category == CheckCategory.TEST

    def test_detects_pytest_tool_section(self, tmp_project: Path) -> None:
        """Detector finds pytest when pyproject.toml has [tool.pytest]."""
        pyproject = tmp_project / "pyproject.toml"
        pyproject.write_text("[tool.pytest]\n")

        checks = detect_checks(tmp_project)

        pytest_checks = [c for c in checks if c.name == "pytest"]
        assert len(pytest_checks) == 1
        assert pytest_checks[0].category == CheckCategory.TEST


class TestDetectRuffAndMypyFromPyprojectToml:
    """TS-08-2: Detect ruff and mypy from pyproject.toml.

    Requirement: 08-REQ-1.2, 08-REQ-1.3
    """

    def test_detects_ruff_and_mypy(self, tmp_project: Path) -> None:
        """Detector finds ruff (LINT) and mypy (TYPE) from their tool sections."""
        pyproject = tmp_project / "pyproject.toml"
        pyproject.write_text("[tool.ruff]\n\n[tool.mypy]\n")

        checks = detect_checks(tmp_project)

        names = {c.name for c in checks}
        assert "ruff" in names
        assert "mypy" in names

        ruff = next(c for c in checks if c.name == "ruff")
        assert ruff.command == ["uv", "run", "ruff", "check", "."]
        assert ruff.category == CheckCategory.LINT

        mypy = next(c for c in checks if c.name == "mypy")
        assert mypy.command == ["uv", "run", "mypy", "."]
        assert mypy.category == CheckCategory.TYPE


class TestDetectNpmTestAndLintFromPackageJson:
    """TS-08-3: Detect npm test and lint from package.json.

    Requirement: 08-REQ-1.2
    """

    def test_detects_npm_test_and_lint(self, tmp_project: Path) -> None:
        """Detector finds npm test and lint scripts from package.json."""
        package_json = tmp_project / "package.json"
        package_json.write_text(
            json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}})
        )

        checks = detect_checks(tmp_project)

        names = {c.name for c in checks}
        assert "npm test" in names
        assert "npm lint" in names

        npm_test = next(c for c in checks if c.name == "npm test")
        assert npm_test.command == ["npm", "test"]
        assert npm_test.category == CheckCategory.TEST

        npm_lint = next(c for c in checks if c.name == "npm lint")
        assert npm_lint.command == ["npm", "run", "lint"]
        assert npm_lint.category == CheckCategory.LINT


class TestDetectMakeTestFromMakefile:
    """TS-08-4: Detect make test from Makefile.

    Requirement: 08-REQ-1.2
    """

    def test_detects_make_test(self, tmp_project: Path) -> None:
        """Detector finds make test when Makefile contains a test target."""
        makefile = tmp_project / "Makefile"
        makefile.write_text("test:\n\tpytest\n")

        checks = detect_checks(tmp_project)

        make_checks = [c for c in checks if c.name == "make test"]
        assert len(make_checks) == 1
        assert make_checks[0].command == ["make", "test"]
        assert make_checks[0].category == CheckCategory.TEST


class TestDetectCargoTestFromCargoToml:
    """TS-08-5: Detect cargo test from Cargo.toml.

    Requirement: 08-REQ-1.2
    """

    def test_detects_cargo_test(self, tmp_project: Path) -> None:
        """Detector finds cargo test when Cargo.toml has [package] section."""
        cargo_toml = tmp_project / "Cargo.toml"
        cargo_toml.write_text('[package]\nname = "myproject"\n')

        checks = detect_checks(tmp_project)

        cargo_checks = [c for c in checks if c.name == "cargo test"]
        assert len(cargo_checks) == 1
        assert cargo_checks[0].command == ["cargo", "test"]
        assert cargo_checks[0].category == CheckCategory.TEST


# -- Edge case tests ---------------------------------------------------------


class TestNoQualityChecksDetected:
    """TS-08-E1: No quality checks detected.

    Requirement: 08-REQ-1.E1
    """

    def test_empty_directory_returns_no_checks(self, tmp_project: Path) -> None:
        """An empty directory produces no check descriptors."""
        checks = detect_checks(tmp_project)
        assert len(checks) == 0


class TestUnparseableConfigFile:
    """TS-08-E2: Unparseable config file.

    Requirement: 08-REQ-1.E2
    """

    def test_invalid_toml_skipped_other_files_detected(
        self, tmp_project: Path,
    ) -> None:
        """Invalid pyproject.toml is skipped; valid package.json still detected."""
        # Write invalid TOML
        pyproject = tmp_project / "pyproject.toml"
        pyproject.write_text("this is not valid [[[toml")

        # Write valid package.json with test script
        package_json = tmp_project / "package.json"
        package_json.write_text(json.dumps({"scripts": {"test": "jest"}}))

        checks = detect_checks(tmp_project)

        assert len(checks) >= 1
        names = {c.name for c in checks}
        assert "npm test" in names
        # pyproject-based checks are absent due to parse error

    def test_invalid_json_skipped(self, tmp_project: Path) -> None:
        """Invalid package.json is skipped without raising."""
        package_json = tmp_project / "package.json"
        package_json.write_text("{not valid json")

        # Should not raise
        checks = detect_checks(tmp_project)
        # No npm checks detected due to parse error
        npm_checks = [c for c in checks if "npm" in c.name]
        assert len(npm_checks) == 0
