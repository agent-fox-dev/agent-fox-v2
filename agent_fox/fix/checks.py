"""Quality check detection and failure collection.

Inspects project configuration files to detect available quality checks,
runs them as subprocesses, and parses failures into structured records.

Requirements: 08-REQ-1.1, 08-REQ-1.2, 08-REQ-1.3, 08-REQ-1.E2,
              08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3, 08-REQ-2.E1
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

SUBPROCESS_TIMEOUT = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Check detection (merged from detector.py)
# ---------------------------------------------------------------------------


class CheckCategory(StrEnum):
    """Category of a quality check."""

    TEST = "test"
    LINT = "lint"
    TYPE = "type"
    BUILD = "build"


@dataclass(frozen=True)
class CheckDescriptor:
    """A detected quality check."""

    name: str  # Human-readable name, e.g. "pytest"
    command: list[str]  # Shell command, e.g. ["uv", "run", "pytest"]
    category: CheckCategory  # Check category


def detect_checks(project_root: Path) -> list[CheckDescriptor]:
    """Inspect project configuration files and return detected checks.

    Detection rules:
    - pyproject.toml [tool.pytest] or [tool.pytest.ini_options] -> pytest
    - pyproject.toml [tool.ruff] -> ruff
    - pyproject.toml [tool.mypy] -> mypy
    - package.json scripts.test -> npm test
    - package.json scripts.lint -> npm lint
    - Makefile with 'test' target -> make test
    - Cargo.toml [package] -> cargo test

    Returns an empty list if no checks are found. The caller is responsible
    for raising an error in that case.
    """
    checks: list[CheckDescriptor] = []

    # Inspect each config file if it exists
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        checks.extend(_inspect_pyproject(pyproject_path))

    package_json_path = project_root / "package.json"
    if package_json_path.exists():
        checks.extend(_inspect_package_json(package_json_path))

    makefile_path = project_root / "Makefile"
    if makefile_path.exists():
        checks.extend(_inspect_makefile(makefile_path))

    cargo_toml_path = project_root / "Cargo.toml"
    if cargo_toml_path.exists():
        checks.extend(_inspect_cargo_toml(cargo_toml_path))

    return checks


def _inspect_pyproject(path: Path) -> list[CheckDescriptor]:
    """Parse pyproject.toml for pytest, ruff, mypy sections."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        logger.warning("Skipping unparseable %s: %s", path, exc)
        return []

    checks: list[CheckDescriptor] = []
    tool = data.get("tool", {})

    # pytest: [tool.pytest] or [tool.pytest.ini_options]
    # tomllib parses [tool.pytest.ini_options] as nested dict:
    # tool -> pytest -> ini_options
    pytest_section = tool.get("pytest", {})
    has_pytest = "pytest" in tool
    has_ini_options = (
        isinstance(pytest_section, dict) and "ini_options" in pytest_section
    )

    if has_pytest or has_ini_options:
        checks.append(
            CheckDescriptor(
                name="pytest",
                command=["uv", "run", "pytest"],
                category=CheckCategory.TEST,
            )
        )

    # ruff: [tool.ruff]
    if "ruff" in tool:
        checks.append(
            CheckDescriptor(
                name="ruff",
                command=["uv", "run", "ruff", "check", "."],
                category=CheckCategory.LINT,
            )
        )

    # mypy: [tool.mypy]
    if "mypy" in tool:
        checks.append(
            CheckDescriptor(
                name="mypy",
                command=["uv", "run", "mypy", "."],
                category=CheckCategory.TYPE,
            )
        )

    return checks


def _inspect_package_json(path: Path) -> list[CheckDescriptor]:
    """Parse package.json for test and lint scripts."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Skipping unparseable %s: %s", path, exc)
        return []

    checks: list[CheckDescriptor] = []
    scripts = data.get("scripts", {})

    if "test" in scripts:
        checks.append(
            CheckDescriptor(
                name="npm test",
                command=["npm", "test"],
                category=CheckCategory.TEST,
            )
        )

    if "lint" in scripts:
        checks.append(
            CheckDescriptor(
                name="npm lint",
                command=["npm", "run", "lint"],
                category=CheckCategory.LINT,
            )
        )

    return checks


def _inspect_makefile(path: Path) -> list[CheckDescriptor]:
    """Scan Makefile for a 'test' target."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Skipping unreadable %s: %s", path, exc)
        return []

    # Match lines starting with 'test:' (a Makefile target)
    if re.search(r"^test:", content, re.MULTILINE):
        return [
            CheckDescriptor(
                name="make test",
                command=["make", "test"],
                category=CheckCategory.TEST,
            )
        ]

    return []


def _inspect_cargo_toml(path: Path) -> list[CheckDescriptor]:
    """Parse Cargo.toml for [package] section."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        logger.warning("Skipping unparseable %s: %s", path, exc)
        return []

    if "package" in data:
        return [
            CheckDescriptor(
                name="cargo test",
                command=["cargo", "test"],
                category=CheckCategory.TEST,
            )
        ]

    return []


# ---------------------------------------------------------------------------
# Failure collection (merged from collector.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureRecord:
    """A structured failure from a quality check."""

    check: CheckDescriptor  # Which check produced this failure
    output: str  # Combined stdout + stderr
    exit_code: int  # Process exit code


def run_checks(
    checks: list[CheckDescriptor],
    project_root: Path,
) -> tuple[list[FailureRecord], list[CheckDescriptor]]:
    """Run all check commands and return (failures, passed_checks).

    Each check is run as a subprocess with a 5-minute timeout.
    Commands that exit 0 are considered passing.
    Commands that exit non-zero produce a FailureRecord.
    Commands that time out produce a FailureRecord with a timeout message.

    Returns a tuple of (failure_records, checks_that_passed).
    """
    failures: list[FailureRecord] = []
    passed: list[CheckDescriptor] = []

    for check in checks:
        try:
            result = subprocess.run(
                check.command,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                cwd=project_root,
            )

            if result.returncode == 0:
                passed.append(check)
            else:
                # Combine stdout and stderr for the failure output
                output = result.stdout + result.stderr
                failures.append(
                    FailureRecord(
                        check=check,
                        output=output,
                        exit_code=result.returncode,
                    )
                )

        except subprocess.TimeoutExpired:
            logger.warning(
                "Check '%s' timed out after %d seconds",
                check.name,
                SUBPROCESS_TIMEOUT,
            )
            failures.append(
                FailureRecord(
                    check=check,
                    output=f"Timeout: check '{check.name}' exceeded "
                    f"{SUBPROCESS_TIMEOUT} second limit",
                    exit_code=-1,
                )
            )

    return failures, passed
