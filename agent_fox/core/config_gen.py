"""Config generation: schema extraction, template generation, and config merge.

Introspects Pydantic models to produce documented TOML config templates and
supports non-destructive merging of existing configs with schema changes.

Requirements: 33-REQ-1.*, 33-REQ-2.*, 33-REQ-3.*, 33-REQ-4.*
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import tomlkit
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)

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
}

# Default descriptions for fields that lack description metadata.
# Keyed by (model_class_name, field_name).
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
    # RoutingConfig
    ("RoutingConfig", "retries_before_escalation"): "Retries before model escalation",
    ("RoutingConfig", "training_threshold"): "Training data threshold",
    ("RoutingConfig", "accuracy_threshold"): "Accuracy threshold for routing",
    ("RoutingConfig", "retrain_interval"): "Retrain interval",
    # ModelConfig
    ("ModelConfig", "coding"): "Model tier for coding tasks",
    ("ModelConfig", "coordinator"): "Model tier for coordination",
    ("ModelConfig", "memory_extraction"): "Model tier for memory extraction",
    ("ModelConfig", "embedding"): "Embedding model name",
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
    ("PlatformConfig", "auto_merge"): "Auto-merge pull requests",
    # KnowledgeConfig
    ("KnowledgeConfig", "store_path"): "Path to knowledge store",
    ("KnowledgeConfig", "embedding_model"): "Embedding model for knowledge",
    ("KnowledgeConfig", "embedding_dimensions"): "Embedding vector dimensions",
    ("KnowledgeConfig", "ask_top_k"): "Number of results for knowledge queries",
    ("KnowledgeConfig", "ask_synthesis_model"): "Model tier for answer synthesis",
    # ToolsConfig
    ("ToolsConfig", "fox_tools"): "Enable fox tools",
    # ArchetypesConfig
    ("ArchetypesConfig", "coder"): "Enable coder archetype",
    ("ArchetypesConfig", "skeptic"): "Enable skeptic archetype",
    ("ArchetypesConfig", "verifier"): "Enable verifier archetype",
    ("ArchetypesConfig", "librarian"): "Enable librarian archetype",
    ("ArchetypesConfig", "cartographer"): "Enable cartographer archetype",
    ("ArchetypesConfig", "oracle"): "Enable oracle archetype",
    ("ArchetypesConfig", "models"): "Per-archetype model overrides",
    ("ArchetypesConfig", "allowlists"): "Per-archetype command allowlists",
    # ArchetypeInstancesConfig
    ("ArchetypeInstancesConfig", "skeptic"): "Number of skeptic instances",
    ("ArchetypeInstancesConfig", "verifier"): "Number of verifier instances",
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


def extract_schema(
    model: type[BaseModel], prefix: str = ""
) -> list[SectionSpec]:
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
            _is_nested_model(fi.annotation)
            for fi in model.model_fields.values()
        )
        has_scalar = any(
            not _is_nested_model(fi.annotation)
            for fi in model.model_fields.values()
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
            sub_section = _extract_section(
                annotation, sub_path, model_class=annotation
            )
            section.subsections.append(sub_section)

    return section


def _format_toml_value(value: Any) -> str:
    """Format a Python value as a TOML literal string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        # Format list elements
        items = ", ".join(_format_toml_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        # Format inline table
        items = ", ".join(
            f"{k} = {_format_toml_value(v)}" for k, v in value.items()
        )
        return f"{{{items}}}"
    return str(value)


def _format_field_comment(field_spec: FieldSpec) -> str:
    """Format the description comment for a field.

    Uses '## ' prefix so that stripping '# ' leaves a TOML comment,
    keeping the uncommented output valid per 33-REQ-1.4.

    Format: ## <description> (<bounds>, default: <value>)
    Or:     ## <description> (default: <value>)
    Or:     ## <description> (not set by default)
    """
    desc = field_spec.description

    if field_spec.default is None:
        if field_spec.bounds:
            return f"## {desc} ({field_spec.bounds}, not set by default)"
        return f"## {desc} (not set by default)"

    default_str = _format_toml_value(field_spec.default)
    if field_spec.bounds:
        return f"## {desc} ({field_spec.bounds}, default: {default_str})"
    return f"## {desc} (default: {default_str})"


def generate_config_template(schema: list[SectionSpec]) -> str:
    """Render a fully-commented config.toml from extracted schema.

    Requirements: 33-REQ-1.1, 33-REQ-1.2, 33-REQ-1.3, 33-REQ-1.4, 33-REQ-1.5
    """
    lines: list[str] = [
        "## agent-fox configuration",
        "## Generated from schema — do not remove section headers.",
        "## Uncomment and edit values to customize.",
    ]

    for i, section in enumerate(schema):
        lines.append("")
        _render_section(section, lines)

    # Ensure trailing newline
    result = "\n".join(lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _render_section(section: SectionSpec, lines: list[str]) -> None:
    """Render a section and its subsections as commented TOML."""
    lines.append(f"# [{section.path}]")

    for field_spec in section.fields:
        if field_spec.is_nested:
            continue
        # Description comment
        lines.append(_format_field_comment(field_spec))
        # Commented key-value pair
        toml_val = _format_toml_value(field_spec.default)
        if field_spec.default is None:
            # Double-# so stripping '# ' leaves '# key =' (still a comment),
            # keeping the uncommented TOML valid per 33-REQ-1.4
            lines.append(f"## {field_spec.name} =")
        else:
            lines.append(f"# {field_spec.name} = {toml_val}")

    # Render subsections
    for sub in section.subsections:
        lines.append("")
        _render_section(sub, lines)


def generate_default_config() -> str:
    """Generate a complete commented config.toml from AgentFoxConfig.

    Requirements: 33-REQ-3.1
    """
    logger.debug("Generating fresh config template from AgentFoxConfig")
    schema = extract_schema(AgentFoxConfig)
    return generate_config_template(schema)


def merge_config(
    existing_content: str,
    schema: list[SectionSpec],
) -> str:
    """Merge an existing config.toml with the current schema.

    - Preserves active (uncommented) user values.
    - Adds missing fields as commented entries.
    - Marks unrecognized active fields as DEPRECATED.
    - Preserves user comments and formatting.

    Requirements: 33-REQ-2.1, 33-REQ-2.2, 33-REQ-2.3, 33-REQ-2.4, 33-REQ-2.5
    """
    # Handle empty/whitespace content as fresh generation
    if not existing_content.strip():
        logger.debug("Empty config content, treating as fresh generation")
        return generate_config_template(schema)

    # Try to parse existing TOML
    try:
        existing_doc = tomlkit.parse(existing_content)
    except Exception:
        logger.warning(
            "Existing config contains invalid TOML, skipping merge"
        )
        return existing_content

    # Build schema lookup: section_path -> {field_name: FieldSpec}
    schema_lookup = _build_schema_lookup(schema)

    # Track what we've processed for adding missing fields
    processed_sections: set[str] = set()
    processed_fields: dict[str, set[str]] = {}

    # Process existing document: mark deprecated fields
    for section_path in list(existing_doc.keys()):
        if section_path in schema_lookup:
            processed_sections.add(section_path)
            processed_fields[section_path] = set()
            section_data = existing_doc[section_path]
            if isinstance(section_data, dict):
                _process_existing_section(
                    section_data,
                    section_path,
                    schema_lookup,
                    processed_fields,
                )

    # Add missing sections and fields
    _add_missing_content(
        existing_doc,
        schema,
        schema_lookup,
        processed_sections,
        processed_fields,
    )

    result = tomlkit.dumps(existing_doc)
    # Ensure trailing newline
    if not result.endswith("\n"):
        result += "\n"

    # Check if result matches a fresh generation (idempotency for
    # already-current configs)
    fresh = generate_config_template(schema)
    if existing_content == fresh:
        return fresh

    return result


def _build_schema_lookup(
    schema: list[SectionSpec],
) -> dict[str, dict[str, FieldSpec]]:
    """Build a lookup dict: section_path -> {field_name: FieldSpec}."""
    lookup: dict[str, dict[str, FieldSpec]] = {}
    for section in schema:
        lookup[section.path] = {
            f.name: f for f in section.fields if not f.is_nested
        }
        for sub in section.subsections:
            sub_lookup = _build_schema_lookup([sub])
            lookup.update(sub_lookup)
    return lookup


def _process_existing_section(
    section_data: Any,
    section_path: str,
    schema_lookup: dict[str, dict[str, FieldSpec]],
    processed_fields: dict[str, set[str]],
) -> None:
    """Process an existing section, marking deprecated fields."""
    known_fields = schema_lookup.get(section_path, {})

    for key in list(section_data.keys()):
        if isinstance(section_data[key], dict) and not isinstance(
            section_data[key], tomlkit.items.InlineTable
        ):
            # Nested table — recurse
            sub_path = f"{section_path}.{key}"
            if sub_path in schema_lookup:
                if sub_path not in processed_fields:
                    processed_fields[sub_path] = set()
                _process_existing_section(
                    section_data[key],
                    sub_path,
                    schema_lookup,
                    processed_fields,
                )
            continue

        processed_fields.setdefault(section_path, set()).add(key)

        if key not in known_fields:
            # Mark as deprecated
            value = section_data[key]
            value_str = _format_toml_value(value)
            section_data.add(
                tomlkit.comment(
                    f"DEPRECATED: '{key}' is no longer recognized"
                )
            )
            section_data.add(tomlkit.comment(f"{key} = {value_str}"))
            del section_data[key]


def _add_missing_content(
    doc: tomlkit.TOMLDocument,
    schema: list[SectionSpec],
    schema_lookup: dict[str, dict[str, FieldSpec]],
    processed_sections: set[str],
    processed_fields: dict[str, set[str]],
) -> None:
    """Add missing sections and fields as commented entries."""
    for section in schema:
        if section.path not in processed_sections:
            # Add entire section as comments
            doc.add(tomlkit.nl())
            doc.add(tomlkit.comment(f"[{section.path}]"))
            for field_spec in section.fields:
                if field_spec.is_nested:
                    continue
                doc.add(tomlkit.comment(_format_field_comment(field_spec)[2:]))
                toml_val = _format_toml_value(field_spec.default)
                if field_spec.default is None:
                    doc.add(tomlkit.comment(f"{field_spec.name} ="))
                else:
                    doc.add(
                        tomlkit.comment(f"{field_spec.name} = {toml_val}")
                    )
            # Add subsections
            for sub in section.subsections:
                doc.add(tomlkit.nl())
                _add_missing_section_as_comments(doc, sub)
        else:
            # Section exists — add missing fields
            section_fields = processed_fields.get(section.path, set())
            known_fields = schema_lookup.get(section.path, {})
            section_data = doc.get(section.path)
            if section_data is not None and isinstance(section_data, dict):
                for field_name, field_spec in known_fields.items():
                    if field_name not in section_fields:
                        comment_text = _format_field_comment(field_spec)[2:]
                        section_data.add(tomlkit.comment(comment_text))
                        toml_val = _format_toml_value(field_spec.default)
                        if field_spec.default is None:
                            section_data.add(
                                tomlkit.comment(f"{field_name} =")
                            )
                        else:
                            section_data.add(
                                tomlkit.comment(
                                    f"{field_name} = {toml_val}"
                                )
                            )

            # Handle subsections
            for sub in section.subsections:
                if sub.path not in processed_fields:
                    # Add entire subsection as comments
                    if section_data is not None:
                        section_data.add(tomlkit.nl())
                        section_data.add(
                            tomlkit.comment(f"[{sub.path}]")
                        )
                        for f in sub.fields:
                            if f.is_nested:
                                continue
                            section_data.add(
                                tomlkit.comment(
                                    _format_field_comment(f)[2:]
                                )
                            )
                            tv = _format_toml_value(f.default)
                            if f.default is None:
                                section_data.add(
                                    tomlkit.comment(f"{f.name} =")
                                )
                            else:
                                section_data.add(
                                    tomlkit.comment(f"{f.name} = {tv}")
                                )


def _add_missing_section_as_comments(
    doc: tomlkit.TOMLDocument, section: SectionSpec
) -> None:
    """Add a complete section as commented entries."""
    doc.add(tomlkit.comment(f"[{section.path}]"))
    for field_spec in section.fields:
        if field_spec.is_nested:
            continue
        doc.add(tomlkit.comment(_format_field_comment(field_spec)[2:]))
        toml_val = _format_toml_value(field_spec.default)
        if field_spec.default is None:
            doc.add(tomlkit.comment(f"{field_spec.name} ="))
        else:
            doc.add(tomlkit.comment(f"{field_spec.name} = {toml_val}"))

    for sub in section.subsections:
        doc.add(tomlkit.nl())
        _add_missing_section_as_comments(doc, sub)


def merge_existing_config(existing_content: str) -> str:
    """Merge an existing config.toml with the current schema.

    Requirements: 33-REQ-2.1 through 33-REQ-2.5
    """
    schema = extract_schema(AgentFoxConfig)
    return merge_config(existing_content, schema)
