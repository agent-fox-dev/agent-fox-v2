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

    retries_before_escalation: int = Field(
        default=1, description="Retries before model escalation"
    )
    training_threshold: int = Field(
        default=20, description="Training data threshold"
    )
    accuracy_threshold: float = Field(
        default=0.75, description="Accuracy threshold for routing"
    )
    retrain_interval: int = Field(
        default=10, description="Retrain interval"
    )

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

    parallel: int = Field(default=1, description="Maximum parallel sessions")
    sync_interval: int = Field(
        default=5, description="Sync interval in task groups"
    )
    hot_load: bool = Field(
        default=True, description="Hot-load specs between sessions"
    )
    max_retries: int = Field(
        default=2, description="Maximum retries per task group"
    )
    session_timeout: int = Field(
        default=30, description="Session timeout in minutes"
    )
    inter_session_delay: int = Field(
        default=3, description="Delay between sessions in seconds"
    )
    max_cost: float | None = Field(
        default=None, description="Maximum cost limit"
    )
    max_sessions: int | None = Field(
        default=None, description="Maximum number of sessions"
    )

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

    coding: str = Field(default="ADVANCED", description="Model tier for coding tasks")
    coordinator: str = Field(
        default="STANDARD", description="Model tier for coordination"
    )
    memory_extraction: str = Field(
        default="SIMPLE", description="Model tier for memory extraction"
    )
    embedding: str = Field(default="voyage-3", description="Embedding model name")


class HookConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pre_code: list[str] = Field(
        default_factory=list, description="Commands to run before coding"
    )
    post_code: list[str] = Field(
        default_factory=list, description="Commands to run after coding"
    )
    sync_barrier: list[str] = Field(
        default_factory=list, description="Commands to run at sync barriers"
    )
    timeout: int = Field(
        default=300, description="Hook command timeout in seconds"
    )
    modes: dict[str, str] = Field(
        default_factory=dict, description="Hook modes configuration"
    )

    @field_validator("timeout")
    @classmethod
    def clamp_timeout(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="hooks.timeout")


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bash_allowlist: list[str] | None = Field(
        default=None, description="Allowed bash commands"
    )
    bash_allowlist_extend: list[str] = Field(
        default_factory=list, description="Additional allowed bash commands"
    )


class ThemeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    playful: bool = Field(default=True, description="Enable playful output style")
    header: str = Field(default="bold #ff8c00", description="Header text style")
    success: str = Field(default="bold green", description="Success text style")
    error: str = Field(default="bold red", description="Error text style")
    warning: str = Field(default="bold yellow", description="Warning text style")
    info: str = Field(default="#daa520", description="Info text style")
    tool: str = Field(default="bold #cd853f", description="Tool text style")
    muted: str = Field(default="dim", description="Muted text style")


class PlatformConfig(BaseModel):
    """Platform configuration.

    Only ``type`` and ``auto_merge`` are meaningful.  Old fields
    (``wait_for_ci``, ``wait_for_review``, ``ci_timeout``,
    ``pr_granularity``, ``labels``) are silently ignored via
    ``extra = "ignore"`` for backward compatibility.

    Requirements: 19-REQ-5.1, 19-REQ-5.2, 19-REQ-5.3, 19-REQ-5.E1
    """

    model_config = ConfigDict(extra="ignore")

    type: str = Field(
        default="none", description="Platform type (none or github)"
    )
    auto_merge: bool = Field(
        default=False, description="Auto-merge pull requests"
    )


class KnowledgeConfig(BaseModel):
    """Knowledge store and fact selection configuration.

    Requirements: 39-REQ-4.2
    """

    model_config = ConfigDict(extra="ignore")

    store_path: str = Field(
        default=".agent-fox/knowledge.duckdb", description="Path to knowledge store"
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2", description="Embedding model for knowledge"
    )
    embedding_dimensions: int = Field(
        default=384, description="Embedding vector dimensions"
    )
    ask_top_k: int = Field(
        default=20, description="Number of results for knowledge queries"
    )
    ask_synthesis_model: str = Field(
        default="STANDARD", description="Model tier for answer synthesis"
    )
    confidence_threshold: float = Field(
        default=0.5,
        description="Minimum confidence for fact inclusion in session context",
    )
    fact_cache_enabled: bool = Field(
        default=True,
        description="Pre-compute fact rankings at plan time",
    )

    @field_validator("ask_top_k")
    @classmethod
    def clamp_ask_top_k(cls, v: int) -> int:
        return _clamp(v, ge=1, field_name="knowledge.ask_top_k")

    @field_validator("confidence_threshold")
    @classmethod
    def clamp_confidence_threshold(cls, v: float) -> float:
        return float(
            _clamp(v, ge=0.0, le=1.0, field_name="knowledge.confidence_threshold")
        )


class ToolsConfig(BaseModel):
    """Configuration for fox tools.

    Requirements: 29-REQ-8.1, 29-REQ-8.E1
    """

    model_config = ConfigDict(extra="ignore")

    fox_tools: bool = Field(default=False, description="Enable fox tools")

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

    skeptic: int = Field(default=1, description="Number of skeptic instances")
    verifier: int = Field(default=1, description="Number of verifier instances")

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

    block_threshold: int = Field(
        default=3, description="Finding count to block merge"
    )

    @field_validator("block_threshold")
    @classmethod
    def clamp_threshold(cls, v: int) -> int:
        return _clamp(v, ge=0, field_name="archetypes.skeptic.block_threshold")


class OracleSettings(BaseModel):
    """Oracle-specific configuration.

    Requirements: 32-REQ-10.2, 32-REQ-10.E1
    """

    model_config = ConfigDict(extra="ignore")

    block_threshold: int | None = Field(
        default=None, description="Drift count to block (None = advisory)"
    )

    @field_validator("block_threshold")
    @classmethod
    def clamp_threshold(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            logger.warning("oracle block_threshold clamped to 1")
            return 1
        return v


class ArchetypesConfig(BaseModel):
    """Archetype enable/disable toggles and per-archetype configuration.

    Requirements: 26-REQ-6.1 through 26-REQ-6.5, 26-REQ-6.E1
    """

    model_config = ConfigDict(extra="ignore")

    coder: bool = Field(default=True, description="Enable coder archetype")
    skeptic: bool = Field(default=False, description="Enable skeptic archetype")
    verifier: bool = Field(default=False, description="Enable verifier archetype")
    librarian: bool = Field(default=False, description="Enable librarian archetype")
    cartographer: bool = Field(
        default=False, description="Enable cartographer archetype"
    )
    oracle: bool = Field(default=False, description="Enable oracle archetype")

    instances: ArchetypeInstancesConfig = Field(
        default_factory=ArchetypeInstancesConfig,
        description="Per-archetype instance counts",
    )
    skeptic_config: SkepticConfig = Field(
        default_factory=SkepticConfig,
        alias="skeptic_settings",
        description="Skeptic-specific configuration",
    )
    oracle_settings: OracleSettings = Field(
        default_factory=OracleSettings,
        description="Oracle-specific configuration",
    )
    models: dict[str, str] = Field(
        default_factory=dict, description="Per-archetype model overrides"
    )
    allowlists: dict[str, list[str]] = Field(
        default_factory=dict, description="Per-archetype command allowlists"
    )

    @field_validator("coder")
    @classmethod
    def coder_always_enabled(cls, v: bool) -> bool:
        if not v:
            logger.warning("archetypes.coder cannot be disabled; ignoring")
        return True


class ModelPricing(BaseModel):
    """Pricing for a single model.

    Requirements: 34-REQ-2.1, 34-REQ-2.E2
    """

    model_config = ConfigDict(extra="ignore")

    input_price_per_m: float = Field(
        default=0.0, description="USD per million input tokens"
    )
    output_price_per_m: float = Field(
        default=0.0, description="USD per million output tokens"
    )

    @field_validator("input_price_per_m", "output_price_per_m")
    @classmethod
    def clamp_negative_price(cls, v: float, info: Any) -> float:
        """Clamp negative pricing values to zero.

        Requirements: 34-REQ-2.E2
        """
        if v < 0:
            logger.warning(
                "Pricing field '%s' value %s is negative, clamped to 0.0",
                info.field_name,
                v,
            )
            return 0.0
        return v


def _default_pricing_models() -> dict[str, ModelPricing]:
    """Return default pricing for all known Claude models.

    Requirements: 34-REQ-2.2, 34-REQ-5.1
    """
    return {
        "claude-haiku-4-5": ModelPricing(
            input_price_per_m=1.00, output_price_per_m=5.00
        ),
        "claude-sonnet-4-6": ModelPricing(
            input_price_per_m=3.00, output_price_per_m=15.00
        ),
        "claude-opus-4-6": ModelPricing(
            input_price_per_m=15.00, output_price_per_m=75.00
        ),
    }


class PricingConfig(BaseModel):
    """Per-model pricing configuration.

    Requirements: 34-REQ-2.1, 34-REQ-2.2, 34-REQ-2.E1
    """

    model_config = ConfigDict(extra="ignore")

    models: dict[str, ModelPricing] = Field(
        default_factory=_default_pricing_models,
        description="Per-model pricing configuration",
    )


class PlanningConfig(BaseModel):
    """Planning and dispatch configuration.

    Requirements: 39-REQ-1.E1, 39-REQ-2.1, 39-REQ-9.3
    """

    model_config = ConfigDict(extra="ignore")

    duration_ordering: bool = Field(
        default=True, description="Sort ready tasks by predicted duration"
    )
    min_outcomes_for_historical: int = Field(
        default=10,
        description="Minimum outcomes before using historical duration data",
    )
    min_outcomes_for_regression: int = Field(
        default=30,
        description="Minimum outcomes before training duration regression model",
    )
    file_conflict_detection: bool = Field(
        default=False,
        description="Detect file conflicts between parallel tasks",
    )

    @field_validator("min_outcomes_for_historical")
    @classmethod
    def clamp_min_outcomes_historical(cls, v: int) -> int:
        field = "planning.min_outcomes_for_historical"
        return int(_clamp(v, ge=1, le=1000, field_name=field))

    @field_validator("min_outcomes_for_regression")
    @classmethod
    def clamp_min_outcomes_regression(cls, v: int) -> int:
        field = "planning.min_outcomes_for_regression"
        return int(_clamp(v, ge=5, le=10000, field_name=field))


class AgentFoxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    hooks: HookConfig = Field(default_factory=HookConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    archetypes: ArchetypesConfig = Field(default_factory=ArchetypesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    planning: PlanningConfig = Field(default_factory=PlanningConfig)


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
