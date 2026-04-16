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

from agent_fox import __version__
from agent_fox.core.config import (
    AgentFoxConfig,
    OrchestratorConfig,
    load_config,
)
from agent_fox.core.config_gen import (
    _FOOTER_COMMENT,
    _GITHUB_REPO_URL,
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
        if in_section and (re.match(r"^# \[[\w.]+\]$", stripped) or re.match(r"^\[[\w.]+\]$", stripped)):
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
        """TS-33-1: Template includes active entries for all promoted fields.

        Promoted fields appear as active (uncommented). Non-promoted fields in
        visible sections are omitted from the simplified template (see
        docs/config-reference.md for all options).
        Requirement: 33-REQ-1.1
        """
        template = generate_default_config()
        schema = extract_schema(AgentFoxConfig)

        for section in schema:
            for field in section.fields:
                if not field.is_nested:
                    if (section.path, field.name) in _PROMOTED_DEFAULTS:
                        assert f"{field.name} =" in template, (
                            f"Missing active entry for '{field.name}' in section '{section.path}'"
                        )

    def test_template_includes_descriptions_and_bounds(self) -> None:
        """TS-33-2: Promoted fields include descriptions and bounds in comments.

        Requirement: 33-REQ-1.2
        """
        template = generate_default_config()

        # parallel has bounds 1-8 and is a promoted field
        assert "1-8" in template, "Missing bounds for parallel field"
        # parallel default is 2
        assert "default: 2" in template, "Missing default for parallel"
        # verifier instances is clamped to 1 (98-REQ-6.2) and is promoted
        assert "verifier = 1" in template, "Missing verifier instances field in template"

    def test_template_has_section_headers(self) -> None:
        """TS-33-3: Template emits proper TOML section headers for visible sections.

        Requirement: 33-REQ-1.3
        """
        template = generate_default_config()

        # Sections with promoted fields have active headers
        for section in ["orchestrator", "archetypes", "models"]:
            assert f"[{section}]" in template, f"Missing active section header for [{section}]"

        # Security has no promoted fields — appears as commented header
        assert "# [security]" in template

        # Hidden sections must not appear (even commented)
        for section in ["routing", "theme", "platform", "knowledge"]:
            assert f"[{section}]" not in template, (
                f"Hidden section [{section}] should not appear in simplified template"
            )
            assert f"# [{section}]" not in template, (
                f"Commented hidden section # [{section}] should not appear in template"
            )

        # Visible sub-table headers
        assert "[archetypes.instances]" in template

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
        """TS-33-5: Promoted fields appear in model definition order.

        Requirement: 33-REQ-1.5
        """
        template = generate_default_config()

        # Check promoted orchestrator fields appear in model definition order
        template_fields = _extract_field_names_in_order(template, "orchestrator")
        model_fields = list(OrchestratorConfig.model_fields.keys())
        # Template should only contain promoted fields, which are a subset of
        # model fields and must maintain their relative order
        for i in range(len(template_fields) - 1):
            idx_a = model_fields.index(template_fields[i])
            idx_b = model_fields.index(template_fields[i + 1])
            assert idx_a < idx_b, (
                f"Field '{template_fields[i]}' appears before '{template_fields[i + 1]}' in template but not in model"
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
                assert not line.lstrip().startswith("#"), "parallel = 4 should not be commented out"
            if "session_timeout = 60" in line:
                assert not line.lstrip().startswith("#"), "session_timeout = 60 should not be commented out"

    def test_merge_adds_missing_fields(self) -> None:
        """TS-33-7: Merge adds fields present in schema but missing from file.

        Only visible sections are added by merge. Hidden sections (routing,
        theme, etc.) are not injected.
        Requirement: 33-REQ-2.2
        """
        existing = "[orchestrator]\nparallel = 4\n"
        merged = merge_existing_config(existing)

        # Should have visible sections added
        assert "[models]" in merged or "# [models]" in merged
        assert "[archetypes]" in merged or "# [archetypes]" in merged
        # Hidden sections must NOT be added by merge
        assert "# [routing]" not in merged and "[routing]" not in merged
        assert "# [theme]" not in merged and "[theme]" not in merged

    def test_merge_preserves_user_comments(self) -> None:
        """TS-33-8: User comments not managed by the generator are preserved.

        Requirement: 33-REQ-2.3
        """
        existing = (
            "# My custom note about this project\n[orchestrator]\n# I set this high for the big repo\nparallel = 8\n"
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
            "security",
            "theme",
            "platform",
            "knowledge",
            "archetypes",
            "pricing",
            "planning",
            "blocking",
            "caching",
            "night_shift",
            "paths",
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

        The simplified template omits non-promoted fields from visible sections.
        This is tested via the schema directly rather than the template output.
        Requirement: 33-REQ-1.E1
        """
        # Verify the format function itself handles None correctly
        from agent_fox.core.config_gen import FieldSpec, _format_field_comment

        fs = FieldSpec(
            name="test_field",
            section="orchestrator",
            python_type="float | None",
            default=None,
            description="A nullable field",
            bounds=None,
            is_nested=False,
        )
        comment = _format_field_comment(fs)
        assert "not set by default" in comment

    def test_empty_list_default(self) -> None:
        """TS-33-E2: Fields with [] default render as [].

        Requirement: 33-REQ-1.E2
        """
        from agent_fox.core.config_gen import _format_toml_value

        assert _format_toml_value([]) == "[]"

    def test_empty_dict_default(self) -> None:
        """TS-33-E3: Fields with {} default render as {}.

        Requirement: 33-REQ-1.E3
        """
        from agent_fox.core.config_gen import _format_toml_value

        assert _format_toml_value({}) == "{}"

    def test_alias_used_in_template(self) -> None:
        """TS-33-E4: Fields with aliases use alias as TOML key.

        After the reviewer consolidation, skeptic_config (alias skeptic_settings)
        was replaced by reviewer_config (no alias). Verify the schema contains
        the reviewer_config field under archetypes.
        Requirement: 33-REQ-3.E1
        """
        schema = extract_schema(AgentFoxConfig)
        archetypes_section = next(s for s in schema if s.path == "archetypes")
        # Find the reviewer_config field (replaces skeptic_config/skeptic_settings)
        reviewer_field = next(
            (f for f in archetypes_section.fields if f.name == "reviewer_config"),
            None,
        )
        assert reviewer_field is not None, "reviewer_config not found in schema"
        assert reviewer_field.name == "reviewer_config"


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
        security_section = None
        for s in schema:
            if s.path == "security":
                security_section = s
                break
        assert security_section is not None, "security section not found"

        bash_allowlist_extend = None
        for f in security_section.fields:
            if f.name == "bash_allowlist_extend":
                bash_allowlist_extend = f
                break
        assert bash_allowlist_extend is not None, "bash_allowlist_extend field not found"
        assert bash_allowlist_extend.default == [], (
            f"Expected [] for bash_allowlist_extend default, got {bash_allowlist_extend.default!r}"
        )


class TestTemplateHeaderFooter:
    """Tests for config template header and footer comments (issue #360)."""

    def test_header_contains_version(self) -> None:
        """Template header includes the agent-fox version that generated the file."""
        template = generate_default_config()
        assert f"agent-fox {__version__}" in template, f"Template header must include version '{__version__}'"

    def test_header_contains_github_repo_url(self) -> None:
        """Template header includes the full GitHub repo URL."""
        template = generate_default_config()
        assert _GITHUB_REPO_URL in template, f"Template header must include GitHub URL '{_GITHUB_REPO_URL}'"

    def test_footer_contains_full_docs_url(self) -> None:
        """Template footer references the docs via full GitHub URL, not a relative path."""
        template = generate_default_config()
        assert "https://github.com/agent-fox-dev/agent-fox/blob/main/docs/config-reference.md" in template, (
            "Template footer must reference docs via full GitHub URL"
        )
        assert "see docs/config-reference.md" not in template, (
            "Template footer must not use a bare relative path to docs"
        )

    def test_footer_appears_exactly_once(self) -> None:
        """Footer appears exactly once at the end of the template."""
        template = generate_default_config()
        lines = template.splitlines()
        footer_lines = [ln for ln in lines if _FOOTER_COMMENT.strip() in ln]
        assert len(footer_lines) == 1, f"Footer should appear exactly once, found {len(footer_lines)}"

    def test_merge_preserves_new_footer(self) -> None:
        """Merge of a fresh config is byte-for-byte identical (footer preserved)."""
        fresh = generate_default_config()
        merged = merge_existing_config(fresh)
        assert merged == fresh, "Merging a fresh config must be idempotent"
