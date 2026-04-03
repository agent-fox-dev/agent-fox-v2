"""Property tests for config generation and merge system.

Test Spec: TS-33-P1 through TS-33-P7
Requirements: 33-REQ-1.*, 33-REQ-2.*, 33-REQ-4.*
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_fox.core.config import AgentFoxConfig, load_config
from agent_fox.core.config_gen import (
    SectionSpec,
    extract_schema,
    generate_default_config,
    merge_existing_config,
)


def _strip_comment_prefixes(template: str) -> str:
    """Remove '# ' prefix from lines that start with it."""
    lines = template.split("\n")
    result = []
    for line in lines:
        if line.startswith("# "):
            result.append(line[2:])
        elif line == "#":
            result.append("")
        else:
            result.append(line)
    return "\n".join(result)


def _count_scalar_fields(sections: list[SectionSpec]) -> int:
    """Count total scalar (non-nested) fields across all sections."""
    total = 0
    for section in sections:
        for field in section.fields:
            if not field.is_nested:
                total += 1
        total += _count_scalar_fields(section.subsections)
    return total


def _count_field_lines(template: str) -> int:
    """Count lines matching field assignment patterns (active or commented)."""
    count = 0
    for line in template.split("\n"):
        # Match 'key = value' or '# key = value' but not section headers
        if re.match(r"^#{0,2}\s*\w+\s*=", line) and not re.match(r"^#\s*\[", line):
            count += 1
    return count


def _get_all_schema_field_names(sections: list[SectionSpec]) -> set[str]:
    """Collect all scalar field names from schema sections recursively."""
    names: set[str] = set()
    for section in sections:
        for field in section.fields:
            if not field.is_nested:
                names.add(field.name)
        names.update(_get_all_schema_field_names(section.subsections))
    return names


def _get_known_fields_by_section(
    sections: list[SectionSpec],
) -> dict[str, set[str]]:
    """Build a map of section_path -> set of field names."""
    result: dict[str, set[str]] = {}
    for section in sections:
        result[section.path] = {f.name for f in section.fields if not f.is_nested}
        sub = _get_known_fields_by_section(section.subsections)
        result.update(sub)
    return result


# --- Strategies for generating valid config overrides ---

# Known orchestrator fields and valid values
_ORCHESTRATOR_FIELDS = {
    "parallel": st.integers(min_value=1, max_value=8),
    "sync_interval": st.integers(min_value=0, max_value=100),
    "hot_load": st.booleans(),
    "max_retries": st.integers(min_value=0, max_value=10),
    "session_timeout": st.integers(min_value=1, max_value=120),
    "inter_session_delay": st.integers(min_value=0, max_value=30),
}

_THEME_FIELDS = {
    "playful": st.booleans(),
}


@st.composite
def valid_orchestrator_overrides(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random subset of valid orchestrator config overrides."""
    subset_keys = draw(
        st.lists(
            st.sampled_from(list(_ORCHESTRATOR_FIELDS.keys())),
            min_size=1,
            max_size=len(_ORCHESTRATOR_FIELDS),
            unique=True,
        )
    )
    return {k: draw(_ORCHESTRATOR_FIELDS[k]) for k in subset_keys}


@st.composite
def valid_config_toml(draw: st.DrawFn) -> str:
    """Generate a valid TOML string with random orchestrator overrides."""
    overrides = draw(valid_orchestrator_overrides())
    lines = ["[orchestrator]"]
    for key, value in overrides.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


@st.composite
def unknown_field_names(draw: st.DrawFn) -> list[str]:
    """Generate random field names that are NOT in the schema."""
    schema = extract_schema(AgentFoxConfig)
    known = _get_all_schema_field_names(schema)

    names = draw(
        st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{2,15}", fullmatch=True).filter(lambda n: n not in known),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    return names


class TestTemplateCompleteness:
    """TS-33-P1: Promoted fields appear as active entries in the template."""

    def test_template_has_all_scalar_fields(self) -> None:
        """Property 1: Template completeness for promoted fields.

        The simplified template only contains promoted fields (not all schema
        fields). Validates that every promoted field appears in the template.
        Validates: 33-REQ-1.1, 68-REQ-1.1
        """
        from agent_fox.core.config_gen import _PROMOTED_DEFAULTS

        schema = extract_schema(AgentFoxConfig)
        template = generate_default_config()

        # Every promoted field must appear as an active (uncommented) entry
        for section in schema:
            for field in section.fields:
                if not field.is_nested:
                    if (section.path, field.name) in _PROMOTED_DEFAULTS:
                        assert f"{field.name} =" in template, (
                            f"Promoted field '{field.name}' in section '{section.path}' missing from template"
                        )


class TestRoundTripDefaultEquivalence:
    """TS-33-P2: Template is valid TOML and loads cleanly."""

    def test_uncommented_template_matches_defaults(self, tmp_path: Path) -> None:
        """Property 2: Simplified template loads as a valid AgentFoxConfig.

        The simplified template uses template-level overrides (e.g.,
        quality_gate = "make check") that differ from model defaults. This
        test verifies the template parses correctly and loads the promoted
        field values.
        Validates: 33-REQ-1.4, 68-REQ-1.2
        """
        import tomllib

        template = generate_default_config()

        # Template (with active sections only) must parse as valid TOML
        parsed = tomllib.loads(template)
        assert isinstance(parsed, dict)

        # Load via load_config succeeds
        config_path = tmp_path / "config.toml"
        config_path.write_text(template)
        config = load_config(config_path)
        assert isinstance(config, AgentFoxConfig)

        # Promoted values are loaded correctly
        assert config.orchestrator.parallel == 2
        assert config.models.coding == "ADVANCED"


class TestMergeValuePreservation:
    """TS-33-P3: Active user values survive merge unchanged."""

    @given(overrides=valid_orchestrator_overrides())
    @settings(max_examples=20)
    def test_active_values_preserved(self, overrides: dict[str, Any]) -> None:
        """Property 3: Merge value preservation.

        Validates: 33-REQ-2.1, 33-REQ-2.5
        """
        lines = ["[orchestrator]"]
        for key, value in overrides.items():
            if isinstance(value, bool):
                lines.append(f"{key} = {str(value).lower()}")
            else:
                lines.append(f"{key} = {value}")
        existing = "\n".join(lines) + "\n"

        merged = merge_existing_config(existing)

        # Every active field should appear active (uncommented) in output
        for key, value in overrides.items():
            if isinstance(value, bool):
                expected = f"{key} = {str(value).lower()}"
            else:
                expected = f"{key} = {value}"
            # Find the line containing this key-value pair
            found = False
            for line in merged.split("\n"):
                if expected in line and not line.lstrip().startswith("#"):
                    found = True
                    break
            assert found, f"Active value '{expected}' not preserved in merged output"


class TestMergeCompleteness:
    """TS-33-P4: After merge, all visible-section fields appear in the output."""

    @given(data=st.data())
    @settings(max_examples=10)
    def test_all_fields_present_after_merge(self, data: st.DataObject) -> None:
        """Property 4: Merge completeness for visible sections.

        After merge, all promoted fields (which are in visible sections)
        appear in the output. Hidden sections are not injected.
        Validates: 33-REQ-2.2, 68-REQ-5.3
        """
        from agent_fox.core.config_gen import _PROMOTED_DEFAULTS

        schema = extract_schema(AgentFoxConfig)

        # Generate a config with a random subset of orchestrator fields
        subset_size = data.draw(st.integers(min_value=0, max_value=min(3, len(_ORCHESTRATOR_FIELDS))))
        if subset_size > 0:
            keys = data.draw(
                st.lists(
                    st.sampled_from(list(_ORCHESTRATOR_FIELDS.keys())),
                    min_size=subset_size,
                    max_size=subset_size,
                    unique=True,
                )
            )
            lines = ["[orchestrator]"]
            for k in keys:
                v = data.draw(_ORCHESTRATOR_FIELDS[k])
                if isinstance(v, bool):
                    lines.append(f"{k} = {str(v).lower()}")
                else:
                    lines.append(f"{k} = {v}")
            existing = "\n".join(lines) + "\n"
        else:
            existing = ""

        merged = merge_existing_config(existing)

        # Every promoted field should appear somewhere in the output
        for section in schema:
            for field in section.fields:
                key = (section.path, field.name)
                if not field.is_nested and key in _PROMOTED_DEFAULTS:
                    assert field.name in merged, f"Promoted field '{field.name}' missing from merged output"


class TestDeprecatedFieldDetection:
    """TS-33-P5: Unknown active fields get DEPRECATED markers."""

    @given(unknowns=unknown_field_names())
    @settings(max_examples=15)
    def test_unknown_fields_marked_deprecated(self, unknowns: list[str]) -> None:
        """Property 5: Deprecated field detection.

        Validates: 33-REQ-2.4
        """
        lines = ["[orchestrator]", "parallel = 1"]
        for name in unknowns:
            lines.append(f'{name} = "test_value"')
        existing = "\n".join(lines) + "\n"

        merged = merge_existing_config(existing)

        for name in unknowns:
            # Find lines referencing this unknown field
            field_lines = [line for line in merged.split("\n") if name in line]
            assert any("DEPRECATED" in line for line in field_lines), f"Unknown field '{name}' not marked as DEPRECATED"


class TestSchemaExtractionDeterminism:
    """TS-33-P6: Multiple calls to extract_schema produce identical results."""

    def test_deterministic_extraction(self) -> None:
        """Property 6: Schema extraction determinism.

        Validates: 33-REQ-1.5, 33-REQ-4.1
        """
        results = [extract_schema(AgentFoxConfig) for _ in range(10)]

        for i in range(1, 10):
            # Compare section paths
            paths_0 = [s.path for s in results[0]]
            paths_i = [s.path for s in results[i]]
            assert paths_0 == paths_i, f"Call {i} has different section paths"

            # Compare field names within each section
            for s0, si in zip(results[0], results[i]):
                names_0 = [f.name for f in s0.fields]
                names_i = [f.name for f in si.fields]
                assert names_0 == names_i, f"Call {i} has different fields in section '{s0.path}'"

                # Compare defaults
                defaults_0 = [f.default for f in s0.fields]
                defaults_i = [f.default for f in si.fields]
                assert defaults_0 == defaults_i, f"Call {i} has different defaults in section '{s0.path}'"


class TestMergeIdempotency:
    """TS-33-P7: Merging an already-merged config is a no-op."""

    @given(config_toml=valid_config_toml())
    @settings(max_examples=15)
    def test_merge_idempotent(self, config_toml: str) -> None:
        """Property 7: Merge idempotency.

        Validates: 33-REQ-2.5
        """
        once = merge_existing_config(config_toml)
        twice = merge_existing_config(once)
        assert twice == once, "Second merge produced different output"
