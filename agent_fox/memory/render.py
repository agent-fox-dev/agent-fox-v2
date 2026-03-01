"""Generate human-readable markdown summary of all facts.

Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.3, 05-REQ-6.E1,
              05-REQ-6.E2
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent_fox.memory.store import DEFAULT_MEMORY_PATH
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
    raise NotImplementedError


def _render_fact(fact: Fact) -> str:
    """Render a single fact as a markdown list item.

    Format:
        - {content} _(spec: {spec_name}, confidence: {confidence})_
    """
    raise NotImplementedError


def _render_empty_summary() -> str:
    """Render the summary content when no facts exist."""
    return "# Agent-Fox Memory\n\n_No facts have been recorded yet._\n"
