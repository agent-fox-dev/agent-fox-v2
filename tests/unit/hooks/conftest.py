"""Fixtures for hook and hot-load tests.

Provides temporary .specs/ directories for hot-load tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_specs_dir(tmp_path: Path) -> Path:
    """Create a temporary .specs/ directory for hot-load tests."""
    specs_dir = tmp_path / ".specs"
    specs_dir.mkdir()
    return specs_dir
