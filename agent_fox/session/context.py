"""Context assembler: gather spec documents and memory facts for a session.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1
"""

from __future__ import annotations

from pathlib import Path


def assemble_context(
    spec_dir: Path,
    task_group: int,
    memory_facts: list[str] | None = None,
) -> str:
    """Assemble task-specific context for a coding session.

    Reads the following files from spec_dir (if they exist):
    - requirements.md
    - design.md
    - tasks.md

    Appends relevant memory facts (if provided).

    Returns a formatted string with section headers.

    Logs a warning for any missing spec file but does not raise.
    """
    raise NotImplementedError
