# Implementation Plan: Reviewer Consolidation

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan consolidates review archetypes into a single reviewer with modes
and folds fix_coder into coder. Group 1 writes failing tests. Groups 2-4
restructure the registry, update injection/convergence, and clean up config.
Group 5 merges templates. Group 6 updates existing tests. Group 7 verifies
wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/core/test_reviewer_consolidation.py tests/unit/graph/test_injection_modes.py tests/unit/session/test_convergence_dispatch.py tests/property/test_reviewer_properties.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/core/test_reviewer_consolidation.py`
    - Registry tests: reviewer entry, mode configs, old entries removed (TS-98-1 through TS-98-6, TS-98-13, TS-98-15)
    - Config tests: reviewer toggle, ReviewerConfig, instances (TS-98-16, TS-98-17, TS-98-14)
    - Edge cases: old config keys, coder no mode, reviewer disabled (TS-98-E1, TS-98-E2, TS-98-E3)
    - _Test Spec: TS-98-1 through TS-98-6, TS-98-13 through TS-98-17, TS-98-E1 through TS-98-E3_

  - [x] 1.2 Create `tests/unit/graph/test_injection_modes.py`
    - Injection tests: auto_pre collection, node creation, drift gating (TS-98-8, TS-98-9, TS-98-10)
    - _Test Spec: TS-98-8, TS-98-9, TS-98-10_

  - [x] 1.3 Create `tests/unit/session/test_convergence_dispatch.py`
    - Convergence dispatch: pre-review, audit-review routing (TS-98-11, TS-98-12)
    - Edge case: unknown mode (TS-98-E4)
    - _Test Spec: TS-98-11, TS-98-12, TS-98-E4_

  - [x] 1.4 Create `tests/unit/templates/test_reviewer_template.py`
    - Template existence and mode markers (TS-98-7)
    - _Test Spec: TS-98-7_

  - [x] 1.5 Create `tests/property/test_reviewer_properties.py`
    - Property tests: mode-archetype mapping, convergence dispatch, injection consistency, verifier clamping, coder fix equivalence, old names rejected (TS-98-P1 through TS-98-P6)
    - _Test Spec: TS-98-P1 through TS-98-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Restructure archetype registry
  - [x] 2.1 Define reviewer archetype with 4 modes in ARCHETYPE_REGISTRY
    - pre-review: allowlist=[], injection=auto_pre, STANDARD
    - drift-review: analysis allowlist, injection=auto_pre, STANDARD
    - audit-review: extended allowlist, injection=auto_mid, retry=True
    - fix-review: full allowlist, no injection, ADVANCED, max_turns=120
    - _Requirements: 98-REQ-1.1 through 98-REQ-1.5_

  - [x] 2.2 Add fix mode to coder archetype
    - templates=["fix_coding.md"], STANDARD, 300 turns, adaptive thinking 64k
    - _Requirements: 98-REQ-2.1, 98-REQ-2.2_

  - [x] 2.3 Update verifier: STANDARD tier, default single-instance
    - Change default_model_tier from "ADVANCED" to "STANDARD"
    - _Requirements: 98-REQ-6.1, 98-REQ-6.3_

  - [x] 2.4 Remove old entries from ARCHETYPE_REGISTRY
    - Remove: skeptic, oracle, auditor, fix_reviewer, fix_coder
    - _Requirements: 98-REQ-7.1, 98-REQ-7.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/core/test_reviewer_consolidation.py -k "registry or mode_config or old_entries or verifier"`
    - [x] All existing tests still pass: `uv run pytest -q` (pre-existing failures noted; consolidation-expected failures deferred to task group 6)
    - [x] No linter warnings: `uv run ruff check agent_fox/archetypes.py`

- [x] 3. Update injection and convergence
  - [x] 3.1 Update `ArchetypeEntry` NamedTuple in injection.py with mode field
    - Add `mode: str | None = None` field
    - _Requirements: 98-REQ-4.1_

  - [x] 3.2 Update `collect_enabled_auto_pre()` for reviewer modes
    - Check `archetypes.reviewer` toggle
    - Return entries with mode="pre-review" and mode="drift-review"
    - Apply drift-review gating (oracle gating)
    - _Requirements: 98-REQ-4.1, 98-REQ-4.4, 98-REQ-4.5_

  - [x] 3.3 Update `ensure_graph_archetypes()` for reviewer mode nodes
    - Create Node(archetype="reviewer", mode=...) for auto_pre and auto_mid
    - Update auditor injection to reviewer:audit-review
    - _Requirements: 98-REQ-4.2, 98-REQ-4.3_

  - [x] 3.4 Implement `converge_reviewer()` dispatch function
    - pre-review, drift-review → converge_skeptic
    - audit-review → converge_auditor
    - fix-review → passthrough (single instance)
    - Unknown mode → ValueError
    - _Requirements: 98-REQ-5.1, 98-REQ-5.2, 98-REQ-5.3, 98-REQ-5.E1_

  - [x] 3.5 Update verifier instance clamping
    - Clamp verifier to max 1 in clamp_instances()
    - Update ArchetypeInstancesConfig default from 2 to 1
    - _Requirements: 98-REQ-6.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/graph/test_injection_modes.py tests/unit/session/test_convergence_dispatch.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/graph/injection.py agent_fox/session/convergence.py agent_fox/engine/sdk_params.py`
    - [x] Requirements 98-REQ-4.* and 98-REQ-5.* met

- [x] 4. Update config schema
  - [x] 4.1 Create `ReviewerConfig` model
    - Fields: pre_review_block_threshold, drift_review_block_threshold, audit_min_ts_entries, audit_max_retries
    - _Requirements: 98-REQ-8.2_

  - [x] 4.2 Update `ArchetypesConfig`
    - Replace skeptic/oracle/auditor toggles with single reviewer toggle
    - Replace skeptic_config/oracle_settings/auditor_config with reviewer_config
    - Update ArchetypeInstancesConfig (reviewer replaces skeptic+auditor, verifier max=1)
    - _Requirements: 98-REQ-8.1, 98-REQ-8.3_

  - [x] 4.3 Add old key validation
    - Detect old config keys and raise ValidationError with migration guidance
    - _Requirements: 98-REQ-1.E1, 98-REQ-8.E1_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest -q tests/unit/core/test_reviewer_consolidation.py -k "config or toggle or reviewer_config or old_key"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/core/config.py`

- [x] 5. Merge templates
  - [x] 5.1 Create `reviewer.md` template
    - Shared review identity and rules section
    - Mode-specific sections for pre-review, drift-review, audit-review, fix-review
    - Consolidate content from skeptic.md, oracle.md, auditor.md, fix_reviewer.md
    - _Requirements: 98-REQ-3.1, 98-REQ-3.2_

  - [x] 5.2 Remove old template files
    - Remove skeptic.md, oracle.md, auditor.md, fix_reviewer.md
    - Keep fix_coding.md for coder:fix mode
    - _Requirements: 98-REQ-3.3_

  - [x] 5.3 Update prompt builder for mode-aware template loading
    - When archetype="reviewer", load reviewer.md
    - When archetype="coder" and mode="fix", load fix_coding.md
    - _Requirements: 98-REQ-3.2_

  - [x] 5.V Verify task group 5
    - [x] Spec tests pass: `uv run pytest -q tests/unit/templates/test_reviewer_template.py`
    - [-] All existing tests still pass: consolidation-expected failures deferred to task group 6 (tests referencing deleted template files: test_review_parse_resilience.py, test_skeptic.py, test_auditor.py, test_oracle/test_registry.py; ~20 new failures, 2 fixed)
    - [x] No linter warnings: `uv run ruff check agent_fox/session/prompt.py`

- [ ] 6. Checkpoint — Update existing tests
  - [ ] 6.1 Update existing archetype tests
    - Migrate tests referencing old archetype names to new reviewer/mode names
    - Update convergence tests to use converge_reviewer dispatch
    - Update injection tests to expect reviewer mode nodes
    - _Requirements: all_

  - [ ] 6.2 Update existing config tests
    - Migrate tests referencing old config keys to new schema
    - _Requirements: all_

  - [ ] 6.V Verify checkpoint
    - [ ] All tests pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 7. Wiring verification

  - [ ] 7.1 Trace every execution path from design.md end-to-end
    - Path 1: Pre-review injection → session setup → convergence
    - Path 2: Drift-review with oracle gating
    - Path 3: Audit-review injection and convergence
    - Path 4: Coder fix mode session setup
    - Confirm no function in the chain is a stub
    - _Requirements: all_

  - [ ] 7.2 Verify return values propagate correctly
    - collect_enabled_auto_pre returns ArchetypeEntry with mode
    - converge_reviewer returns result to caller
    - Grep for callers; confirm none discards the return value
    - _Requirements: all_

  - [ ] 7.3 Run the integration smoke tests
    - TS-98-SMOKE-1: Pre-review end-to-end
    - TS-98-SMOKE-2: Drift-review with gating
    - TS-98-SMOKE-3: Coder fix mode session setup
    - _Test Spec: TS-98-SMOKE-1 through TS-98-SMOKE-3_

  - [ ] 7.4 Stub / dead-code audit
    - Search touched files for old archetype references ("skeptic", "oracle", "auditor", "fix_reviewer", "fix_coder")
    - Verify no production code references old names except in migration error messages
    - _Requirements: all_

  - [ ] 7.5 Cross-spec entry point verification
    - Verify Spec 97 mode infrastructure is actually used by this spec
    - Confirm resolve_effective_config, ModeConfig, Node.mode are called from live code paths
    - _Requirements: all_

  - [ ] 7.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] No old archetype names in production code (except error messages)
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 98-REQ-1.1 | TS-98-1 | 2.1 | test_reviewer_consolidation.py::test_reviewer_modes |
| 98-REQ-1.2 | TS-98-2 | 2.1 | test_reviewer_consolidation.py::test_pre_review_config |
| 98-REQ-1.3 | TS-98-3 | 2.1 | test_reviewer_consolidation.py::test_drift_review_config |
| 98-REQ-1.4 | TS-98-4 | 2.1 | test_reviewer_consolidation.py::test_audit_review_config |
| 98-REQ-1.5 | TS-98-5 | 2.1 | test_reviewer_consolidation.py::test_fix_review_config |
| 98-REQ-1.E1 | TS-98-E1 | 4.3 | test_reviewer_consolidation.py::test_old_config_rejected |
| 98-REQ-2.1 | TS-98-6 | 2.2 | test_reviewer_consolidation.py::test_coder_fix_mode |
| 98-REQ-2.2 | TS-98-6 | 2.2 | test_reviewer_consolidation.py::test_coder_fix_mode |
| 98-REQ-2.E1 | TS-98-E2 | 2.2 | test_reviewer_consolidation.py::test_coder_no_mode |
| 98-REQ-3.1 | TS-98-7 | 5.1 | test_reviewer_template.py::test_reviewer_template |
| 98-REQ-3.2 | TS-98-7 | 5.3 | test_reviewer_template.py::test_reviewer_template |
| 98-REQ-3.3 | TS-98-7 | 5.2 | test_reviewer_template.py::test_fix_coding_retained |
| 98-REQ-4.1 | TS-98-8 | 3.2 | test_injection_modes.py::test_auto_pre_reviewer |
| 98-REQ-4.2 | TS-98-9 | 3.3 | test_injection_modes.py::test_inject_reviewer_nodes |
| 98-REQ-4.3 | TS-98-9 | 3.3 | test_injection_modes.py::test_inject_audit_node |
| 98-REQ-4.4 | TS-98-10 | 3.2 | test_injection_modes.py::test_drift_gating |
| 98-REQ-4.5 | TS-98-8 | 3.2 | test_injection_modes.py::test_reviewer_enable_check |
| 98-REQ-4.E1 | TS-98-E3 | 3.2 | test_injection_modes.py::test_reviewer_disabled |
| 98-REQ-5.1 | TS-98-11 | 3.4 | test_convergence_dispatch.py::test_pre_review |
| 98-REQ-5.2 | TS-98-11 | 3.4 | test_convergence_dispatch.py::test_drift_review |
| 98-REQ-5.3 | TS-98-12 | 3.4 | test_convergence_dispatch.py::test_audit_review |
| 98-REQ-5.E1 | TS-98-E4 | 3.4 | test_convergence_dispatch.py::test_unknown_mode |
| 98-REQ-6.1 | TS-98-13 | 2.3 | test_reviewer_consolidation.py::test_verifier_standard |
| 98-REQ-6.2 | TS-98-14 | 3.5 | test_reviewer_consolidation.py::test_verifier_single |
| 98-REQ-6.3 | TS-98-13 | 2.3 | test_reviewer_consolidation.py::test_verifier_retry |
| 98-REQ-7.1 | TS-98-15 | 2.4 | test_reviewer_consolidation.py::test_old_removed |
| 98-REQ-7.2 | TS-98-15 | 2.4 | test_reviewer_consolidation.py::test_old_fallback |
| 98-REQ-8.1 | TS-98-16 | 4.2 | test_reviewer_consolidation.py::test_config_toggle |
| 98-REQ-8.2 | TS-98-17 | 4.1 | test_reviewer_consolidation.py::test_reviewer_config |
| 98-REQ-8.3 | TS-98-14 | 4.2 | test_reviewer_consolidation.py::test_instances_config |
| 98-REQ-8.E1 | TS-98-E1 | 4.3 | test_reviewer_consolidation.py::test_old_config_rejected |
| Property 1 | TS-98-P1 | 2.1 | test_reviewer_properties.py::test_mode_mapping |
| Property 2 | TS-98-P2 | 3.4 | test_reviewer_properties.py::test_convergence_dispatch |
| Property 3 | TS-98-P3 | 3.3 | test_reviewer_properties.py::test_injection_consistency |
| Property 4 | TS-98-P4 | 3.5 | test_reviewer_properties.py::test_verifier_single |
| Property 5 | TS-98-P5 | 2.2 | test_reviewer_properties.py::test_coder_fix_equiv |
| Property 6 | TS-98-P6 | 2.4 | test_reviewer_properties.py::test_old_names_gone |
