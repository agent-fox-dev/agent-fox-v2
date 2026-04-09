"""SDK parameter resolution helpers.

Resolves agent execution parameters (max_turns, thinking, fallback
model, max budget, instance clamping) from hierarchical configuration:
config.toml overrides > archetype registry defaults.

Extracted from session_lifecycle.py to reduce module size.

Requirements: 56-REQ-1.*, 56-REQ-2.*, 56-REQ-3.*, 56-REQ-4.*, 56-REQ-5.*
"""

from __future__ import annotations

import logging

from agent_fox.core.config import AgentFoxConfig, SecurityConfig
from agent_fox.session.archetypes import get_archetype

logger = logging.getLogger(__name__)


def resolve_max_turns(config: AgentFoxConfig, archetype: str) -> int | None:
    """Resolve max_turns for the given archetype.

    Resolution order (highest to lowest priority):
      1. archetypes.overrides.<name>.max_turns (unified table)
      2. archetypes.max_turns.<name> (legacy dict)
      3. Archetype registry default
    Returns None when configured as 0 (unlimited).

    Requirements: 56-REQ-1.1, 56-REQ-1.2, 56-REQ-1.4, 56-REQ-5.1, 207-REQ-2
    """
    # 1. Unified per-archetype override table (highest priority)
    override = config.archetypes.overrides.get(archetype)
    if override is not None and override.max_turns is not None:
        return override.max_turns if override.max_turns > 0 else None

    # 2. Legacy dict
    configured = config.archetypes.max_turns.get(archetype)
    if configured is not None:
        return configured if configured > 0 else None  # 0 = unlimited

    # 3. Registry default
    entry = get_archetype(archetype)
    return entry.default_max_turns


def resolve_thinking(config: AgentFoxConfig, archetype: str) -> dict | None:
    """Resolve thinking configuration for the given archetype.

    Resolution order (highest to lowest priority):
      1. archetypes.overrides.<name>.thinking_mode / thinking_budget (unified table)
      2. archetypes.thinking.<name> (legacy dict)
      3. Archetype registry default
    Returns None when mode is ``disabled``.

    Requirements: 56-REQ-4.1, 56-REQ-4.2, 56-REQ-4.3, 56-REQ-5.1, 207-REQ-2
    """
    # 1. Unified per-archetype override table (highest priority)
    override = config.archetypes.overrides.get(archetype)
    if override is not None and override.thinking_mode is not None:
        if override.thinking_mode == "disabled":
            return None
        budget = override.thinking_budget if override.thinking_budget is not None else 10000
        return {"type": override.thinking_mode, "budget_tokens": budget}

    # 2. Legacy dict
    configured = config.archetypes.thinking.get(archetype)
    if configured is not None:
        if configured.mode == "disabled":
            return None
        return {"type": configured.mode, "budget_tokens": configured.budget_tokens}

    # 3. Registry default
    entry = get_archetype(archetype)
    if entry.default_thinking_mode == "disabled":
        return None
    return {
        "type": entry.default_thinking_mode,
        "budget_tokens": entry.default_thinking_budget,
    }


def resolve_fallback_model(config: AgentFoxConfig) -> str | None:
    """Resolve the fallback model ID from config.

    Returns None when the configured value is empty.
    Logs a warning when the model is not in the local model registry.

    Requirements: 56-REQ-3.1, 56-REQ-3.2, 56-REQ-3.4, 56-REQ-3.E1
    """
    from agent_fox.core.models import MODEL_REGISTRY

    model = config.models.fallback_model
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


def clamp_instances(archetype: str, instances: int) -> int:
    """Clamp instance counts to valid ranges.

    - Coder: always 1 (26-REQ-4.E1).
    - Any archetype: max 5 (26-REQ-4.E2).
    - Minimum: 1.
    """
    if archetype == "coder" and instances > 1:
        logger.warning(
            "Coder archetype does not support multi-instance; clamped instances from %d to 1",
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


def resolve_model_tier(config: AgentFoxConfig, archetype: str) -> str:
    """Resolve model tier for the given archetype.

    Priority (highest to lowest):
      1. archetypes.overrides.<name>.model_tier (unified table)
      2. archetypes.models.<name> (legacy dict)
      3. Archetype registry default

    Requirements: 26-REQ-4.4, 26-REQ-6.3, 207-REQ-2
    """
    # 1. Unified per-archetype override table (highest priority)
    override = config.archetypes.overrides.get(archetype)
    if override and override.model_tier:
        return override.model_tier

    # 2. Legacy dict override
    config_override = config.archetypes.models.get(archetype)
    if config_override:
        return config_override

    # 3. Fall back to archetype registry default
    entry = get_archetype(archetype)
    return entry.default_model_tier


def resolve_security_config(
    config: AgentFoxConfig,
    archetype: str,
) -> SecurityConfig | None:
    """Resolve security config for the given archetype.

    Returns a SecurityConfig with the archetype's allowlist override,
    or None to use the global default.

    Priority (highest to lowest):
      1. archetypes.overrides.<name>.allowlist (unified table)
      2. archetypes.allowlists.<name> (legacy dict)
      3. Archetype registry default
      4. None -> use global config.security

    Requirements: 26-REQ-3.4, 26-REQ-6.4, 207-REQ-2
    """
    # 1. Unified per-archetype override table (highest priority)
    override = config.archetypes.overrides.get(archetype)
    if override and override.allowlist is not None:
        return SecurityConfig(bash_allowlist=override.allowlist)

    # 2. Legacy dict override
    config_allowlist = config.archetypes.allowlists.get(archetype)
    if config_allowlist is not None:
        return SecurityConfig(bash_allowlist=config_allowlist)

    # 3. Fall back to archetype registry default
    entry = get_archetype(archetype)
    if entry.default_allowlist is not None:
        return SecurityConfig(bash_allowlist=entry.default_allowlist)

    # None means use global config.security
    return None
