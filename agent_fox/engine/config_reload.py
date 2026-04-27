"""Configuration hot-reload: detect changes, diff, and apply new config.

Requirements: 66-REQ-1.1 through 66-REQ-7.2, 103-REQ-3.1
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Any

from agent_fox.core.config import (
    AgentFoxConfig,
    ArchetypesConfig,
    OrchestratorConfig,
    PlanningConfig,
    load_config,
)
from agent_fox.core.errors import ConfigError
from agent_fox.core.models import content_hash
from agent_fox.engine.audit_helpers import emit_audit_event
from agent_fox.engine.circuit import CircuitBreaker
from agent_fox.knowledge.audit import AuditEventType

logger = logging.getLogger(__name__)


def diff_configs(old: AgentFoxConfig, new: AgentFoxConfig) -> dict[str, dict[str, Any]]:
    """Compare two AgentFoxConfig instances field-by-field.

    Returns a dict mapping "section.field" -> {"old": ..., "new": ...}
    for every field whose value has changed. Handles nested Pydantic
    models by walking model_fields one level deep.

    Requirements: 66-REQ-6.2
    """
    changed: dict[str, dict[str, Any]] = {}
    for section_name in AgentFoxConfig.model_fields:
        old_section = getattr(old, section_name)
        new_section = getattr(new, section_name)
        if old_section == new_section:
            continue
        if hasattr(old_section.__class__, "model_fields") and hasattr(new_section.__class__, "model_fields"):
            for field_name in old_section.__class__.model_fields:
                old_val = getattr(old_section, field_name)
                new_val = getattr(new_section, field_name)
                if old_val != new_val:
                    changed[f"{section_name}.{field_name}"] = {
                        "old": old_val,
                        "new": new_val,
                    }
        else:
            changed[section_name] = {"old": old_section, "new": new_section}
    return changed


@dataclasses.dataclass(frozen=True)
class ReloadResult:
    """Result of a successful config hot-reload.

    Requirements: 103-REQ-3.1
    """

    config: OrchestratorConfig
    circuit: CircuitBreaker
    archetypes: ArchetypesConfig | None
    planning: PlanningConfig


class ConfigReloader:
    """Manages configuration hot-reload from disk.

    Tracks the config file hash and applies changes when the file
    is modified, preserving immutable fields (like ``parallel``) and
    emitting audit events for changed fields.
    """

    def __init__(
        self,
        config_path: Path | None,
        full_config: AgentFoxConfig | None,
    ) -> None:
        self._config_path = config_path
        self._full_config = full_config
        self._config_hash: str = ""

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def full_config(self) -> AgentFoxConfig | None:
        return self._full_config

    @property
    def config_hash(self) -> str:
        return self._config_hash

    @config_hash.setter
    def config_hash(self, value: str) -> None:
        self._config_hash = value

    def reload(
        self,
        *,
        current_config: OrchestratorConfig,
        circuit: CircuitBreaker,
        sink: Any | None,
        run_id: str,
    ) -> ReloadResult | None:
        """Reload configuration from disk if the file has changed.

        Returns a ReloadResult if the config changed,
        or None if no reload was needed or an error occurred.

        Requirements: 66-REQ-1.1 through 66-REQ-7.2, 103-REQ-3.1
        """
        if self._config_path is None:
            return None

        try:
            raw = self._config_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Config hot-reload: cannot read %s: %s", self._config_path, exc)
            return None

        new_hash = content_hash(raw)
        if new_hash == self._config_hash:
            return None

        try:
            new_full_config = load_config(self._config_path)
        except (ConfigError, OSError, ValueError) as exc:
            logger.warning(
                "Config hot-reload: failed to parse %s: %s; keeping current config",
                self._config_path,
                exc,
            )
            return None

        old_full_config = self._full_config or AgentFoxConfig()
        new_orch_cfg = new_full_config.orchestrator

        original_parallel = current_config.parallel
        if new_orch_cfg.parallel != original_parallel:
            logger.warning(
                "Config hot-reload: 'parallel' changed from %d to %d but "
                "cannot be changed at runtime; keeping original value.",
                original_parallel,
                new_orch_cfg.parallel,
            )
            new_orch_cfg = new_orch_cfg.model_copy(update={"parallel": original_parallel})
            new_full_config = new_full_config.model_copy(update={"orchestrator": new_orch_cfg})

        changed_fields = diff_configs(old_full_config, new_full_config)

        new_circuit = CircuitBreaker(new_orch_cfg)

        self._full_config = new_full_config
        self._config_hash = new_hash

        if changed_fields:
            emit_audit_event(
                sink,
                run_id,
                AuditEventType.CONFIG_RELOADED,
                payload={"changed_fields": changed_fields},
            )

        logger.info(
            "Config hot-reload: applied %d changed field(s) from %s",
            len(changed_fields),
            self._config_path,
        )

        return ReloadResult(
            config=new_orch_cfg,
            circuit=new_circuit,
            archetypes=new_full_config.archetypes,
            planning=new_full_config.planning,
        )
