"""Generate human-readable markdown summary of all facts.

Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.3, 05-REQ-6.E1,
              05-REQ-6.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.memory.memory import DEFAULT_MEMORY_PATH, load_all_facts
from agent_fox.memory.types import Fact

logger = logging.getLogger("agent_fox.memory.render")

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
    memory_path: Path = DEFAULT_MEMORY_PATH,
    output_path: Path = DEFAULT_SUMMARY_PATH,
) -> None:
    """Generate a human-readable markdown summary of all facts.

    Creates `docs/memory.md` with facts organized by category. Each fact
    entry includes the content, source spec name, and confidence level.

    Creates the output directory if it does not exist.

    Args:
        memory_path: Path to the JSONL fact file.
        output_path: Path to the output markdown file.
    """
    facts = load_all_facts(memory_path)

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


def _render_empty_summary() -> str:
    """Render the summary content when no facts exist."""
    return "# Agent-Fox Memory\n\n_No facts have been recorded yet._\n"
