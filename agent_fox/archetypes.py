"""Archetype registry: named configurations for agent session execution.

Maps archetype names to their configuration (template files, model tier,
allowlist overrides, injection mode, flags).

Moved to top-level package so both ``graph`` and ``session`` can import
without cross-module coupling.

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
        default_max_turns=300,
        default_thinking_mode="adaptive",
        default_thinking_budget=64000,
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
        default_max_turns=80,
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
        default_max_turns=80,
    ),
    "verifier": ArchetypeEntry(
        name="verifier",
        templates=["verifier.md"],
        default_model_tier="ADVANCED",
        injection="auto_post",
        task_assignable=True,
        retry_predecessor=True,
        default_max_turns=120,
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
        default_max_turns=80,
    ),
    "triage": ArchetypeEntry(
        name="triage",
        templates=["triage.md"],
        default_model_tier="ADVANCED",
        injection=None,
        task_assignable=False,
        default_allowlist=[
            "ls",
            "cat",
            "git",
            "wc",
            "head",
            "tail",
        ],
        default_max_turns=80,
    ),
    "fix_reviewer": ArchetypeEntry(
        name="fix_reviewer",
        templates=["fix_reviewer.md"],
        default_model_tier="ADVANCED",
        injection=None,
        task_assignable=False,
        retry_predecessor=False,
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
            "make",
        ],
        default_max_turns=120,
    ),
    "fix_coder": ArchetypeEntry(
        name="fix_coder",
        templates=["fix_coding.md"],
        default_model_tier="STANDARD",
        injection=None,
        task_assignable=False,
        retry_predecessor=False,
        default_max_turns=300,
        default_thinking_mode="adaptive",
        default_thinking_budget=64000,
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
