# Implementation Plan: Init AGENTS.md Template

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec adds AGENTS.md scaffolding to the `agent-fox init` command. The
implementation is small: one static template file, one helper function, and
two call sites. Task group 1 writes failing tests, task group 2 creates the
template file and implements the feature.

## Test Commands

- Spec tests: `uv run pytest tests/unit/cli/test_agents_md.py tests/property/cli/test_agents_md_props.py -q`
- Unit tests: `uv run pytest tests/unit/cli/test_agents_md.py -q`
- Property tests: `uv run pytest tests/property/cli/test_agents_md_props.py -q`
- Integration tests: `uv run pytest tests/integration/test_init.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/cli/init.py agent_fox/_templates/agents_md.md tests/unit/cli/test_agents_md.py tests/property/cli/test_agents_md_props.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file
    - Create `tests/unit/cli/test_agents_md.py`
    - Set up fixtures: `tmp_project_root` (temporary directory)
    - Import `_ensure_agents_md` from `agent_fox.cli.init`
    - _Test Spec: TS-44-1 through TS-44-12, TS-44-E1, TS-44-E2_

  - [x] 1.2 Translate acceptance-criterion tests
    - `test_template_file_exists` — TS-44-1
    - `test_template_is_valid_utf8` — TS-44-2
    - `test_template_contains_placeholders` — TS-44-3
    - `test_creates_agents_md_when_absent` — TS-44-4
    - `test_skips_when_agents_md_exists` — TS-44-7
    - `test_created_regardless_of_claude_md` — TS-44-10
    - `test_created_when_claude_md_absent` — TS-44-11
    - Tests MUST fail (function does not exist yet)
    - _Test Spec: TS-44-1 through TS-44-4, TS-44-7, TS-44-10, TS-44-11_

  - [x] 1.3 Translate edge-case tests
    - `test_missing_template_raises_error` — TS-44-E1
    - `test_empty_agents_md_not_overwritten` — TS-44-E2
    - Tests MUST fail
    - _Test Spec: TS-44-E1, TS-44-E2_

  - [x] 1.4 Create property test file
    - Create `tests/property/cli/test_agents_md_props.py`
    - `test_idempotent_creation` — TS-44-P1
    - `test_content_fidelity` — TS-44-P2
    - `test_existing_file_preservation` — TS-44-P3
    - `test_claude_md_independence` — TS-44-P4
    - `test_return_value_correctness` — TS-44-P5
    - Use Hypothesis strategies: `text(min_size=0, max_size=10000)`, `booleans()`
    - _Test Spec: TS-44-P1 through TS-44-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/cli/test_agents_md.py tests/property/cli/test_agents_md_props.py`

- [x] 2. Implement AGENTS.md scaffolding
  - [x] 2.1 Create the template file
    - Create `agent_fox/_templates/agents_md.md`
    - Content is a generalized version of the repo's `AGENTS.md` with
      placeholder markers (`<main_package>`, `<test_directory>`)
    - _Requirements: 44-REQ-1.1, 44-REQ-1.2, 44-REQ-1.3_

  - [x] 2.2 Add `_AGENTS_MD_TEMPLATE` constant and `_ensure_agents_md()` function
    - Add `_TEMPLATES_DIR` and `_AGENTS_MD_TEMPLATE` path constants
    - Implement `_ensure_agents_md(project_root: Path) -> str`
    - Check `AGENTS.md` existence, write template if absent, return status
    - _Requirements: 44-REQ-2.1, 44-REQ-3.1, 44-REQ-3.E1, 44-REQ-1.E1_

  - [x] 2.3 Wire `_ensure_agents_md()` into `init_cmd()`
    - Add call in the fresh-init path (after `_ensure_claude_settings`)
    - Add call in the re-init path (after `_ensure_claude_settings`)
    - Display `Created AGENTS.md.` message when result is `"created"` (non-JSON only)
    - Include `"agents_md"` field in JSON output on both paths
    - _Requirements: 44-REQ-2.2, 44-REQ-2.3, 44-REQ-3.2, 44-REQ-3.3_

  - [x] 2.4 Add integration tests
    - Extend `tests/integration/test_init.py` or add tests in unit file:
      - `test_init_creates_agents_md_message` — TS-44-5
      - `test_init_json_agents_md_created` — TS-44-6
      - `test_init_silent_skip` — TS-44-8
      - `test_init_json_agents_md_skipped` — TS-44-9
      - `test_agents_md_not_in_gitignore` — TS-44-12
    - _Test Spec: TS-44-5, TS-44-6, TS-44-8, TS-44-9, TS-44-12_

  - [x] 2.V Verify task group 2
    - [x] All unit tests pass: `uv run pytest tests/unit/cli/test_agents_md.py -q`
    - [x] All property tests pass: `uv run pytest tests/property/cli/test_agents_md_props.py -q`
    - [x] Integration tests pass: `uv run pytest tests/integration/test_init.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/cli/init.py tests/unit/cli/test_agents_md.py tests/property/cli/test_agents_md_props.py`
    - [x] Requirements 44-REQ-1.*, 44-REQ-2.*, 44-REQ-3.* acceptance criteria met
    - [x] Requirements 44-REQ-4.*, 44-REQ-5.* acceptance criteria met

- [x] 3. Checkpoint — Feature Complete
  - Ensure all tests pass: `uv run pytest -q`
  - Ensure linting passes: `uv run ruff check agent_fox/cli/init.py`
  - Update `docs/cli-reference.md` if init command documentation needs changes

### Checkbox States

| Syntax   | Meaning                |
|----------|------------------------|
| `- [ ]`  | Not started (required) |
| `- [ ]*` | Not started (optional) |
| `- [x]`  | Completed              |
| `- [-]`  | In progress            |
| `- [~]`  | Queued                 |

Tasks are **required by default**. Mark optional tasks with `*` after checkbox: `- [ ]* Optional task`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 44-REQ-1.1 | TS-44-1 | 2.1 | `test_agents_md.py::test_template_file_exists` |
| 44-REQ-1.2 | TS-44-2 | 2.1 | `test_agents_md.py::test_template_is_valid_utf8` |
| 44-REQ-1.3 | TS-44-3 | 2.1 | `test_agents_md.py::test_template_contains_placeholders` |
| 44-REQ-1.E1 | TS-44-E1 | 2.2 | `test_agents_md.py::test_missing_template_raises_error` |
| 44-REQ-2.1 | TS-44-4 | 2.2, 2.3 | `test_agents_md.py::test_creates_agents_md_when_absent` |
| 44-REQ-2.2 | TS-44-5 | 2.3 | `test_agents_md.py::test_init_creates_agents_md_message` |
| 44-REQ-2.3 | TS-44-6 | 2.3 | `test_agents_md.py::test_init_json_agents_md_created` |
| 44-REQ-3.1 | TS-44-7 | 2.2 | `test_agents_md.py::test_skips_when_agents_md_exists` |
| 44-REQ-3.2 | TS-44-8 | 2.3 | `test_agents_md.py::test_init_silent_skip` |
| 44-REQ-3.3 | TS-44-9 | 2.3 | `test_agents_md.py::test_init_json_agents_md_skipped` |
| 44-REQ-3.E1 | TS-44-E2 | 2.2 | `test_agents_md.py::test_empty_agents_md_not_overwritten` |
| 44-REQ-4.1 | TS-44-10 | 2.2 | `test_agents_md.py::test_created_regardless_of_claude_md` |
| 44-REQ-4.2 | TS-44-11 | 2.2 | `test_agents_md.py::test_created_when_claude_md_absent` |
| 44-REQ-5.1 | TS-44-12 | 2.3 | `test_agents_md.py::test_agents_md_not_in_gitignore` |
| Property 1 | TS-44-P1 | 2.2 | `test_agents_md_props.py::test_idempotent_creation` |
| Property 2 | TS-44-P2 | 2.2 | `test_agents_md_props.py::test_content_fidelity` |
| Property 3 | TS-44-P3 | 2.2 | `test_agents_md_props.py::test_existing_file_preservation` |
| Property 4 | TS-44-P4 | 2.2 | `test_agents_md_props.py::test_claude_md_independence` |
| Property 5 | TS-44-P5 | 2.2 | `test_agents_md_props.py::test_return_value_correctness` |

## Notes

- The implementation touches only `agent_fox/cli/init.py` and adds one template file.
- Pattern follows existing init helpers (`_ensure_claude_settings`).
- Integration tests should use the Click test runner with `CliRunner` and mock git operations.
- Property tests should use `@settings(max_examples=50)` to keep CI fast.
