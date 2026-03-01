"""JSONL-based fact store for structured memory.

Append facts, read all facts, load facts filtered by spec name.
Manages the `.agent-fox/memory.jsonl` file.

Requirements: 05-REQ-3.1, 05-REQ-3.2, 05-REQ-3.3, 05-REQ-3.E1,
              05-REQ-3.E2
"""

from __future__ import annotations

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
    raise NotImplementedError


def load_all_facts(path: Path = DEFAULT_MEMORY_PATH) -> list[Fact]:
    """Load all facts from the JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        A list of all Fact objects. Returns an empty list if the file
        does not exist or is empty.
    """
    raise NotImplementedError


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
    raise NotImplementedError


def write_facts(facts: list[Fact], path: Path = DEFAULT_MEMORY_PATH) -> None:
    """Overwrite the JSONL file with the given facts.

    Used by compaction to rewrite the file after deduplication.

    Args:
        facts: The complete list of facts to write.
        path: Path to the JSONL file.
    """
    raise NotImplementedError


def _fact_to_dict(fact: Fact) -> dict:
    """Serialize a Fact to a JSON-compatible dictionary."""
    raise NotImplementedError


def _dict_to_fact(data: dict) -> Fact:
    """Deserialize a dictionary to a Fact object."""
    raise NotImplementedError
