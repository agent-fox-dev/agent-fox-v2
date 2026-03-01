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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_fox.core.errors import ConfigError

logger = logging.getLogger(__name__)


def _clamp(
    value: int,
    *,
    ge: int | None = None,
    le: int | None = None,
    field_name: str,
) -> int:
    """Clamp an integer to valid bounds, logging a warning if adjusted."""
    original = value
    if ge is not None and value < ge:
        value = ge
    if le is not None and value > le:
        value = le
    if value != original:
        logger.warning(
            "Config field '%s' value %d out of range, clamped to %d",
            field_name,
            original,
            value,
        )
    return value


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
    model_config = ConfigDict(extra="ignore")

    type: str = "none"
    pr_granularity: str = "session"
    wait_for_ci: bool = False
    wait_for_review: bool = False
    auto_merge: bool = False
    ci_timeout: int = Field(default=600)
    labels: list[str] = Field(default_factory=list)

    @field_validator("ci_timeout")
    @classmethod
    def clamp_ci_timeout(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="platform.ci_timeout")


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "SIMPLE"


class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_path: str = ".agent-fox/knowledge.duckdb"
    embedding_model: str = "voyage-3"
    embedding_dimensions: int = 1024
    ask_top_k: int = Field(default=20)
    ask_synthesis_model: str = "STANDARD"

    @field_validator("ask_top_k")
    @classmethod
    def clamp_ask_top_k(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="knowledge.ask_top_k")


class AgentFoxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    hooks: HookConfig = Field(default_factory=HookConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)


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
