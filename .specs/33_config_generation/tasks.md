# Implementation Plan: Config Generation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in five groups: (1) write failing tests, (2) schema
extraction and template generation, (3) config merge logic, (4) wire into
`init` command and clean up dead code, (5) integration tests and documentation.

## Test Commands

- Spec tests: `uv run pytest tests/unit/core/test_config_gen.py tests/property/core/test_config_gen_props.py -v`
- Unit tests: `uv run pytest tests/unit/core/test_config_gen.py -v`
- Property tests: `uv run pytest tests/property/core/test_config_gen_props.py -v`
- Integration tests: `uv run pytest tests/integration/test_init.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create `tests/unit/core/test_config_gen.py`
    - Test class `TestTemplateGeneration` with tests for TS-33-1 through TS-33-5
    - Test class `TestConfigMerge` with tests for TS-33-6 through TS-33-10
    - Test class `TestSchemaExtraction` with tests for TS-33-12, TS-33-13
    - Test class `TestDeadCodeRemoval` with tests for TS-33-14, TS-33-15
    - Tests import from `agent_fox.core.config_gen` (module does not exist yet)
    - _Test Spec: TS-33-1 through TS-33-15_

  - [ ] 1.2 Create edge case tests in `tests/unit/core/test_config_gen.py`
    - Test class `TestTemplateEdgeCases` with TS-33-E1 through TS-33-E4
    - Test class `TestMergeEdgeCases` with TS-33-E5 through TS-33-E7
    - _Test Spec: TS-33-E1 through TS-33-E7_

  - [ ] 1.3 Create `tests/property/core/test_config_gen_props.py`
    - Property tests TS-33-P1 through TS-33-P7
    - Use Hypothesis strategies for generating random config overrides and field subsets
    - _Test Spec: TS-33-P1 through TS-33-P7_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/core/test_config_gen.py tests/property/core/test_config_gen_props.py`

- [ ] 2. Schema extraction and template generation
  - [ ] 2.1 Add `tomlkit` dependency
    - Add to `pyproject.toml` dependencies
    - Run `uv sync` to install
    - _Requirements: 33-REQ-1.1_

  - [ ] 2.2 Create `agent_fox/core/config_gen.py` — schema extraction
    - Implement `FieldSpec` and `SectionSpec` dataclasses
    - Implement `extract_schema(model, prefix)` that walks Pydantic `model_fields`
    - Handle nested `BaseModel` fields recursively as subsections
    - Use field aliases where defined (e.g., `skeptic_settings`)
    - Invoke `default_factory` for mutable defaults
    - Extract bounds from `_clamp` calls via field validator inspection or hardcoded map
    - _Requirements: 33-REQ-4.1, 33-REQ-4.2, 33-REQ-4.E1_

  - [ ] 2.3 Implement `generate_config_template(schema)` in `config_gen.py`
    - Render each section as `# [section_name]` header
    - Render each field as description comment + commented key-value pair
    - Handle None defaults with "not set by default" comment
    - Handle empty list/dict defaults
    - Add file header comment
    - _Requirements: 33-REQ-1.1, 33-REQ-1.2, 33-REQ-1.3, 33-REQ-1.4, 33-REQ-1.5_
    - _Requirements: 33-REQ-1.E1, 33-REQ-1.E2, 33-REQ-1.E3_

  - [ ] 2.4 Implement `generate_default_config()` convenience function
    - Combines `extract_schema` + `generate_config_template`
    - _Requirements: 33-REQ-3.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest tests/unit/core/test_config_gen.py::TestTemplateGeneration tests/unit/core/test_config_gen.py::TestSchemaExtraction tests/unit/core/test_config_gen.py::TestTemplateEdgeCases -v`
    - [ ] Property tests pass: `uv run pytest tests/property/core/test_config_gen_props.py::TestTemplateCompleteness tests/property/core/test_config_gen_props.py::TestRoundTripDefaultEquivalence tests/property/core/test_config_gen_props.py::TestSchemaExtractionDeterminism -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/core/config_gen.py`
    - [ ] Requirements 33-REQ-1.*, 33-REQ-3.*, 33-REQ-4.* acceptance criteria met

- [ ] 3. Config merge logic
  - [ ] 3.1 Implement `merge_config(existing_content, schema)` in `config_gen.py`
    - Parse existing content with `tomlkit`
    - Identify active user values and preserve them
    - Add missing schema fields as commented entries with descriptions
    - Preserve user comments and formatting
    - _Requirements: 33-REQ-2.1, 33-REQ-2.2, 33-REQ-2.3_

  - [ ] 3.2 Implement deprecated field detection
    - Compare active keys against schema field names per section
    - Prefix unrecognized fields with `# DEPRECATED: '<key>' is no longer recognized`
    - Comment out the deprecated value
    - _Requirements: 33-REQ-2.4_

  - [ ] 3.3 Implement no-op detection and edge cases
    - Skip merge when output would be identical (byte-for-byte)
    - Handle invalid TOML: catch parse error, log warning, return unchanged
    - Handle empty/whitespace content: delegate to fresh generation
    - _Requirements: 33-REQ-2.5, 33-REQ-2.E1, 33-REQ-2.E2_

  - [ ] 3.4 Implement `merge_existing_config(existing_content)` convenience function
    - Combines `extract_schema` + `merge_config`
    - _Requirements: 33-REQ-2.1 through 33-REQ-2.5_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest tests/unit/core/test_config_gen.py::TestConfigMerge tests/unit/core/test_config_gen.py::TestMergeEdgeCases -v`
    - [ ] Property tests pass: `uv run pytest tests/property/core/test_config_gen_props.py::TestMergeValuePreservation tests/property/core/test_config_gen_props.py::TestMergeCompleteness tests/property/core/test_config_gen_props.py::TestDeprecatedFieldDetection tests/property/core/test_config_gen_props.py::TestMergeIdempotency -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/core/config_gen.py`
    - [ ] Requirements 33-REQ-2.* acceptance criteria met

- [ ] 4. Wire into init and clean up dead code
  - [ ] 4.1 Remove `MemoryConfig` from `agent_fox/core/config.py`
    - Delete `MemoryConfig` class
    - Remove `memory` field from `AgentFoxConfig`
    - Ensure `[memory]` in TOML is silently ignored (root model has `extra="ignore"`)
    - _Requirements: 33-REQ-5.1, 33-REQ-5.2_

  - [ ] 4.2 Add `description` metadata to `Field()` calls in `config.py`
    - Add `description=` kwarg to fields that lack it, so the generator can
      extract meaningful comments
    - _Requirements: 33-REQ-1.2_

  - [ ] 4.3 Update `agent_fox/cli/init.py` to use the generator
    - Remove `_DEFAULT_CONFIG` string constant
    - Fresh init: call `generate_default_config()` and write result
    - Re-init: read existing file, call `merge_existing_config()`, write result
    - Update log messages to report merge actions
    - _Requirements: 33-REQ-1.1, 33-REQ-2.1 through 33-REQ-2.5_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/core/test_config_gen.py::TestDeadCodeRemoval -v`
    - [ ] Integration tests pass: `uv run pytest tests/integration/test_init.py -v`
    - [ ] All existing tests still pass: `uv run pytest -x -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/core/config.py agent_fox/core/config_gen.py agent_fox/cli/init.py`
    - [ ] Requirements 33-REQ-5.* acceptance criteria met

- [ ] 5. Checkpoint — Integration and documentation
  - [ ] 5.1 Update or add integration tests in `tests/integration/test_init.py`
    - Test fresh init produces a complete config.toml (TS-33-11)
    - Test re-init merges correctly (new fields added, user values preserved)
    - Test re-init with deprecated fields marks them
    - _Test Spec: TS-33-11_

  - [ ] 5.2 Verify all tests pass end-to-end
    - `uv run pytest -x -q`
    - `uv run ruff check agent_fox/ tests/`

  - [ ] 5.3 Update documentation
    - Update `docs/cli-reference.md` — describe the merge behavior on re-init
    - Update `README.md` if it references config setup

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/core/test_config_gen.py tests/property/core/test_config_gen_props.py tests/integration/test_init.py -v`
    - [ ] Full test suite passes: `uv run pytest -x -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`
    - [ ] All 33-REQ-* acceptance criteria met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 33-REQ-1.1 | TS-33-1 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_contains_all_fields` |
| 33-REQ-1.2 | TS-33-2 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_includes_descriptions_and_bounds` |
| 33-REQ-1.3 | TS-33-3 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_has_section_headers` |
| 33-REQ-1.4 | TS-33-4 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_uncommented_is_valid_toml` |
| 33-REQ-1.5 | TS-33-5 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_field_ordering` |
| 33-REQ-1.E1 | TS-33-E1 | 2.3 | `test_config_gen.py::TestTemplateEdgeCases::test_none_default` |
| 33-REQ-1.E2 | TS-33-E2 | 2.3 | `test_config_gen.py::TestTemplateEdgeCases::test_empty_list_default` |
| 33-REQ-1.E3 | TS-33-E3 | 2.3 | `test_config_gen.py::TestTemplateEdgeCases::test_empty_dict_default` |
| 33-REQ-2.1 | TS-33-6 | 3.1 | `test_config_gen.py::TestConfigMerge::test_merge_preserves_active_values` |
| 33-REQ-2.2 | TS-33-7 | 3.1 | `test_config_gen.py::TestConfigMerge::test_merge_adds_missing_fields` |
| 33-REQ-2.3 | TS-33-8 | 3.1 | `test_config_gen.py::TestConfigMerge::test_merge_preserves_user_comments` |
| 33-REQ-2.4 | TS-33-9 | 3.2 | `test_config_gen.py::TestConfigMerge::test_merge_marks_deprecated` |
| 33-REQ-2.5 | TS-33-10 | 3.3 | `test_config_gen.py::TestConfigMerge::test_merge_noop_when_current` |
| 33-REQ-2.E1 | TS-33-E5 | 3.3 | `test_config_gen.py::TestMergeEdgeCases::test_invalid_toml_skips_merge` |
| 33-REQ-2.E2 | TS-33-E6 | 3.3 | `test_config_gen.py::TestMergeEdgeCases::test_empty_config_treated_as_fresh` |
| 33-REQ-3.1 | TS-33-11 | 2.4 | `test_init.py::test_fresh_config_loads_defaults` |
| 33-REQ-3.2 | TS-33-4 | 2.3 | `test_config_gen.py::TestTemplateGeneration::test_template_uncommented_is_valid_toml` |
| 33-REQ-3.E1 | TS-33-E4 | 2.2 | `test_config_gen.py::TestTemplateEdgeCases::test_alias_used_in_template` |
| 33-REQ-4.1 | TS-33-12 | 2.2 | `test_config_gen.py::TestSchemaExtraction::test_returns_all_sections` |
| 33-REQ-4.2 | TS-33-13 | 2.2 | `test_config_gen.py::TestSchemaExtraction::test_auto_discovers_new_fields` |
| 33-REQ-4.E1 | TS-33-E7 | 2.2 | `test_config_gen.py::TestMergeEdgeCases::test_factory_default_resolved` |
| 33-REQ-5.1 | TS-33-14 | 4.1 | `test_config_gen.py::TestDeadCodeRemoval::test_memory_config_removed` |
| 33-REQ-5.2 | TS-33-15 | 4.1 | `test_config_gen.py::TestDeadCodeRemoval::test_memory_section_ignored` |
| Property 1 | TS-33-P1 | 2.3 | `test_config_gen_props.py::TestTemplateCompleteness` |
| Property 2 | TS-33-P2 | 2.4 | `test_config_gen_props.py::TestRoundTripDefaultEquivalence` |
| Property 3 | TS-33-P3 | 3.1 | `test_config_gen_props.py::TestMergeValuePreservation` |
| Property 4 | TS-33-P4 | 3.1 | `test_config_gen_props.py::TestMergeCompleteness` |
| Property 5 | TS-33-P5 | 3.2 | `test_config_gen_props.py::TestDeprecatedFieldDetection` |
| Property 6 | TS-33-P6 | 2.2 | `test_config_gen_props.py::TestSchemaExtractionDeterminism` |
| Property 7 | TS-33-P7 | 3.3 | `test_config_gen_props.py::TestMergeIdempotency` |

## Notes

- `tomlkit` preserves comments and formatting — critical for the merge use case.
  Do not substitute with `tomli-w` (which discards comments).
- The `_clamp` bounds are currently encoded in validator functions, not in field
  metadata. The schema extractor will need either a hardcoded bounds map or
  introspection of the validator source. A hardcoded map keyed by
  `(model_name, field_name)` is simpler and sufficient since bounds rarely change.
- Existing tests in `test_config.py` and `test_config_props.py` must continue
  to pass after `MemoryConfig` removal. Check for any assertions referencing
  `config.memory`.
- The `skeptic_config` field has alias `skeptic_settings` — the template must
  use `skeptic_settings` as the TOML key to match what `load_config` expects.
