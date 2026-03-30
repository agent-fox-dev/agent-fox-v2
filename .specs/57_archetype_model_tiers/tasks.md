# Implementation Plan: Archetype Model Tier Defaults

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This is a small, focused change: flip 4 constants in the archetype registry,
change 1 line in the orchestrator's ceiling logic, and update documentation.
Task group 1 writes failing tests, task group 2 implements the changes, task
group 3 is the checkpoint.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_archetype_tiers.py tests/property/test_archetype_tiers_props.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_archetype_tiers.py`
    - Tests for TS-57-1 through TS-57-5: registry default tier assertions
    - Tests for TS-57-6: escalation ladder ceiling is ADVANCED
    - Tests for TS-57-7: STANDARD agent escalates to ADVANCED
    - Tests for TS-57-8: ADVANCED agent blocks after exhaustion
    - Tests for TS-57-9: config override takes precedence
    - Tests for TS-57-10: no config override falls back to registry
    - Tests for TS-57-11: assessed tier overrides everything
    - Tests for TS-57-E1: unknown archetype falls back to coder
    - Tests for TS-57-E2: assessment pipeline failure uses default + ADVANCED ceiling
    - Tests for TS-57-E3: invalid config tier raises ConfigError
    - Tests for TS-57-12 through TS-57-14: documentation content assertions
    - _Test Spec: TS-57-1 through TS-57-14, TS-57-E1 through TS-57-E3_

  - [x] 1.2 Create property test file `tests/property/test_archetype_tiers_props.py`
    - Tests for TS-57-P1: all registry defaults match spec
    - Tests for TS-57-P2: ceiling is always ADVANCED
    - Tests for TS-57-P3: STANDARD agents reach ADVANCED before exhaustion
    - Tests for TS-57-P4: ADVANCED agents exhaust without escalation
    - Tests for TS-57-P5: config override precedence
    - _Test Spec: TS-57-P1 through TS-57-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_archetype_tiers.py tests/property/test_archetype_tiers_props.py`

- [x] 2. Implement registry and ceiling changes
  - [x] 2.1 Update `ARCHETYPE_REGISTRY` in `agent_fox/session/archetypes.py`
    - Change Coder: `default_model_tier="STANDARD"` (was `"ADVANCED"`)
    - Change Skeptic: `default_model_tier="ADVANCED"` (was `"STANDARD"`)
    - Change Oracle: `default_model_tier="ADVANCED"` (was `"STANDARD"`)
    - Change Verifier: `default_model_tier="ADVANCED"` (was `"STANDARD"`)
    - _Requirements: 57-REQ-1.1, 57-REQ-1.2, 57-REQ-1.3, 57-REQ-1.4_

  - [x] 2.2 Fix tier ceiling in `agent_fox/engine/engine.py:_assess_node()`
    - Replace `tier_ceiling = ModelTier(entry.default_model_tier)` with `tier_ceiling = ModelTier.ADVANCED`
    - Separate archetype default tier into `archetype_default_tier` variable for pipeline fallback
    - _Requirements: 57-REQ-2.1, 57-REQ-2.E1_

  - [x] 2.3 Fix any existing tests broken by the default change
    - Updated `tests/unit/engine/test_session_lifecycle.py`: Coder now Sonnet, Skeptic now Opus
    - Updated `tests/unit/session/test_prompt_archetype.py`: Skeptic now Opus
    - Updated `tests/unit/oracle/test_registry.py`: Oracle default now ADVANCED
    - Updated stale comment in `tests/unit/test_predecessor_escalation.py`
    - Updated `docs/archetypes.md` with new tiers, escalation section, config override docs
    - _Requirements: 57-REQ-1.1 through 57-REQ-1.5_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_archetype_tiers.py tests/property/test_archetype_tiers_props.py`
    - [x] All existing tests still pass: `uv run pytest -q` (excluding pre-existing spec 58 failures)
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/session/archetypes.py agent_fox/engine/engine.py`
    - [x] Requirements 57-REQ-1.1 through 57-REQ-3.3 acceptance criteria met

- [x] 3. Checkpoint - Documentation and final verification
  - [x] 3.1 Update `docs/archetypes.md` with new default tiers
    - List each archetype and its default model tier
    - Describe config override mechanism via `archetypes.models`
    - Explain escalation: retry at current tier, then escalate to ADVANCED
    - _Requirements: 57-REQ-4.1, 57-REQ-4.2, 57-REQ-4.3_

  - [x] 3.2 Update config.toml comments to reflect new defaults
    - Update the commented example for `archetypes.models`
    - _Requirements: 57-REQ-4.2_

  - [x] 3.V Verify task group 3
    - [x] All spec tests pass: `uv run pytest -q tests/unit/test_archetype_tiers.py tests/property/test_archetype_tiers_props.py`
    - [x] Full test suite passes: `uv run pytest -q` (excluding pre-existing spec 58 failures)
    - [x] No linter warnings: `uv run ruff check agent_fox/ tests/` (16 pre-existing I001 errors, none introduced)
    - [x] Documentation is accurate and complete

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 57-REQ-1.1 | TS-57-1 | 2.1 | `test_archetype_tiers.py::test_skeptic_default_advanced` |
| 57-REQ-1.2 | TS-57-2 | 2.1 | `test_archetype_tiers.py::test_oracle_default_advanced` |
| 57-REQ-1.3 | TS-57-3 | 2.1 | `test_archetype_tiers.py::test_verifier_default_advanced` |
| 57-REQ-1.4 | TS-57-4 | 2.1 | `test_archetype_tiers.py::test_coder_default_standard` |
| 57-REQ-1.5 | TS-57-5 | 2.1 | `test_archetype_tiers.py::test_remaining_archetypes_standard` |
| 57-REQ-1.E1 | TS-57-E1 | 2.1 | `test_archetype_tiers.py::test_unknown_archetype_fallback` |
| 57-REQ-2.1 | TS-57-6 | 2.2 | `test_archetype_tiers.py::test_ceiling_always_advanced` |
| 57-REQ-2.2 | TS-57-7 | 2.2 | `test_archetype_tiers.py::test_standard_escalates_to_advanced` |
| 57-REQ-2.3 | TS-57-8 | 2.2 | `test_archetype_tiers.py::test_advanced_blocks_after_exhaustion` |
| 57-REQ-2.E1 | TS-57-E2 | 2.2 | `test_archetype_tiers.py::test_pipeline_failure_uses_default_with_advanced_ceiling` |
| 57-REQ-3.1 | TS-57-9 | — (existing) | `test_archetype_tiers.py::test_config_override_precedence` |
| 57-REQ-3.2 | TS-57-10 | — (existing) | `test_archetype_tiers.py::test_no_override_uses_registry` |
| 57-REQ-3.3 | TS-57-11 | — (existing) | `test_archetype_tiers.py::test_assessed_tier_overrides_all` |
| 57-REQ-3.E1 | TS-57-E3 | — (existing) | `test_archetype_tiers.py::test_invalid_config_tier_raises` |
| 57-REQ-4.1 | — | 3.1 | Manual (docs review) |
| 57-REQ-4.2 | — | 3.1, 3.2 | Manual (docs review) |
| 57-REQ-4.3 | — | 3.1 | Manual (docs review) |
| Property 1 | TS-57-P1 | 2.1 | `test_archetype_tiers_props.py::test_registry_defaults_match_spec` |
| Property 2 | TS-57-P2 | 2.2 | `test_archetype_tiers_props.py::test_ceiling_always_advanced` |
| Property 3 | TS-57-P3 | 2.2 | `test_archetype_tiers_props.py::test_standard_reaches_advanced` |
| Property 4 | TS-57-P4 | 2.2 | `test_archetype_tiers_props.py::test_advanced_exhausts_without_escalation` |
| 57-REQ-4.1 | TS-57-12 | 3.1 | `test_archetype_tiers.py::test_docs_list_default_tiers` |
| 57-REQ-4.2 | TS-57-13 | 3.1, 3.2 | `test_archetype_tiers.py::test_docs_describe_config_override` |
| 57-REQ-4.3 | TS-57-14 | 3.1 | `test_archetype_tiers.py::test_docs_explain_escalation` |
| Property 5 | TS-57-P5 | — (existing) | `test_archetype_tiers_props.py::test_config_override_precedence` |

## Notes

- This is a small, focused change. The core implementation is 4 constant changes
  in the archetype registry and 1 line change in the orchestrator.
- Task group 2.3 (fixing broken tests) may require updating assertions in
  existing test files that hardcode expectations about archetype default tiers.
- The `EscalationLadder` and `_resolve_model_tier` logic are unchanged — only
  the data they operate on changes.
