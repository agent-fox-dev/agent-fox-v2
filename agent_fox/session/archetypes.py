"""Archetype registry: named configurations for agent session execution.

Maps archetype names to their configuration (template files, model tier,
allowlist overrides, injection mode, flags).

Requirements: 26-REQ-3.1, 26-REQ-3.2, 26-REQ-3.3, 26-REQ-3.E1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchetypeEntry:
    """Configuration bundle for a single archetype."""

    name: str
    templates: list[str] = field(default_factory=list)
    default_model_tier: str = "STANDARD"
    injection: str | None = None  # "auto_pre" | "auto_post" | "manual" | None
    task_assignable: bool = True
    retry_predecessor: bool = False
    default_allowlist: list[str] | None = None  # None = use global
    default_max_turns: int = 200
    default_thinking_mode: str = "disabled"
    default_thinking_budget: int = 10000


ARCHETYPE_REGISTRY: dict[str, ArchetypeEntry] = {
    "coder": ArchetypeEntry(
        name="coder",
        templates=["coding.md"],
        default_model_tier="STANDARD",
        injection=None,
        task_assignable=True,
        default_max_turns=200,
        default_thinking_mode="adaptive",
        default_thinking_budget=10000,
    ),
    "oracle": ArchetypeEntry(
        name="oracle",
        templates=["oracle.md"],
        default_model_tier="ADVANCED",
        injection="auto_pre",
        task_assignable=True,
        default_allowlist=[
            "ls",
            "cat",
            "git",
            "grep",
            "find",
            "head",
            "tail",
            "wc",
        ],
        default_max_turns=50,
    ),
    "skeptic": ArchetypeEntry(
        name="skeptic",
        templates=["skeptic.md"],
        default_model_tier="ADVANCED",
        injection="auto_pre",
        task_assignable=True,
        default_allowlist=[
            "ls",
            "cat",
            "git",
            "wc",
            "head",
            "tail",
        ],
        default_max_turns=50,
    ),
    "verifier": ArchetypeEntry(
        name="verifier",
        templates=["verifier.md"],
        default_model_tier="ADVANCED",
        injection="auto_post",
        task_assignable=True,
        retry_predecessor=True,
        default_max_turns=75,
    ),
    "librarian": ArchetypeEntry(
        name="librarian",
        templates=["librarian.md"],
        default_model_tier="STANDARD",
        injection="manual",
        task_assignable=True,
        default_max_turns=100,
    ),
    "cartographer": ArchetypeEntry(
        name="cartographer",
        templates=["cartographer.md"],
        default_model_tier="STANDARD",
        injection="manual",
        task_assignable=True,
        default_max_turns=100,
    ),
    "coordinator": ArchetypeEntry(
        name="coordinator",
        templates=["coordinator.md"],
        default_model_tier="STANDARD",
        injection=None,
        task_assignable=False,
        default_max_turns=30,
    ),
    "auditor": ArchetypeEntry(
        name="auditor",
        templates=["auditor.md"],
        default_model_tier="STANDARD",
        injection="auto_mid",
        task_assignable=True,
        retry_predecessor=True,
        default_allowlist=[
            "ls",
            "cat",
            "git",
            "grep",
            "find",
            "head",
            "tail",
            "wc",
            "uv",
        ],
        default_max_turns=50,
    ),
}


def get_archetype(name: str) -> ArchetypeEntry:
    """Look up an archetype by name, falling back to 'coder'.

    Args:
        name: Archetype name to look up.

    Returns:
        The matching ArchetypeEntry, or the coder entry if not found.
    """
    entry = ARCHETYPE_REGISTRY.get(name)
    if entry is None:
        logger.warning("Unknown archetype '%s', falling back to 'coder'", name)
        return ARCHETYPE_REGISTRY["coder"]
    return entry
