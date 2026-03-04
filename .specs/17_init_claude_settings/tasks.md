# Implementation Plan: Init Claude Settings

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec extends the existing `agent-fox init` command to create and maintain
`.claude/settings.local.json`. The implementation adds a constant, a helper
function, and two call sites to the existing `agent_fox/cli/init.py` module.
Task group 1 writes failing tests, task group 2 implements the feature.

## Test Commands

- Spec tests: `uv run pytest tests/unit/cli/test_claude_settings.py tests/property/cli/test_claude_settings_props.py -q`
- Unit tests: `uv run pytest tests/unit/cli/test_claude_settings.py -q`
- Property tests: `uv run pytest tests/property/cli/test_claude_settings_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_init.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/cli/init.py tests/unit/cli/test_claude_settings.py tests/property/cli/test_claude_settings_props.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file
    - Create `tests/unit/cli/test_claude_settings.py`
    - Set up fixtures: `tmp_project_root` (temporary directory), `settings_path` helper
    - Import `_ensure_claude_settings` and `CANONICAL_PERMISSIONS` from `agent_fox.cli.init`
    - _Test Spec: TS-17-1 through TS-17-5, TS-17-E1 through TS-17-E4_

  - [x] 1.2 Translate acceptance-criterion tests
    - `test_creates_file_when_absent` — TS-17-1
    - `test_creates_claude_directory_when_absent` — TS-17-2
    - `test_merges_missing_entries` — TS-17-3
    - `test_preserves_user_entries` — TS-17-4
    - `test_preserves_entry_ordering` — TS-17-5
    - Tests MUST fail (imports will fail since functions don't exist yet)
    - _Test Spec: TS-17-1 through TS-17-5_

  - [x] 1.3 Translate edge-case tests
    - `test_noop_when_all_canonical_present` — TS-17-E1
    - `test_invalid_json_logs_warning_and_skips` — TS-17-E2
    - `test_missing_permissions_structure_created` — TS-17-E3
    - `test_allow_not_a_list_logs_warning_and_skips` — TS-17-E4
    - _Test Spec: TS-17-E1 through TS-17-E4_

  - [x] 1.4 Create property test file
    - Create `tests/property/cli/test_claude_settings_props.py`
    - `test_canonical_coverage` — TS-17-P1
    - `test_user_entry_preservation` — TS-17-P2
    - `test_idempotency` — TS-17-P3
    - `test_order_preservation` — TS-17-P4
    - Use Hypothesis strategies: `lists(text(min_size=1), max_size=50)`
    - _Test Spec: TS-17-P1 through TS-17-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests pass (implementation already existed from prior work)
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/cli/test_claude_settings.py tests/property/cli/test_claude_settings_props.py`

- [x] 2. Implement Claude settings setup
  - [x] 2.1 Add `CANONICAL_PERMISSIONS` constant to `agent_fox/cli/init.py`
    - Define the list of canonical permission strings as a module-level constant
    - Place it near the existing `_GITIGNORE_ENTRIES` constant
    - _Requirements: 17-REQ-1.3_

  - [x] 2.2 Implement `_ensure_claude_settings()` function
    - Create `.claude/` directory if needed (`mkdir(parents=True, exist_ok=True)`)
    - If file doesn't exist: write canonical permissions as formatted JSON
    - If file exists: read, parse, merge missing entries, preserve existing, write back
    - Handle error cases: invalid JSON, missing structure, non-list `allow`
    - Use `json` module with `indent=2` for readable output
    - _Requirements: 17-REQ-1.1, 17-REQ-1.2, 17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3_
    - _Requirements: 17-REQ-2.E1, 17-REQ-2.E2, 17-REQ-2.E3_

  - [x] 2.3 Wire `_ensure_claude_settings()` into `init_cmd()`
    - Add call in the fresh-init path (after `_update_gitignore`)
    - Add call in the already-initialized path (after `_update_gitignore`)
    - _Requirements: 17-REQ-1.1_

  - [x] 2.4 Add integration test for init command
    - Extend `tests/integration/test_init.py` with a test that runs
      `agent-fox init` and verifies `.claude/settings.local.json` is created
      with canonical permissions
    - _Requirements: 17-REQ-1.1, 17-REQ-1.2_

  - [x] 2.V Verify task group 2
    - [x] All unit tests pass: `uv run pytest tests/unit/cli/test_claude_settings.py -q`
    - [x] All property tests pass: `uv run pytest tests/property/cli/test_claude_settings_props.py -q`
    - [x] Integration tests pass: `uv run pytest tests/integration/test_init.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/cli/init.py tests/unit/cli/test_claude_settings.py tests/property/cli/test_claude_settings_props.py`
    - [x] Requirements 17-REQ-1.1, 17-REQ-1.2, 17-REQ-1.3 acceptance criteria met
    - [x] Requirements 17-REQ-2.1, 17-REQ-2.2, 17-REQ-2.3 acceptance criteria met
    - [x] Edge cases 17-REQ-1.E1, 17-REQ-2.E1, 17-REQ-2.E2, 17-REQ-2.E3 handled

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
| 17-REQ-1.1 | TS-17-1 | 2.2, 2.3 | `test_claude_settings.py::test_creates_file_when_absent` |
| 17-REQ-1.2 | TS-17-2 | 2.2 | `test_claude_settings.py::test_creates_claude_directory_when_absent` |
| 17-REQ-1.3 | TS-17-1 | 2.1 | `test_claude_settings.py::test_creates_file_when_absent` |
| 17-REQ-2.1 | TS-17-3 | 2.2 | `test_claude_settings.py::test_merges_missing_entries` |
| 17-REQ-2.2 | TS-17-4 | 2.2 | `test_claude_settings.py::test_preserves_user_entries` |
| 17-REQ-2.3 | TS-17-5 | 2.2 | `test_claude_settings.py::test_preserves_entry_ordering` |
| 17-REQ-1.E1 | TS-17-E1 | 2.2 | `test_claude_settings.py::test_noop_when_all_canonical_present` |
| 17-REQ-2.E1 | TS-17-E2 | 2.2 | `test_claude_settings.py::test_invalid_json_logs_warning_and_skips` |
| 17-REQ-2.E2 | TS-17-E3 | 2.2 | `test_claude_settings.py::test_missing_permissions_structure_created` |
| 17-REQ-2.E3 | TS-17-E4 | 2.2 | `test_claude_settings.py::test_allow_not_a_list_logs_warning_and_skips` |
| Property 1 | TS-17-P1 | 2.2 | `test_claude_settings.py::test_canonical_coverage` |
| Property 2 | TS-17-P2 | 2.2 | `test_claude_settings.py::test_user_entry_preservation` |
| Property 3 | TS-17-P3 | 2.2 | `test_claude_settings.py::test_idempotency` |
| Property 4 | TS-17-P4 | 2.2 | `test_claude_settings.py::test_order_preservation` |

## Notes

- The implementation touches only `agent_fox/cli/init.py` — no new modules needed.
- Pattern follows existing init helpers (`_update_gitignore`, `_ensure_develop_branch`).
- JSON output uses `indent=2` with a trailing newline for clean diffs.
- Property tests should use `@settings(max_examples=50)` to keep CI fast.
