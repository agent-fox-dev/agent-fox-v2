"""Archetype registry: named configurations for agent session execution.

Maps archetype names to their configuration (model tier, allowlist
overrides, injection mode, flags).

Moved to top-level package so both ``graph`` and ``session`` can import
without cross-module coupling.

Requirements: 26-REQ-3.1, 26-REQ-3.2, 26-REQ-3.3, 26-REQ-3.E1
             97-REQ-1.1, 97-REQ-1.2, 97-REQ-1.3, 97-REQ-1.4, 97-REQ-1.5,
             97-REQ-1.E1, 97-REQ-1.E2
             100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3, 100-REQ-1.4,
             100-REQ-1.E1, 100-REQ-2.1
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_fox.core.config import AgentFoxConfig

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
    templates: list[str] = field(default_factory=list)  # 97-REQ-1.3 (reserved; profiles used in practice)
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
        default_model_tier="STANDARD",
        injection=None,
        task_assignable=True,
        default_max_turns=300,
        default_thinking_mode="adaptive",
        default_thinking_budget=64000,
        modes={
            "fix": ModeConfig(
                max_turns=300,
                thinking_mode="adaptive",
                thinking_budget=64000,
            ),
        },
    ),
    "reviewer": ArchetypeEntry(
        name="reviewer",
        default_model_tier="STANDARD",
        injection=None,  # mode-specific injection
        task_assignable=True,
        default_max_turns=80,
        modes={
            "pre-review": ModeConfig(
                injection="auto_pre",
                allowlist=[],  # no shell access
            ),
            "drift-review": ModeConfig(
                injection="auto_pre",
                allowlist=["ls", "cat", "git", "grep", "find", "head", "tail", "wc"],
            ),
            "audit-review": ModeConfig(
                injection="auto_mid",
                allowlist=["ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv"],
                retry_predecessor=True,
            ),
            "fix-review": ModeConfig(
                model_tier="ADVANCED",
                allowlist=["ls", "cat", "git", "grep", "find", "head", "tail", "wc", "uv", "make"],
                max_turns=120,
            ),
        },
    ),
    "verifier": ArchetypeEntry(
        name="verifier",
        default_model_tier="STANDARD",  # Changed from ADVANCED (98-REQ-6.1)
        injection="auto_post",
        task_assignable=True,
        retry_predecessor=True,
        default_max_turns=120,
    ),
    # "triage" was removed in spec 100 and absorbed into maintainer:hunt.
    # get_archetype("triage") falls back to "coder" with a warning (100-REQ-1.E1).
    "maintainer": ArchetypeEntry(
        name="maintainer",
        default_model_tier="STANDARD",
        injection=None,
        task_assignable=False,
        default_max_turns=80,
        modes={
            "hunt": ModeConfig(
                # Read-only analysis allowlist (100-REQ-1.2)
                allowlist=["ls", "cat", "git", "wc", "head", "tail"],
            ),
            "fix-triage": ModeConfig(
                # Read-only analysis for single-issue triage (fixes #383)
                allowlist=["ls", "cat", "git", "wc", "head", "tail"],
            ),
            "extraction": ModeConfig(
                # No shell access for extraction mode (100-REQ-1.3)
                allowlist=[],
            ),
        },
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

    # Apply non-None ModeConfig fields onto the base entry.
    # ModeConfig field names map to ArchetypeEntry field names as follows:
    #   templates       -> templates        (direct 1:1)
    #   model_tier      -> default_model_tier
    #   max_turns       -> default_max_turns
    #   thinking_mode   -> default_thinking_mode
    #   thinking_budget -> default_thinking_budget
    #   allowlist       -> default_allowlist
    #   injection       -> injection
    #   retry_predecessor -> retry_predecessor
    return dataclasses.replace(
        entry,
        templates=(mode_cfg.templates if mode_cfg.templates is not None else entry.templates),
        injection=(mode_cfg.injection if mode_cfg.injection is not None else entry.injection),
        default_allowlist=(mode_cfg.allowlist if mode_cfg.allowlist is not None else entry.default_allowlist),
        default_model_tier=(mode_cfg.model_tier if mode_cfg.model_tier is not None else entry.default_model_tier),
        default_max_turns=(mode_cfg.max_turns if mode_cfg.max_turns is not None else entry.default_max_turns),
        default_thinking_mode=(
            mode_cfg.thinking_mode if mode_cfg.thinking_mode is not None else entry.default_thinking_mode
        ),
        default_thinking_budget=(
            mode_cfg.thinking_budget if mode_cfg.thinking_budget is not None else entry.default_thinking_budget
        ),
        retry_predecessor=(
            mode_cfg.retry_predecessor if mode_cfg.retry_predecessor is not None else entry.retry_predecessor
        ),
    )


def _resolve_custom_preset(
    name: str,
    config: AgentFoxConfig | None,
) -> str:
    """Resolve the permission preset name for a custom archetype.

    Returns the preset name (a built-in archetype name).  Defaults to
    ``'coder'`` if no preset is configured and logs a warning.

    Requirements: 99-REQ-4.E1
    """
    if config is not None:
        custom_cfg = config.archetypes.custom.get(name)
        if custom_cfg is not None:
            return custom_cfg.permissions

    logger.warning(
        "Custom archetype '%s' has no permission preset in config; defaulting to 'coder' permissions",
        name,
    )
    return "coder"


def get_archetype(
    name: str,
    *,
    project_dir: Path | None = None,
    config: AgentFoxConfig | None = None,
) -> ArchetypeEntry:
    """Look up an archetype by name, with custom archetype fallback.

    Resolution order:
    1. ``ARCHETYPE_REGISTRY[name]`` — built-in archetypes.
    2. Custom archetype — profile exists at
       ``<project_dir>/.agent-fox/profiles/<name>.md`` and a permission
       preset is resolved from *config*.
    3. Fallback to ``'coder'`` with a warning.

    Args:
        name: Archetype name to look up.
        project_dir: Project root directory used to locate custom profiles.
            Pass ``None`` to skip custom archetype resolution.
        config: Loaded ``AgentFoxConfig`` providing custom archetype
            permission presets.  Pass ``None`` to use the default preset.

    Returns:
        The matching ``ArchetypeEntry``.

    Raises:
        ConfigError: When a custom archetype's permission preset references
            a non-existent built-in archetype (99-REQ-4.E2).

    Requirements: 99-REQ-4.1, 99-REQ-4.3, 99-REQ-4.4, 99-REQ-4.E1,
                  99-REQ-4.E2
    """
    # 1. Built-in registry lookup
    entry = ARCHETYPE_REGISTRY.get(name)
    if entry is not None:
        return entry

    # 2. Custom archetype fallback
    if project_dir is not None:
        from agent_fox.session.profiles import has_custom_profile

        if has_custom_profile(name, project_dir):
            preset_name = _resolve_custom_preset(name, config)
            preset_entry = ARCHETYPE_REGISTRY.get(preset_name)
            if preset_entry is None:
                from agent_fox.core.errors import ConfigError

                raise ConfigError(
                    f"Custom archetype '{name}' references invalid permission "
                    f"preset '{preset_name}'. Valid built-in archetypes: "
                    f"{list(ARCHETYPE_REGISTRY.keys())}",
                )
            return dataclasses.replace(preset_entry, name=name)

    # 3. Final fallback to coder
    logger.warning("Unknown archetype '%s', falling back to 'coder'", name)
    return ARCHETYPE_REGISTRY["coder"]
