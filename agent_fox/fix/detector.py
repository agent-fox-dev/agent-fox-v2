"""Quality check detection.

Inspects project configuration files (pyproject.toml, package.json, Makefile,
Cargo.toml) to detect available quality checks and return check descriptors.

Requirements: 08-REQ-1.1, 08-REQ-1.2, 08-REQ-1.3, 08-REQ-1.E2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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
    raise NotImplementedError


def _inspect_pyproject(path: Path) -> list[CheckDescriptor]:
    """Parse pyproject.toml for pytest, ruff, mypy sections."""
    raise NotImplementedError


def _inspect_package_json(path: Path) -> list[CheckDescriptor]:
    """Parse package.json for test and lint scripts."""
    raise NotImplementedError


def _inspect_makefile(path: Path) -> list[CheckDescriptor]:
    """Scan Makefile for a 'test' target."""
    raise NotImplementedError


def _inspect_cargo_toml(path: Path) -> list[CheckDescriptor]:
    """Parse Cargo.toml for [package] section."""
    raise NotImplementedError
