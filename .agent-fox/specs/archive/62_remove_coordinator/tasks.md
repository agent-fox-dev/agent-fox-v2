# Implementation Plan: Remove Coordinator Archetype

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a removal spec. Task group 1 writes tests that assert absence of the
coordinator. Task group 2 removes all coordinator code and updates existing
tests. Task group 3 is a final verification checkpoint.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/graph/test_no_coordinator.py tests/unit/session/test_no_coordinator.py tests/unit/core/test_no_coordinator.py tests/property/test_no_coordinator_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test files for coordinator absence assertions
    - Create `tests/unit/session/test_no_coordinator.py` for TS-62-1, TS-62-2, TS-62-6, TS-62-7
    - Create `tests/unit/graph/test_no_coordinator.py` for TS-62-4, TS-62-5, TS-62-9
    - Create `tests/unit/core/test_no_coordinator.py` for TS-62-3, TS-62-8, TS-62-E1
    - Create `tests/property/test_no_coordinator_props.py` for TS-62-P1, TS-62-P2
    - _Test Spec: TS-62-1 through TS-62-9, TS-62-E1, TS-62-P1, TS-62-P2_

  - [x] 1.2 Translate acceptance-criterion tests
    - One test function per TS-62-{N} entry
    - Tests MUST fail (coordinator still exists)
    - _Test Spec: TS-62-1 through TS-62-9_

  - [x] 1.3 Translate edge-case tests
    - One test function for TS-62-E1
    - _Test Spec: TS-62-E1_

  - [x] 1.4 Translate property tests
    - One property test per TS-62-P{N} entry
    - _Test Spec: TS-62-P1, TS-62-P2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — coordinator still exists
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Remove coordinator code and update existing tests
  - [x] 2.1 Remove coordinator from archetype registry and prompt mapping
    - Delete `"coordinator"` entry from `ARCHETYPE_REGISTRY` in `agent_fox/session/archetypes.py`
    - Remove `"coordinator": "coordinator"` from role mapping in `agent_fox/session/prompt.py`
    - Remove `"coordinator"` from known archetypes in `agent_fox/spec/parser.py`
    - _Requirements: 1.1, 1.2, 4.1, 5.1_

  - [x] 2.2 Remove coordinator from graph builder
    - Delete `_apply_coordinator_overrides()` function from `agent_fox/graph/builder.py`
    - Remove `coordinator_overrides` parameter from `build_graph()`
    - Remove Layer 2 call and update Layer 3 comment to Layer 2
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 2.3 Remove coordinator template and config
    - Delete `agent_fox/_templates/prompts/coordinator.md`
    - Remove `coordinator` field from `ModelConfig` in `agent_fox/core/config.py`
    - Remove coordinator description from `agent_fox/core/config_gen.py`
    - _Requirements: 2.1, 6.1, 6.2_

  - [x] 2.4 Update existing tests that reference coordinator
    - Remove `TestCoordinatorNotAssignable` class from `tests/unit/session/test_archetypes.py`
    - Remove `"coordinator"` from archetype lists in `test_archetypes.py`, `test_archetype_tiers.py`, `test_archetype_tiers_props.py`
    - Remove coordinator prompt tests from `tests/unit/session/test_prompt.py`
    - Remove coordinator role from `tests/property/session/test_prompt_props.py`
    - Remove coordinator from `tests/unit/test_sdk_config.py`
    - Remove coordinator from `tests/property/test_sdk_features_props.py`
    - Remove coordinator override test from `tests/unit/graph/test_builder_archetypes.py`
    - Remove coordinator from `tests/property/ui/test_progress_events_props.py`
    - Remove coordinator default config assertion from `tests/property/core/test_config_props.py`
    - _Requirements: 7.1, 7.2_

  - [x] 2.5 Update config files
    - Remove `coordinator = "ADVANCED"` from `.agent-fox/config.toml`
    - Remove `coordinator = "STANDARD"` from `hack/config.toml`
    - _Requirements: 6.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/graph/test_no_coordinator.py tests/unit/session/test_no_coordinator.py tests/unit/core/test_no_coordinator.py tests/property/test_no_coordinator_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 1.1–7.2 acceptance criteria met

- [x] 3. Checkpoint — Coordinator fully removed
  - Ensure `make check` passes with no regressions.
  - Verify no remaining references to coordinator in tracked Python files:
    `git grep -l coordinator -- '*.py' | grep -v archive | grep -v __pycache__`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 62-REQ-1.1 | TS-62-1 | 2.1 | `test_no_coordinator.py::test_coordinator_absent_from_registry` |
| 62-REQ-1.2 | TS-62-2 | 2.1 | `test_no_coordinator.py::test_get_archetype_coordinator_falls_back` |
| 62-REQ-2.1 | TS-62-3 | 2.3 | `test_no_coordinator.py::test_coordinator_template_deleted` |
| 62-REQ-3.1 | TS-62-4 | 2.2 | `test_no_coordinator.py::test_build_graph_no_coordinator_overrides_param` |
| 62-REQ-3.2 | TS-62-5 | 2.2 | `test_no_coordinator.py::test_apply_coordinator_overrides_removed` |
| 62-REQ-3.3 | TS-62-9 | 2.2 | `test_no_coordinator.py::test_two_layer_archetype_assignment` |
| 62-REQ-4.1 | TS-62-6 | 2.1 | `test_no_coordinator.py::test_prompt_role_mapping_excludes_coordinator` |
| 62-REQ-5.1 | TS-62-7 | 2.1 | `test_no_coordinator.py::test_parser_known_archetypes_excludes_coordinator` |
| 62-REQ-6.1 | TS-62-8 | 2.3 | `test_no_coordinator.py::test_model_config_no_coordinator_field` |
| 62-REQ-6.E1 | TS-62-E1 | 2.3 | `test_no_coordinator.py::test_config_with_coordinator_loads_ok` |
| 62-REQ-7.1 | (make check) | 2.4 | `make check` |
| 62-REQ-7.2 | (audit) | 2.4 | `git grep` |
| Property 1 | TS-62-P1 | 2.1–2.3 | `test_no_coordinator_props.py::test_no_coordinator_in_any_collection` |
| Property 6 | TS-62-P2 | 2.3 | `test_no_coordinator_props.py::test_config_tolerance_extra_model_fields` |

## Notes

- Archived specs in `.specs/archive/` are not modified — they reference the
  coordinator historically and are retained for decision records.
- The `ModelConfig` class uses `extra="ignore"`, so existing config files with
  a `coordinator` field will continue to load without error after the field is
  removed.
