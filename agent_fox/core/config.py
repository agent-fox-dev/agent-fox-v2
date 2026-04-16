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
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self

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


class Clamped:
    """Annotation marking a numeric field for automatic clamping."""

    __slots__ = ("ge", "le", "cast")

    def __init__(
        self,
        ge: int | float | None = None,
        le: int | float | None = None,
        cast: type | None = None,
    ) -> None:
        self.ge = ge
        self.le = le
        self.cast = cast


def _auto_clamp_validator() -> Any:
    """Return a model_validator that clamps all fields annotated with Clamped."""

    @model_validator(mode="after")
    def _validate(self: Any) -> Any:
        for name, field_info in type(self).model_fields.items():
            for meta in field_info.metadata:
                if isinstance(meta, Clamped):
                    value = getattr(self, name)
                    if value is None:
                        continue
                    clamped = _clamp(value, ge=meta.ge, le=meta.le, field_name=name)
                    if meta.cast is not None:
                        clamped = meta.cast(clamped)
                    if clamped != value:
                        object.__setattr__(self, name, clamped)
        return self

    return _validate


class RoutingConfig(BaseModel):
    """Model routing configuration.

    Requirements: 89-REQ-4.1, 89-REQ-4.2
    """

    model_config = ConfigDict(extra="ignore")

    retries_before_escalation: Annotated[int, Clamped(ge=0, le=3, cast=int)] = Field(
        default=1, description="Retries before model escalation"
    )
    max_timeout_retries: Annotated[int, Clamped(ge=0, cast=int)] = Field(
        default=2,
        description="Maximum timeout retries before falling through to escalation",
    )
    timeout_multiplier: Annotated[float, Clamped(ge=1.0)] = Field(
        default=1.5,
        description=("Factor by which max_turns and session_timeout are extended on timeout retry"),
    )
    timeout_ceiling_factor: Annotated[float, Clamped(ge=1.0)] = Field(
        default=2.0,
        description=("Maximum session_timeout as a factor of the original configured value"),
    )

    _auto_clamp = _auto_clamp_validator()


class OrchestratorConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parallel: Annotated[int, Clamped(ge=1, le=8)] = Field(default=2, description="Maximum parallel sessions")
    sync_interval: Annotated[int, Clamped(ge=0)] = Field(default=5, description="Sync interval in task groups")
    hot_load: bool = Field(default=True, description="Hot-load specs between sessions")
    max_retries: Annotated[int, Clamped(ge=0)] = Field(default=2, description="Maximum retries per task group")
    session_timeout: Annotated[int, Clamped(ge=1)] = Field(default=30, description="Session timeout in minutes")
    inter_session_delay: Annotated[int, Clamped(ge=0)] = Field(
        default=3, description="Delay between sessions in seconds"
    )
    max_cost: float | None = Field(default=None, description="Maximum cost limit")
    max_sessions: int | None = Field(default=None, description="Maximum number of sessions")
    audit_retention_runs: Annotated[int, Clamped(ge=1, cast=int)] = Field(
        default=20,
        description="Maximum number of runs to retain in the audit log",
    )
    max_blocked_fraction: float | None = Field(
        default=None,
        description=("Stop the run when this fraction of nodes are blocked (0.0-1.0). None = disabled."),
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
        default=8.0,
        ge=0.0,
        description="Maximum USD spend per session, 0 = unlimited",
    )

    causal_context_limit: Annotated[int, Clamped(ge=10, le=10000, cast=int)] = Field(
        default=200,
        description=(
            "Maximum number of prior facts included in the causal extraction "
            "prompt. When total non-superseded facts exceed this limit, prior "
            "facts are ranked by embedding similarity to the new facts and "
            "only the top N are included."
        ),
    )

    watch_interval: Annotated[int, Clamped(ge=10, cast=int)] = Field(
        default=60,
        description=("Seconds between watch polls when --watch is active. Values below 10 are clamped to 10."),
    )

    _auto_clamp = _auto_clamp_validator()

    @field_validator("max_blocked_fraction")
    @classmethod
    def clamp_max_blocked_fraction(cls, v: float | None) -> float | None:
        if v is None:
            return v
        return _clamp(v, ge=0.0, le=1.0, field_name="max_blocked_fraction")


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coding: str = Field(default="ADVANCED", description="Model tier for coding tasks")
    memory_extraction: str = Field(default="SIMPLE", description="Model tier for memory extraction")
    fallback_model: str = Field(
        default="claude-sonnet-4-6",
        description="Fallback model ID when primary is unavailable",
    )


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bash_allowlist: list[str] | None = Field(default=None, description="Allowed bash commands")
    bash_allowlist_extend: list[str] = Field(default_factory=list, description="Additional allowed bash commands")


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


class RetrievalConfig(BaseModel):
    """Retrieval tuning parameters. Lives under [knowledge.retrieval].

    Requirements: 104-REQ-5.3, 104-REQ-5.E1
    """

    model_config = ConfigDict(extra="ignore")

    rrf_k: int = Field(default=60, description="RRF smoothing constant")
    max_facts: int = Field(default=50, description="Maximum facts in anchor set")
    token_budget: int = Field(
        default=30_000,
        description="Maximum characters for formatted context block",
    )
    keyword_top_k: int = Field(default=100, description="Candidate cap for keyword signal")
    vector_top_k: int = Field(default=50, description="Candidate cap for vector signal")
    entity_max_depth: int = Field(default=2, description="Max traversal depth for entity signal")
    entity_max_entities: int = Field(default=50, description="Max entities traversed in entity signal")
    causal_max_depth: int = Field(default=3, description="Max traversal depth for causal signal")


class KnowledgeConfig(BaseModel):
    """Knowledge store and fact selection configuration.

    Requirements: 39-REQ-4.2
    """

    model_config = ConfigDict(extra="ignore")

    store_path: str = Field(default=".agent-fox/knowledge.duckdb", description="Path to knowledge store")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Embedding model for knowledge")
    embedding_dimensions: int = Field(default=384, description="Embedding vector dimensions")
    ask_top_k: Annotated[int, Clamped(ge=1)] = Field(default=20, description="Number of results for knowledge queries")
    ask_synthesis_model: str = Field(default="STANDARD", description="Model tier for answer synthesis")
    confidence_threshold: Annotated[float, Clamped(ge=0.0, le=1.0)] = Field(
        default=0.5,
        description="Minimum confidence for fact inclusion in session context",
    )
    fact_cache_enabled: bool = Field(
        default=True,
        description="Pre-compute fact rankings at plan time",
    )
    dedup_similarity_threshold: float = Field(
        default=0.92,
        description="Cosine similarity threshold for near-duplicate detection",
    )
    contradiction_similarity_threshold: float = Field(
        default=0.8,
        description="Cosine similarity threshold for contradiction candidates",
    )
    contradiction_model: str = Field(
        default="SIMPLE",
        description="Model tier for contradiction classification LLM calls",
    )
    decay_half_life_days: float = Field(
        default=90.0,
        description="Days for fact confidence to halve",
    )
    decay_floor: float = Field(
        default=0.1,
        description="Effective confidence below which facts are auto-superseded",
    )
    cleanup_fact_threshold: int = Field(
        default=500,
        description="Active fact count above which decay cleanup runs",
    )
    cleanup_enabled: bool = Field(
        default=True,
        description="Enable/disable end-of-run fact lifecycle cleanup",
    )
    retrieval: RetrievalConfig = Field(
        default_factory=RetrievalConfig,
        description="Adaptive retrieval configuration (rrf_k, max_facts, token_budget, etc.)",
    )

    _auto_clamp = _auto_clamp_validator()


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


class PerArchetypeConfig(BaseModel):
    """Unified per-archetype configuration table.

    Used via ``[archetypes.overrides.<name>]`` in config.toml. Provides a
    single, consolidated surface for all per-archetype knobs that previously
    required separate dict fields (``models``, ``max_turns``, ``thinking``,
    ``allowlists``).

    Requirements: 207-REQ-1, 207-REQ-2, 207-REQ-3
    """

    model_config = ConfigDict(extra="ignore")

    model_tier: str | None = Field(
        default=None,
        description="Model tier override (SIMPLE, STANDARD, ADVANCED). None = use registry default.",
    )
    max_turns: int | None = Field(
        default=None,
        description="Max turns override. 0 = unlimited. None = use registry default.",
        ge=0,
    )
    thinking_mode: Literal["enabled", "adaptive", "disabled"] | None = Field(
        default=None,
        description="Extended thinking mode. None = use registry default.",
    )
    thinking_budget: int | None = Field(
        default=None,
        description="Extended thinking budget tokens. None = use registry default.",
        ge=0,
    )
    allowlist: list[str] | None = Field(
        default=None,
        description="Bash command allowlist override. None = use registry default.",
    )
    modes: dict[str, PerArchetypeConfig] = Field(
        default_factory=dict,
        description=(
            "Per-mode overrides for this archetype. TOML: [archetypes.overrides.<name>.modes.<mode>]. 97-REQ-3.1"
        ),
    )

    @model_validator(mode="after")
    def validate_thinking(self) -> Self:
        """thinking_budget must be > 0 when thinking_mode is 'enabled'."""
        if self.thinking_mode == "enabled" and self.thinking_budget is not None and self.thinking_budget <= 0:
            raise ValueError("thinking_budget must be > 0 when thinking_mode is 'enabled'")
        return self


# Required for self-referential Pydantic model (modes: dict[str, PerArchetypeConfig])
PerArchetypeConfig.model_rebuild()


class ArchetypeInstancesConfig(BaseModel):
    """Per-archetype instance count configuration.

    Requirements: 26-REQ-6.2, 46-REQ-2.2, 98-REQ-8.3
    """

    model_config = ConfigDict(extra="ignore")

    reviewer: Annotated[int, Clamped(ge=1, le=5)] = Field(
        default=1, description="Number of reviewer instances (replaces skeptic+auditor)"
    )
    verifier: int = Field(default=1, description="Number of verifier instances (max clamped to 1)")

    _auto_clamp = _auto_clamp_validator()

    @field_validator("verifier")
    @classmethod
    def clamp_verifier_to_one(cls, v: int) -> int:
        """Verifier is always single-instance (98-REQ-6.2)."""
        if v != 1:
            logger.warning(
                "verifier instances clamped from %d to 1 (maximum is 1)",
                v,
            )
        return 1


class SkepticConfig(BaseModel):
    """Skeptic-specific configuration.

    Requirements: 26-REQ-8.4
    """

    model_config = ConfigDict(extra="ignore")

    block_threshold: Annotated[int, Clamped(ge=0)] = Field(default=3, description="Finding count to block merge")

    _auto_clamp = _auto_clamp_validator()


class OracleSettings(BaseModel):
    """Oracle-specific configuration.

    Requirements: 32-REQ-10.2, 32-REQ-10.E1
    """

    model_config = ConfigDict(extra="ignore")

    block_threshold: int | None = Field(default=None, description="Drift count to block (None = advisory)")

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

    min_ts_entries: Annotated[int, Clamped(ge=1, cast=int)] = Field(
        default=5, description="Minimum TS entries to trigger auditor injection"
    )
    max_retries: Annotated[int, Clamped(ge=0, cast=int)] = Field(
        default=2, description="Maximum auditor-coder retry iterations"
    )

    _auto_clamp = _auto_clamp_validator()


class ReviewerConfig(BaseModel):
    """Reviewer-specific configuration, replacing SkepticConfig + OracleSettings + AuditorConfig.

    Contains mode-specific settings keyed by mode name concept, stored as flat fields.

    Requirements: 98-REQ-8.2
    """

    model_config = ConfigDict(extra="ignore")

    pre_review_block_threshold: Annotated[int, Clamped(ge=0)] = Field(
        default=3,
        description="Finding count to block merge for pre-review mode",
    )
    drift_review_block_threshold: int | None = Field(
        default=None,
        description="Drift count to block for drift-review mode (None = advisory only)",
    )
    audit_min_ts_entries: Annotated[int, Clamped(ge=1, cast=int)] = Field(
        default=5,
        description="Minimum TS entries to trigger audit-review injection",
    )
    audit_max_retries: Annotated[int, Clamped(ge=0, cast=int)] = Field(
        default=2,
        description="Maximum audit-review/coder retry iterations",
    )

    _auto_clamp = _auto_clamp_validator()


class CustomArchetypeConfig(BaseModel):
    """Configuration for a custom (project-defined) archetype.

    Specifies which built-in archetype's permission profile the custom
    archetype should inherit. Validated semantically at runtime by
    ``get_archetype()`` — the config layer only validates types/syntax.

    Requirements: 99-REQ-4.2
    """

    model_config = ConfigDict(extra="ignore")

    permissions: str = Field(
        default="coder",
        description="Built-in archetype name whose permissions to inherit",
    )


class ArchetypesConfig(BaseModel):
    """Archetype enable/disable toggles and per-archetype configuration.

    Requirements: 26-REQ-6.1 through 26-REQ-6.5, 26-REQ-6.E1, 46-REQ-2.1,
                  98-REQ-8.1, 98-REQ-8.2, 98-REQ-8.3, 98-REQ-8.E1
    """

    model_config = ConfigDict(extra="forbid")

    coder: bool = Field(default=True, description="Enable coder archetype")
    reviewer: bool = Field(default=True, description="Enable reviewer archetype (replaces skeptic, oracle, auditor)")
    verifier: bool = Field(default=True, description="Enable verifier archetype")

    instances: ArchetypeInstancesConfig = Field(
        default_factory=ArchetypeInstancesConfig,
        description="Per-archetype instance counts",
    )
    reviewer_config: ReviewerConfig = Field(
        default_factory=ReviewerConfig,
        description="Reviewer-specific configuration (replaces skeptic_config, oracle_settings, auditor_config)",
    )
    models: dict[str, str] = Field(default_factory=dict, description="Per-archetype model overrides")
    allowlists: dict[str, list[str]] = Field(default_factory=dict, description="Per-archetype command allowlists")
    max_turns: dict[str, int] = Field(
        default_factory=dict,
        description="Per-archetype maximum turn limits",
    )
    thinking: dict[str, ThinkingConfig] = Field(
        default_factory=dict,
        description="Per-archetype extended thinking configuration",
    )
    overrides: dict[str, PerArchetypeConfig] = Field(
        default_factory=dict,
        description=(
            "Unified per-archetype configuration tables. "
            "TOML: [archetypes.overrides.<name>]. "
            "Takes precedence over models/max_turns/thinking/allowlists dicts."
        ),
    )
    custom: dict[str, CustomArchetypeConfig] = Field(
        default_factory=dict,
        description=(
            "Custom archetype configurations keyed by archetype name. "
            "TOML: [archetypes.custom.<name>]. "
            "Requirements: 99-REQ-4.2"
        ),
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
                raise ValueError(f"max_turns for '{archetype}' must be >= 0, got {turns}")
        return v

    @model_validator(mode="before")
    @classmethod
    def reject_old_archetype_keys(cls, data: Any) -> Any:
        """Raise a validation error when old archetype config keys are used.

        Keys that were deprecated (not obsolete) are silently stripped with a
        warning logged, rather than raising a hard error.

        Requirements: 98-REQ-1.E1, 98-REQ-8.E1, 100-REQ-2.E1
        """
        if not isinstance(data, dict):
            return data

        # Deprecated keys that are silently stripped with a deprecation warning
        # (100-REQ-2.E1: triage absorbed into maintainer:hunt in spec 100)
        deprecated_keys = {"triage": "maintainer:hunt"}
        found_deprecated = [k for k in deprecated_keys if k in data]
        if found_deprecated:
            for key in found_deprecated:
                logger.warning(
                    "Deprecated config key 'archetypes.%s' will be ignored. "
                    "The triage archetype has been absorbed into maintainer:hunt. "
                    "Please remove this key from your config. (100-REQ-2.E1)",
                    key,
                )
            data = {k: v for k, v in data.items() if k not in found_deprecated}

        old_keys = {
            "skeptic": "reviewer (pre-review mode)",
            "oracle": "reviewer (drift-review mode)",
            "auditor": "reviewer (audit-review mode)",
            "skeptic_config": "reviewer_config",
            "skeptic_settings": "reviewer_config",
            "oracle_settings": "reviewer_config",
            "auditor_config": "reviewer_config",
            "fix_reviewer": "reviewer (fix-review mode)",
            "fix_coder": "coder (fix mode)",
        }
        found = [k for k in old_keys if k in data]
        if found:
            guidance = "; ".join(f"'{k}' → use '{old_keys[k]}'" for k in found)
            raise ValueError(
                f"Obsolete archetype config key(s) detected: {found!r}. "
                f"Please migrate to the reviewer archetype with modes. "
                f"Migration: {guidance}. "
                f"See docs for the new reviewer config schema."
            )
        return data


class ModelPricing(BaseModel):
    """Pricing for a single model.

    Requirements: 34-REQ-2.1, 34-REQ-2.E2
    """

    model_config = ConfigDict(extra="ignore")

    # Requirements: 34-REQ-2.E2
    input_price_per_m: Annotated[float, Clamped(ge=0.0)] = Field(
        default=0.0, description="USD per million input tokens"
    )
    output_price_per_m: Annotated[float, Clamped(ge=0.0)] = Field(
        default=0.0, description="USD per million output tokens"
    )
    cache_read_price_per_m: Annotated[float, Clamped(ge=0.0)] = Field(
        default=0.0, description="USD per million cache-read input tokens"
    )
    cache_creation_price_per_m: Annotated[float, Clamped(ge=0.0)] = Field(
        default=0.0, description="USD per million cache-creation input tokens"
    )

    _auto_clamp = _auto_clamp_validator()


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
        "claude-opus-4-5": ModelPricing(
            input_price_per_m=5.00,
            output_price_per_m=25.00,
            cache_read_price_per_m=0.50,
            cache_creation_price_per_m=6.25,
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

    duration_ordering: bool = Field(default=True, description="Sort ready tasks by predicted duration")
    min_outcomes_for_historical: Annotated[int, Clamped(ge=1, le=1000, cast=int)] = Field(
        default=10,
        description="Minimum outcomes before using historical duration data",
    )
    min_outcomes_for_regression: Annotated[int, Clamped(ge=5, le=10000, cast=int)] = Field(
        default=30,
        description="Minimum outcomes before training duration regression model",
    )
    file_conflict_detection: bool = Field(
        default=False,
        description="Detect file conflicts between parallel tasks",
    )

    _auto_clamp = _auto_clamp_validator()


class BlockingConfig(BaseModel):
    """Blocking threshold learning configuration.

    Requirements: 39-REQ-10.2, 39-REQ-10.3
    """

    model_config = ConfigDict(extra="ignore")

    learn_thresholds: bool = Field(
        default=False,
        description="Learn blocking thresholds from history",
    )
    min_decisions_for_learning: Annotated[int, Clamped(ge=1, le=1000, cast=int)] = Field(
        default=20,
        description="Minimum blocking decisions before learning thresholds",
    )
    max_false_negative_rate: Annotated[float, Clamped(ge=0.0, le=1.0)] = Field(
        default=0.1,
        description="Maximum acceptable false negative rate",
    )

    _auto_clamp = _auto_clamp_validator()


class CachePolicy(StrEnum):
    """Prompt caching strategy for auxiliary API calls.

    Requirements: 77-REQ-1.1, 77-REQ-1.3, 77-REQ-1.4, 77-REQ-1.5
    """

    NONE = "NONE"
    DEFAULT = "DEFAULT"
    EXTENDED = "EXTENDED"


class CachingConfig(BaseModel):
    """Prompt caching configuration.

    Requirements: 77-REQ-1.1, 77-REQ-1.2, 77-REQ-1.E1
    """

    model_config = ConfigDict(extra="ignore")

    cache_policy: CachePolicy = Field(
        default=CachePolicy.DEFAULT,
        description="Caching policy: NONE, DEFAULT (5-min), or EXTENDED (1-hour TTL)",
    )

    @field_validator("cache_policy", mode="before")
    @classmethod
    def _parse_policy_case_insensitive(cls, v: Any) -> Any:
        """Accept policy values case-insensitively."""
        if isinstance(v, str):
            return v.upper()
        return v


class NightShiftCategoryConfig(BaseModel):
    """Per-category enable/disable toggles.

    All eight built-in categories are enabled by default.

    Requirements: 61-REQ-9.2, 67-REQ-5.1
    """

    model_config = ConfigDict(extra="ignore")

    dependency_freshness: bool = True
    todo_fixme: bool = True
    test_coverage: bool = True
    deprecated_api: bool = True
    linter_debt: bool = True
    dead_code: bool = True
    documentation_drift: bool = True
    quality_gate: bool = True


class NightShiftConfig(BaseModel):
    """Night-shift daemon configuration.

    Requirements: 61-REQ-9.1, 61-REQ-9.E1
    """

    model_config = ConfigDict(extra="ignore")

    issue_check_interval: int = Field(
        default=900,
        description="Seconds between issue checks (minimum 60)",
    )
    hunt_scan_interval: int = Field(
        default=21600,
        description="Seconds between hunt scans (minimum 60)",
    )
    categories: NightShiftCategoryConfig = Field(
        default_factory=NightShiftCategoryConfig,
        description="Category enable/disable toggles",
    )
    quality_gate_timeout: int = Field(
        default=600,
        description="Per-check timeout in seconds (minimum 60)",
    )

    # --- New fields for daemon framework (spec 85) ---

    spec_interval: int = Field(
        default=300,
        description="Seconds between spec executor cycles (minimum 10)",
    )
    enabled_streams: list[str] = Field(
        default=["specs", "fixes", "hunts"],
        description="List of enabled work stream config names",
    )
    merge_strategy: str = Field(
        default="direct",
        description="Merge strategy: 'direct' or 'pr'",
    )

    # --- Fix branch push (spec 93) ---

    push_fix_branch: bool = Field(
        default=False,
        description="Push fix branches to origin before harvest",
    )

    @field_validator("spec_interval")
    @classmethod
    def clamp_spec_interval(cls, v: int) -> int:
        """Clamp spec_interval to a minimum of 10 seconds.

        Requirements: 85-REQ-9.E1
        """
        if v < 10:
            logger.warning(
                "Config field 'spec_interval' value %d below minimum, clamped to 10",
                v,
            )
            return 10
        return v

    @field_validator("enabled_streams")
    @classmethod
    def default_empty_enabled_streams(cls, v: list[str]) -> list[str]:
        """Treat empty enabled_streams as all streams enabled.

        Requirements: 85-REQ-9.E2
        """
        if not v:
            return ["specs", "fixes", "hunts"]
        return v

    @field_validator("issue_check_interval", "hunt_scan_interval")
    @classmethod
    def clamp_interval_minimum(cls, v: int, info: object) -> int:
        """Clamp intervals to a minimum of 60 seconds.

        Requirements: 61-REQ-9.E1
        """
        if v < 60:
            logger.warning(
                "Config field '%s' value %d below minimum, clamped to 60",
                getattr(info, "field_name", "interval"),
                v,
            )
            return 60
        return v

    @field_validator("quality_gate_timeout")
    @classmethod
    def clamp_quality_gate_timeout(cls, v: int, info: object) -> int:
        """Clamp quality_gate_timeout to a minimum of 60 seconds.

        Requirements: 67-REQ-5.3
        """
        if v < 60:
            logger.warning(
                "Config field '%s' value %d below minimum, clamped to 60",
                getattr(info, "field_name", "quality_gate_timeout"),
                v,
            )
            return 60
        return v


class AgentFoxConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    theme: ThemeConfig = Field(default_factory=ThemeConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    archetypes: ArchetypesConfig = Field(default_factory=ArchetypesConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    planning: PlanningConfig = Field(default_factory=PlanningConfig)
    blocking: BlockingConfig = Field(default_factory=BlockingConfig)
    caching: CachingConfig = Field(default_factory=CachingConfig)
    night_shift: NightShiftConfig = Field(default_factory=NightShiftConfig)


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

    # Security: reject symlinks to prevent path traversal (CWE-59)
    if path.is_symlink():
        logger.warning("Config file is a symlink; skipping for security")
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
