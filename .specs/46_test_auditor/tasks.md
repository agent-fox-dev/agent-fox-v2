# Implementation Plan: Test Auditor Archetype

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into four groups plus a checkpoint:

- **Group 1**: Write all failing tests from test_spec.md.
- **Group 2**: Registry entry, config model, detection function, and prompt
  template (foundation).
- **Group 3**: Auto-mid injection in graph builder, TS entry counting.
- **Group 4**: Convergence function, circuit breaker, output persistence,
  GitHub issue filing, audit events.
- **Group 5**: Checkpoint — full verification.

## Test Commands

- Spec tests: `uv run pytest tests/unit/session/test_auditor.py tests/unit/graph/test_builder_auditor.py tests/unit/core/test_config_auditor.py tests/unit/engine/test_auditor_circuit_breaker.py -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- Property tests: `uv run pytest tests/unit/ -q -k "property or hypothesis"`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create registry and config test files
    - Create `tests/unit/session/test_auditor.py` with tests for TS-46-1,
      TS-46-2 (registry entry, get_archetype)
    - Create `tests/unit/core/test_config_auditor.py` with tests for TS-46-3
      through TS-46-6 (config defaults, clamping, AuditorConfig)
    - _Test Spec: TS-46-1 through TS-46-6_

  - [ ] 1.2 Create detection and injection test files
    - Create `tests/unit/graph/test_builder_auditor.py` with tests for
      TS-46-7 through TS-46-16 (detection function, injection logic,
      coexistence, multiple test groups)
    - Include TS-46-E1 (no test groups), TS-46-E4, TS-46-E5 (TS entry counting)
    - _Test Spec: TS-46-7 through TS-46-16, TS-46-E1, TS-46-E4, TS-46-E5_

  - [ ] 1.3 Create convergence and prompt template test files
    - Add convergence tests to `tests/unit/session/test_auditor.py`:
      TS-46-19 through TS-46-22 (union, passthrough, empty, no LLM)
    - Add prompt template tests: TS-46-17, TS-46-18
    - _Test Spec: TS-46-17 through TS-46-22_

  - [ ] 1.4 Create circuit breaker and output test files
    - Create `tests/unit/engine/test_auditor_circuit_breaker.py` with tests
      for TS-46-23 through TS-46-28 (retry trigger, re-run, circuit breaker
      block, GitHub issue, max_retries=0, PASS no retry)
    - Add output persistence tests to `tests/unit/session/test_auditor.py`:
      TS-46-29 through TS-46-32 (audit.md, GitHub issues, audit events)
    - Add TS-46-E2 (gh unavailable), TS-46-E3 (write failure)
    - _Test Spec: TS-46-23 through TS-46-32, TS-46-E2, TS-46-E3_

  - [ ] 1.5 Create property test cases
    - Add TS-46-P1, TS-46-P2 to `tests/unit/graph/test_builder_auditor.py`
      (detection completeness/specificity)
    - Add TS-46-P3 to `tests/unit/graph/test_builder_auditor.py`
      (injection graph integrity)
    - Add TS-46-P4, TS-46-P5 to `tests/unit/session/test_auditor.py`
      (convergence union, determinism)
    - Add TS-46-P6 to `tests/unit/engine/test_auditor_circuit_breaker.py`
      (circuit breaker bound)
    - Add TS-46-P7 to `tests/unit/core/test_config_auditor.py`
      (config clamping)
    - _Test Spec: TS-46-P1 through TS-46-P7_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Registry entry, config, detection, and prompt template
  - [ ] 2.1 Add auditor to archetype registry
    - Add `"auditor"` entry to `ARCHETYPE_REGISTRY` in
      `agent_fox/session/archetypes.py` with injection="auto_mid",
      retry_predecessor=True, templates=["auditor.md"],
      default_model_tier="STANDARD", default_allowlist with all 9 commands
    - _Requirements: 46-REQ-1.1, 46-REQ-1.2, 46-REQ-1.3, 46-REQ-1.4,
      46-REQ-1.E1_

  - [ ] 2.2 Add AuditorConfig and config fields
    - Add `AuditorConfig` pydantic model to `agent_fox/core/config.py`
      with `min_ts_entries` (default 5, clamped >= 1) and `max_retries`
      (default 2, clamped >= 0)
    - Add `auditor: bool = False` to `ArchetypesConfig`
    - Add `auditor_config: AuditorConfig` to `ArchetypesConfig`
    - Add `auditor: int = 1` to `ArchetypeInstancesConfig` (clamped 1-5)
    - _Requirements: 46-REQ-2.1, 46-REQ-2.2, 46-REQ-2.3, 46-REQ-2.4,
      46-REQ-2.E1, 46-REQ-2.E2_

  - [ ] 2.3 Implement is_test_writing_group detection function
    - Add `_TEST_GROUP_PATTERNS` and `is_test_writing_group(title: str) -> bool`
      to `agent_fox/graph/builder.py`
    - Case-insensitive substring matching against defined patterns
    - _Requirements: 46-REQ-3.1, 46-REQ-3.2, 46-REQ-3.E1, 46-REQ-3.E2_

  - [ ] 2.4 Create auditor.md prompt template
    - Create `agent_fox/_templates/prompts/auditor.md`
    - Include five audit dimensions, JSON output format, FAIL criteria,
      {spec_name} and {task_group} variables
    - Read-only + test runner constraints
    - _Requirements: 46-REQ-5.1, 46-REQ-5.2, 46-REQ-5.3, 46-REQ-5.4,
      46-REQ-5.5_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: TS-46-1 through TS-46-10, TS-46-17, TS-46-18
    - [ ] TS-46-P1, TS-46-P2, TS-46-P7 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 3. Auto-mid injection in graph builder
  - [ ] 3.1 Implement count_ts_entries function
    - Add `count_ts_entries(spec_dir: Path) -> int` to
      `agent_fox/graph/builder.py`
    - Count `### TS-` lines in test_spec.md; return 0 if file missing
    - _Requirements: 46-REQ-4.4_

  - [ ] 3.2 Implement auto_mid injection
    - Add `_inject_auto_mid_nodes()` to `agent_fox/graph/builder.py`
    - Call from `_inject_archetype_nodes()` alongside existing auto_pre/
      auto_post logic
    - For each spec: iterate task groups, detect test-writing groups,
      check TS threshold, create auditor node with fractional group number,
      wire edges
    - Handle multiple test-writing groups per spec
    - Handle test-writing group as last group (no successor edge)
    - _Requirements: 46-REQ-4.1, 46-REQ-4.2, 46-REQ-4.3, 46-REQ-4.E1,
      46-REQ-4.E2, 46-REQ-4.E3_

  - [ ] 3.3 Update runtime injection in engine.py
    - Add auto_mid handling to `_ensure_archetype_nodes()` for legacy plan
      compatibility
    - _Requirements: 46-REQ-4.1_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: TS-46-11 through TS-46-16, TS-46-E1, TS-46-E4,
      TS-46-E5
    - [ ] TS-46-P3 passes
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 4. Convergence, circuit breaker, output, and events
  - [ ] 4.1 Implement converge_auditor
    - Add `AuditEntry`, `AuditResult` dataclasses and `converge_auditor()`
      to `agent_fox/session/convergence.py`
    - Union semantics: worst verdict per TS entry wins
    - Overall FAIL if any instance FAIL
    - Single instance passthrough, empty list returns PASS
    - _Requirements: 46-REQ-6.1, 46-REQ-6.2, 46-REQ-6.3, 46-REQ-6.4,
      46-REQ-6.E1, 46-REQ-6.E2_

  - [ ] 4.2 Implement circuit breaker in engine.py
    - Extend retry-predecessor logic to check `auditor_config.max_retries`
      for auditor archetype nodes
    - When circuit breaker trips: set node to "blocked", log WARNING
    - Wire GitHub issue filing on circuit breaker trip
    - Emit `auditor.circuit_breaker` audit event
    - _Requirements: 46-REQ-7.1, 46-REQ-7.2, 46-REQ-7.3, 46-REQ-7.4,
      46-REQ-7.5, 46-REQ-7.6, 46-REQ-7.E1, 46-REQ-7.E2_

  - [ ] 4.3 Implement output persistence
    - Add `_persist_auditor_results()` function
    - Write audit.md with per-entry verdict table
    - Handle filesystem errors gracefully
    - _Requirements: 46-REQ-8.1, 46-REQ-8.E2_

  - [ ] 4.4 Wire GitHub issue filing and audit events
    - File issue on FAIL: `[Auditor] {spec_name}: FAIL`
    - File issue on circuit breaker: `[Auditor] {spec_name}: circuit breaker tripped`
    - Close issue on PASS
    - Emit `auditor.retry` event on each retry
    - Handle gh unavailability gracefully
    - _Requirements: 46-REQ-8.2, 46-REQ-8.3, 46-REQ-8.4, 46-REQ-8.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: TS-46-19 through TS-46-32, TS-46-E2, TS-46-E3
    - [ ] TS-46-P4, TS-46-P5, TS-46-P6 pass
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

- [ ] 5. Checkpoint — Test Auditor Complete
  - Verify all spec tests pass: full spec test command from top of document
  - Verify all property tests pass: `uv run pytest -q -k "property or hypothesis"`
  - Run full test suite: `uv run pytest -q`
  - Run linter: `uv run ruff check agent_fox/ tests/`
  - Ask the user if questions arise

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 46-REQ-1.1 | TS-46-1 | 2.1 | `tests/unit/session/test_auditor.py::test_registry_entry` |
| 46-REQ-1.2 | TS-46-1 | 2.1 | `tests/unit/session/test_auditor.py::test_registry_entry` |
| 46-REQ-1.3 | TS-46-1 | 2.1 | `tests/unit/session/test_auditor.py::test_registry_entry` |
| 46-REQ-1.4 | TS-46-1 | 2.1 | `tests/unit/session/test_auditor.py::test_registry_entry` |
| 46-REQ-1.E1 | TS-46-2 | 2.1 | `tests/unit/session/test_auditor.py::test_get_archetype_auditor` |
| 46-REQ-2.1 | TS-46-3 | 2.2 | `tests/unit/core/test_config_auditor.py::test_auditor_default_false` |
| 46-REQ-2.2 | TS-46-4 | 2.2 | `tests/unit/core/test_config_auditor.py::test_instance_clamping` |
| 46-REQ-2.3 | TS-46-5 | 2.2 | `tests/unit/core/test_config_auditor.py::test_auditor_config_defaults` |
| 46-REQ-2.4 | TS-46-5 | 2.2 | `tests/unit/core/test_config_auditor.py::test_auditor_config_defaults` |
| 46-REQ-2.E1 | TS-46-3 | 2.2 | `tests/unit/core/test_config_auditor.py::test_auditor_default_false` |
| 46-REQ-2.E2 | TS-46-6 | 2.2 | `tests/unit/core/test_config_auditor.py::test_max_retries_zero` |
| 46-REQ-3.1 | TS-46-7, TS-46-8 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_detection_matches` |
| 46-REQ-3.2 | TS-46-7 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_detection_matches` |
| 46-REQ-3.3 | TS-46-16 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_multiple_test_groups` |
| 46-REQ-3.E1 | TS-46-9 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_detection_rejects` |
| 46-REQ-3.E2 | TS-46-10 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_detection_substring` |
| 46-REQ-4.1 | TS-46-11 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_auto_mid_injection` |
| 46-REQ-4.2 | TS-46-11 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_auto_mid_injection` |
| 46-REQ-4.3 | TS-46-11 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_auto_mid_injection` |
| 46-REQ-4.4 | TS-46-13 | 3.1 | `tests/unit/graph/test_builder_auditor.py::test_injection_skipped_below_threshold` |
| 46-REQ-4.E1 | TS-46-12 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_injection_disabled` |
| 46-REQ-4.E2 | TS-46-14 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_injection_last_group` |
| 46-REQ-4.E3 | TS-46-15 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_coexistence_skeptic` |
| 46-REQ-5.1 | TS-46-17 | 2.4 | `tests/unit/session/test_auditor.py::test_template_exists` |
| 46-REQ-5.2 | TS-46-18 | 2.4 | `tests/unit/session/test_auditor.py::test_template_content` |
| 46-REQ-5.3 | TS-46-18 | 2.4 | `tests/unit/session/test_auditor.py::test_template_content` |
| 46-REQ-5.4 | TS-46-18 | 2.4 | `tests/unit/session/test_auditor.py::test_template_content` |
| 46-REQ-5.5 | TS-46-18 | 2.4 | `tests/unit/session/test_auditor.py::test_template_content` |
| 46-REQ-6.1 | TS-46-19 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_union` |
| 46-REQ-6.2 | TS-46-19 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_union` |
| 46-REQ-6.3 | TS-46-19 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_union` |
| 46-REQ-6.4 | TS-46-22 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_no_llm` |
| 46-REQ-6.E1 | TS-46-20 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_single` |
| 46-REQ-6.E2 | TS-46-21 | 4.1 | `tests/unit/session/test_auditor.py::test_convergence_empty` |
| 46-REQ-7.1 | TS-46-23 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_retry_on_fail` |
| 46-REQ-7.2 | TS-46-24 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_auditor_reruns` |
| 46-REQ-7.3 | TS-46-25 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_circuit_breaker_blocks` |
| 46-REQ-7.4 | TS-46-25 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_circuit_breaker_blocks` |
| 46-REQ-7.5 | TS-46-25 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_circuit_breaker_blocks` |
| 46-REQ-7.6 | TS-46-26 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_circuit_breaker_files_issue` |
| 46-REQ-7.E1 | TS-46-27 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_max_retries_zero_blocks` |
| 46-REQ-7.E2 | TS-46-28 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_pass_no_retry` |
| 46-REQ-8.1 | TS-46-29 | 4.3 | `tests/unit/session/test_auditor.py::test_audit_file_written` |
| 46-REQ-8.2 | TS-46-30 | 4.4 | `tests/unit/session/test_auditor.py::test_github_issue_on_fail` |
| 46-REQ-8.3 | TS-46-31 | 4.4 | `tests/unit/session/test_auditor.py::test_github_issue_closed_on_pass` |
| 46-REQ-8.4 | TS-46-32 | 4.4 | `tests/unit/session/test_auditor.py::test_retry_audit_event` |
| 46-REQ-8.E1 | TS-46-E2 | 4.4 | `tests/unit/session/test_auditor.py::test_gh_unavailable` |
| 46-REQ-8.E2 | TS-46-E3 | 4.3 | `tests/unit/session/test_auditor.py::test_audit_write_failure` |
| Property 1 | TS-46-P1 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_prop_detection_completeness` |
| Property 2 | TS-46-P2 | 2.3 | `tests/unit/graph/test_builder_auditor.py::test_prop_detection_specificity` |
| Property 3 | TS-46-P3 | 3.2 | `tests/unit/graph/test_builder_auditor.py::test_prop_injection_integrity` |
| Property 4 | TS-46-P4 | 4.1 | `tests/unit/session/test_auditor.py::test_prop_convergence_union` |
| Property 5 | TS-46-P5 | 4.1 | `tests/unit/session/test_auditor.py::test_prop_convergence_determinism` |
| Property 6 | TS-46-P6 | 4.2 | `tests/unit/engine/test_auditor_circuit_breaker.py::test_prop_circuit_breaker_bound` |
| Property 7 | TS-46-P7 | 2.2 | `tests/unit/core/test_config_auditor.py::test_prop_config_clamping` |

## Notes

- **Group 2 is the foundation group.** It delivers the registry entry, config,
  detection function, and prompt template. These have no dependencies on the
  graph builder changes and can be tested independently.
- **Group 3 depends on group 2** for the detection function and config model.
- **Group 4 depends on groups 2 and 3** for the convergence data types and
  injection logic.
- **Property tests** use `hypothesis` strategies. Ensure `hypothesis` is
  available in dev dependencies.
- **Circuit breaker tests** mock the orchestrator's retry-predecessor
  machinery. Follow the patterns in
  `tests/unit/engine/test_retry_predecessor.py`.
- **GitHub issue tests** mock `subprocess` calls to `gh` CLI. No real GitHub
  API calls in tests.
