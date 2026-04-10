# Implementation Plan: Transient Audit Reports

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Small, focused change to two modules. Group 2 handles the core path change and
PASS deletion (all in `auditor_output.py`). Group 3 adds the completion
cleanup hook (new method on `GraphSync`, new call in `engine.py`). Group 4 is
the mandatory wiring verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/session/test_transient_audit.py tests/property/session/test_transient_audit_props.py tests/integration/session/test_transient_audit_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/session/test_transient_audit.py`
- Property tests: `uv run pytest -q tests/property/session/test_transient_audit_props.py`
- Integration tests: `uv run pytest -q tests/integration/session/test_transient_audit_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file
    - Create `tests/unit/session/test_transient_audit.py`
    - Translate TS-92-1 through TS-92-7 into pytest test functions
    - Translate TS-92-E1 through TS-92-E5 into pytest test functions
    - All tests must use `tmp_path` to simulate project root
    - _Test Spec: TS-92-1 through TS-92-7, TS-92-E1 through TS-92-E5_

  - [x] 1.2 Create property test file
    - Create `tests/property/session/test_transient_audit_props.py`
    - Translate TS-92-P1 through TS-92-P4 using Hypothesis
    - _Test Spec: TS-92-P1 through TS-92-P4_

  - [x] 1.3 Create integration smoke test file
    - Create `tests/integration/session/test_transient_audit_smoke.py`
    - Translate TS-92-SMOKE-1 and TS-92-SMOKE-2
    - _Test Spec: TS-92-SMOKE-1, TS-92-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `make lint`

- [x] 2. Change audit report output path and add PASS deletion
  - [x] 2.1 Change `audit_path` computation in `persist_auditor_results`
    - In `agent_fox/session/auditor_output.py`, change line 70 from
      `audit_path = spec_dir / "audit.md"` to derive path via
      `spec_dir.parent.parent / ".agent-fox" / "audit"`
    - Add `audit_dir.mkdir(parents=True, exist_ok=True)` before writing
    - Name file `f"audit_{spec_dir.name}.md"`
    - _Requirements: 92-REQ-1.1, 92-REQ-1.2, 92-REQ-1.3_

  - [x] 2.2 Add PASS verdict early-return with deletion
    - Before writing, check `result.overall_verdict == "PASS"`
    - If PASS: delete `audit_path` if it exists, then return early
    - Wrap deletion in try/except OSError to log and not raise
    - _Requirements: 92-REQ-3.1, 92-REQ-3.E1, 92-REQ-3.E2_

  - [x] 2.3 Update existing tests in `test_auditor.py`
    - Update `TestAuditFileWritten.test_audit_file_written` to assert the new
      path (`tmp_path / ".agent-fox" / "audit" / "audit_{name}.md"`)
    - Update `TestAuditWriteFailure` if it references the old path
    - _Requirements: 92-REQ-1.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/session/test_transient_audit.py -k "TS_92_1 or TS_92_2 or TS_92_3 or TS_92_4 or TS_92_5 or TS_92_E1 or TS_92_E2 or TS_92_E3"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 92-REQ-1.1, 92-REQ-1.2, 92-REQ-1.3, 92-REQ-2.1, 92-REQ-3.1 acceptance criteria met

- [x] 3. Add spec completion cleanup
  - [x] 3.1 Add `completed_spec_names()` to `GraphSync`
    - In `agent_fox/engine/graph_sync.py`, add method to `GraphSync`
    - Group `self.node_states` by spec (via `_spec_name`), return set of specs
      where all nodes are `"completed"`
    - _Requirements: 92-REQ-4.1_

  - [x] 3.2 Add `cleanup_completed_spec_audits` to `auditor_output.py`
    - New function accepting `project_root: Path` and `completed_specs: set[str]`
    - Iterate specs, delete matching `audit_{spec}.md` files
    - Per-spec try/except: log warning on OSError, continue
    - _Requirements: 92-REQ-4.2, 92-REQ-4.E1, 92-REQ-4.E2_

  - [x] 3.3 Call cleanup from engine finally block
    - In `agent_fox/engine/engine.py`, after `self._sync_plan_statuses(state)`
      in the finally block (~line 592), call
      `cleanup_completed_spec_audits(Path.cwd(), self._graph_sync.completed_spec_names())`
    - Wrap in try/except to avoid disrupting existing finally-block logic
    - _Requirements: 92-REQ-4.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/session/test_transient_audit.py -k "TS_92_6 or TS_92_7 or TS_92_E4 or TS_92_E5"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `make lint`
    - [x] Requirements 92-REQ-4.1, 92-REQ-4.2 acceptance criteria met

- [x] 4. Wiring verification

  - [x] 4.1 Trace every execution path from design.md end-to-end
    - Path 1: `review_persistence.py` → `persist_auditor_results` → writes to
      `.agent-fox/audit/` (verify the call at line 339 still flows through)
    - Path 2: Same entry, PASS verdict → deletion logic (verify branch exists)
    - Path 3: `engine.py` finally block → `completed_spec_names()` →
      `cleanup_completed_spec_audits` (verify call chain is live)
    - _Requirements: all_

  - [x] 4.2 Verify return values propagate correctly
    - `completed_spec_names()` returns `set[str]` consumed by
      `cleanup_completed_spec_audits`
    - Grep for callers; confirm none discards the return value
    - _Requirements: all_

  - [x] 4.3 Run the integration smoke tests
    - `uv run pytest -q tests/integration/session/test_transient_audit_smoke.py`
    - _Test Spec: TS-92-SMOKE-1, TS-92-SMOKE-2_

  - [x] 4.4 Stub / dead-code audit
    - Search files touched by this spec for `return []`, `return None` on
      non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `NotImplementedError`
    - Verify no unjustified stubs remain

  - [x] 4.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All existing tests still pass: `make check`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 92-REQ-1.1 | TS-92-1 | 2.1 | test_transient_audit.py::test_non_pass_writes_to_new_location |
| 92-REQ-1.2 | TS-92-2 | 2.1 | test_transient_audit.py::test_audit_dir_created_automatically |
| 92-REQ-1.3 | TS-92-3 | 2.1 | test_transient_audit.py::test_no_audit_in_spec_dir |
| 92-REQ-1.E1 | TS-92-E1 | 2.1 | test_transient_audit.py::test_dir_creation_failure |
| 92-REQ-2.1 | TS-92-4 | 2.1 | test_transient_audit.py::test_overwrite_existing_report |
| 92-REQ-3.1 | TS-92-5 | 2.2 | test_transient_audit.py::test_pass_deletes_existing_report |
| 92-REQ-3.E1 | TS-92-E2 | 2.2 | test_transient_audit.py::test_pass_no_file_no_error |
| 92-REQ-3.E2 | TS-92-E3 | 2.2 | test_transient_audit.py::test_pass_deletion_filesystem_error |
| 92-REQ-4.1 | TS-92-6, TS-92-7 | 3.1, 3.3 | test_transient_audit.py::test_cleanup_completed_specs, test_completed_spec_names |
| 92-REQ-4.2 | TS-92-6 | 3.2 | test_transient_audit.py::test_cleanup_completed_specs |
| 92-REQ-4.E1 | TS-92-E4 | 3.2 | test_transient_audit.py::test_cleanup_no_files_no_error |
| 92-REQ-4.E2 | TS-92-E5 | 3.2 | test_transient_audit.py::test_cleanup_partial_failure |
| Property 1 | TS-92-P1 | 2.1 | test_transient_audit_props.py::test_output_location_invariant |
| Property 2 | TS-92-P2 | 2.2 | test_transient_audit_props.py::test_pass_always_deletes |
| Property 3 | TS-92-P3 | 3.2 | test_transient_audit_props.py::test_cleanup_only_deletes_matching |
| Property 4 | TS-92-P4 | 2.1 | test_transient_audit_props.py::test_overwrite_idempotency |
| Path 1+2 | TS-92-SMOKE-1 | 2.1, 2.2 | test_transient_audit_smoke.py::test_full_lifecycle |
| Path 3 | TS-92-SMOKE-2 | 3.1, 3.2 | test_transient_audit_smoke.py::test_completion_cleanup |

## Notes

- The function signature of `persist_auditor_results` is unchanged — the new
  path is derived from `spec_dir.name` and `spec_dir.parent.parent`.
- Existing tests in `test_auditor.py` need path assertion updates (task 2.3)
  but no logic changes.
- The engine integration (task 3.3) must be wrapped in try/except to avoid
  disrupting the existing finally-block error handling.
