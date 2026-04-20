# Implementation Plan: Steering Document

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Four task groups: (1) write failing tests, (2) implement init and loading logic,
(3) update templates, (4) documentation checkpoint. The init and prompt changes
are in group 2; template changes are in group 3 because they don't affect
runtime behavior and can be done independently.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/cli/test_steering.py tests/unit/session/test_steering.py tests/integration/test_steering.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test files
    - `tests/unit/cli/test_steering.py` — init-related tests
    - `tests/unit/session/test_steering.py` — load_steering and placeholder detection tests
    - `tests/integration/test_steering.py` — context assembly ordering test
    - `tests/property/session/test_steering_props.py` — property tests
    - _Test Spec: TS-64-1 through TS-64-11_

  - [x] 1.2 Translate acceptance-criterion tests
    - TS-64-1: init creates file when absent
    - TS-64-2: init skips existing file
    - TS-64-3: placeholder contains sentinel and comments
    - TS-64-4: init creates .specs directory
    - TS-64-5: load_steering returns content for real directives
    - TS-64-6: steering placement in assembled context
    - TS-64-7: missing file returns None
    - TS-64-8: placeholder-only returns None
    - TS-64-9: all skill templates reference steering.md
    - TS-64-10: AGENTS.md template references steering.md
    - TS-64-11: sentinel marker in placeholder constant
    - _Test Spec: TS-64-1 through TS-64-11_

  - [x] 1.3 Translate edge-case tests
    - TS-64-E1: permission error creating .specs
    - TS-64-E2: unreadable steering file at runtime
    - _Test Spec: TS-64-E1, TS-64-E2_

  - [x] 1.4 Translate property tests
    - TS-64-P1: idempotent initialization
    - TS-64-P2: placeholder detection accuracy
    - TS-64-P3: context ordering invariant
    - _Test Spec: TS-64-P1, TS-64-P2, TS-64-P3_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement init and runtime loading
  - [x] 2.1 Add `_STEERING_PLACEHOLDER` constant and `_ensure_steering_md()` to `agent_fox/cli/init.py`
    - Define placeholder content with sentinel marker
    - Create `.specs/` directory if needed
    - Write placeholder if file absent, skip if present
    - Handle OSError gracefully
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.E1_

  - [x] 2.2 Wire `_ensure_steering_md()` into `init_cmd()`
    - Call in both fresh-init and re-init paths
    - Report status in JSON output and CLI output
    - _Requirements: 1.1, 1.2_

  - [x] 2.3 Add `STEERING_PLACEHOLDER_SENTINEL`, `load_steering()` to `agent_fox/session/prompt.py`
    - Define sentinel constant
    - Implement placeholder detection (strip HTML comments, check for non-whitespace)
    - Read file, return content or None
    - Log at DEBUG level
    - _Requirements: 2.1, 2.3, 2.4, 2.E1, 5.1, 5.2_

  - [x] 2.4 Integrate steering into `assemble_context()`
    - Add optional `project_root: Path | None = None` parameter
    - Call `load_steering()` when project_root is provided
    - Insert `## Steering Directives` section after spec files, before memory facts
    - _Requirements: 2.1, 2.2_

  - [x] 2.5 Update callers of `assemble_context()` to pass `project_root`
    - Find all call sites and add `project_root=Path.cwd()` or equivalent
    - _Requirements: 2.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/cli/test_steering.py tests/unit/session/test_steering.py tests/integration/test_steering.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/session/test_steering_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 1.*, 2.*, 5.* acceptance criteria met

- [x] 3. Update templates
  - [x] 3.1 Add steering reference to AGENTS.md template
    - Add step to "Understand Before You Code" section in `agent_fox/_templates/agents_md.md`
    - Place after existing orientation steps, before "Explore the codebase"
    - _Requirements: 4.1, 4.2_

  - [x] 3.2 Add steering instruction to all skill templates
    - Add instruction block to each file in `agent_fox/_templates/skills/`
    - Place early in each skill (before main workflow steps)
    - Instruction: read and follow `.specs/steering.md` if it exists
    - _Requirements: 3.1, 3.2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/cli/test_steering.py::test_agents_md_template_references_steering tests/unit/cli/test_steering.py::test_skill_templates_reference_steering`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 3.*, 4.* acceptance criteria met

- [x] 4. Checkpoint — Steering Document Complete
  - Ensure all tests pass, update docs if needed.
  - Update CLAUDE.md if the steering document changes any documented workflow.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 64-REQ-1.1 | TS-64-1 | 2.1, 2.2 | test_steering.py::test_init_creates_steering |
| 64-REQ-1.2 | TS-64-2 | 2.1 | test_steering.py::test_init_skips_existing |
| 64-REQ-1.3 | TS-64-3 | 2.1 | test_steering.py::test_placeholder_content |
| 64-REQ-1.4 | TS-64-4 | 2.1 | test_steering.py::test_init_creates_specs_dir |
| 64-REQ-1.E1 | TS-64-E1 | 2.1 | test_steering.py::test_init_permission_error |
| 64-REQ-2.1 | TS-64-5 | 2.3 | test_steering.py::test_load_real_content |
| 64-REQ-2.2 | TS-64-6 | 2.4 | test_steering.py::test_context_ordering |
| 64-REQ-2.3 | TS-64-7 | 2.3 | test_steering.py::test_load_missing_file |
| 64-REQ-2.4 | TS-64-8 | 2.3 | test_steering.py::test_load_placeholder_only |
| 64-REQ-2.E1 | TS-64-E2 | 2.3 | test_steering.py::test_load_unreadable |
| 64-REQ-3.1 | TS-64-9 | 3.2 | test_steering.py::test_skill_templates |
| 64-REQ-3.2 | TS-64-9 | 3.2 | test_steering.py::test_skill_templates |
| 64-REQ-4.1 | TS-64-10 | 3.1 | test_steering.py::test_agents_md_template |
| 64-REQ-4.2 | TS-64-10 | 3.1 | test_steering.py::test_agents_md_template |
| 64-REQ-5.1 | TS-64-11 | 2.3 | test_steering.py::test_sentinel_in_placeholder |
| 64-REQ-5.2 | TS-64-8 | 2.3 | test_steering.py::test_load_placeholder_only |
| Property 1 | TS-64-P1 | 2.1 | test_steering_props.py::test_idempotent_init |
| Property 2 | TS-64-P2 | 2.3 | test_steering_props.py::test_placeholder_detection |
| Property 3 | TS-64-P3 | 2.4 | test_steering_props.py::test_context_ordering |

## Notes

- The `assemble_context()` signature change is backward-compatible (optional
  param with `None` default).
- Skill templates are static files read by Claude Code / Cursor — the
  instruction to read steering.md relies on the consuming agent's ability
  to read files from the project directory.
- The AGENTS.md template change only affects newly-initialized projects.
  Existing AGENTS.md files need manual update or re-init.
