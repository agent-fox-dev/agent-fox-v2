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
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

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


def _clamped_validator(
    *fields: str,
    ge: int | float | None = None,
    le: int | float | None = None,
    cast: type | None = None,
) -> classmethod:
    """Factory for field_validator methods that clamp numeric values.

    Returns a pydantic field_validator classmethod. If *cast* is given the
    result is cast (e.g. ``int``).
    """

    @field_validator(*fields)
    @classmethod
    def _validate(cls: Any, v: Any, info: Any) -> Any:
        result = _clamp(v, ge=ge, le=le, field_name=info.field_name)
        return cast(result) if cast else result

    return _validate


class RoutingConfig(BaseModel):
    """Adaptive model routing configuration.

    Requirements: 30-REQ-5.1, 30-REQ-5.2, 30-REQ-5.E1, 30-REQ-5.E2
    """

    model_config = ConfigDict(extra="ignore")

    retries_before_escalation: int = Field(
        default=1, description="Retries before model escalation"
    )
    training_threshold: int = Field(default=20, description="Training data threshold")
    accuracy_threshold: float = Field(
        default=0.75, description="Accuracy threshold for routing"
    )
    retrain_interval: int = Field(default=10, description="Retrain interval")

    clamp_retries = _clamped_validator(
        "retries_before_escalation", ge=0, le=3, cast=int
    )
    clamp_training = _clamped_validator("training_threshold", ge=5, le=1000, cast=int)
    clamp_accuracy = _clamped_validator("accuracy_threshold", ge=0.5, le=1.0)
    clamp_retrain = _clamped_validator("retrain_interval", ge=5, le=100, cast=int)


class OrchestratorConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parallel: int = Field(default=2, description="Maximum parallel sessions")
    sync_interval: int = Field(default=5, description="Sync interval in task groups")
    hot_load: bool = Field(default=True, description="Hot-load specs between sessions")
    max_retries: int = Field(default=2, description="Maximum retries per task group")
    session_timeout: int = Field(default=30, description="Session timeout in minutes")
    inter_session_delay: int = Field(
        default=3, description="Delay between sessions in seconds"
    )
    max_cost: float | None = Field(default=None, description="Maximum cost limit")
    max_sessions: int | None = Field(
        default=None, description="Maximum number of sessions"
    )
    audit_retention_runs: int = Field(
        default=20,
        description="Maximum number of runs to retain in the audit log",
    )
    max_blocked_fraction: float | None = Field(
        default=None,
        description=(
            "Stop the run when this fraction of nodes are blocked "
            "(0.0-1.0). None = disabled."
        ),
    )
    quality_gate: str = Field(
        default="",
        description="Shell command to run after each coder session",
    )
    quality_gate_timeout: int = Field(
        default=300,
        description="Quality gate timeout in seconds",
    )

    max_budget_usd: float = Field(
        default=2.0,
        ge=0.0,
        description="Maximum USD spend per session, 0 = unlimited",
    )

    causal_context_limit: int = Field(
        default=200,
        description=(
            "Maximum number of prior facts included in the causal extraction "
            "prompt. When total non-superseded facts exceed this limit, prior "
            "facts are ranked by embedding similarity to the new facts and "
            "only the top N are included."
        ),
    )

    watch_interval: int = Field(
        default=60,
        description=(
            "Seconds between watch polls when --watch is active. "
            "Values below 10 are clamped to 10."
        ),
    )

    clamp_parallel = _clamped_validator("parallel", ge=1, le=8)
    clamp_sync_interval = _clamped_validator("sync_interval", ge=0)
    clamp_max_retries = _clamped_validator("max_retries", ge=0)
    clamp_session_timeout = _clamped_validator("session_timeout", ge=1)
    clamp_inter_session_delay = _clamped_validator("inter_session_delay", ge=0)
    clamp_audit_retention = _clamped_validator("audit_retention_runs", ge=1, cast=int)
    clamp_causal_context_limit = _clamped_validator(
        "causal_context_limit", ge=10, le=10000, cast=int
    )
    clamp_watch_interval = _clamped_validator("watch_interval", ge=10, cast=int)

    @field_validator("max_blocked_fraction")
    @classmethod
    def clamp_max_blocked_fraction(cls, v: float | None) -> float | None:
        if v is None:
            return v
        return _clamp(v, ge=0.0, le=1.0, field_name="max_blocked_fraction")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coding: str = Field(default="ADVANCED", description="Model tier for coding tasks")
    memory_extraction: str = Field(
        default="SIMPLE", description="Model tier for memory extraction"
    )
    fallback_model: str = Field(
        default="claude-sonnet-4-6",
        description="Fallback model ID when primary is unavailable",
    )


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
    timeout: int = Field(default=300, description="Hook command timeout in seconds")
    modes: dict[str, str] = Field(
        default_factory=dict, description="Hook modes configuration"
    )

    clamp_timeout = _clamped_validator("timeout", ge=1)


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
    """Platform configuration for issue tracking.

    Only ``type`` and ``url`` are meaningful.  Old fields
    (``auto_merge``, ``wait_for_ci``, ``wait_for_review``, ``ci_timeout``,
    ``pr_granularity``, ``labels``) are silently ignored via
    ``extra = "ignore"`` for backward compatibility.

    Requirements: 65-REQ-1.1, 65-REQ-1.2, 65-REQ-1.E1,
                  65-REQ-2.1, 65-REQ-2.2, 65-REQ-2.3, 65-REQ-2.E1
    """

    model_config = ConfigDict(extra="ignore")

    type: str = Field(default="none", description="Platform type (none or github)")
    url: str = Field(default="", description="Issue tracker URL (defaults from type)")


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

    clamp_ask_top_k = _clamped_validator("ask_top_k", ge=1)
    clamp_confidence = _clamped_validator("confidence_threshold", ge=0.0, le=1.0)


class ThinkingConfig(BaseModel):
    """Extended thinking configuration for an archetype.

    Requirements: 56-REQ-4.1, 56-REQ-4.E1, 56-REQ-4.E2
    """

    model_config = ConfigDict(extra="ignore")

    mode: Literal["enabled", "adaptive", "disabled"] = "disabled"
    budget_tokens: int = Field(default=10000, ge=0)

    @model_validator(mode="after")
    def validate_budget(self) -> Self:
        """budget_tokens must be > 0 when mode is 'enabled'."""
        if self.mode == "enabled" and self.budget_tokens <= 0:
            raise ValueError("budget_tokens must be > 0 when mode is 'enabled'")
        return self


class ArchetypeInstancesConfig(BaseModel):
    """Per-archetype instance count configuration.

    Requirements: 26-REQ-6.2, 46-REQ-2.2
    """

    model_config = ConfigDict(extra="ignore")

    skeptic: int = Field(default=1, description="Number of skeptic instances")
    verifier: int = Field(default=2, description="Number of verifier instances")
    auditor: int = Field(default=1, description="Number of auditor instances")

    clamp_instances = _clamped_validator("skeptic", "verifier", "auditor", ge=1, le=5)


class SkepticConfig(BaseModel):
    """Skeptic-specific configuration.

    Requirements: 26-REQ-8.4
    """

    model_config = ConfigDict(extra="ignore")

    block_threshold: int = Field(default=3, description="Finding count to block merge")

    clamp_threshold = _clamped_validator("block_threshold", ge=0)


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


class AuditorConfig(BaseModel):
    """Auditor-specific configuration.

    Requirements: 46-REQ-2.3, 46-REQ-2.4
    """

    model_config = ConfigDict(extra="ignore")

    min_ts_entries: int = Field(
        default=5, description="Minimum TS entries to trigger auditor injection"
    )
    max_retries: int = Field(
        default=2, description="Maximum auditor-coder retry iterations"
    )

    clamp_min_ts = _clamped_validator("min_ts_entries", ge=1, cast=int)
    clamp_max_retries = _clamped_validator("max_retries", ge=0, cast=int)


class ArchetypesConfig(BaseModel):
    """Archetype enable/disable toggles and per-archetype configuration.

    Requirements: 26-REQ-6.1 through 26-REQ-6.5, 26-REQ-6.E1, 46-REQ-2.1
    """

    model_config = ConfigDict(extra="ignore")

    coder: bool = Field(default=True, description="Enable coder archetype")
    skeptic: bool = Field(default=True, description="Enable skeptic archetype")
    verifier: bool = Field(default=True, description="Enable verifier archetype")
    librarian: bool = Field(default=False, description="Enable librarian archetype")
    cartographer: bool = Field(
        default=False, description="Enable cartographer archetype"
    )
    oracle: bool = Field(default=True, description="Enable oracle archetype")
    auditor: bool = Field(default=True, description="Enable auditor archetype")

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
    auditor_config: AuditorConfig = Field(
        default_factory=AuditorConfig,
        description="Auditor-specific configuration",
    )
    models: dict[str, str] = Field(
        default_factory=dict, description="Per-archetype model overrides"
    )
    allowlists: dict[str, list[str]] = Field(
        default_factory=dict, description="Per-archetype command allowlists"
    )
    max_turns: dict[str, int] = Field(
        default_factory=dict,
        description="Per-archetype maximum turn limits",
    )
    thinking: dict[str, ThinkingConfig] = Field(
        default_factory=dict,
        description="Per-archetype extended thinking configuration",
    )

    @field_validator("coder")
    @classmethod
    def coder_always_enabled(cls, v: bool) -> bool:
        if not v:
            logger.warning("archetypes.coder cannot be disabled; ignoring")
        return True

    @field_validator("max_turns")
    @classmethod
    def validate_max_turns_non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        """Reject negative max_turns values.

        Requirements: 56-REQ-1.E1
        """
        for archetype, turns in v.items():
            if turns < 0:
                raise ValueError(
                    f"max_turns for '{archetype}' must be >= 0, got {turns}"
                )
        return v


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
    cache_read_price_per_m: float = Field(
        default=0.0, description="USD per million cache-read input tokens"
    )
    cache_creation_price_per_m: float = Field(
        default=0.0, description="USD per million cache-creation input tokens"
    )

    # Requirements: 34-REQ-2.E2
    clamp_negative_price = _clamped_validator(
        "input_price_per_m",
        "output_price_per_m",
        "cache_read_price_per_m",
        "cache_creation_price_per_m",
        ge=0.0,
    )


def _default_pricing_models() -> dict[str, ModelPricing]:
    """Return default pricing for all known Claude models.

    Requirements: 34-REQ-2.2, 34-REQ-5.1
    """
    return {
        "claude-haiku-4-5": ModelPricing(
            input_price_per_m=1.00,
            output_price_per_m=5.00,
            cache_read_price_per_m=0.10,
            cache_creation_price_per_m=1.25,
        ),
        "claude-sonnet-4-6": ModelPricing(
            input_price_per_m=3.00,
            output_price_per_m=15.00,
            cache_read_price_per_m=0.30,
            cache_creation_price_per_m=3.75,
        ),
        "claude-opus-4-6": ModelPricing(
            input_price_per_m=5.00,
            output_price_per_m=25.00,
            cache_read_price_per_m=0.50,
            cache_creation_price_per_m=6.25,
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

    clamp_min_historical = _clamped_validator(
        "min_outcomes_for_historical", ge=1, le=1000, cast=int
    )
    clamp_min_regression = _clamped_validator(
        "min_outcomes_for_regression", ge=5, le=10000, cast=int
    )


class BlockingConfig(BaseModel):
    """Blocking threshold learning configuration.

    Requirements: 39-REQ-10.2, 39-REQ-10.3
    """

    model_config = ConfigDict(extra="ignore")

    learn_thresholds: bool = Field(
        default=False,
        description="Learn blocking thresholds from history",
    )
    min_decisions_for_learning: int = Field(
        default=20,
        description="Minimum blocking decisions before learning thresholds",
    )
    max_false_negative_rate: float = Field(
        default=0.1,
        description="Maximum acceptable false negative rate",
    )

    clamp_min_decisions = _clamped_validator(
        "min_decisions_for_learning", ge=1, le=1000, cast=int
    )
    clamp_fnr = _clamped_validator("max_false_negative_rate", ge=0.0, le=1.0)


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
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    planning: PlanningConfig = Field(default_factory=PlanningConfig)
    blocking: BlockingConfig = Field(default_factory=BlockingConfig)

    # Lazy import to avoid circular dependency; default is constructed
    # from NightShiftConfig which lives in agent_fox.nightshift.config.
    night_shift: Any = Field(default=None, description="Night-shift configuration")

    @model_validator(mode="after")
    def _default_night_shift(self) -> Self:
        """Populate night_shift with NightShiftConfig if not provided."""
        if self.night_shift is None:
            from agent_fox.nightshift.config import NightShiftConfig

            self.night_shift = NightShiftConfig()
        return self


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
