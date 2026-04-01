"""Config schema: types, metadata, and Pydantic model introspection.

Extracts schema information from Pydantic models for config template
generation and merge operations.

Requirements: 33-REQ-4.1, 33-REQ-4.2, 33-REQ-4.E1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# Hardcoded bounds map: (model_class_name, field_name) -> bounds string.
# Bounds are encoded in field_validator functions using _clamp() and cannot
# be extracted programmatically without source inspection. This map is
# simpler and sufficient since bounds rarely change.
_BOUNDS_MAP: dict[tuple[str, str], str] = {
    # OrchestratorConfig
    ("OrchestratorConfig", "parallel"): "1-8",
    ("OrchestratorConfig", "sync_interval"): ">=0",
    ("OrchestratorConfig", "max_retries"): ">=0",
    ("OrchestratorConfig", "session_timeout"): ">=1",
    ("OrchestratorConfig", "inter_session_delay"): ">=0",
    ("OrchestratorConfig", "watch_interval"): ">=10",
    # RoutingConfig
    ("RoutingConfig", "retries_before_escalation"): "0-3",
    ("RoutingConfig", "training_threshold"): "5-1000",
    ("RoutingConfig", "accuracy_threshold"): "0.5-1.0",
    ("RoutingConfig", "retrain_interval"): "5-100",
    # HookConfig
    ("HookConfig", "timeout"): ">=1",
    # KnowledgeConfig
    ("KnowledgeConfig", "ask_top_k"): ">=1",
    # ArchetypeInstancesConfig
    ("ArchetypeInstancesConfig", "skeptic"): "1-5",
    ("ArchetypeInstancesConfig", "verifier"): "1-5",
    # SkepticConfig
    ("SkepticConfig", "block_threshold"): ">=0",
    # OracleSettings
    ("OracleSettings", "block_threshold"): ">=1",
    # AuditorConfig
    ("AuditorConfig", "min_ts_entries"): ">=1",
    ("AuditorConfig", "max_retries"): ">=0",
    # ArchetypeInstancesConfig (auditor)
    ("ArchetypeInstancesConfig", "auditor"): "1-5",
}

# Sections that appear in the simplified config template (active or commented).
# Sections NOT in this set are completely omitted from the template output.
# Requirements: 68-REQ-1.1, 68-REQ-1.2
_VISIBLE_SECTIONS: set[str] = {
    "orchestrator",
    "models",
    "archetypes",
    "archetypes.instances",
    "archetypes.thinking",
    "archetypes.thinking.coder",
    "archetypes.thinking.skeptic",
    "archetypes.thinking.verifier",
    "security",
}

# Fields rendered as active (uncommented) in the default config template.
# Keyed by (section_path, field_name). Sections with promoted fields are
# rendered first with an active [section] header; remaining sections follow
# as commented # [section] blocks.
_PROMOTED_DEFAULTS: set[tuple[str, str]] = {
    ("orchestrator", "parallel"),
    ("orchestrator", "quality_gate"),
    ("orchestrator", "max_budget_usd"),
    ("models", "coding"),
    ("archetypes", "coder"),
    ("archetypes", "skeptic"),
    ("archetypes", "verifier"),
    ("archetypes", "oracle"),
    ("archetypes", "auditor"),
    ("archetypes.instances", "verifier"),
}

# Template-level value overrides for promoted fields.
# These override the model's default value in the generated template only.
# Requirements: 68-REQ-2.1, 68-REQ-2.2, 68-REQ-2.4, 68-REQ-2.5
_PROMOTED_DEFAULTS_OVERRIDES: dict[tuple[str, str], object] = {
    ("orchestrator", "quality_gate"): "make check",
    ("orchestrator", "max_budget_usd"): 5.0,
}

# Default descriptions for fields that lack description metadata.
# Keyed by (model_class_name, field_name).
# Requirements: 68-REQ-3.1, 68-REQ-3.2, 68-REQ-3.3
_DEFAULT_DESCRIPTIONS: dict[tuple[str, str], str] = {
    # OrchestratorConfig
    ("OrchestratorConfig", "parallel"): "Maximum parallel sessions",
    ("OrchestratorConfig", "sync_interval"): "Sync interval in task groups",
    ("OrchestratorConfig", "hot_load"): "Hot-load specs between sessions",
    ("OrchestratorConfig", "max_retries"): "Maximum retries per task group",
    ("OrchestratorConfig", "session_timeout"): "Session timeout in minutes",
    ("OrchestratorConfig", "inter_session_delay"): "Delay between sessions in seconds",
    ("OrchestratorConfig", "max_cost"): "Maximum cost limit",
    ("OrchestratorConfig", "max_sessions"): "Maximum number of sessions",
    ("OrchestratorConfig", "max_blocked_fraction"): (
        "Stop run when this fraction of nodes are blocked"
    ),
    ("OrchestratorConfig", "quality_gate"): (
        "Shell command run after each coder session to verify quality"
    ),
    ("OrchestratorConfig", "max_budget_usd"): (
        "Per-session budget cap in USD (0 = unlimited)"
    ),
    # RoutingConfig
    ("RoutingConfig", "retries_before_escalation"): "Retries before model escalation",
    ("RoutingConfig", "training_threshold"): "Training data threshold",
    ("RoutingConfig", "accuracy_threshold"): "Accuracy threshold for routing",
    ("RoutingConfig", "retrain_interval"): "Retrain interval",
    # ModelConfig
    ("ModelConfig", "coding"): (
        "Model tier for coding tasks: SIMPLE, STANDARD, or ADVANCED"
    ),
    ("ModelConfig", "memory_extraction"): "Model tier for memory extraction",
    # HookConfig
    ("HookConfig", "pre_code"): "Commands to run before coding",
    ("HookConfig", "post_code"): "Commands to run after coding",
    ("HookConfig", "sync_barrier"): "Commands to run at sync barriers",
    ("HookConfig", "timeout"): "Hook command timeout in seconds",
    ("HookConfig", "modes"): "Hook modes configuration",
    # SecurityConfig
    ("SecurityConfig", "bash_allowlist"): "Allowed bash commands",
    ("SecurityConfig", "bash_allowlist_extend"): "Additional allowed bash commands",
    # ThemeConfig
    ("ThemeConfig", "playful"): "Enable playful output style",
    ("ThemeConfig", "header"): "Header text style",
    ("ThemeConfig", "success"): "Success text style",
    ("ThemeConfig", "error"): "Error text style",
    ("ThemeConfig", "warning"): "Warning text style",
    ("ThemeConfig", "info"): "Info text style",
    ("ThemeConfig", "tool"): "Tool text style",
    ("ThemeConfig", "muted"): "Muted text style",
    # PlatformConfig
    ("PlatformConfig", "type"): "Platform type (none or github)",
    ("PlatformConfig", "url"): "Issue tracker URL — overrides default for type",
    # KnowledgeConfig
    ("KnowledgeConfig", "store_path"): "Path to knowledge store",
    ("KnowledgeConfig", "embedding_model"): "Embedding model for knowledge",
    ("KnowledgeConfig", "embedding_dimensions"): "Embedding vector dimensions",
    ("KnowledgeConfig", "ask_top_k"): "Number of results for knowledge queries",
    ("KnowledgeConfig", "ask_synthesis_model"): "Model tier for answer synthesis",
    # ArchetypesConfig
    ("ArchetypesConfig", "coder"): "Enable coder archetype",
    ("ArchetypesConfig", "skeptic"): "Code review — flags issues before merge",
    ("ArchetypesConfig", "verifier"): (
        "Post-code verification — runs tests, checks correctness"
    ),
    ("ArchetypesConfig", "librarian"): "Enable librarian archetype",
    ("ArchetypesConfig", "cartographer"): "Enable cartographer archetype",
    ("ArchetypesConfig", "oracle"): (
        "Spec-drift detection — compares code against specs"
    ),
    ("ArchetypesConfig", "auditor"): (
        "Test-quality gate — ensures test coverage meets standards"
    ),
    ("ArchetypesConfig", "models"): "Per-archetype model overrides",
    ("ArchetypesConfig", "allowlists"): "Per-archetype command allowlists",
    # ArchetypeInstancesConfig
    ("ArchetypeInstancesConfig", "skeptic"): "Number of skeptic instances",
    ("ArchetypeInstancesConfig", "verifier"): (
        "Run multiple verifier instances for deeper coverage"
    ),
    ("ArchetypeInstancesConfig", "auditor"): "Number of auditor instances",
    # AuditorConfig
    ("AuditorConfig", "min_ts_entries"): (
        "Minimum TS entries to trigger auditor injection"
    ),
    ("AuditorConfig", "max_retries"): "Maximum auditor-coder retry iterations",
    # SkepticConfig
    ("SkepticConfig", "block_threshold"): "Finding count to block merge",
    # OracleSettings
    ("OracleSettings", "block_threshold"): "Drift count to block (None = advisory)",
}


@dataclass
class FieldSpec:
    """Describes a single config field for template generation."""

    name: str  # TOML key name (uses alias if defined)
    section: str  # dot-separated section path
    python_type: str  # human-readable type string
    default: Any  # resolved default value (factory invoked)
    description: str  # brief description for the comment
    bounds: str | None  # e.g. "1-8" or ">=0", None if unconstrained
    is_nested: bool  # True if this field is a nested BaseModel


@dataclass
class SectionSpec:
    """Describes a config section (TOML table)."""

    path: str  # dot-separated section path
    fields: list[FieldSpec] = field(default_factory=list)
    subsections: list[SectionSpec] = field(default_factory=list)


def _get_toml_key(field_name: str, field_info: FieldInfo) -> str:
    """Get the TOML key for a field, using alias if defined."""
    if field_info.alias is not None:
        return field_info.alias
    return field_name


def _resolve_default(field_info: FieldInfo) -> Any:
    """Resolve the default value for a field, invoking factories.

    Requirements: 33-REQ-4.E1
    """
    from pydantic_core import PydanticUndefined

    if field_info.default_factory is not None:
        return field_info.default_factory()
    if field_info.default is not PydanticUndefined and field_info.default is not None:
        return field_info.default
    if field_info.default is PydanticUndefined:
        return None
    return field_info.default


def _get_python_type_str(annotation: Any) -> str:
    """Convert a type annotation to a human-readable string."""
    if annotation is None:
        return "any"
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        # Handle Optional (Union with None)
        args = getattr(annotation, "__args__", ())
        if origin is type(None):
            return "none"
        # types.UnionType for X | Y
        import types

        if origin is types.UnionType or str(origin) in (
            "typing.Union",
            "types.UnionType",
        ):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return _get_python_type_str(non_none[0])
            return " | ".join(_get_python_type_str(a) for a in non_none)
        if origin is list:
            return "list"
        if origin is dict:
            return "dict"
        return str(origin)
    # Check for union types (Python 3.10+ X | Y)
    import types

    if isinstance(annotation, types.UnionType):
        args = annotation.__args__
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _get_python_type_str(non_none[0])
        return " | ".join(_get_python_type_str(a) for a in non_none)
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


def _is_nested_model(annotation: Any) -> bool:
    """Check if a type annotation is a nested BaseModel."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return False


def _get_description(
    model_class: type[BaseModel], field_name: str, field_info: FieldInfo
) -> str:
    """Get description for a field from metadata or fallback map."""
    if field_info.description:
        return field_info.description
    key = (model_class.__name__, field_name)
    return _DEFAULT_DESCRIPTIONS.get(key, field_name.replace("_", " ").title())


def _get_bounds(model_class: type[BaseModel], field_name: str) -> str | None:
    """Get bounds string for a field from the hardcoded map."""
    key = (model_class.__name__, field_name)
    return _BOUNDS_MAP.get(key)


def extract_schema(model: type[BaseModel], prefix: str = "") -> list[SectionSpec]:
    """Walk a Pydantic model tree and return a list of SectionSpecs.

    For the root model (no prefix), each field that is a nested BaseModel
    becomes a section. For non-root models, the model itself is a section
    with its scalar fields.

    Requirements: 33-REQ-4.1, 33-REQ-4.2, 33-REQ-4.E1
    """
    if not prefix:
        # Check if this is a root model (all fields are nested BaseModels)
        # or a flat model (has scalar fields directly)
        has_nested = any(
            _is_nested_model(fi.annotation) for fi in model.model_fields.values()
        )
        has_scalar = any(
            not _is_nested_model(fi.annotation) for fi in model.model_fields.values()
        )

        if has_nested and not has_scalar:
            # Pure root model: each nested field is a section
            sections: list[SectionSpec] = []
            for field_name, field_info in model.model_fields.items():
                annotation = field_info.annotation
                if _is_nested_model(annotation):
                    section = _extract_section(
                        annotation, field_name, model_class=annotation
                    )
                    sections.append(section)
            return sections
        elif has_nested and has_scalar:
            # Mixed: root model with both scalar and nested fields
            sections = []
            for field_name, field_info in model.model_fields.items():
                annotation = field_info.annotation
                if _is_nested_model(annotation):
                    section = _extract_section(
                        annotation, field_name, model_class=annotation
                    )
                    sections.append(section)
            return sections
        else:
            # Flat model: treat as a single section
            section_name = model.__name__
            section = _extract_section(model, section_name, model_class=model)
            return [section]
    else:
        # Non-root: treat the model itself as a section
        section = _extract_section(model, prefix, model_class=model)
        return [section]


def _extract_section(
    model: type[BaseModel], path: str, model_class: type[BaseModel]
) -> SectionSpec:
    """Extract a SectionSpec from a Pydantic model."""
    section = SectionSpec(path=path)

    for field_name, field_info in model.model_fields.items():
        toml_key = _get_toml_key(field_name, field_info)
        annotation = field_info.annotation
        is_nested = _is_nested_model(annotation)

        default = _resolve_default(field_info)

        field_spec = FieldSpec(
            name=toml_key,
            section=path,
            python_type=_get_python_type_str(annotation),
            default=default,
            description=_get_description(model_class, field_name, field_info),
            bounds=_get_bounds(model_class, field_name),
            is_nested=is_nested,
        )
        section.fields.append(field_spec)

        if is_nested:
            sub_path = f"{path}.{toml_key}"
            sub_section = _extract_section(annotation, sub_path, model_class=annotation)
            section.subsections.append(sub_section)

    return section
