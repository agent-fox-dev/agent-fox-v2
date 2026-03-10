"""Shared fixtures for fox tools unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "tools"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the tools fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_py(fixtures_dir: Path) -> Path:
    """Return path to the Python fixture file."""
    return fixtures_dir / "sample.py"


@pytest.fixture
def sample_js(fixtures_dir: Path) -> Path:
    """Return path to the JavaScript fixture file."""
    return fixtures_dir / "sample.js"


@pytest.fixture
def sample_ts(fixtures_dir: Path) -> Path:
    """Return path to the TypeScript fixture file."""
    return fixtures_dir / "sample.ts"


@pytest.fixture
def sample_rs(fixtures_dir: Path) -> Path:
    """Return path to the Rust fixture file."""
    return fixtures_dir / "sample.rs"


@pytest.fixture
def sample_go(fixtures_dir: Path) -> Path:
    """Return path to the Go fixture file."""
    return fixtures_dir / "sample.go"


@pytest.fixture
def sample_java(fixtures_dir: Path) -> Path:
    """Return path to the Java fixture file."""
    return fixtures_dir / "sample.java"


@pytest.fixture
def make_temp_file(tmp_path: Path):
    """Factory fixture: create a temp file with given content."""

    def _make(content: str, name: str = "test.txt") -> Path:
        p = tmp_path / name
        p.write_text(content)
        return p

    return _make


@pytest.fixture
def make_temp_file_with_lines(tmp_path: Path):
    """Factory fixture: create a temp file with N numbered lines."""

    def _make(n: int, name: str = "test.txt") -> Path:
        lines = [f"line {i}\n" for i in range(1, n + 1)]
        p = tmp_path / name
        p.write_text("".join(lines))
        return p

    return _make
