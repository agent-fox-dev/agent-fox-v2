"""JSONL-based fact store for structured memory.

Append facts, read all facts, load facts filtered by spec name.
Manages the `.agent-fox/memory.jsonl` file.

Requirements: 05-REQ-3.1, 05-REQ-3.2, 05-REQ-3.3, 05-REQ-3.E1,
              05-REQ-3.E2
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agent_fox.memory.types import Fact

logger = logging.getLogger("agent_fox.memory.store")

DEFAULT_MEMORY_PATH = Path(".agent-fox/memory.jsonl")


def append_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Append facts to the JSONL file.

    Creates the file and parent directories if they do not exist.

    Args:
        facts: List of Fact objects to append.
        path: Path to the JSONL file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for fact in facts:
                line = json.dumps(_fact_to_dict(fact), ensure_ascii=False)
                f.write(line + "\n")
    except OSError:
        logger.error("Failed to write facts to %s", path, exc_info=True)


def load_all_facts(path: Path = DEFAULT_MEMORY_PATH) -> list[Fact]:
    """Load all facts from the JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        A list of all Fact objects. Returns an empty list if the file
        does not exist or is empty.
    """
    if not path.exists():
        return []

    facts: list[Fact] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            data = json.loads(stripped)
            facts.append(_dict_to_fact(data))
    return facts


def load_facts_by_spec(
    spec_name: str,
    path: Path = DEFAULT_MEMORY_PATH,
) -> list[Fact]:
    """Load facts filtered by specification name.

    Args:
        spec_name: The specification name to filter by.
        path: Path to the JSONL file.

    Returns:
        A list of Fact objects matching the spec name.
    """
    return [f for f in load_all_facts(path) if f.spec_name == spec_name]


def write_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Overwrite the JSONL file with the given facts.

    Used by compaction to rewrite the file after deduplication.

    Args:
        facts: The complete list of facts to write.
        path: Path to the JSONL file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for fact in facts:
                line = json.dumps(_fact_to_dict(fact), ensure_ascii=False)
                f.write(line + "\n")
    except OSError:
        logger.error("Failed to write facts to %s", path, exc_info=True)


def _fact_to_dict(fact: Fact) -> dict:
    """Serialize a Fact to a JSON-compatible dictionary."""
    return {
        "id": fact.id,
        "content": fact.content,
        "category": fact.category,
        "spec_name": fact.spec_name,
        "keywords": fact.keywords,
        "confidence": fact.confidence,
        "created_at": fact.created_at,
        "supersedes": fact.supersedes,
    }


def _dict_to_fact(data: dict) -> Fact:
    """Deserialize a dictionary to a Fact object."""
    return Fact(
        id=data["id"],
        content=data["content"],
        category=data["category"],
        spec_name=data["spec_name"],
        keywords=data["keywords"],
        confidence=data["confidence"],
        created_at=data["created_at"],
        supersedes=data.get("supersedes"),
    )
