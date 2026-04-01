"""Config merge: non-destructive merging of existing configs with schema changes.

Preserves active (uncommented) user values, adds missing fields as
commented entries, and marks unrecognized active fields as DEPRECATED.

Requirements: 33-REQ-2.1, 33-REQ-2.2, 33-REQ-2.3, 33-REQ-2.4, 33-REQ-2.5
"""

from __future__ import annotations

import logging
import re
from typing import Any

import tomlkit
from tomlkit.items import InlineTable

from agent_fox.core.config import AgentFoxConfig
from agent_fox.core.config_schema import FieldSpec, SectionSpec, extract_schema

logger = logging.getLogger(__name__)


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
    from agent_fox.core.config_gen import generate_config_template

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
    commented_sections = set(
        m.group(1)
        for m in re.finditer(r"^#\s*\[([^\]]+)\]", existing_content, re.MULTILINE)
    )
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
                if (
                    field_name not in section_active
                    and field_name not in section_commented
                ):
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

    # Add missing sections (not active and not already commented)
    for section in schema:
        if (
            section.path not in active_sections
            and section.path not in commented_sections
        ):
            new_lines = [""] + _render_section_comments(section)
            # Also add subsections
            for sub in section.subsections:
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

    result = "\n".join(result_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


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
    from agent_fox.core.config_gen import _format_toml_value

    known_fields = schema_lookup.get(section_path, {})

    for key in list(section_data.keys()):
        if isinstance(section_data[key], dict) and not isinstance(
            section_data[key], InlineTable
        ):
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


def _apply_deprecation(
    lines: list[str], section_path: str, key: str, value_str: str
) -> None:
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
    from agent_fox.core.config_gen import _format_field_comment, _format_toml_value

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
