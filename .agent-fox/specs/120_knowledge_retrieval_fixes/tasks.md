# Implementation Plan: Knowledge Retrieval Fixes

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Four focused fixes to the knowledge system's read side. The changes touch
`fox_provider.py`, `review_store.py`, `summary_store.py`, `engine.py`, and
`session_lifecycle.py` (or `result_handler.py`). No new tables, no new
dependencies. Task groups are ordered by dependency: run_id wiring first
(unblocks summary retrieval), then pre-review elevation, then all-archetype
summaries, then cross-run carry-forward.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/ tests/integration/knowledge/ -k "120 or retrieval_fix"`
- Unit tests: `uv run pytest -q tests/unit/knowledge/`
- Property tests: `uv run pytest -q tests/property/knowledge/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file for run_id wiring tests
    - Create `tests/unit/knowledge/test_run_id_wiring.py`
    - Implement TS-120-1 (set_run_id stores run ID)
    - Implement TS-120-2 (summaries retrieved after set_run_id)
    - Implement TS-120-3 (cross-spec summaries retrieved)
    - Implement TS-120-E1 (set_run_id never called)
    - Implement TS-120-E2 (set_run_id with empty string)
    - _Test Spec: TS-120-1, TS-120-2, TS-120-3, TS-120-E1, TS-120-E2_

  - [x] 1.2 Create test file for pre-review elevation tests
    - Create `tests/unit/knowledge/test_prereview_elevation.py`
    - Implement TS-120-5 (pre-review in primary review results)
    - Implement TS-120-6 (pre-review tracked in finding_injections)
    - Implement TS-120-7 (pre-review excluded from cross-group)
    - Implement TS-120-E3 (no group 0 findings)
    - Implement TS-120-E4 (group 0 session no self-inject)
    - _Test Spec: TS-120-5, TS-120-6, TS-120-7, TS-120-E3, TS-120-E4_

  - [x] 1.3 Create test file for archetype summary tests
    - Create `tests/unit/knowledge/test_archetype_summaries.py`
    - Implement TS-120-8 (reviewer summary generated)
    - Implement TS-120-9 (verifier summary generated)
    - Implement TS-120-10 (same-spec includes all archetypes)
    - Implement TS-120-E5 (reviewer zero findings)
    - Implement TS-120-E6 (verifier zero verdicts)
    - _Test Spec: TS-120-8, TS-120-9, TS-120-10, TS-120-E5, TS-120-E6_

  - [x] 1.4 Create test file for cross-run carry-forward tests
    - Create `tests/unit/knowledge/test_cross_run_carryforward.py`
    - Implement TS-120-11 (prior-run findings surfaced)
    - Implement TS-120-12 (prior-run findings capped)
    - Implement TS-120-13 (prior-run not tracked)
    - Implement TS-120-E7 (no prior runs)
    - Implement TS-120-E8 (all prior superseded)
    - _Test Spec: TS-120-11, TS-120-12, TS-120-13, TS-120-E7, TS-120-E8_

  - [x] 1.5 Create property test file
    - Create `tests/property/knowledge/test_retrieval_fix_props.py`
    - Implement TS-120-P1 (run_id gating)
    - Implement TS-120-P2 (no duplication review/cross-group)
    - Implement TS-120-P3 (prior-run never tracked)
    - Implement TS-120-P4 (archetype summary completeness)
    - _Test Spec: TS-120-P1, TS-120-P2, TS-120-P3, TS-120-P4_

  - [x] 1.6 Create engine wiring test
    - Add test to `tests/unit/engine/` for TS-120-4
    - Verify engine calls set_run_id on provider
    - _Test Spec: TS-120-4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check`

- [x] 2. Fix run_id wiring (Fix 1)
  - [x] 2.1 Add set_run_id method to FoxKnowledgeProvider
    - Add `set_run_id(self, run_id: str) -> None` method
    - Store `run_id if run_id else None` in `self._run_id`
    - _Requirements: 120-REQ-1.1, 120-REQ-1.2_

  - [x] 2.2 Wire set_run_id in engine.py
    - After `generate_run_id()` in `Engine._init_run`, call
      `knowledge_provider.set_run_id(self._run_id)`
    - The knowledge_provider is accessible via the run setup dict
    - _Requirements: 120-REQ-1.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: TS-120-1, TS-120-2, TS-120-3, TS-120-4, TS-120-E1, TS-120-E2
    - [x] Property test passes: TS-120-P1
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check`
    - [x] Requirements 120-REQ-1.1 through 120-REQ-1.5, 120-REQ-1.E1, 120-REQ-1.E2 met

- [ ] 3. Elevate pre-review findings (Fix 2)
  - [ ] 3.1 Update query_active_findings to include group 0
    - Add `include_prereview: bool = False` parameter
    - When `include_prereview=True` and `task_group is not None` and
      `task_group != "0"`, use `task_group IN (?, '0')` in SQL WHERE clause
    - _Requirements: 120-REQ-2.1_

  - [ ] 3.2 Update _query_reviews in fox_provider.py
    - Pass `include_prereview=True` when `task_group` is not None and
      not `"0"`
    - _Requirements: 120-REQ-2.1, 120-REQ-2.2, 120-REQ-2.4_

  - [ ] 3.3 Update query_cross_group_findings to exclude group 0
    - Change SQL from `task_group != ?` to
      `task_group != ? AND task_group != '0'` when the caller is not
      group 0 itself
    - Add `exclude_prereview: bool = False` parameter
    - _Requirements: 120-REQ-2.3_

  - [ ] 3.4 Update _query_cross_group_reviews in fox_provider.py
    - Pass `exclude_prereview=True` when `task_group != "0"`
    - _Requirements: 120-REQ-2.3, 120-REQ-2.E2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: TS-120-5, TS-120-6, TS-120-7, TS-120-E3, TS-120-E4
    - [ ] Property test passes: TS-120-P2
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 120-REQ-2.1 through 120-REQ-2.4, 120-REQ-2.E1, 120-REQ-2.E2 met

- [ ] 4. All-archetype summary storage (Fix 3)
  - [ ] 4.1 Add generate_archetype_summary function
    - Add to `knowledge/fox_provider.py` (or a new helper in the same package)
    - For reviewer: count findings by severity, include top 3 descriptions
    - For verifier: count pass/fail, list FAIL requirement IDs
    - Handle empty lists gracefully
    - _Requirements: 120-REQ-3.1, 120-REQ-3.2, 120-REQ-3.E1, 120-REQ-3.E2_

  - [ ] 4.2 Wire summary generation for reviewer/verifier sessions
    - In the session completion path (session_lifecycle.py or result_handler.py),
      generate summary for reviewer and verifier archetypes
    - Set `context["summary"]` before calling `ingest()`
    - _Requirements: 120-REQ-3.1, 120-REQ-3.2_

  - [ ] 4.3 Remove archetype='coder' filter from query_same_spec_summaries
    - In `summary_store.py`, remove the `AND archetype = 'coder'` clause
    - _Requirements: 120-REQ-3.3_

  - [ ] 4.4 Update context prefix to include archetype
    - Verify that `_query_same_spec_summaries` result formatting in
      fox_provider.py includes archetype in the `[CONTEXT]` prefix
    - _Requirements: 120-REQ-3.4_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: TS-120-8, TS-120-9, TS-120-10, TS-120-E5, TS-120-E6
    - [ ] Property test passes: TS-120-P4
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 120-REQ-3.1 through 120-REQ-3.4, 120-REQ-3.E1, 120-REQ-3.E2 met

- [ ] 5. Cross-run finding carry-forward (Fix 4)
  - [ ] 5.1 Add query_prior_run_findings to review_store.py
    - Query active critical/major findings created before current run start
    - Use the `runs` table to identify the current run's start time
    - Sort by severity, cap at max_items
    - _Requirements: 120-REQ-4.1, 120-REQ-4.3_

  - [ ] 5.2 Add query_prior_run_verdicts to review_store.py
    - Query active FAIL verdicts created before current run start
    - Cap at max_items
    - _Requirements: 120-REQ-4.5_

  - [ ] 5.3 Add _query_prior_run_findings to fox_provider.py
    - Call query_prior_run_findings and query_prior_run_verdicts
    - Format as `[PRIOR-RUN]` items with source context
    - Append to result list WITHOUT tracking in finding_injections
    - _Requirements: 120-REQ-4.1, 120-REQ-4.2, 120-REQ-4.4_

  - [ ] 5.4 Add max_prior_run_items config field
    - Add `max_prior_run_items: int = 5` to KnowledgeProviderConfig
    - _Requirements: 120-REQ-4.3_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: TS-120-11, TS-120-12, TS-120-13, TS-120-E7, TS-120-E8
    - [ ] Property test passes: TS-120-P3
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check`
    - [ ] Requirements 120-REQ-4.1 through 120-REQ-4.5, 120-REQ-4.E1 through 120-REQ-4.E3 met

- [ ] 6. Checkpoint - Integration Smoke Tests
  - [ ] 6.1 Create integration smoke test file
    - Create `tests/integration/knowledge/test_retrieval_fixes_smoke.py`
    - Implement TS-120-SMOKE-1 (end-to-end summary flow)
    - Implement TS-120-SMOKE-2 (pre-review to coder flow)
    - Implement TS-120-SMOKE-3 (cross-run carry-forward flow)
    - _Test Spec: TS-120-SMOKE-1, TS-120-SMOKE-2, TS-120-SMOKE-3_

  - [ ] 6.2 Update documentation
    - Update `docs/memory.md` with summary of changes
    - _Requirements: all_

  - [ ] 6.V Verify task group 6
    - [ ] All smoke tests pass
    - [ ] All unit and property tests pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check`

- [ ] 7. Wiring verification

  - [ ] 7.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code -- errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 7.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [ ] 7.3 Run the integration smoke tests
    - All `TS-120-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-120-SMOKE-1 through TS-120-SMOKE-3_

  - [ ] 7.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 7.5 Cross-spec entry point verification
    - Verify that `set_run_id()` is called from production code (engine.py)
    - Verify that `generate_archetype_summary()` is called from production
      code (session_lifecycle.py or result_handler.py)
    - Verify that `query_prior_run_findings()` is called from
      `_query_prior_run_findings()` in fox_provider.py
    - _Requirements: all_

  - [ ] 7.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 120-REQ-1.1 | TS-120-1 | 2.1 | test_run_id_wiring.py |
| 120-REQ-1.2 | TS-120-2 | 2.1 | test_run_id_wiring.py |
| 120-REQ-1.3 | TS-120-4 | 2.2 | test_engine_run_id.py |
| 120-REQ-1.4 | TS-120-2 | 2.1 | test_run_id_wiring.py |
| 120-REQ-1.5 | TS-120-3 | 2.1 | test_run_id_wiring.py |
| 120-REQ-1.E1 | TS-120-E1 | 2.1 | test_run_id_wiring.py |
| 120-REQ-1.E2 | TS-120-E2 | 2.1 | test_run_id_wiring.py |
| 120-REQ-2.1 | TS-120-5 | 3.1, 3.2 | test_prereview_elevation.py |
| 120-REQ-2.2 | TS-120-6 | 3.2 | test_prereview_elevation.py |
| 120-REQ-2.3 | TS-120-7 | 3.3, 3.4 | test_prereview_elevation.py |
| 120-REQ-2.4 | TS-120-5 | 3.2 | test_prereview_elevation.py |
| 120-REQ-2.E1 | TS-120-E3 | 3.1 | test_prereview_elevation.py |
| 120-REQ-2.E2 | TS-120-E4 | 3.4 | test_prereview_elevation.py |
| 120-REQ-3.1 | TS-120-8 | 4.1, 4.2 | test_archetype_summaries.py |
| 120-REQ-3.2 | TS-120-9 | 4.1, 4.2 | test_archetype_summaries.py |
| 120-REQ-3.3 | TS-120-10 | 4.3 | test_archetype_summaries.py |
| 120-REQ-3.4 | TS-120-10 | 4.4 | test_archetype_summaries.py |
| 120-REQ-3.E1 | TS-120-E5 | 4.1 | test_archetype_summaries.py |
| 120-REQ-3.E2 | TS-120-E6 | 4.1 | test_archetype_summaries.py |
| 120-REQ-4.1 | TS-120-11 | 5.1, 5.3 | test_cross_run_carryforward.py |
| 120-REQ-4.2 | TS-120-11 | 5.3 | test_cross_run_carryforward.py |
| 120-REQ-4.3 | TS-120-12 | 5.1, 5.4 | test_cross_run_carryforward.py |
| 120-REQ-4.4 | TS-120-13 | 5.3 | test_cross_run_carryforward.py |
| 120-REQ-4.5 | TS-120-11 | 5.2, 5.3 | test_cross_run_carryforward.py |
| 120-REQ-4.E1 | TS-120-E7 | 5.1 | test_cross_run_carryforward.py |
| 120-REQ-4.E2 | TS-120-E8 | 5.1 | test_cross_run_carryforward.py |
| 120-REQ-4.E3 | TS-120-E7 | 5.1 | test_cross_run_carryforward.py |

## Notes

- All database operations use in-memory DuckDB in tests. No test database
  fixtures or external dependencies.
- The `runs` table already exists (created in prior specs). Cross-run queries
  use it to determine run boundaries.
- The `review_findings` table does not have a `run_id` column. Cross-run
  queries use `created_at` timestamps relative to the current run's start
  time from the `runs` table.
- Existing tests for `fox_provider.py`, `review_store.py`, and
  `summary_store.py` must continue to pass. The changes are backward-
  compatible: new parameters have defaults that preserve existing behavior.
