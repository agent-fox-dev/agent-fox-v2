"""Parse source files to extract function/method boundaries and body contents.

Requirements: 87-REQ-1.2, 87-REQ-2.1, 87-REQ-2.4, 87-REQ-2.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.scope_guard.models import FileChange, FunctionBody


def extract_function_body(file_path: Path, function_id: str) -> FunctionBody | None:
    """Parse source file, locate function by ID, extract body text and metadata."""
    raise NotImplementedError


def extract_all_functions(file_path: Path) -> list[FunctionBody]:
    """Extract all functions from a source file."""
    raise NotImplementedError


def extract_modified_functions(file_change: FileChange) -> list[FunctionBody]:
    """Parse diff to identify and extract modified function bodies."""
    raise NotImplementedError
