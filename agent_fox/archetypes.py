"""Archetype registry: named configurations for agent session execution.

Maps archetype names to their configuration (template files, model tier,
allowlist overrides, injection mode, flags).

Moved to top-level package so both ``graph`` and ``session`` can import
without cross-module coupling.

Requirements: 26-REQ-3.1, 26-REQ-3.2, 26-REQ-3.3, 26-REQ-3.E1
             97-REQ-1.1, 97-REQ-1.2, 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5,
             97-REQ-1.E1, 97-REQ-1.E2
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModeConfig:
    """Mode-specific overrides for an archetype entry.

    Every field defaults to None, meaning 'inherit from base'.
    An empty list for allowlist means 'no shell access'.

    Requirements: 97-REQ-1.1
    """

    templates: list[str] | None = None
    injection: str | None = None
    allowlist: list[str] | None = None
    model_tier: str | None = None
    max_turns: int | None = None
    thinking_mode: str | None = None
    thinking_budget: int | None = None
    retry_predecessor: bool | None = None


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
    modes: dict[str, ModeConfig] = field(default_factory=dict)  # 97-REQ-1.2


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


def resolve_effective_config(
    entry: ArchetypeEntry,
    mode: str | None = None,
) -> ArchetypeEntry:
    """Merge mode overrides onto base entry, returning a resolved entry.

    When mode is None, the base entry is returned unchanged.
    When mode names an existing ModeConfig, non-None fields from that config
    override the corresponding base fields; None fields inherit from the base.
    When mode is unknown (not present in entry.modes), a warning is logged and
    the base entry is returned unchanged.

    Requirements: 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5, 97-REQ-1.E1, 97-REQ-1.E2

    Args:
        entry: The base ArchetypeEntry to resolve from.
        mode: The mode name to apply, or None for the base config.

    Returns:
        A new ArchetypeEntry with mode overrides applied, or the base entry
        if mode is None or unknown.
    """
    if mode is None:
        return entry

    mode_cfg = entry.modes.get(mode)
    if mode_cfg is None:
        logger.warning(
            "Unknown mode '%s' for archetype '%s', using base config",
            mode,
            entry.name,
        )
        return entry

    # Build override kwargs: only apply non-None ModeConfig fields.
    # ModeConfig field names map to ArchetypeEntry field names as follows:
    #   model_tier      -> default_model_tier
    #   max_turns       -> default_max_turns
    #   thinking_mode   -> default_thinking_mode
    #   thinking_budget -> default_thinking_budget
    #   allowlist       -> default_allowlist
    #   templates       -> templates
    #   injection       -> injection
    #   retry_predecessor -> retry_predecessor
    overrides: dict[str, object] = {}
    if mode_cfg.templates is not None:
        overrides["templates"] = mode_cfg.templates
    if mode_cfg.injection is not None:
        overrides["injection"] = mode_cfg.injection
    if mode_cfg.allowlist is not None:
        overrides["default_allowlist"] = mode_cfg.allowlist
    if mode_cfg.model_tier is not None:
        overrides["default_model_tier"] = mode_cfg.model_tier
    if mode_cfg.max_turns is not None:
        overrides["default_max_turns"] = mode_cfg.max_turns
    if mode_cfg.thinking_mode is not None:
        overrides["default_thinking_mode"] = mode_cfg.thinking_mode
    if mode_cfg.thinking_budget is not None:
        overrides["default_thinking_budget"] = mode_cfg.thinking_budget
    if mode_cfg.retry_predecessor is not None:
        overrides["retry_predecessor"] = mode_cfg.retry_predecessor

    return dataclasses.replace(entry, **overrides)


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
