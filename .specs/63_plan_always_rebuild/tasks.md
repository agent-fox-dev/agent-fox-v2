# Implementation Plan: Plan Always Rebuild

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

A two-group plan: write failing tests, then make the code changes (removals)
to make them pass. The implementation is straightforward deletion of dead code
and simplification of the `plan_cmd` function.

## Test Commands

- Spec tests: `uv run pytest tests/unit/cli/test_plan_always_rebuild.py tests/integration/test_plan.py -q`
- Unit tests: `uv run pytest tests/unit/cli/test_plan_always_rebuild.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check && uv run ruff format --check`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file `tests/unit/cli/test_plan_always_rebuild.py`
    - TS-63-5: Assert `_compute_specs_hash`, `_compute_config_hash`,
      `_cache_matches_request` do not exist in `agent_fox.cli.plan`
    - TS-63-6: Assert `PlanMetadata` has no `specs_hash` or `config_hash` fields
    - _Test Spec: TS-63-5, TS-63-6_

  - [ ] 1.2 Add edge case test for old plan.json loading
    - TS-63-E1: Write a plan.json with `specs_hash`/`config_hash` in metadata,
      verify `load_plan()` succeeds and the loaded metadata lacks those fields
    - _Test Spec: TS-63-E1_

  - [ ] 1.3 Add integration tests
    - TS-63-1: Plan rebuilds after spec modification (no `--reanalyze` needed)
    - TS-63-4: `--reanalyze` rejected as unrecognized option
    - Modify or replace existing `test_plan_with_reanalyze` test
    - _Test Spec: TS-63-1, TS-63-4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`

- [ ] 2. Remove cache and --reanalyze
  - [ ] 2.1 Remove `--reanalyze` option and cache logic from `plan_cmd`
    - Remove `@click.option("--reanalyze", ...)` decorator
    - Remove `reanalyze` parameter from `plan_cmd`
    - Remove the `if not reanalyze and plan_path.exists():` block
    - Remove hash computation calls (`_compute_specs_hash`, `_compute_config_hash`)
    - The function should always call `_build_plan()` and `save_plan()`
    - _Requirements: 63-REQ-1.1, 63-REQ-1.2, 63-REQ-2.1_

  - [ ] 2.2 Remove dead functions from `agent_fox/cli/plan.py`
    - Delete `_compute_specs_hash()`
    - Delete `_compute_config_hash()`
    - Delete `_cache_matches_request()`
    - Remove unused imports (`hashlib`, `json`, and any others now unused)
    - _Requirements: 63-REQ-3.1_

  - [ ] 2.3 Remove `specs_hash` and `config_hash` from `PlanMetadata`
    - Edit `agent_fox/graph/types.py`: remove the two fields
    - Edit `agent_fox/graph/persistence.py`: remove references in
      `_metadata_from_dict` (the `.get()` calls for removed fields)
    - _Requirements: 63-REQ-3.2, 63-REQ-3.E1_

  - [ ] 2.4 Update documentation
    - Edit `docs/cli-reference.md`: remove `--reanalyze` row and caching
      description
    - _Requirements: 63-REQ-4.1, 63-REQ-4.2_

  - [ ] 2.5 Remove or update existing tests
    - Remove `test_plan_with_reanalyze` from `tests/integration/test_plan.py`
    - Remove any unit tests that reference `_compute_specs_hash`,
      `_compute_config_hash`, or `_cache_matches_request`
    - _Requirements: 63-REQ-2.1, 63-REQ-3.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/cli/test_plan_always_rebuild.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check && uv run ruff format --check`
    - [ ] Requirements 63-REQ-1.*, 63-REQ-2.*, 63-REQ-3.*, 63-REQ-4.* met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 63-REQ-1.1 | TS-63-1 | 2.1 | `test_plan_always_rebuild.py` / `test_plan.py` |
| 63-REQ-1.2 | TS-63-2 | 2.1 | `test_plan.py` |
| 63-REQ-1.3 | TS-63-3 | 2.1 | `test_plan_always_rebuild.py` |
| 63-REQ-2.1 | TS-63-4 | 2.1 | `test_plan.py` |
| 63-REQ-2.2 | TS-63-4 | 2.1 | `test_plan.py` |
| 63-REQ-3.1 | TS-63-5 | 2.2 | `test_plan_always_rebuild.py` |
| 63-REQ-3.2 | TS-63-6 | 2.3 | `test_plan_always_rebuild.py` |
| 63-REQ-3.E1 | TS-63-E1 | 2.3 | `test_plan_always_rebuild.py` |
| 63-REQ-4.1 | — | 2.4 | Manual review |
| 63-REQ-4.2 | — | 2.4 | Manual review |
