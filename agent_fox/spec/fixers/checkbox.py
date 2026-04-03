"""Checkbox fixer: normalize invalid checkbox characters.

Requirements: 20-REQ-6.*
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.spec._patterns import (
    CHECKBOX_LINE as _CHECKBOX_LINE,
)
from agent_fox.spec._patterns import (
    VALID_CHECKBOX_CHARS as _VALID_CHECKBOX_CHARS,
)

from .types import FixResult


def fix_invalid_checkbox_state(
    spec_name: str,
    tasks_path: Path,
) -> list[FixResult]:
    """Normalize invalid checkbox characters to [ ] (not started).

    Scans task group and subtask lines for checkbox characters not in
    {' ', 'x', '-', '~'} and replaces them with a space.
    """
    if not tasks_path.is_file():
        return []

    text = tasks_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    results: list[FixResult] = []

    for i, line in enumerate(lines):
        m = _CHECKBOX_LINE.match(line)
        if m:
            char = m.group(2)
            if char not in _VALID_CHECKBOX_CHARS:
                # Replace the invalid checkbox character with a space
                start = m.start(2)
                end = m.end(2)
                lines[i] = line[:start] + " " + line[end:]
                results.append(
                    FixResult(
                        rule="invalid-checkbox-state",
                        spec_name=spec_name,
                        file=str(tasks_path),
                        description=(f"Normalized invalid checkbox '[{char}]' to '[ ]' on line {i + 1}"),
                    )
                )

    if results:
        tasks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results
