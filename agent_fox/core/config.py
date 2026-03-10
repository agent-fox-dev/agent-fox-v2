"""Configuration system: TOML loading, pydantic models, defaults.

Loads project configuration from a TOML file, validates all fields using
pydantic models, and merges with documented defaults. Out-of-range numeric
values are clamped to the nearest valid bound rather than rejected.

Requirements: 01-REQ-2.1, 01-REQ-2.2, 01-REQ-2.3, 01-REQ-2.4, 01-REQ-2.5,
              01-REQ-2.6, 01-REQ-2.E1, 01-REQ-2.E2, 01-REQ-2.E3
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_fox.core.errors import ConfigError

logger = logging.getLogger(__name__)


def _clamp(
    value: int | float,
    *,
    ge: int | float | None = None,
    le: int | float | None = None,
    field_name: str,
) -> int | float:
    """Clamp a numeric value to valid bounds, logging a warning if adjusted."""
    original = value
    if ge is not None and value < ge:
        value = type(original)(ge) if isinstance(original, int) else ge
    if le is not None and value > le:
        value = type(original)(le) if isinstance(original, int) else le
    if value != original:
        logger.warning(
            "Config field '%s' value %s out of range, clamped to %s",
            field_name,
            original,
            value,
        )
    return value


class RoutingConfig(BaseModel):
    """Adaptive model routing configuration.

    Requirements: 30-REQ-5.1, 30-REQ-5.2, 30-REQ-5.E1, 30-REQ-5.E2
    """

    model_config = ConfigDict(extra="ignore")

    retries_before_escalation: int = Field(default=1)
    training_threshold: int = Field(default=20)
    accuracy_threshold: float = Field(default=0.75)
    retrain_interval: int = Field(default=10)

    @field_validator("retries_before_escalation")
    @classmethod
    def clamp_retries(cls, v: int) -> int:
        return int(
            _clamp(v, ge=0, le=3, field_name="routing.retries_before_escalation")
        )

    @field_validator("training_threshold")
    @classmethod
    def clamp_training_threshold(cls, v: int) -> int:
        return int(_clamp(v, ge=5, le=1000, field_name="routing.training_threshold"))

    @field_validator("accuracy_threshold")
    @classmethod
    def clamp_accuracy_threshold(cls, v: float) -> float:
        return float(_clamp(v, ge=0.5, le=1.0, field_name="routing.accuracy_threshold"))

    @field_validator("retrain_interval")
    @classmethod
    def clamp_retrain_interval(cls, v: int) -> int:
        return int(_clamp(v, ge=5, le=100, field_name="routing.retrain_interval"))


class OrchestratorConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parallel: int = Field(default=1)
    sync_interval: int = Field(default=5)
    hot_load: bool = True
    max_retries: int = Field(default=2)
    session_timeout: int = Field(default=30)  # minutes
    inter_session_delay: int = Field(default=3)  # seconds
    max_cost: float | None = None
    max_sessions: int | None = None

    @field_validator("parallel")
    @classmethod
    def clamp_parallel(cls, v: int) -> int:
        return _clamp(v, ge=1, le=8, field_name="parallel")

    @field_validator("sync_interval")
    @classmethod
    def clamp_sync_interval(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="sync_interval")

    @field_validator("max_retries")
    @classmethod
    def clamp_max_retries(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="max_retries")

    @field_validator("session_timeout")
    @classmethod
    def clamp_session_timeout(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="session_timeout")

    @field_validator("inter_session_delay")
    @classmethod
    def clamp_inter_session_delay(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="inter_session_delay")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coding: str = "ADVANCED"
    coordinator: str = "STANDARD"
    memory_extraction: str = "SIMPLE"
    embedding: str = "voyage-3"


class HookConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pre_code: list[str] = Field(default_factory=list)
    post_code: list[str] = Field(default_factory=list)
    sync_barrier: list[str] = Field(default_factory=list)
    timeout: int = Field(default=300)
    modes: dict[str, str] = Field(default_factory=dict)

    @field_validator("timeout")
    @classmethod
    def clamp_timeout(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="hooks.timeout")


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bash_allowlist: list[str] | None = None
    bash_allowlist_extend: list[str] = Field(default_factory=list)


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    playful: bool = True
    header: str = "bold #ff8c00"
    success: str = "bold green"
    error: str = "bold red"
    warning: str = "bold yellow"
    info: str = "#daa520"
    tool: str = "bold #cd853f"
    muted: str = "dim"


class PlatformConfig(BaseModel):
    """Platform configuration.

    Only ``type`` and ``auto_merge`` are meaningful.  Old fields
    (``wait_for_ci``, ``wait_for_review``, ``ci_timeout``,
    ``pr_granularity``, ``labels``) are silently ignored via
    ``extra = "ignore"`` for backward compatibility.

    Requirements: 19-REQ-5.1, 19-REQ-5.2, 19-REQ-5.3, 19-REQ-5.E1
    """

    model_config = ConfigDict(extra="ignore")

    type: str = "none"  # "none" | "github"
    auto_merge: bool = False  # only meaningful when type = "github"


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "SIMPLE"


class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_path: str = ".agent-fox/knowledge.duckdb"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    ask_top_k: int = Field(default=20)
    ask_synthesis_model: str = "STANDARD"

    @field_validator("ask_top_k")
    @classmethod
    def clamp_ask_top_k(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="knowledge.ask_top_k")


class ToolsConfig(BaseModel):
    """Configuration for fox tools.

    Requirements: 29-REQ-8.1, 29-REQ-8.E1
    """

    model_config = ConfigDict(extra="ignore")

    fox_tools: bool = False

    @field_validator("fox_tools", mode="before")
    @classmethod
    def validate_fox_tools_is_bool(cls, v: Any) -> bool:
        """Reject non-boolean values for fox_tools.

        Requirements: 29-REQ-8.E1
        """
        if not isinstance(v, bool):
            msg = f"tools.fox_tools must be a boolean, got {type(v).__name__}: {v!r}"
            raise ValueError(msg)
        return v


class ArchetypeInstancesConfig(BaseModel):
    """Per-archetype instance count configuration.

    Requirements: 26-REQ-6.2
    """

    model_config = ConfigDict(extra="ignore")

    skeptic: int = Field(default=1)
    verifier: int = Field(default=1)

    @field_validator("skeptic", "verifier")
    @classmethod
    def clamp_instances(cls, v: int, info: Any) -> int:
        field = info.field_name
        return _clamp(v, ge=1, le=5, field_name=f"archetypes.instances.{field}")


class SkepticConfig(BaseModel):
    """Skeptic-specific configuration.

    Requirements: 26-REQ-8.4
    """

    model_config = ConfigDict(extra="ignore")

    block_threshold: int = Field(default=3)

    @field_validator("block_threshold")
    @classmethod
    def clamp_threshold(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="archetypes.skeptic.block_threshold")


class ArchetypesConfig(BaseModel):
    """Archetype enable/disable toggles and per-archetype configuration.

    Requirements: 26-REQ-6.1 through 26-REQ-6.5, 26-REQ-6.E1
    """

    model_config = ConfigDict(extra="ignore")

    coder: bool = True
    skeptic: bool = False
    verifier: bool = False
    librarian: bool = False
    cartographer: bool = False

    instances: ArchetypeInstancesConfig = Field(
        default_factory=ArchetypeInstancesConfig
    )
    skeptic_config: SkepticConfig = Field(
        default_factory=SkepticConfig, alias="skeptic_settings"
    )
    models: dict[str, str] = Field(default_factory=dict)
    allowlists: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("coder")
    @classmethod
    def coder_always_enabled(cls, v: bool) -> bool:
        if not v:
            logger.warning("archetypes.coder cannot be disabled; ignoring")
        return True


class AgentFoxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    hooks: HookConfig = Field(default_factory=HookConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    archetypes: ArchetypesConfig = Field(default_factory=ArchetypesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


def load_config(path: Path | None = None) -> AgentFoxConfig:
    """Load config from TOML, validate, and merge with defaults.

    Args:
        path: Path to a TOML configuration file. If None or the file does
              not exist, all defaults are returned.

    Returns:
        A fully populated AgentFoxConfig with defaults for missing fields.

    Raises:
        ConfigError: If the file contains invalid TOML or fields with
                     wrong types.
    """
    # 01-REQ-2.E1: missing file returns defaults without error
    if path is None or not path.exists():
        return AgentFoxConfig()

    # Read and parse TOML
    raw = path.read_text(encoding="utf-8")

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        # 01-REQ-2.E2: invalid TOML raises ConfigError
        raise ConfigError(
            f"Failed to parse config file {path}: {exc}",
            path=str(path),
        ) from exc

    # 01-REQ-2.6: log warning for unknown top-level keys
    known_sections = set(AgentFoxConfig.model_fields.keys())
    for key in data:
        if key not in known_sections:
            logger.warning("Ignoring unknown config section: '%s'", key)

    # Validate and construct config with pydantic
    try:
        return AgentFoxConfig(**data)
    except ValidationError as exc:
        # 01-REQ-2.2: report clear error identifying field, value, expected type
        field_errors = []
        for err in exc.errors():
            loc = " → ".join(str(part) for part in err["loc"])
            msg = err["msg"]
            field_errors.append(f"  {loc}: {msg}")
        error_detail = "\n".join(field_errors)
        raise ConfigError(
            f"Invalid configuration in {path}:\n{error_detail}",
            path=str(path),
            details=exc.errors(),
        ) from exc
