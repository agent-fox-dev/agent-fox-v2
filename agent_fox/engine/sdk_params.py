"""SDK parameter resolution helpers.

Resolves agent execution parameters (max_turns, thinking, fallback
model, max budget, instance clamping) from hierarchical configuration:
config.toml overrides > archetype registry defaults.

Extracted from session_lifecycle.py to reduce module size.

Requirements: 56-REQ-1.*, 56-REQ-2.*, 56-REQ-3.*, 56-REQ-4.*, 56-REQ-5.*
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agent_fox.archetypes import get_archetype
from agent_fox.core.config import AgentFoxConfig, SecurityConfig

logger = logging.getLogger(__name__)


def resolve_max_turns(config: AgentFoxConfig, archetype: str, *, mode: str | None = None) -> int | None:
    """Resolve max_turns for the given archetype.

    Resolution order (highest to lowest priority):
      1. archetypes.overrides.<name>.modes.<mode>.max_turns (mode-level override)
      2. archetypes.overrides.<name>.max_turns (unified table)
      3. archetypes.max_turns.<name> (legacy dict)
      4. Archetype registry default (via resolve_effective_config for mode)
    Returns None when configured as 0 (unlimited).

    Requirements: 56-REQ-1.1, 56-REQ-1.2, 56-REQ-1.4, 56-REQ-5.1, 207-REQ-2,
                  97-REQ-4.2, 97-REQ-3.3
    """
    from agent_fox.archetypes import resolve_effective_config

    override = config.archetypes.overrides.get(archetype)

    # 1. Mode-level config override (highest priority)
    if mode is not None and override is not None:
        mode_override = override.modes.get(mode)
        if mode_override is not None and mode_override.max_turns is not None:
            return mode_override.max_turns if mode_override.max_turns > 0 else None

    # 2. Unified per-archetype override table
    if override is not None and override.max_turns is not None:
        return override.max_turns if override.max_turns > 0 else None

    # 3. Legacy dict
    configured = config.archetypes.max_turns.get(archetype)
    if configured is not None:
        return configured if configured > 0 else None  # 0 = unlimited

    # 4. Registry default (via mode-resolved effective config)
    entry = get_archetype(archetype)
    effective = resolve_effective_config(entry, mode)
    return effective.default_max_turns


def resolve_thinking(config: AgentFoxConfig, archetype: str, *, mode: str | None = None) -> dict | None:
    """Resolve thinking configuration for the given archetype.

    Resolution order (highest to lowest priority):
      1. archetypes.overrides.<name>.modes.<mode>.thinking_mode / thinking_budget (mode-level override)
      2. archetypes.overrides.<name>.thinking_mode / thinking_budget (unified table)
      3. archetypes.thinking.<name> (legacy dict)
      4. Archetype registry default (via resolve_effective_config for mode)
    Returns None when mode is ``disabled``.

    Requirements: 56-REQ-4.1, 56-REQ-4.2, 56-REQ-4.3, 56-REQ-5.1, 207-REQ-2,
                  97-REQ-4.3, 97-REQ-3.3
    """
    from agent_fox.archetypes import resolve_effective_config

    override = config.archetypes.overrides.get(archetype)

    # 1. Mode-level config override (highest priority)
    if mode is not None and override is not None:
        mode_cfg = override.modes.get(mode)
        if mode_cfg is not None and mode_cfg.thinking_mode is not None:
            if mode_cfg.thinking_mode == "disabled":
                return None
            budget = mode_cfg.thinking_budget if mode_cfg.thinking_budget is not None else 10000
            return {"type": mode_cfg.thinking_mode, "budget_tokens": budget}

    # 2. Unified per-archetype override table
    if override is not None and override.thinking_mode is not None:
        if override.thinking_mode == "disabled":
            return None
        budget = override.thinking_budget if override.thinking_budget is not None else 10000
        return {"type": override.thinking_mode, "budget_tokens": budget}

    # 3. Legacy dict
    configured = config.archetypes.thinking.get(archetype)
    if configured is not None:
        if configured.mode == "disabled":
            return None
        return {"type": configured.mode, "budget_tokens": configured.budget_tokens}

    # 4. Registry default (via mode-resolved effective config)
    entry = get_archetype(archetype)
    effective = resolve_effective_config(entry, mode)
    if effective.default_thinking_mode == "disabled":
        return None
    return {
        "type": effective.default_thinking_mode,
        "budget_tokens": effective.default_thinking_budget,
    }


def resolve_fallback_model(config: AgentFoxConfig) -> str | None:
    """Resolve the fallback model ID from config.

    Reads from ``config.routing.fallback_model`` (the canonical location).
    Returns None when the configured value is empty.
    Logs a warning when the model is not in the local model registry.

    Requirements: 56-REQ-3.1, 56-REQ-3.2, 56-REQ-3.4, 56-REQ-3.E1
    """
    from agent_fox.core.models import MODEL_REGISTRY

    model = config.routing.fallback_model
    if not model:
        return None
    if model not in MODEL_REGISTRY:
        logger.warning(
            "Fallback model '%s' is not in the model registry; passing to SDK anyway (56-REQ-3.E1)",
            model,
        )
    return model


def resolve_max_budget(config: AgentFoxConfig) -> float | None:
    """Resolve max_budget_usd from config.

    Returns None when configured as 0.0 (unlimited).

    Requirements: 56-REQ-2.1, 56-REQ-2.2, 56-REQ-2.E1
    """
    budget = config.orchestrator.max_budget_usd
    if budget == 0.0:
        return None
    return budget


def clamp_instances(archetype: str, instances: int, *, mode: str | None = None) -> int:
    """Clamp instance counts to valid ranges.

    - Coder: always 1 regardless of mode (26-REQ-4.E1, 97-REQ-4.5).
    - Verifier: always 1 (single-instance, 98-REQ-6.2).
    - Any archetype: max 5 (26-REQ-4.E2).
    - Minimum: 1.

    The mode parameter is accepted for API consistency but does not affect
    clamping behavior — coder is always clamped to 1 regardless of mode.

    Requirements: 26-REQ-4.E1, 26-REQ-4.E2, 97-REQ-4.5, 98-REQ-6.2
    """
    if archetype == "coder" and instances > 1:
        logger.warning(
            "Coder archetype does not support multi-instance; clamped instances from %d to 1",
            instances,
        )
        return 1
    if archetype == "verifier" and instances != 1:
        logger.warning(
            "Verifier archetype is always single-instance; clamped instances from %d to 1",
            instances,
        )
        return 1
    if instances > 5:
        logger.warning(
            "Instances for archetype '%s' clamped from %d to 5 (maximum)",
            archetype,
            instances,
        )
        return 5
    if instances < 1:
        logger.warning(
            "Instances for archetype '%s' clamped from %d to 1 (minimum)",
            archetype,
            instances,
        )
        return 1
    return instances


_ARCHETYPE_MODEL_KEYS: dict[str, str] = {"coder": "coding"}


def resolve_model_tier(config: AgentFoxConfig, archetype: str, *, mode: str | None = None) -> str:
    """Resolve model tier for the given archetype.

    Priority (highest to lowest):
      1. archetypes.overrides.<name>.modes.<mode>.model_tier (mode-level override)
      2. archetypes.overrides.<name>.model_tier (unified table)
      3. archetypes.models.<name> (legacy dict)
      4. models.<key> global config (e.g. models.coding for coder archetype)
      5. Archetype registry default (via resolve_effective_config for mode)

    Requirements: 26-REQ-4.4, 26-REQ-6.3, 207-REQ-2, 97-REQ-4.1, 97-REQ-3.3
    """
    from agent_fox.archetypes import resolve_effective_config

    override = config.archetypes.overrides.get(archetype)

    # 1. Mode-level config override (highest priority)
    if mode is not None and override is not None:
        mode_override = override.modes.get(mode)
        if mode_override is not None and mode_override.model_tier:
            return mode_override.model_tier

    # 2. Unified per-archetype override table
    if override and override.model_tier:
        return override.model_tier

    # 3. Legacy dict override
    config_override = config.archetypes.models.get(archetype)
    if config_override:
        return config_override

    # 4. Global [models] config section (deprecated)
    model_key = _ARCHETYPE_MODEL_KEYS.get(archetype)
    if model_key is not None:
        global_tier = getattr(config.models, model_key, None)
        if global_tier:
            logger.warning(
                "[models] %s is deprecated and will be removed in a future release. "
                "Use [archetypes.overrides.%s] model_tier = %r instead.",
                model_key,
                archetype,
                global_tier,
            )
            return global_tier

    # 5. Fall back to archetype registry default (via mode-resolved effective config)
    entry = get_archetype(archetype)
    effective = resolve_effective_config(entry, mode)
    return effective.default_model_tier


def resolve_security_config(
    config: AgentFoxConfig,
    archetype: str,
    *,
    mode: str | None = None,
) -> SecurityConfig | None:
    """Resolve security config for the given archetype.

    Returns a SecurityConfig with the archetype's allowlist override,
    or None to use the global default.

    Priority (highest to lowest):
      1. archetypes.overrides.<name>.modes.<mode>.allowlist (mode-level override)
      2. archetypes.overrides.<name>.allowlist (unified table)
      3. archetypes.allowlists.<name> (legacy dict)
      4. Archetype registry default (via resolve_effective_config for mode)
      5. None -> use global config.security

    An empty list allowlist ([]) produces SecurityConfig(bash_allowlist=[]) which
    blocks all Bash commands (97-REQ-5.2). A None allowlist means "inherit from
    the next level down" (97-REQ-5.E1).

    Requirements: 26-REQ-3.4, 26-REQ-6.4, 207-REQ-2, 97-REQ-4.4, 97-REQ-3.3,
                  97-REQ-5.1, 97-REQ-5.2, 97-REQ-5.E1
    """
    from agent_fox.archetypes import resolve_effective_config

    override = config.archetypes.overrides.get(archetype)

    # 1. Mode-level config override (highest priority)
    if mode is not None and override is not None:
        mode_cfg = override.modes.get(mode)
        if mode_cfg is not None and mode_cfg.allowlist is not None:
            return SecurityConfig(bash_allowlist=mode_cfg.allowlist)

    # 2. Unified per-archetype override table
    if override and override.allowlist is not None:
        return SecurityConfig(bash_allowlist=override.allowlist)

    # 3. Legacy dict override
    config_allowlist = config.archetypes.allowlists.get(archetype)
    if config_allowlist is not None:
        return SecurityConfig(bash_allowlist=config_allowlist)

    # 4. Fall back to archetype registry default (via mode-resolved effective config)
    entry = get_archetype(archetype)
    effective = resolve_effective_config(entry, mode)
    if effective.default_allowlist is not None:
        return SecurityConfig(bash_allowlist=effective.default_allowlist)

    # None means use global config.security
    return None


@dataclass(frozen=True)
class ResolvedSessionParams:
    """All SDK session parameters resolved from config + archetype."""

    max_turns: int | None
    thinking: dict | None
    fallback_model: str | None
    max_budget_usd: float | None


def resolve_session_params(
    config: AgentFoxConfig,
    archetype: str,
    *,
    mode: str | None = None,
    model_id: str | None = None,
    max_turns_override: int | None = None,
) -> ResolvedSessionParams:
    """Resolve all SDK session parameters in one call.

    Consolidates the repeated pattern of calling resolve_max_turns,
    resolve_thinking, resolve_fallback_model, and resolve_max_budget,
    including the fallback-nulling guard when fallback equals the
    main model.
    """
    max_turns = (
        max_turns_override if max_turns_override is not None else resolve_max_turns(config, archetype, mode=mode)
    )
    thinking = resolve_thinking(config, archetype, mode=mode)
    fallback = resolve_fallback_model(config)
    budget = resolve_max_budget(config)

    if fallback and model_id and fallback == model_id:
        fallback = None

    return ResolvedSessionParams(
        max_turns=max_turns,
        thinking=thinking,
        fallback_model=fallback,
        max_budget_usd=budget,
    )
