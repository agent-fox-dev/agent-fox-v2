"""Generate human-readable markdown summary of all facts.

Reads facts from DuckDB instead of JSONL.

Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.3, 05-REQ-6.E1,
              05-REQ-6.E2, 39-REQ-2.1, 49-REQ-2.2
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from agent_fox.knowledge.facts import Fact
from agent_fox.knowledge.store import read_all_facts

logger = logging.getLogger("agent_fox.knowledge.rendering")

DEFAULT_SUMMARY_PATH = Path("docs/memory.md")

CATEGORY_TITLES: dict[str, str] = {
    "gotcha": "Gotchas",
    "pattern": "Patterns",
    "decision": "Decisions",
    "convention": "Conventions",
    "anti_pattern": "Anti-Patterns",
    "fragile_area": "Fragile Areas",
}


def render_summary(
    conn: duckdb.DuckDBPyConnection | None = None,
    output_path: Path = DEFAULT_SUMMARY_PATH,
) -> None:
    """Generate a human-readable markdown summary of all facts.

    Creates `docs/memory.md` with facts organized by category. Each fact
    entry includes the content, source spec name, and confidence level.

    Uses :func:`read_all_facts` so that facts are always available even
    when *conn* is ``None`` — falls back to a read-only DuckDB open,
    then to the JSONL file.

    Creates the output directory if it does not exist.

    Args:
        conn: DuckDB connection. Falls back automatically when ``None``.
        output_path: Path to the output markdown file.
    """
    facts: list[Fact] = read_all_facts(conn)

    # Create the output directory if it doesn't exist.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not facts:
        output_path.write_text(_render_empty_summary(), encoding="utf-8")
        logger.info("Rendered empty memory summary to %s", output_path)
        return

    # Group facts by category.
    by_category: dict[str, list[Fact]] = {}
    for fact in facts:
        by_category.setdefault(fact.category, []).append(fact)

    # Build the markdown content.
    lines: list[str] = ["# Agent-Fox Memory", ""]

    for category_value, title in CATEGORY_TITLES.items():
        category_facts = by_category.get(category_value)
        if not category_facts:
            continue
        lines.append(f"## {title}")
        lines.append("")
        for fact in category_facts:
            lines.append(_render_fact(fact))
        lines.append("")

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Rendered memory summary to %s", output_path)


def _render_fact(fact: Fact) -> str:
    """Render a single fact as a markdown list item.

    Format:
        - {content} _(spec: {spec_name}, confidence: {confidence})_
    """
    conf = f"{fact.confidence:.2f}"
    return f"- {fact.content} _(spec: {fact.spec_name}, confidence: {conf})_"


def render_summary_json(
    conn: duckdb.DuckDBPyConnection | None = None,
    output_path: Path = Path("docs/memory.json"),
) -> int:
    """Export all active facts to a JSON file.

    Produces a JSON object with a ``facts`` array and a ``generated``
    ISO-8601 timestamp.  Each fact object contains ``id``, ``content``,
    ``category``, ``spec_name``, and ``confidence``.

    Args:
        conn: DuckDB connection. Falls back automatically when ``None``.
        output_path: Path to the output JSON file.

    Returns:
        The number of facts written.

    Requirements: 49-REQ-2.2, 49-REQ-2.E1
    """
    facts: list[Fact] = read_all_facts(conn)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fact_dicts = [
        {
            "id": fact.id,
            "content": fact.content,
            "category": fact.category,
            "spec_name": fact.spec_name,
            "confidence": fact.confidence,
        }
        for fact in facts
    ]

    data = {
        "facts": fact_dicts,
        "generated": datetime.now(UTC).isoformat(),
    }
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Rendered memory JSON to %s (%d facts)", output_path, len(facts))
    return len(facts)


def _render_empty_summary() -> str:
    """Render the summary content when no facts exist."""
    return "# Agent-Fox Memory\n\n_No facts have been recorded yet._\n"
