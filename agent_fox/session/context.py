"""Context assembler: gather spec documents and memory facts for a session.

Requirements: 03-REQ-4.1 through 03-REQ-4.E1, 13-REQ-7.1, 13-REQ-7.2,
              15-REQ-1.1, 15-REQ-1.2, 15-REQ-1.E1
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb  # noqa: F401

from agent_fox.knowledge.causal import traverse_causal_chain

logger = logging.getLogger(__name__)

# Spec files to read, in order, with their section headers.
_SPEC_FILES: list[tuple[str, str]] = [
    ("requirements.md", "## Requirements"),
    ("design.md", "## Design"),
    ("test_spec.md", "## Test Specification"),
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
    - test_spec.md
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
                "Spec file '%s' not found in %s, skipping",
                filename,
                spec_dir,
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
    # 1. Start with keyword facts, trimmed to fit within max_facts
    keyword_budget = max_facts - causal_budget
    if keyword_budget < 0:
        keyword_budget = 0
    selected_keywords = keyword_facts[:keyword_budget]

    # Track seen IDs for deduplication
    seen_ids: set[str] = {f["id"] for f in selected_keywords}
    result: list[dict] = list(selected_keywords)

    # 2. For each keyword fact, traverse causal graph for linked facts
    causal_candidates: list[tuple[int, dict]] = []  # (abs_depth, fact_dict)
    for kw_fact in selected_keywords:
        fact_id = kw_fact["id"]
        try:
            chain = traverse_causal_chain(conn, fact_id, max_depth=3)
        except Exception:
            logger.debug("Failed to traverse causal chain for fact %s", fact_id)
            continue
        for cf in chain:
            if cf.fact_id not in seen_ids:
                causal_candidates.append(
                    (
                        abs(cf.depth),
                        {
                            "id": cf.fact_id,
                            "content": cf.content,
                            "spec_name": cf.spec_name,
                            "session_id": cf.session_id,
                            "commit_sha": cf.commit_sha,
                        },
                    )
                )

    # 3. Also query for facts linked to the current spec_name
    try:
        rows = conn.execute(
            "SELECT CAST(id AS VARCHAR), content, spec_name, session_id, "
            "commit_sha FROM memory_facts WHERE spec_name = ?",
            [spec_name],
        ).fetchall()
        for row in rows:
            fid = row[0]
            if fid not in seen_ids:
                try:
                    chain = traverse_causal_chain(conn, fid, max_depth=2)
                except Exception:
                    continue
                for cf in chain:
                    if cf.fact_id not in seen_ids:
                        causal_candidates.append(
                            (
                                abs(cf.depth),
                                {
                                    "id": cf.fact_id,
                                    "content": cf.content,
                                    "spec_name": cf.spec_name,
                                    "session_id": cf.session_id,
                                    "commit_sha": cf.commit_sha,
                                },
                            )
                        )
    except Exception:
        logger.debug("Failed to query facts for spec_name %s", spec_name)

    # 4. Deduplicate and rank causal candidates by proximity (depth)
    causal_candidates.sort(key=lambda x: x[0])

    # 5. Add causal facts up to the budget and max_facts limit
    remaining_budget = min(causal_budget, max_facts - len(result))
    for _depth, fact_dict in causal_candidates:
        if remaining_budget <= 0:
            break
        if fact_dict["id"] not in seen_ids:
            seen_ids.add(fact_dict["id"])
            result.append(fact_dict)
            remaining_budget -= 1

    # Final trim to ensure budget compliance
    return result[:max_facts]
