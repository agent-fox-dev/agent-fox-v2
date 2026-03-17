"""Shared archetype injection logic used by both the graph builder and engine.

Centralizes the decision logic for which archetypes to inject (auto_pre,
auto_mid, auto_post), oracle gating, instance resolution, and auditor
configuration. The builder and engine each handle their own mutation
(Node dataclass vs raw dict) but share these helpers.

Requirements: 26-REQ-5.3, 26-REQ-5.4, 32-REQ-3.1, 32-REQ-3.2,
              46-REQ-3.1, 46-REQ-4.1, 46-REQ-4.4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


class ArchetypeEntry(NamedTuple):
    """Lightweight tuple of (name, registry_entry) for an enabled archetype."""

    name: str
    entry: Any


def resolve_instances(archetypes_config: Any, arch_name: str) -> int:
    """Resolve the instance count for an archetype from config.

    Returns 1 if config is missing or value is not an int.
    """
    instances_cfg = getattr(archetypes_config, "instances", None)
    instances = getattr(instances_cfg, arch_name, 1) if instances_cfg else 1
    return instances if isinstance(instances, int) else 1


def is_archetype_enabled(name: str, archetypes_config: Any | None) -> bool:
    """Check if an archetype is enabled in config."""
    if archetypes_config is None:
        return name == "coder"
    return getattr(archetypes_config, name, False)


def collect_enabled_auto_pre(
    archetypes_config: Any,
    spec_path: Path | None = None,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_pre archetypes, applying oracle gating.

    Args:
        archetypes_config: The archetypes configuration object.
        spec_path: Path to the spec directory (for oracle gating).
            If None, oracle gating is skipped.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_pre archetypes.
    """
    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    enabled: list[ArchetypeEntry] = [
        ArchetypeEntry(arch_name, entry)
        for arch_name, entry in ARCHETYPE_REGISTRY.items()
        if entry.injection == "auto_pre"
        and is_archetype_enabled(arch_name, archetypes_config)
    ]

    # Gate oracle: skip when spec has no existing code to validate against
    if any(a.name == "oracle" for a in enabled) and spec_path is not None:
        from agent_fox.graph.builder import spec_has_existing_code

        if not spec_has_existing_code(spec_path):
            enabled = [a for a in enabled if a.name != "oracle"]
            logger.info(
                "Skipping oracle for %s: no existing code to validate",
                spec_path.name,
            )

    return enabled


def collect_enabled_auto_post(
    archetypes_config: Any,
) -> list[ArchetypeEntry]:
    """Collect enabled auto_post archetypes.

    Returns:
        List of ArchetypeEntry tuples for enabled auto_post archetypes.
    """
    from agent_fox.session.archetypes import ARCHETYPE_REGISTRY

    return [
        ArchetypeEntry(arch_name, entry)
        for arch_name, entry in ARCHETYPE_REGISTRY.items()
        if entry.injection == "auto_post"
        and is_archetype_enabled(arch_name, archetypes_config)
    ]


class AuditorConfig(NamedTuple):
    """Resolved auditor injection configuration."""

    enabled: bool
    min_ts_entries: int
    instances: int


def resolve_auditor_config(archetypes_config: Any) -> AuditorConfig:
    """Resolve auditor injection configuration from archetypes config.

    Returns:
        AuditorConfig with enabled flag, minimum TS entries, and instance count.
    """
    enabled = getattr(archetypes_config, "auditor", False)
    if not enabled:
        return AuditorConfig(enabled=False, min_ts_entries=5, instances=1)

    auditor_cfg = getattr(archetypes_config, "auditor_config", None)
    min_ts = getattr(auditor_cfg, "min_ts_entries", 5) if auditor_cfg else 5
    instances = resolve_instances(archetypes_config, "auditor")

    return AuditorConfig(enabled=True, min_ts_entries=min_ts, instances=instances)
