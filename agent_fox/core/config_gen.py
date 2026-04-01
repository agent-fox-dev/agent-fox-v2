"""Config generation: TOML template rendering from schema.

Renders documented TOML config templates from extracted schema with
promoted defaults active.

Requirements: 33-REQ-1.*, 33-REQ-3.*
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from agent_fox.core.config import AgentFoxConfig

# Re-export symbols that external code imports from this module.
from agent_fox.core.config_merge import (  # noqa: F401
    merge_config,
    merge_existing_config,
)
from agent_fox.core.config_schema import (  # noqa: F401
    _PROMOTED_DEFAULTS,
    _PROMOTED_DEFAULTS_OVERRIDES,
    _VISIBLE_SECTIONS,
    FieldSpec,
    SectionSpec,
    extract_schema,
)

logger = logging.getLogger(__name__)


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
