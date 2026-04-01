# Implementation Plan: Config Simplification

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation proceeds in four groups: (1) write failing tests,
(2) update schema and template generation, (3) update merge logic and code
defaults, (4) create reference documentation. Groups 2 and 3 contain the core
code changes; group 4 is documentation-only.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/core/test_config_simplification.py tests/property/core/test_config_simplification_props.py tests/integration/core/test_config_simplification_integ.py -v`
- Unit tests: `uv run pytest -q tests/unit/core/test_config_simplification.py -v`
- Property tests: `uv run pytest -q tests/property/core/test_config_simplification_props.py -v`
- Integration tests: `uv run pytest -q tests/integration/core/test_config_simplification_integ.py -v`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/core/test_config_simplification.py`
    - Test functions for TS-68-1 through TS-68-10, TS-68-12 through TS-68-14, TS-68-17
    - Tests for template visibility, promoted fields, footer, line count, descriptions
    - Tests for merge behavior: hidden section preservation, no hidden injection, empty merge, footer dedup
    - _Test Spec: TS-68-1 through TS-68-10, TS-68-12 through TS-68-14, TS-68-17_

  - [x] 1.2 Create property test file `tests/property/core/test_config_simplification_props.py`
    - Property tests for TS-68-P1 through TS-68-P6
    - Template TOML validity, section containment, merge preservation, hidden section injection, footer dedup, verifier default
    - _Test Spec: TS-68-P1 through TS-68-P6_

  - [x] 1.3 Create integration test file `tests/integration/core/test_config_simplification_integ.py`
    - Integration test for TS-68-11: hidden sections load correctly
    - _Test Spec: TS-68-11_

  - [x] 1.4 Create edge case tests in unit test file
    - TS-68-E1 through TS-68-E4: merge with hidden sections, template parsability, deprecated fields, description fallback
    - _Test Spec: TS-68-E1 through TS-68-E4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [ ] 2. Simplify template generation
  - [ ] 2.1 Update `_VISIBLE_SECTIONS` and `_PROMOTED_DEFAULTS` in `config_schema.py`
    - Add `_VISIBLE_SECTIONS` set with orchestrator, models, archetypes (+ subsections), security
    - Update `_PROMOTED_DEFAULTS` to include quality_gate, max_budget_usd, instances.verifier
    - _Requirements: 68-REQ-1.1, 68-REQ-2.1 through 68-REQ-2.5_

  - [ ] 2.2 Update `_DEFAULT_DESCRIPTIONS` in `config_schema.py`
    - Replace terse descriptions with plain-language explanations for all promoted fields
    - Ensure no description is a mechanical transformation of the field name
    - _Requirements: 68-REQ-3.1, 68-REQ-3.2, 68-REQ-3.3_

  - [ ] 2.3 Update `generate_config_template()` in `config_gen.py`
    - Filter sections to only render those in `_VISIBLE_SECTIONS`
    - Append footer comment referencing `docs/config-reference.md`
    - Ensure template stays under 60 lines
    - _Requirements: 68-REQ-1.1, 68-REQ-1.2, 68-REQ-1.4, 68-REQ-6.1_

  - [ ] 2.4 Update `ArchetypeInstancesConfig.verifier` default in config model
    - Change default from `1` to `2`
    - _Requirements: 68-REQ-2.6_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/core/test_config_simplification.py -k "test_visible or test_hidden or test_footer or test_line_count or test_quality_gate or test_verifier_instances or test_archetype_toggles or test_budget_model or test_verifier_default or test_descriptions" -v`
    - [ ] Property tests pass: `uv run pytest -q tests/property/core/test_config_simplification_props.py -v`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 68-REQ-1.1 through 68-REQ-1.4, 68-REQ-2.1 through 68-REQ-2.6, 68-REQ-3.1 through 68-REQ-3.3, 68-REQ-6.1 acceptance criteria met

- [ ] 3. Update merge logic
  - [ ] 3.1 Update `merge_config()` in `config_merge.py`
    - Skip adding hidden sections (not in `_VISIBLE_SECTIONS`) when they are absent from existing config
    - Preserve hidden sections that ARE present in existing config
    - Handle footer non-duplication during merge
    - _Requirements: 68-REQ-5.1, 68-REQ-5.3, 68-REQ-1.E1, 68-REQ-6.E1_

  - [ ] 3.2 Update empty-config handling in `merge_config()`
    - When existing content is empty/whitespace, produce simplified template (not verbose)
    - _Requirements: 68-REQ-5.E2_

  - [ ] 3.3 Verify deprecated field handling preserved
    - Ensure existing DEPRECATED marking behavior still works
    - _Requirements: 68-REQ-5.E1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/core/test_config_simplification.py -k "test_merge" -v`
    - [ ] Integration tests pass: `uv run pytest -q tests/integration/core/test_config_simplification_integ.py -v`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 68-REQ-5.1 through 68-REQ-5.3, 68-REQ-1.E1, 68-REQ-5.E1, 68-REQ-5.E2, 68-REQ-6.E1 acceptance criteria met

- [ ] 4. Create config reference documentation
  - [ ] 4.1 Write `docs/config-reference.md`
    - Table of contents with links to each section
    - Every config section as a heading
    - Every field with type, default, bounds, description
    - TOML examples for complex fields (thinking, pricing, allowlists)
    - _Requirements: 68-REQ-4.1, 68-REQ-4.2, 68-REQ-4.3, 68-REQ-4.4_

  - [ ] 4.2 Update template header comment
    - Remove "do not remove section headers" instruction (no longer relevant with simplified template)
    - _Requirements: 68-REQ-1.4_

  - [ ] 4.V Verify task group 4
    - [ ] Doc tests pass: `uv run pytest -q tests/unit/core/test_config_simplification.py -k "test_reference_doc" -v`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 68-REQ-4.1 through 68-REQ-4.4 acceptance criteria met

- [ ] 5. Checkpoint — Config Simplification Complete
  - Ensure all tests pass, ask the user if questions arise.
  - Update relevant documentation (README if needed).

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 68-REQ-1.1 | TS-68-1 | 2.1, 2.3 | test_visible_sections |
| 68-REQ-1.2 | TS-68-2 | 2.3 | test_hidden_sections_omitted |
| 68-REQ-1.3 | TS-68-3 | 2.3 | test_footer_present |
| 68-REQ-1.4 | TS-68-4 | 2.3 | test_line_count_bound |
| 68-REQ-1.5 | TS-68-11 | (no code change) | test_hidden_sections_load |
| 68-REQ-1.E1 | TS-68-12, TS-68-E1 | 3.1 | test_merge_preserves_hidden |
| 68-REQ-1.E2 | TS-68-E2 | 2.3 | test_template_valid_toml |
| 68-REQ-2.1 | TS-68-5 | 2.1 | test_quality_gate_promoted |
| 68-REQ-2.2 | TS-68-6 | 2.1 | test_verifier_instances_promoted |
| 68-REQ-2.3 | TS-68-7 | 2.1 | test_archetype_toggles_promoted |
| 68-REQ-2.4 | TS-68-8 | 2.1 | test_budget_model_promoted |
| 68-REQ-2.5 | TS-68-8 | 2.1 | test_budget_model_promoted |
| 68-REQ-2.6 | TS-68-9 | 2.4 | test_verifier_default_changed |
| 68-REQ-3.1 | TS-68-10 | 2.2 | test_descriptions_meaningful |
| 68-REQ-3.2 | TS-68-10 | 2.2 | test_descriptions_meaningful |
| 68-REQ-3.3 | TS-68-10 | 2.2 | test_descriptions_meaningful |
| 68-REQ-3.E1 | TS-68-E4 | (existing) | test_description_fallback |
| 68-REQ-4.1 | TS-68-15 | 4.1 | test_reference_doc_exists |
| 68-REQ-4.2 | TS-68-16 | 4.1 | test_reference_doc_coverage |
| 68-REQ-4.3 | TS-68-15 | 4.1 | test_reference_doc_exists |
| 68-REQ-4.4 | TS-68-15 | 4.1 | test_reference_doc_exists |
| 68-REQ-5.1 | TS-68-12 | 3.1 | test_merge_preserves_values |
| 68-REQ-5.2 | TS-68-14 | 3.2 | test_merge_empty_config |
| 68-REQ-5.3 | TS-68-13 | 3.1 | test_merge_no_hidden_injection |
| 68-REQ-5.E1 | TS-68-E3 | 3.3 | test_deprecated_fields_marked |
| 68-REQ-5.E2 | TS-68-14 | 3.2 | test_merge_empty_config |
| 68-REQ-6.1 | TS-68-3 | 2.3 | test_footer_present |
| 68-REQ-6.E1 | TS-68-17 | 3.1 | test_footer_not_duplicated |
| Property 1 | TS-68-P1 | 2.3 | test_prop_template_valid_toml |
| Property 2 | TS-68-P2 | 2.3 | test_prop_visible_containment |
| Property 6 | TS-68-P3 | 3.1 | test_prop_merge_preserves_values |
| Property 7 | TS-68-P4 | 3.1 | test_prop_no_hidden_injection |
| Property 9 | TS-68-P5 | 3.1 | test_prop_footer_non_duplication |
| Property 10 | TS-68-P6 | 2.4 | test_prop_verifier_default |

## Notes

- Task group 2 is the largest group because template generation and schema
  changes are tightly coupled — changing `_VISIBLE_SECTIONS` without updating
  the generator would break tests.
- The `quality_gate` promoted value (`"make check"`) is a template-level
  default, not a code-level default. The `OrchestratorConfig.quality_gate`
  field still defaults to `""` in the Pydantic model.
- Existing tests in `tests/unit/core/test_config_gen.py` and
  `tests/property/core/test_config_gen_props.py` will likely need updates
  in task groups 2-3 since the template output format changes.
