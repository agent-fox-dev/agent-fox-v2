"""Context assembler: gather spec documents and memory facts for a session.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 13-REQ-7.1, 13-REQ-7.2
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb  # noqa: F401

logger = logging.getLogger(__name__)

# Spec files to read, in order, with their section headers.
_SPEC_FILES: list[tuple[str, str]] = [
    ("requirements.md", "## Requirements"),
    ("design.md", "## Design"),
    ("tasks.md", "## Tasks"),
]


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
    sections: list[str] = []

    # 03-REQ-4.1: Read spec documents
    for filename, header in _SPEC_FILES:
        filepath = spec_dir / filename
        if not filepath.exists():
            # 03-REQ-4.E1: Skip missing files with a warning
            logger.warning(
                "Spec file '%s' not found in %s, skipping", filename, spec_dir,
            )
            continue
        content = filepath.read_text(encoding="utf-8")
        sections.append(f"{header}\n\n{content}")

    # 03-REQ-4.2: Include memory facts
    if memory_facts:
        facts_text = "\n".join(f"- {fact}" for fact in memory_facts)
        sections.append(f"## Memory Facts\n\n{facts_text}")

    # 03-REQ-4.3: Return formatted string with section headers
    return "\n\n---\n\n".join(sections)


def select_context_with_causal(
    conn: duckdb.DuckDBPyConnection,
    spec_name: str,
    touched_files: list[str],
    *,
    keyword_facts: list[dict],
    max_facts: int = 50,
    causal_budget: int = 10,
) -> list[dict]:
    """Select session context facts with causal enhancement.

    1. Start with keyword_facts from the existing selection (REQ-061).
    2. For each keyword fact, query the causal graph for linked facts.
    3. Also query for facts causally linked to the current spec_name.
    4. Deduplicate and rank: keyword matches first, then causal links
       ordered by proximity (depth).
    5. Trim to max_facts total.

    The causal_budget controls how many of the max_facts slots are
    reserved for causally-linked facts (default: 10 of 50).
    """
    raise NotImplementedError
