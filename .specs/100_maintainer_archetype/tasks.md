# Implementation Plan: Maintainer Archetype

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This plan creates the maintainer archetype, absorbs triage, and stubs
knowledge extraction in five task groups. Group 1 writes failing tests.
Group 2 defines the archetype and extraction types. Group 3 updates the
nightshift pipeline. Group 4 creates the template. Group 5 verifies wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/core/test_maintainer_archetype.py tests/unit/nightshift/test_triage_migration.py tests/property/test_maintainer_properties.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/core/test_maintainer_archetype.py`
    - Registry tests: maintainer entry, mode configs, not task assignable (TS-100-1 through TS-100-4)
    - Triage removed (TS-100-5)
    - Template existence (TS-100-7)
    - Extraction types (TS-100-8, TS-100-9, TS-100-10)
    - Edge cases: triage fallback, extraction no exception (TS-100-E1, TS-100-E3)
    - _Test Spec: TS-100-1 through TS-100-10, TS-100-E1, TS-100-E3_

  - [x] 1.2 Create `tests/unit/nightshift/test_triage_migration.py`
    - Triage uses maintainer:hunt (TS-100-6)
    - Nightshift model tier resolution (TS-100-11)
    - Old triage config key (TS-100-E2)
    - _Test Spec: TS-100-6, TS-100-11, TS-100-E2_

  - [x] 1.3 Create `tests/property/test_maintainer_properties.py`
    - Property tests: mode config, triage removed, extraction safety, nightshift resolution (TS-100-P1 through TS-100-P4)
    - _Test Spec: TS-100-P1 through TS-100-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Define maintainer archetype and extraction types
  - [x] 2.1 Add maintainer entry to ARCHETYPE_REGISTRY
    - hunt mode: analysis allowlist, STANDARD, task_assignable=False
    - extraction mode: empty allowlist, STANDARD, task_assignable=False
    - _Requirements: 100-REQ-1.1, 100-REQ-1.2, 100-REQ-1.3, 100-REQ-1.4_

  - [x] 2.2 Remove triage entry from ARCHETYPE_REGISTRY
    - _Requirements: 100-REQ-2.1, 100-REQ-1.E1_

  - [x] 2.3 Create `agent_fox/nightshift/extraction.py`
    - ExtractionInput dataclass (session_id, transcript, spec_name, archetype, mode)
    - ExtractionResult dataclass (facts, session_id, status)
    - extract_knowledge() stub function
    - _Requirements: 100-REQ-4.1, 100-REQ-4.2, 100-REQ-4.3, 100-REQ-4.E1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/core/test_maintainer_archetype.py -k "registry or extraction"`
    - [x] Property tests pass: `uv run pytest -q tests/property/test_maintainer_properties.py -k "mode_config or triage_removed or extraction"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/archetypes.py agent_fox/nightshift/extraction.py`

- [ ] 3. Update nightshift pipeline
  - [ ] 3.1 Update `run_batch_triage()` to use maintainer:hunt
    - Change model tier resolution from triage to maintainer:hunt
    - Change security config resolution from triage to maintainer:hunt
    - _Requirements: 100-REQ-2.2, 100-REQ-5.1, 100-REQ-5.2_

  - [ ] 3.2 Update triage prompt builder for maintainer template
    - Load maintainer.md hunt section content for triage prompts
    - _Requirements: 100-REQ-5.3_

  - [ ] 3.3 Update existing nightshift tests
    - Migrate tests referencing triage archetype to maintainer:hunt
    - _Requirements: 100-REQ-2.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/nightshift/test_triage_migration.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/nightshift/`

- [ ] 4. Create maintainer template
  - [ ] 4.1 Create `agent_fox/_templates/prompts/maintainer.md`
    - Shared maintainer identity section
    - Hunt mode section: scanning, triage, dependency detection, consolidation
    - Extraction mode section: transcript reading, fact identification, knowledge writing
    - Incorporate relevant content from triage.md
    - _Requirements: 100-REQ-3.1, 100-REQ-3.2, 100-REQ-3.3, 100-REQ-2.3_

  - [ ] 4.2 Remove old triage.md template
    - Verify no other code references triage.md
    - _Requirements: 100-REQ-2.1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/core/test_maintainer_archetype.py -k "template"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/`

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1: Nightshift triage → resolve_model_tier("maintainer", mode="hunt") → AI call
    - Path 2: extract_knowledge(input) → ExtractionResult (stub)
    - Confirm no function in the chain is an unreplaced stub
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - resolve_model_tier returns tier used by triage AI call
    - extract_knowledge returns ExtractionResult consumed by caller
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - TS-100-SMOKE-1: Nightshift triage via maintainer
    - TS-100-SMOKE-2: Extraction stub end-to-end
    - _Test Spec: TS-100-SMOKE-1, TS-100-SMOKE-2_

  - [ ] 5.4 Stub / dead-code audit
    - Search touched files for references to "triage" archetype
    - Verify no production code references triage except in fallback warning
    - Document the intentional extraction stub with rationale
    - _Requirements: all_

  - [ ] 5.5 Cross-spec entry point verification
    - Verify Spec 97 mode infrastructure is used (ModeConfig, resolve_effective_config)
    - Verify nightshift engine actually calls the updated triage function
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain (extraction stub is justified and documented)
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] No triage references in production code (except fallback warning)
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 100-REQ-1.1 | TS-100-1 | 2.1 | test_maintainer_archetype.py::test_maintainer_modes |
| 100-REQ-1.2 | TS-100-2 | 2.1 | test_maintainer_archetype.py::test_hunt_config |
| 100-REQ-1.3 | TS-100-3 | 2.1 | test_maintainer_archetype.py::test_extraction_config |
| 100-REQ-1.4 | TS-100-4 | 2.1 | test_maintainer_archetype.py::test_not_assignable |
| 100-REQ-1.E1 | TS-100-E1 | 2.2 | test_maintainer_archetype.py::test_triage_fallback |
| 100-REQ-2.1 | TS-100-5 | 2.2 | test_maintainer_archetype.py::test_triage_removed |
| 100-REQ-2.2 | TS-100-6 | 3.1 | test_triage_migration.py::test_uses_maintainer |
| 100-REQ-2.3 | TS-100-7 | 4.1 | test_maintainer_archetype.py::test_template |
| 100-REQ-2.E1 | TS-100-E2 | 3.3 | test_triage_migration.py::test_old_config |
| 100-REQ-3.1 | TS-100-7 | 4.1 | test_maintainer_archetype.py::test_template |
| 100-REQ-3.2 | TS-100-7 | 4.1 | test_maintainer_archetype.py::test_template |
| 100-REQ-3.3 | TS-100-7 | 4.1 | test_maintainer_archetype.py::test_template |
| 100-REQ-4.1 | TS-100-8 | 2.3 | test_maintainer_archetype.py::test_extraction_input |
| 100-REQ-4.2 | TS-100-9 | 2.3 | test_maintainer_archetype.py::test_extraction_result |
| 100-REQ-4.3 | TS-100-10 | 2.3 | test_maintainer_archetype.py::test_extraction_stub |
| 100-REQ-4.E1 | TS-100-E3 | 2.3 | test_maintainer_archetype.py::test_extraction_no_error |
| 100-REQ-5.1 | TS-100-11 | 3.1 | test_triage_migration.py::test_tier_resolution |
| 100-REQ-5.2 | TS-100-11 | 3.1 | test_triage_migration.py::test_security_resolution |
| 100-REQ-5.3 | TS-100-6 | 3.2 | test_triage_migration.py::test_prompt_builder |
| Property 1 | TS-100-P1 | 2.1 | test_maintainer_properties.py::test_mode_config |
| Property 2 | TS-100-P2 | 2.2 | test_maintainer_properties.py::test_triage_removed |
| Property 3 | TS-100-P3 | 2.3 | test_maintainer_properties.py::test_extraction_safety |
| Property 4 | TS-100-P4 | 3.1 | test_maintainer_properties.py::test_nightshift_resolution |
