# Implementation Plan: Cross-Iteration Hunt Scan Deduplication

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds a dedup gate to the hunt scan pipeline. Task group 1
writes failing tests. Group 2 implements the pure functions in a new `dedup.py`
module. Group 3 integrates the dedup gate into the engine and modifies issue
creation to embed fingerprints and attach labels. Group 4 is the wiring
verification.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/nightshift/test_dedup.py tests/integration/nightshift/test_dedup.py tests/property/nightshift/test_dedup_props.py`
- Unit tests: `uv run pytest -q tests/unit/nightshift/test_dedup.py`
- Property tests: `uv run pytest -q tests/property/nightshift/test_dedup_props.py`
- Integration tests: `uv run pytest -q tests/integration/nightshift/test_dedup.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/nightshift/test_dedup.py`
    - Test `compute_fingerprint()` — TS-79-1, TS-79-2, TS-79-3, TS-79-4, TS-79-14, TS-79-15
    - Test `embed_fingerprint()` — TS-79-5
    - Test `extract_fingerprint()` — TS-79-6, TS-79-7, TS-79-8
    - _Test Spec: TS-79-1 through TS-79-8, TS-79-14, TS-79-15_

  - [x] 1.2 Create integration test file `tests/integration/nightshift/test_dedup.py`
    - Test `filter_known_duplicates()` — TS-79-9, TS-79-10
    - Test issue creation with label — TS-79-11, TS-79-12, TS-79-13
    - Test edge cases — TS-79-E1, TS-79-E2, TS-79-E3, TS-79-E4
    - Test smoke tests — TS-79-SMOKE-1, TS-79-SMOKE-2
    - _Test Spec: TS-79-9 through TS-79-13, TS-79-E1 through TS-79-E4, TS-79-SMOKE-1, TS-79-SMOKE-2_

  - [x] 1.3 Create property test file `tests/property/nightshift/test_dedup_props.py`
    - Fingerprint determinism — TS-79-P1
    - Fingerprint uniqueness — TS-79-P2
    - Embed-extract round-trip — TS-79-P3
    - Dedup gate conservation — TS-79-P4
    - Fail-open guarantee — TS-79-P5
    - Empty files stability — TS-79-P6
    - _Test Spec: TS-79-P1 through TS-79-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [x] 2. Implement dedup module (pure functions)
  - [x] 2.1 Create `agent_fox/nightshift/dedup.py` with module docstring
    - Define `FINGERPRINT_LABEL = "af:hunt"`
    - Define `_FINGERPRINT_PATTERN` regex
    - _Requirements: 79-REQ-3.1_

  - [x] 2.2 Implement `compute_fingerprint()`
    - SHA-256 of category + NUL + sorted deduplicated affected_files joined by NUL
    - Return first 16 hex characters
    - Handle empty affected_files (category-only hash)
    - _Requirements: 79-REQ-1.1, 79-REQ-1.2, 79-REQ-1.3, 79-REQ-1.E1, 79-REQ-1.E2, 79-REQ-5.1, 79-REQ-5.2, 79-REQ-5.E1_

  - [x] 2.3 Implement `embed_fingerprint()` and `extract_fingerprint()`
    - Append `\n<!-- af:fingerprint:{fp} -->` to body
    - Extract first match of `_FINGERPRINT_PATTERN` from body, return hex or None
    - _Requirements: 79-REQ-2.1, 79-REQ-2.2, 79-REQ-2.E1, 79-REQ-2.E2_

  - [x] 2.4 Implement `filter_known_duplicates()`
    - Fetch open `af:hunt` issues via `platform.list_issues_by_label`
    - Extract fingerprints from issue bodies into a dict (fp -> issue_number)
    - Compute fingerprint for each group, skip if in known set
    - Log skips at INFO with group title and matching issue number
    - Catch platform exceptions: log warning, return all groups (fail-open)
    - _Requirements: 79-REQ-4.1, 79-REQ-4.2, 79-REQ-4.3, 79-REQ-4.4, 79-REQ-4.E1, 79-REQ-4.E2, 79-REQ-4.E3_

  - [x] 2.V Verify task group 2
    - [x] Unit tests pass: `uv run pytest -q tests/unit/nightshift/test_dedup.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/nightshift/test_dedup_props.py`
    - [x] Integration tests for filter pass: `uv run pytest -q tests/integration/nightshift/test_dedup.py -k "filter"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 79-REQ-1.*, 79-REQ-2.*, 79-REQ-4.*, 79-REQ-5.* met

- [x] 3. Pipeline integration
  - [x] 3.1 Modify `create_issues_from_groups()` in `finding.py`
    - Import `compute_fingerprint`, `embed_fingerprint`, `FINGERPRINT_LABEL` from dedup
    - Before calling `platform.create_issue()`, compute fingerprint and embed in body
    - Pass `labels=[FINGERPRINT_LABEL]` to `platform.create_issue()`
    - _Requirements: 79-REQ-2.1, 79-REQ-3.1, 79-REQ-3.2_

  - [x] 3.2 Modify `_run_hunt_scan()` in `engine.py`
    - Import `filter_known_duplicates` from dedup
    - Insert dedup gate call between `consolidate_findings()` and `create_issues_from_groups()`
    - _Requirements: 79-REQ-4.1, 79-REQ-4.2_

  - [x] 3.3 Verify af:fix label coexistence
    - Ensure `--auto` mode assigns `af:fix` after creation (existing behavior)
    - Issues should have both `af:hunt` (from creation) and `af:fix` (from assign_label)
    - _Requirements: 79-REQ-3.2, 79-REQ-3.E1_

  - [x] 3.V Verify task group 3
    - [x] All integration tests pass: `uv run pytest -q tests/integration/nightshift/test_dedup.py`
    - [x] Smoke tests pass: `uv run pytest -q tests/integration/nightshift/test_dedup.py -k "smoke"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check && uv run ruff format --check`
    - [x] Requirements 79-REQ-3.* met
    - [x] Full pipeline: `make check`

- [ ] 4. Wiring verification
  - [ ] 4.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - _Requirements: all_

  - [ ] 4.2 Verify return values propagate correctly
    - `filter_known_duplicates` returns `list[FindingGroup]` consumed by `create_issues_from_groups`
    - `compute_fingerprint` return value is used by both `filter_known_duplicates` and `create_issues_from_groups`
    - `extract_fingerprint` return value is used by `filter_known_duplicates`
    - _Requirements: all_

  - [ ] 4.3 Run the integration smoke tests
    - All `TS-79-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-79-SMOKE-1, TS-79-SMOKE-2_

  - [ ] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be either justified or replaced with real implementation
    - Document any intentional stubs here with rationale

  - [ ] 4.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 79-REQ-1.1 | TS-79-1 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-1.2 | TS-79-2 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-1.3 | TS-79-3 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-1.E1 | TS-79-4 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-1.E2 | TS-79-3 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-2.1 | TS-79-5, TS-79-12 | 2.3, 3.1 | tests/unit/nightshift/test_dedup.py, tests/integration/nightshift/test_dedup.py |
| 79-REQ-2.2 | TS-79-6 | 2.3 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-2.E1 | TS-79-8 | 2.3 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-2.E2 | TS-79-7 | 2.3 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-3.1 | TS-79-11 | 3.1 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-3.2 | TS-79-13 | 3.3 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-3.E1 | TS-79-E4 | 3.3 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.1 | TS-79-9 | 2.4, 3.2 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.2 | TS-79-9 | 2.4, 3.2 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.3 | TS-79-10 | 2.4 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.4 | TS-79-9 | 2.4 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.E1 | TS-79-E1 | 2.4 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.E2 | TS-79-E2 | 2.4 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-4.E3 | TS-79-E3 | 2.4 | tests/integration/nightshift/test_dedup.py |
| 79-REQ-5.1 | TS-79-14 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-5.2 | TS-79-2 | 2.2 | tests/unit/nightshift/test_dedup.py |
| 79-REQ-5.E1 | TS-79-15 | 2.2 | tests/unit/nightshift/test_dedup.py |
| Property 1 | TS-79-P1 | 2.2 | tests/property/nightshift/test_dedup_props.py |
| Property 2 | TS-79-P2 | 2.2 | tests/property/nightshift/test_dedup_props.py |
| Property 3 | TS-79-P3 | 2.3 | tests/property/nightshift/test_dedup_props.py |
| Property 4 | TS-79-P4 | 2.4 | tests/property/nightshift/test_dedup_props.py |
| Property 5 | TS-79-P5 | 2.4 | tests/property/nightshift/test_dedup_props.py |
| Property 6 | TS-79-P6 | 2.2 | tests/property/nightshift/test_dedup_props.py |
| Path 1 | TS-79-SMOKE-1 | 3.2 | tests/integration/nightshift/test_dedup.py |
| Path 2 | TS-79-SMOKE-2 | 3.2 | tests/integration/nightshift/test_dedup.py |

## Notes

- The `af:hunt` label is passed via the `labels` parameter of `create_issue()`,
  which is already supported by both the protocol and the GitHub implementation.
  No platform changes needed.
- The `list_issues_by_label()` method already populates `IssueResult.body`,
  so fingerprint extraction works without platform modifications.
- Existing hunt-scan tests may need minor updates if they assert on
  `create_issue` call arguments (body content, labels parameter).
- Property tests should use `@pytest.mark.asyncio` for async tests and
  `suppress(HealthCheck.function_scoped_fixture)` for Hypothesis+fixtures.
