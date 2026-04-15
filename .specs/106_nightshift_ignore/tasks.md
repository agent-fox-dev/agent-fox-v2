# Implementation Plan: Night-Shift Ignore File

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds a `.night-shift` ignore file for hunt scan file
exclusion. Task group 1 writes failing tests. Group 2 adds `pathspec` as a
dependency and implements the `nightshift.ignore` module. Group 3 integrates
with `HuntScanner`. Group 4 extends the init command. Group 5 verifies
end-to-end wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_nightshift_ignore.py tests/property/test_nightshift_ignore_props.py tests/integration/test_nightshift_ignore_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/test_nightshift_ignore.py`
- Property tests: `uv run pytest -q tests/property/test_nightshift_ignore_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_nightshift_ignore.py`
    - Test `load_ignore_spec` with valid file (TS-106-1)
    - Test comments and blank lines (TS-106-2)
    - Test missing file returns defaults-only (TS-106-3)
    - Test default exclusions always applied (TS-106-4)
    - Test default exclusions cannot be negated (TS-106-5)
    - Test `filter_findings` removes ignored files (TS-106-6)
    - Test findings with empty affected_files preserved (TS-106-7)
    - Test additive with .gitignore (TS-106-8)
    - Test gitwildmatch patterns (TS-106-13)
    - Test POSIX relative paths (TS-106-14)
    - Test pathspec in pyproject.toml dependencies (TS-106-12)
    - _Test Spec: TS-106-1 through TS-106-8, TS-106-12, TS-106-13, TS-106-14_

  - [x] 1.2 Create unit tests for init integration
    - Test `_ensure_nightshift_ignore` creates file (TS-106-9)
    - Test init skips existing file (TS-106-10)
    - Test `InitResult` has nightshift_ignore field (TS-106-11)
    - _Test Spec: TS-106-9, TS-106-10, TS-106-11_

  - [x] 1.3 Create edge case tests
    - Test unreadable `.night-shift` file (TS-106-E1)
    - Test empty `.night-shift` file (TS-106-E2)
    - Test init permission error (TS-106-E3)
    - Test HuntScanner works when ignore loading fails (TS-106-E4)
    - _Test Spec: TS-106-E1, TS-106-E2, TS-106-E3, TS-106-E4_

  - [x] 1.4 Create property tests `tests/property/test_nightshift_ignore_props.py`
    - Default exclusions always hold (TS-106-P1)
    - filter_findings never adds findings (TS-106-P2)
    - load_ignore_spec never raises (TS-106-P3)
    - Findings with empty affected_files survive (TS-106-P4)
    - Init idempotency (TS-106-P5)
    - _Test Spec: TS-106-P1 through TS-106-P5_

  - [x] 1.5 Create integration smoke tests `tests/integration/test_nightshift_ignore_smoke.py`
    - Hunt scan respects `.night-shift` file (TS-106-SMOKE-1)
    - Init creates loadable `.night-shift` (TS-106-SMOKE-2)
    - _Test Spec: TS-106-SMOKE-1, TS-106-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Implement `nightshift.ignore` module and add `pathspec` dependency
  - [x] 2.1 Add `pathspec>=0.12` to `pyproject.toml` dependencies
    - Add to `[project] dependencies` list
    - Run `uv lock` to update lockfile
    - _Requirements: 106-REQ-5.1_

  - [x] 2.2 Create `agent_fox/nightshift/ignore.py`
    - Define `DEFAULT_EXCLUSIONS` constant list
    - Define `NIGHTSHIFT_IGNORE_FILENAME = ".night-shift"`
    - Define `NIGHTSHIFT_IGNORE_SEED` constant with seed file content
    - Implement `NightShiftIgnoreSpec` frozen dataclass with `is_ignored()` method
    - Implement `load_ignore_spec(project_root)` function
    - Implement `filter_findings(findings, spec)` function
    - Also added `_ensure_nightshift_ignore` and `InitResult.nightshift_ignore` to
      `init_project.py` to make unit test module importable (per test design)
    - _Requirements: 106-REQ-1.1, 106-REQ-1.2, 106-REQ-1.3, 106-REQ-1.4,
      106-REQ-1.E1, 106-REQ-1.E2, 106-REQ-2.1, 106-REQ-2.E1,
      106-REQ-3.2, 106-REQ-3.3, 106-REQ-6.1, 106-REQ-6.2, 106-REQ-6.3_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_nightshift_ignore.py -k "not init and not scanner"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/ignore.py`
    - [x] Requirements 106-REQ-1.*, 106-REQ-2.*, 106-REQ-5.1, 106-REQ-6.* acceptance criteria met

- [x] 3. Integrate with HuntScanner
  - [x] 3.1 Modify `HuntScanner.run()` in `agent_fox/nightshift/hunt.py`
    - Import `load_ignore_spec` and `filter_findings`
    - After gathering all findings, call `load_ignore_spec(project_root)`
    - Call `filter_findings(all_findings, ignore_spec)`
    - Wrap in try/except to handle unexpected errors (106-REQ-3.E1)
    - _Requirements: 106-REQ-3.1, 106-REQ-3.E1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_nightshift_ignore.py tests/integration/test_nightshift_ignore_smoke.py -k "scanner or smoke_1"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/nightshift/hunt.py`
    - [x] Requirements 106-REQ-3.1, 106-REQ-3.E1 acceptance criteria met

- [x] 4. Extend init command
  - [x] 4.1 Add `_ensure_nightshift_ignore()` to `agent_fox/workspace/init_project.py`
    - Import `NIGHTSHIFT_IGNORE_SEED` from `nightshift.ignore`
    - Implement `_ensure_nightshift_ignore(project_root) -> str`
    - Add `nightshift_ignore: str = "skipped"` field to `InitResult`
    - Call `_ensure_nightshift_ignore` from both init paths (fresh and re-init)
    - _Requirements: 106-REQ-4.1, 106-REQ-4.2, 106-REQ-4.4,
      106-REQ-4.E1, 106-REQ-4.E2_

  - [x] 4.2 Update CLI output in `agent_fox/cli/init.py`
    - Add text output: `"Created .night-shift."` when status is `"created"`
    - Add JSON output: `"night_shift_ignore": result.nightshift_ignore`
    - _Requirements: 106-REQ-4.3_

  - [x] 4.V Verify task group 4
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/test_nightshift_ignore.py -k "init"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/workspace/init_project.py agent_fox/cli/init.py`
    - [x] Requirements 106-REQ-4.* acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-106-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-106-SMOKE-1, TS-106-SMOKE-2_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 5.5 Cross-spec entry point verification
    - Verify `load_ignore_spec` is called from `HuntScanner.run()` in
      production code
    - Verify `_ensure_nightshift_ignore` is called from `init_project()` in
      production code
    - Verify `filter_findings` is called from `HuntScanner.run()` after
      category execution
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 106-REQ-1.1 | TS-106-1 | 2.2 | test_load_valid_file |
| 106-REQ-1.2 | TS-106-1 | 2.2 | test_load_valid_file |
| 106-REQ-1.3 | TS-106-2 | 2.2 | test_comments_blank_lines |
| 106-REQ-1.4 | TS-106-3 | 2.2 | test_missing_file_defaults |
| 106-REQ-1.E1 | TS-106-E1 | 2.2 | test_unreadable_file |
| 106-REQ-1.E2 | TS-106-E2 | 2.2 | test_empty_file |
| 106-REQ-2.1 | TS-106-4 | 2.2 | test_default_exclusions |
| 106-REQ-2.E1 | TS-106-5 | 2.2 | test_defaults_cannot_negate |
| 106-REQ-3.1 | TS-106-SMOKE-1 | 3.1 | test_smoke_hunt_scan |
| 106-REQ-3.2 | TS-106-6, TS-106-7 | 2.2 | test_filter_findings_* |
| 106-REQ-3.3 | TS-106-8 | 2.2 | test_additive_gitignore |
| 106-REQ-3.E1 | TS-106-E4 | 3.1 | test_scanner_ignore_failure |
| 106-REQ-4.1 | TS-106-9 | 4.1 | test_init_creates_file |
| 106-REQ-4.2 | TS-106-9 | 4.1 | test_init_creates_file |
| 106-REQ-4.3 | TS-106-11 | 4.2 | test_init_result_field |
| 106-REQ-4.4 | TS-106-11 | 4.1 | test_init_result_field |
| 106-REQ-4.E1 | TS-106-10 | 4.1 | test_init_skips_existing |
| 106-REQ-4.E2 | TS-106-E3 | 4.1 | test_init_permission_error |
| 106-REQ-5.1 | TS-106-12 | 2.1 | test_pathspec_dependency |
| 106-REQ-6.1 | TS-106-13 | 2.2 | test_gitwildmatch |
| 106-REQ-6.2 | TS-106-14 | 2.2 | test_posix_paths |
| 106-REQ-6.3 | TS-106-1 | 2.2 | test_load_valid_file |
| Property 1 | TS-106-P1 | 2.2 | test_prop_defaults_always |
| Property 2 | TS-106-P2 | 2.2 | test_prop_filter_monotonic |
| Property 3 | TS-106-P3 | 2.2 | test_prop_never_raises |
| Property 4 | TS-106-P4 | 2.2 | test_prop_empty_files_survive |
| Property 6 | TS-106-P5 | 4.1 | test_prop_init_idempotent |
| Path 1 | TS-106-SMOKE-1 | 3.1 | test_smoke_hunt_scan |
| Path 2 | TS-106-SMOKE-2 | 4.1 | test_smoke_init_loadable |

## Notes

- `pathspec` is promoted from optional to required. Existing code in
  `agent_fox/knowledge/lang/registry.py` that dynamically imports pathspec
  can be simplified in a future spec, but is out of scope here.
- The `filter_findings` function operates on the `Finding.affected_files`
  field. Findings with no affected files (common for categories like
  `dependency_freshness`) are always preserved.
- Static tool output (ruff, pytest) is not filtered by `.night-shift`. Those
  tools have their own ignore mechanisms (ruff.toml, pytest.ini, etc.).
