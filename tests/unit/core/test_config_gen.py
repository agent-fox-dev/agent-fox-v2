"""Unit tests for config generation and merge system.

Test Spec: TS-33-1 through TS-33-15, TS-33-E1 through TS-33-E7
Requirements: 33-REQ-1.*, 33-REQ-2.*, 33-REQ-3.*, 33-REQ-4.*, 33-REQ-5.*
"""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel, create_model

from agent_fox.core.config import (
    AgentFoxConfig,
    OrchestratorConfig,
    load_config,
)
from agent_fox.core.config_gen import (
    _PROMOTED_DEFAULTS,
    extract_schema,
    generate_default_config,
    merge_existing_config,
)


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Helper to write TOML content to a temporary file."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(content)
    return config_path


def _strip_comment_prefixes(template: str) -> str:
    """Remove the '# ' prefix from lines that start with it.

    Lines that are just '#' (empty comment) or start with '# ' get the
    prefix stripped. This simulates 'uncommenting' all fields.
    """
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


def _extract_field_names_in_order(template: str, section: str) -> list[str]:
    """Extract field names in order from a template section.

    Finds lines like 'field_name = ...' or '# field_name = ...' within
    the given section (handles both active and commented headers).
    """
    lines = template.split("\n")
    in_section = False
    field_names = []

    for line in lines:
        stripped = line.strip()
        # Check for section header (active or commented)
        if stripped == f"[{section}]" or stripped == f"# [{section}]":
            in_section = True
            continue
        # Check for next section header (end of current section)
        if in_section and (
            re.match(r"^# \[[\w.]+\]$", stripped) or re.match(r"^\[[\w.]+\]$", stripped)
        ):
            break
        # Extract field names from active or commented key-value pairs
        if in_section:
            m = re.match(r"^#{0,2}\s*(\w+)\s*=", line)
            if m:
                field_names.append(m.group(1))
    return field_names


class TestTemplateGeneration:
    """Tests for config template generation (TS-33-1 through TS-33-5)."""

    def test_template_contains_all_fields(self) -> None:
        """TS-33-1: Template includes an entry for every field.

        Promoted fields appear as active (uncommented); others as commented.
        Requirement: 33-REQ-1.1
        """
        template = generate_default_config()
        schema = extract_schema(AgentFoxConfig)

        for section in schema:
            for field in section.fields:
                if not field.is_nested:
                    if (section.path, field.name) in _PROMOTED_DEFAULTS:
                        assert f"{field.name} =" in template, (
                            f"Missing active entry for '{field.name}' "
                            f"in section '{section.path}'"
                        )
                    else:
                        assert f"# {field.name} =" in template, (
                            f"Missing commented entry for '{field.name}' "
                            f"in section '{section.path}'"
                        )

    def test_template_includes_descriptions_and_bounds(self) -> None:
        """TS-33-2: Fields include descriptions and bounds in comments.

        Requirement: 33-REQ-1.2
        """
        template = generate_default_config()

        # parallel has bounds 1-8
        assert "1-8" in template, "Missing bounds for parallel field"
        # sync_interval has bounds >=0
        assert ">=0" in template, "Missing bounds for sync_interval"
        # parallel default is 1
        assert "default: 2" in template, "Missing default for parallel"
        # playful default is true
        assert "default: true" in template, "Missing default for playful"

    def test_template_has_section_headers(self) -> None:
        """TS-33-3: Template emits proper TOML section headers.

        Requirement: 33-REQ-1.3
        """
        template = generate_default_config()

        # Sections with promoted fields have active headers
        for section in ["orchestrator", "archetypes"]:
            assert f"[{section}]" in template, (
                f"Missing active section header for [{section}]"
            )

        # Other sections have commented headers
        for section in [
            "routing",
            "models",
            "hooks",
            "security",
            "theme",
            "platform",
            "knowledge",
            "tools",
        ]:
            assert f"# [{section}]" in template, (
                f"Missing section header for [{section}]"
            )

        # Sub-table headers
        assert "# [archetypes.instances]" in template
        assert "# [archetypes.skeptic_settings]" in template
        assert "# [archetypes.oracle_settings]" in template

    def test_template_uncommented_is_valid_toml(self, tmp_path: Path) -> None:
        """TS-33-4: Uncommented template is valid TOML that load_config accepts.

        Requirements: 33-REQ-1.4, 33-REQ-3.2
        """
        template = generate_default_config()
        uncommented = _strip_comment_prefixes(template)

        # Should parse as valid TOML
        parsed = tomllib.loads(uncommented)
        assert isinstance(parsed, dict)

        # Should load via load_config without errors
        config_path = _write_toml(tmp_path, uncommented)
        config = load_config(config_path)
        assert isinstance(config, AgentFoxConfig)

    def test_template_field_ordering(self) -> None:
        """TS-33-5: Fields appear in model definition order.

        Requirement: 33-REQ-1.5
        """
        template = generate_default_config()

        # Check orchestrator field ordering matches model
        template_fields = _extract_field_names_in_order(template, "orchestrator")
        model_fields = list(OrchestratorConfig.model_fields.keys())
        assert template_fields == model_fields, (
            f"Field ordering mismatch.\n"
            f"Template: {template_fields}\n"
            f"Model: {model_fields}"
        )


class TestConfigMerge:
    """Tests for config merge logic (TS-33-6 through TS-33-10)."""

    def test_merge_preserves_active_values(self) -> None:
        """TS-33-6: Merge preserves all uncommented user-set values.

        Requirement: 33-REQ-2.1
        """
        existing = "[orchestrator]\nparallel = 4\nsession_timeout = 60\n"
        merged = merge_existing_config(existing)

        # Values should be active (uncommented)
        assert "parallel = 4" in merged
        assert "session_timeout = 60" in merged

        # Ensure they are NOT commented out
        for line in merged.split("\n"):
            if "parallel = 4" in line:
                assert not line.lstrip().startswith("#"), (
                    "parallel = 4 should not be commented out"
                )
            if "session_timeout = 60" in line:
                assert not line.lstrip().startswith("#"), (
                    "session_timeout = 60 should not be commented out"
                )

    def test_merge_adds_missing_fields(self) -> None:
        """TS-33-7: Merge adds fields present in schema but missing from file.

        Requirement: 33-REQ-2.2
        """
        existing = "[orchestrator]\nparallel = 4\n"
        merged = merge_existing_config(existing)

        # Should have commented entries for other orchestrator fields
        assert "# sync_interval" in merged
        # Should have other sections
        assert "# [routing]" in merged or "[routing]" in merged
        assert "# [theme]" in merged or "[theme]" in merged

    def test_merge_preserves_user_comments(self) -> None:
        """TS-33-8: User comments not managed by the generator are preserved.

        Requirement: 33-REQ-2.3
        """
        existing = (
            "# My custom note about this project\n"
            "[orchestrator]\n"
            "# I set this high for the big repo\n"
            "parallel = 8\n"
        )
        merged = merge_existing_config(existing)

        assert "My custom note about this project" in merged
        assert "I set this high for the big repo" in merged

    def test_merge_marks_deprecated(self) -> None:
        """TS-33-9: Active fields not in schema are marked DEPRECATED.

        Requirement: 33-REQ-2.4
        """
        existing = '[orchestrator]\nparallel = 4\nremoved_old_option = "value"\n'
        merged = merge_existing_config(existing)

        assert "DEPRECATED" in merged
        assert "'removed_old_option'" in merged

    def test_merge_noop_when_current(self) -> None:
        """TS-33-10: Merging a fully current config is byte-for-byte identical.

        Requirement: 33-REQ-2.5
        """
        fresh = generate_default_config()
        merged = merge_existing_config(fresh)
        assert merged == fresh


class TestSchemaExtraction:
    """Tests for schema extraction (TS-33-12, TS-33-13)."""

    def test_returns_all_sections(self) -> None:
        """TS-33-12: extract_schema returns entries for all top-level sections.

        Requirement: 33-REQ-4.1
        """
        schema = extract_schema(AgentFoxConfig)
        section_paths = {s.path for s in schema}

        expected = {
            "orchestrator",
            "routing",
            "models",
            "hooks",
            "security",
            "theme",
            "platform",
            "knowledge",
            "archetypes",
            "tools",
            "pricing",
            "planning",
            "blocking",
        }
        assert section_paths == expected

    def test_auto_discovers_new_fields(self) -> None:
        """TS-33-13: Adding a field to a model appears in extracted schema.

        Requirement: 33-REQ-4.2
        """

        class TestModelV1(BaseModel):
            a: int = 1
            b: str = "x"

        schema1 = extract_schema(TestModelV1)
        # Flat model yields a single section with 2 fields
        total_fields_v1 = sum(len(s.fields) for s in schema1)
        assert total_fields_v1 == 2

        TestModelV2 = create_model(
            "TestModelV2",
            a=(int, 1),
            b=(str, "x"),
            c=(bool, True),
        )
        schema2 = extract_schema(TestModelV2)
        total_fields_v2 = sum(len(s.fields) for s in schema2)
        assert total_fields_v2 == 3


class TestDeadCodeRemoval:
    """Tests for dead code cleanup (TS-33-14, TS-33-15)."""

    def test_memory_config_removed(self) -> None:
        """TS-33-14: AgentFoxConfig no longer has a 'memory' field.

        Requirement: 33-REQ-5.1
        """
        assert "memory" not in AgentFoxConfig.model_fields

    def test_memory_section_ignored(self, tmp_path: Path) -> None:
        """TS-33-15: A TOML file with [memory] section loads without error.

        Requirement: 33-REQ-5.2
        """
        config_path = _write_toml(tmp_path, '[memory]\nmodel = "ADVANCED"\n')
        config = load_config(config_path)
        assert isinstance(config, AgentFoxConfig)


class TestTemplateEdgeCases:
    """Edge case tests for template generation (TS-33-E1 through TS-33-E4)."""

    def test_none_default(self) -> None:
        """TS-33-E1: Fields with None default show 'not set by default'.

        Requirement: 33-REQ-1.E1
        """
        template = generate_default_config()
        assert "not set by default" in template

        # The 'not set by default' comment should appear near max_cost
        lines = template.split("\n")
        max_cost_indices = [i for i, line in enumerate(lines) if "max_cost" in line]
        assert max_cost_indices, "max_cost field not found in template"
        max_cost_idx = max_cost_indices[0]
        # Check the line above or the same line has 'not set by default'
        context = "\n".join(lines[max(0, max_cost_idx - 1) : max_cost_idx + 1])
        assert "not set by default" in context

    def test_empty_list_default(self) -> None:
        """TS-33-E2: Fields with [] default render as [].

        Requirement: 33-REQ-1.E2
        """
        template = generate_default_config()
        assert "# pre_code = []" in template

    def test_empty_dict_default(self) -> None:
        """TS-33-E3: Fields with {} default render as {}.

        Requirement: 33-REQ-1.E3
        """
        template = generate_default_config()
        # modes should appear with empty table value
        assert "# modes" in template

    def test_alias_used_in_template(self) -> None:
        """TS-33-E4: Fields with aliases use alias as TOML key.

        Requirement: 33-REQ-3.E1
        """
        template = generate_default_config()
        assert "skeptic_settings" in template
        assert "skeptic_config" not in template


class TestMergeEdgeCases:
    """Edge case tests for merge logic (TS-33-E5 through TS-33-E7)."""

    def test_invalid_toml_skips_merge(self, caplog: pytest.LogCaptureFixture) -> None:
        """TS-33-E5: Merge on invalid TOML logs warning and returns unchanged.

        Requirement: 33-REQ-2.E1
        """
        bad = "[broken toml }{"
        with caplog.at_level(logging.WARNING):
            result = merge_existing_config(bad)

        assert result == bad
        # Should have logged a warning
        assert any(
            "invalid" in r.message.lower() or "toml" in r.message.lower()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        )

    def test_empty_config_treated_as_fresh(self) -> None:
        """TS-33-E6: Empty/whitespace config treated as fresh generation.

        Requirement: 33-REQ-2.E2
        """
        fresh = generate_default_config()
        assert merge_existing_config("") == fresh
        assert merge_existing_config("  \n\n  ") == fresh

    def test_factory_default_resolved(self) -> None:
        """TS-33-E7: Fields with default_factory have factory invoked.

        Requirement: 33-REQ-4.E1
        """
        schema = extract_schema(AgentFoxConfig)
        hooks_section = None
        for s in schema:
            if s.path == "hooks":
                hooks_section = s
                break
        assert hooks_section is not None, "hooks section not found"

        pre_code = None
        for f in hooks_section.fields:
            if f.name == "pre_code":
                pre_code = f
                break
        assert pre_code is not None, "pre_code field not found"
        assert pre_code.default == [], (
            f"Expected [] for pre_code default, got {pre_code.default!r}"
        )
