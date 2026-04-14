"""Config generation: schema extraction, TOML template rendering, and merge.

Extracts schema information from Pydantic models, renders documented TOML
config templates with promoted defaults active, and non-destructively merges
existing configs with schema changes.

Requirements: 33-REQ-1.*, 33-REQ-2.*, 33-REQ-3.*, 33-REQ-4.1, 33-REQ-4.2,
              33-REQ-4.E1
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, cast

import tomlkit
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from tomlkit.items import InlineTable

from agent_fox.core.config import AgentFoxConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema types, metadata, and Pydantic model introspection
# ---------------------------------------------------------------------------

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
    ("RoutingConfig", "max_timeout_retries"): ">=0",
    ("RoutingConfig", "timeout_multiplier"): ">=1.0",
    ("RoutingConfig", "timeout_ceiling_factor"): ">=1.0",
    # HookConfig
    ("HookConfig", "timeout"): ">=1",
    # KnowledgeConfig
    ("KnowledgeConfig", "ask_top_k"): ">=1",
    # ArchetypeInstancesConfig
    ("ArchetypeInstancesConfig", "reviewer"): "1-5",
    ("ArchetypeInstancesConfig", "verifier"): "1",
    # ReviewerConfig
    ("ReviewerConfig", "pre_review_block_threshold"): ">=0",
    ("ReviewerConfig", "drift_review_block_threshold"): ">=1",
    ("ReviewerConfig", "audit_min_ts_entries"): ">=1",
    ("ReviewerConfig", "audit_max_retries"): ">=0",
}

# Sections that appear in the simplified config template (active or commented).
# Sections NOT in this set are completely omitted from the template output.
# Requirements: 68-REQ-1.1, 68-REQ-1.2
_VISIBLE_SECTIONS: set[str] = {
    "orchestrator",
    "models",
    "archetypes",
    "archetypes.instances",
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
    ("archetypes", "reviewer"),
    ("archetypes", "verifier"),
    ("archetypes.instances", "verifier"),
}

# Template-level value overrides for promoted fields.
# These override the model's default value in the generated template only.
# Requirements: 68-REQ-2.1, 68-REQ-2.2, 68-REQ-2.4, 68-REQ-2.5
_PROMOTED_DEFAULTS_OVERRIDES: dict[tuple[str, str], object] = {
    ("orchestrator", "quality_gate"): "make check",
    ("orchestrator", "max_budget_usd"): 8.0,
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
    ("OrchestratorConfig", "max_blocked_fraction"): ("Stop run when this fraction of nodes are blocked"),
    ("OrchestratorConfig", "quality_gate"): ("Shell command run after each coder session to verify quality"),
    ("OrchestratorConfig", "max_budget_usd"): ("Per-session budget cap in USD (0 = unlimited)"),
    # RoutingConfig
    ("RoutingConfig", "retries_before_escalation"): "Retries before model escalation",
    ("RoutingConfig", "training_threshold"): "Training data threshold",
    ("RoutingConfig", "accuracy_threshold"): "Accuracy threshold for routing",
    ("RoutingConfig", "retrain_interval"): "Retrain interval",
    ("RoutingConfig", "max_timeout_retries"): (
        "Maximum timeout retries before falling through to escalation (0 = disable)"
    ),
    ("RoutingConfig", "timeout_multiplier"): (
        "Factor by which max_turns and session_timeout are extended on timeout retry (>=1.0)"
    ),
    ("RoutingConfig", "timeout_ceiling_factor"): (
        "Maximum session_timeout as a factor of the original configured value (>=1.0)"
    ),
    # ModelConfig
    ("ModelConfig", "coding"): ("Model tier for coding tasks: SIMPLE, STANDARD, or ADVANCED"),
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
    ("ArchetypesConfig", "reviewer"): (
        "Enable reviewer archetype (pre-review, drift-review, audit-review, fix-review modes)"
    ),
    ("ArchetypesConfig", "verifier"): ("Post-code verification — runs tests, checks correctness"),
    ("ArchetypesConfig", "models"): "Per-archetype model overrides",
    ("ArchetypesConfig", "allowlists"): "Per-archetype command allowlists",
    # ArchetypeInstancesConfig
    ("ArchetypeInstancesConfig", "reviewer"): "Number of reviewer instances",
    ("ArchetypeInstancesConfig", "verifier"): "Verifier instances (clamped to 1)",
    # ReviewerConfig
    ("ReviewerConfig", "pre_review_block_threshold"): "Finding count to block merge for pre-review",
    ("ReviewerConfig", "drift_review_block_threshold"): "Drift count to block (None = advisory)",
    ("ReviewerConfig", "audit_min_ts_entries"): ("Minimum TS entries to trigger audit-review injection"),
    ("ReviewerConfig", "audit_max_retries"): "Maximum audit-review/coder retry iterations",
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
        return field_info.default_factory()  # type: ignore[call-arg]
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


def _get_description(model_class: type[BaseModel], field_name: str, field_info: FieldInfo) -> str:
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
        has_nested = any(_is_nested_model(fi.annotation) for fi in model.model_fields.values())
        has_scalar = any(not _is_nested_model(fi.annotation) for fi in model.model_fields.values())

        if has_nested and not has_scalar:
            # Pure root model: each nested field is a section
            sections: list[SectionSpec] = []
            for field_name, field_info in model.model_fields.items():
                annotation = field_info.annotation
                if _is_nested_model(annotation):
                    model_cls = cast(type[BaseModel], annotation)
                    section = _extract_section(model_cls, field_name, model_class=model_cls)
                    sections.append(section)
            return sections
        elif has_nested and has_scalar:
            # Mixed: root model with both scalar and nested fields
            sections = []
            for field_name, field_info in model.model_fields.items():
                annotation = field_info.annotation
                if _is_nested_model(annotation):
                    model_cls = cast(type[BaseModel], annotation)
                    section = _extract_section(model_cls, field_name, model_class=model_cls)
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


def _extract_section(model: type[BaseModel], path: str, model_class: type[BaseModel]) -> SectionSpec:
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
            nested_cls = cast(type[BaseModel], annotation)
            sub_section = _extract_section(nested_cls, sub_path, model_class=nested_cls)
            section.subsections.append(sub_section)

    return section


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------


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
        # Format inline table — values may be nested dicts (from BaseModel)
        items = ", ".join(f"{k} = {_format_toml_value(v)}" for k, v in value.items())
        return f"{{{items}}}"
    # Handle Pydantic BaseModel instances by converting to dict first
    if isinstance(value, BaseModel):
        return _format_toml_value(value.model_dump())
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


def _section_has_promoted(section: SectionSpec) -> bool:
    """Check if a section has any promoted (active) fields."""
    for field_spec in section.fields:
        if field_spec.is_nested:
            continue
        if (section.path, field_spec.name) in _PROMOTED_DEFAULTS:
            return True
    return False


_FOOTER_COMMENT = "## For all configuration options, see docs/config-reference.md"


def generate_config_template(schema: list[SectionSpec]) -> str:
    """Render a config.toml from extracted schema with promoted defaults active.

    Only sections in _VISIBLE_SECTIONS are rendered. Sections with promoted
    fields are rendered first with active [section] headers; remaining visible
    sections follow as commented # [section] blocks.

    Requirements: 33-REQ-1.1, 33-REQ-1.2, 33-REQ-1.3, 33-REQ-1.4, 33-REQ-1.5,
                  68-REQ-1.1, 68-REQ-1.2, 68-REQ-1.3, 68-REQ-1.4, 68-REQ-6.1
    """
    lines: list[str] = [
        "## agent-fox configuration",
        "## Uncomment and edit values to customize.",
    ]

    # Filter schema to only visible sections
    visible_schema = [s for s in schema if s.path in _VISIBLE_SECTIONS]

    # Partition into active (have promoted fields) and inactive sections
    active_sections = [s for s in visible_schema if _section_has_promoted(s)]
    inactive_sections = [s for s in visible_schema if not _section_has_promoted(s)]

    for section in active_sections:
        lines.append("")
        _render_section(section, lines)

    for section in inactive_sections:
        lines.append("")
        _render_section(section, lines)

    lines.append("")
    lines.append(_FOOTER_COMMENT)

    # Ensure trailing newline
    result = "\n".join(lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _render_section(section: SectionSpec, lines: list[str]) -> None:
    """Render a section and its subsections.

    If the section has promoted fields, render it with an active [section]
    header and promoted fields uncommented. Otherwise render fully commented.
    """
    has_promoted = _section_has_promoted(section)

    if has_promoted:
        lines.append(f"[{section.path}]")
    else:
        lines.append(f"# [{section.path}]")

    # Render promoted (active) fields first, then inactive fields
    promoted_fields = []
    inactive_fields = []
    for field_spec in section.fields:
        if field_spec.is_nested:
            continue
        if (section.path, field_spec.name) in _PROMOTED_DEFAULTS:
            promoted_fields.append(field_spec)
        else:
            inactive_fields.append(field_spec)

    for field_spec in promoted_fields:
        lines.append(_format_field_comment(field_spec))
        # Use template-level override value if available
        override = _PROMOTED_DEFAULTS_OVERRIDES.get((section.path, field_spec.name))
        value = override if override is not None else field_spec.default
        toml_val = _format_toml_value(value)
        lines.append(f"{field_spec.name} = {toml_val}")

    # Inactive fields are omitted from the simplified template.
    # All options are documented in docs/config-reference.md.
    # (inactive_fields are still rendered during config_merge operations)

    # Render subsections (filtered to visible sections only)
    for sub in section.subsections:
        if sub.path not in _VISIBLE_SECTIONS:
            continue
        lines.append("")
        _render_section(sub, lines)


def generate_default_config() -> str:
    """Generate a complete commented config.toml from AgentFoxConfig.

    Requirements: 33-REQ-3.1
    """
    logger.debug("Generating fresh config template from AgentFoxConfig")
    schema = extract_schema(AgentFoxConfig)
    return generate_config_template(schema)


# ---------------------------------------------------------------------------
# Config merge: non-destructive merging with schema changes
# ---------------------------------------------------------------------------


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

    The merge uses a text-based approach rather than pure tomlkit manipulation
    to ensure idempotency. Commented-out entries from prior merges are detected
    by scanning the raw text, preventing duplicate additions.
    """
    # Handle empty/whitespace content as fresh generation (33-REQ-2.E2)
    if not existing_content.strip():
        logger.debug("Empty config content, treating as fresh generation")
        return generate_config_template(schema)

    # Idempotency shortcut: if content is already a fresh template, return as-is
    fresh = generate_config_template(schema)
    if existing_content == fresh:
        return fresh

    # Try to parse existing TOML (33-REQ-2.E1)
    try:
        existing_doc = tomlkit.parse(existing_content)
    except Exception:
        logger.warning("Existing config contains invalid TOML, skipping merge")
        return existing_content

    # Build schema lookup: section_path -> {field_name: FieldSpec}
    schema_lookup = _build_schema_lookup(schema)

    # Scan raw text for already-present commented sections and fields.
    # This prevents adding duplicates on re-merge (idempotency).
    commented_sections = set(m.group(1) for m in re.finditer(r"^#\s*\[([^\]]+)\]", existing_content, re.MULTILINE))
    commented_fields: dict[str, set[str]] = {}
    _scan_commented_fields(existing_content, commented_fields)

    # Collect active sections and fields from parsed TOML
    active_sections: set[str] = set()
    active_fields: dict[str, set[str]] = {}
    deprecated_entries: list[tuple[str, str, str]] = []  # (section, key, value_str)

    for section_path in list(existing_doc.keys()):
        active_sections.add(section_path)
        active_fields[section_path] = set()
        section_data = existing_doc[section_path]
        if isinstance(section_data, dict):
            _collect_active_fields(
                section_data,
                section_path,
                schema_lookup,
                active_fields,
                deprecated_entries,
            )

    # Count actions for logging
    added_count = 0
    deprecated_count = len(deprecated_entries)

    # Build result: start with existing content lines
    result_lines = existing_content.rstrip("\n").split("\n")

    # Apply deprecated field markers: replace active deprecated lines in-place
    for section_path, key, value_str in deprecated_entries:
        _apply_deprecation(result_lines, section_path, key, value_str)

    # Add missing fields to existing sections
    for section in schema:
        if section.path in active_sections:
            section_known = schema_lookup.get(section.path, {})
            section_active = active_fields.get(section.path, set())
            section_commented = commented_fields.get(section.path, set())
            missing_fields = []
            for field_name, field_spec in section_known.items():
                if field_name not in section_active and field_name not in section_commented:
                    missing_fields.append(field_spec)
                    added_count += 1
            if missing_fields:
                insert_idx = _find_section_end(result_lines, section.path)
                new_lines = _render_field_comments(missing_fields)
                result_lines[insert_idx:insert_idx] = new_lines

            # Handle subsections of active sections
            for sub in section.subsections:
                if sub.path not in active_fields and sub.path not in commented_sections:
                    insert_idx = _find_section_end(result_lines, section.path)
                    new_lines = [""] + _render_section_comments(sub)
                    result_lines[insert_idx:insert_idx] = new_lines
                    added_count += _count_section_fields(sub)

    # Add missing sections (not active and not already commented).
    # Only add sections that are visible (in _VISIBLE_SECTIONS) — hidden
    # sections are never injected into a config that doesn't already have them.
    # Requirements: 68-REQ-5.3
    for section in schema:
        if section.path not in _VISIBLE_SECTIONS:
            continue
        if section.path not in active_sections and section.path not in commented_sections:
            new_lines = [""] + _render_section_comments(section)
            # Also add subsections (visible only)
            for sub in section.subsections:
                if sub.path not in _VISIBLE_SECTIONS:
                    continue
                if sub.path not in commented_sections:
                    new_lines.extend([""] + _render_section_comments(sub))
            result_lines.extend(new_lines)
            added_count += _count_section_fields(section)

    if added_count > 0 or deprecated_count > 0:
        logger.info(
            "Config merge: %d fields preserved, %d added, %d deprecated",
            sum(len(v) for v in active_fields.values()),
            added_count,
            deprecated_count,
        )

    # Ensure the footer appears exactly once at the end.
    # Requirements: 68-REQ-6.1, 68-REQ-6.E1
    _ensure_footer(result_lines, _FOOTER_COMMENT)

    result = "\n".join(result_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _ensure_footer(lines: list[str], footer: str) -> None:
    """Ensure the footer comment appears exactly once at the end of the file.

    Removes any existing occurrences of the footer, strips trailing blank
    lines, then appends a blank line and the footer.
    Requirements: 68-REQ-6.1, 68-REQ-6.E1
    """
    # Remove all existing occurrences
    lines[:] = [ln for ln in lines if ln.strip() != footer.strip()]
    # Strip trailing blank lines for idempotency
    while lines and not lines[-1].strip():
        lines.pop()
    # Append a blank line then the footer
    lines.append("")
    lines.append(footer)


def _build_schema_lookup(
    schema: list[SectionSpec],
) -> dict[str, dict[str, FieldSpec]]:
    """Build a lookup dict: section_path -> {field_name: FieldSpec}."""
    lookup: dict[str, dict[str, FieldSpec]] = {}
    for section in schema:
        lookup[section.path] = {f.name: f for f in section.fields if not f.is_nested}
        for sub in section.subsections:
            sub_lookup = _build_schema_lookup([sub])
            lookup.update(sub_lookup)
    return lookup


def _scan_commented_fields(content: str, result: dict[str, set[str]]) -> None:
    """Scan raw text to find commented-out field entries per section.

    Identifies patterns like '# field_name = value' that appear after
    section-like comments '# [section_name]'. This allows the merge to
    detect already-present commented entries and avoid duplicating them.
    """
    current_section: str | None = None
    for line in content.split("\n"):
        stripped = line.strip()
        # Check for commented section header: # [section_name]
        m = re.match(r"^#\s*\[([\w.]+)\]$", stripped)
        if m:
            current_section = m.group(1)
            continue
        # Check for active section header: [section_name]
        m = re.match(r"^\[([\w.]+)\]$", stripped)
        if m:
            current_section = m.group(1)
            continue
        # Check for commented field: # field_name = ...  or ## field_name =
        m = re.match(r"^#{1,2}\s+(\w+)\s*=", stripped)
        if m and current_section:
            result.setdefault(current_section, set()).add(m.group(1))


def _collect_active_fields(
    section_data: Any,
    section_path: str,
    schema_lookup: dict[str, dict[str, FieldSpec]],
    active_fields: dict[str, set[str]],
    deprecated_entries: list[tuple[str, str, str]],
) -> None:
    """Collect active (uncommented) fields and identify deprecated ones."""
    known_fields = schema_lookup.get(section_path, {})

    for key in list(section_data.keys()):
        if isinstance(section_data[key], dict) and not isinstance(section_data[key], InlineTable):
            # Nested table — recurse
            sub_path = f"{section_path}.{key}"
            if sub_path in schema_lookup:
                active_fields.setdefault(sub_path, set())
                _collect_active_fields(
                    section_data[key],
                    sub_path,
                    schema_lookup,
                    active_fields,
                    deprecated_entries,
                )
            continue

        active_fields.setdefault(section_path, set()).add(key)

        if key not in known_fields:
            # Record deprecated field for later processing
            value = section_data[key]
            value_str = _format_toml_value(value)
            deprecated_entries.append((section_path, key, value_str))


def _apply_deprecation(lines: list[str], section_path: str, key: str, value_str: str) -> None:
    """Replace an active deprecated field line with a DEPRECATED comment.

    Requirements: 33-REQ-2.4
    """
    in_section = False
    section_header = f"[{section_path}]"

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section_header:
            in_section = True
            continue
        if in_section and re.match(r"^\[[\w.]+\]$", stripped):
            break
        if in_section and re.match(rf"^{re.escape(key)}\s*=", stripped):
            lines[i] = f"# DEPRECATED: '{key}' is no longer recognized\n# {stripped}"
            break


def _find_section_end(lines: list[str], section_path: str) -> int:
    """Find the line index where a section ends (before the next section)."""
    in_section = False
    section_header = f"[{section_path}]"
    last_content_idx = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == section_header:
            in_section = True
            last_content_idx = i + 1
            continue
        if in_section:
            # Another active section header ends this one
            if re.match(r"^\[[\w.]+\]$", stripped):
                return last_content_idx
            # Track last non-empty line in this section
            if stripped:
                last_content_idx = i + 1

    return last_content_idx


def _render_commented_field(lines: list[str], field_spec: FieldSpec) -> None:
    """Append a single field as commented TOML lines."""
    lines.append(_format_field_comment(field_spec))
    toml_val = _format_toml_value(field_spec.default)
    if field_spec.default is None:
        lines.append(f"## {field_spec.name} =")
    else:
        lines.append(f"# {field_spec.name} = {toml_val}")


def _render_field_comments(fields: list[FieldSpec]) -> list[str]:
    """Render a list of fields as commented TOML lines."""
    lines: list[str] = []
    for field_spec in fields:
        _render_commented_field(lines, field_spec)
    return lines


def _render_section_comments(section: SectionSpec) -> list[str]:
    """Render a complete section as commented TOML lines."""
    lines: list[str] = [f"# [{section.path}]"]
    for field_spec in section.fields:
        if field_spec.is_nested:
            continue
        _render_commented_field(lines, field_spec)

    for sub in section.subsections:
        lines.append("")
        lines.extend(_render_section_comments(sub))

    return lines


def _count_section_fields(section: SectionSpec) -> int:
    """Count scalar fields in a section and its subsections."""
    count = sum(1 for f in section.fields if not f.is_nested)
    for sub in section.subsections:
        count += _count_section_fields(sub)
    return count


def merge_existing_config(existing_content: str) -> str:
    """Merge an existing config.toml with the current schema.

    Requirements: 33-REQ-2.1 through 33-REQ-2.5
    """
    schema = extract_schema(AgentFoxConfig)
    return merge_config(existing_content, schema)
