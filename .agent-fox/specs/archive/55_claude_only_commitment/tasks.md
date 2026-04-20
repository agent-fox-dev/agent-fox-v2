# Implementation Plan: Claude-Only Commitment

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec is lightweight: simplify the backend factory, update docstrings,
create an ADR, and update the README. Task group 1 writes failing tests,
task group 2 implements all changes, task group 3 checkpoints.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_claude_only.py tests/property/test_claude_only_props.py tests/integration/test_claude_only_integration.py`
- Unit tests: `uv run pytest -q tests/unit/test_claude_only.py`
- Property tests: `uv run pytest -q tests/property/test_claude_only_props.py`
- Integration tests: `uv run pytest -q tests/integration/test_claude_only_integration.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_claude_only.py`
    - Test `get_backend()` returns ClaudeBackend (TS-55-4)
    - Test `get_backend()` has no parameters (TS-55-5)
    - Test `AgentBackend` is exported and runtime-checkable (TS-55-7)
    - Test `AgentBackend` docstring mentions Claude-only (TS-55-8)
    - Test ADR content has alternatives and non-coding mention (TS-55-2, TS-55-3)
    - Test mock backend satisfies protocol (TS-55-E2)
    - Test ADR number uniqueness (TS-55-E1)
    - _Test Spec: TS-55-2, TS-55-3, TS-55-4, TS-55-5, TS-55-7, TS-55-8, TS-55-E1, TS-55-E2_

  - [x] 1.2 Create property test file `tests/property/test_claude_only_props.py`
    - Property: factory always returns AgentBackend (TS-55-P1)
    - Property: factory has no parameters (TS-55-P2)
    - Property: protocol is runtime-checkable (TS-55-P3)
    - _Test Spec: TS-55-P1, TS-55-P2, TS-55-P3_

  - [x] 1.3 Create integration test file `tests/integration/test_claude_only_integration.py`
    - Test ADR file exists (TS-55-1)
    - Test no call sites pass name argument to get_backend (TS-55-6)
    - Test README mentions Claude (TS-55-9)
    - _Test Spec: TS-55-1, TS-55-6, TS-55-9_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/test_claude_only.py tests/property/test_claude_only_props.py tests/integration/test_claude_only_integration.py`

- [x] 2. Implement Claude-only commitment
  - [x] 2.1 Simplify `get_backend()` in `agent_fox/session/backends/__init__.py`
    - Remove `name` parameter
    - Return `ClaudeBackend()` directly
    - Update docstring to explain Claude-only commitment
    - _Requirements: 55-REQ-2.1, 55-REQ-2.2_

  - [x] 2.2 Update all call sites that pass name to `get_backend()`
    - Search `agent_fox/` for `get_backend("claude")` or `get_backend(name=`
    - Update to `get_backend()` (no args)
    - _Requirements: 55-REQ-2.3, 55-REQ-2.E1_

  - [x] 2.3 Update `AgentBackend` protocol docstring
    - Add note that `ClaudeBackend` is the only production implementation
    - State the protocol exists for test mock injection
    - _Requirements: 55-REQ-3.1, 55-REQ-3.2_

  - [x] 2.4 Create ADR
    - Determine next ADR number from existing `docs/adr/` files
    - Create `docs/adr/NN-use-claude-exclusively.md`
    - Include: Status, Context, Decision, Alternatives (OpenAI, Gemini, multi-provider), Consequences, Future (non-coding use)
    - _Requirements: 55-REQ-1.1, 55-REQ-1.2, 55-REQ-1.3, 55-REQ-1.E1_

  - [x] 2.5 Update README.md
    - Add a statement in the overview that agent-fox is built exclusively for Claude
    - _Requirements: 55-REQ-5.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/test_claude_only.py tests/property/test_claude_only_props.py tests/integration/test_claude_only_integration.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [x] Requirements 55-REQ-1.1 through 55-REQ-5.2 acceptance criteria met

- [x] 3. Checkpoint — Claude-Only Commitment Complete
  - Ensure all tests pass, verify documentation is coherent.
  - Verify ADR is properly numbered and formatted.
  - Verify README statement reads naturally.

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 55-REQ-1.1 | TS-55-1 | 2.4 | test_claude_only_integration.py::test_adr_exists |
| 55-REQ-1.2 | TS-55-2 | 2.4 | test_claude_only.py::test_adr_alternatives |
| 55-REQ-1.3 | TS-55-3 | 2.4 | test_claude_only.py::test_adr_non_coding |
| 55-REQ-1.E1 | TS-55-E1 | 2.4 | test_claude_only.py::test_adr_number_unique |
| 55-REQ-2.1 | TS-55-4, TS-55-P1 | 2.1 | test_claude_only.py::test_get_backend_returns_claude |
| 55-REQ-2.2 | TS-55-5, TS-55-P2 | 2.1 | test_claude_only.py::test_get_backend_no_params |
| 55-REQ-2.3 | TS-55-6 | 2.2 | test_claude_only_integration.py::test_no_name_arg_calls |
| 55-REQ-2.E1 | TS-55-6 | 2.2 | test_claude_only_integration.py::test_no_name_arg_calls |
| 55-REQ-3.1 | TS-55-7, TS-55-P1, TS-55-P3 | 2.3 | test_claude_only.py::test_protocol_exported |
| 55-REQ-3.2 | TS-55-8 | 2.3 | test_claude_only.py::test_protocol_docstring |
| 55-REQ-3.E1 | TS-55-E2, TS-55-P3 | 2.3 | test_claude_only.py::test_mock_satisfies_protocol |
| 55-REQ-4.1 | — | — (no change) | test_claude_only.py::test_get_backend_returns_claude |
| 55-REQ-4.2 | — | — (no change) | — |
| 55-REQ-5.1 | TS-55-9 | 2.5 | test_claude_only_integration.py::test_readme_claude |
