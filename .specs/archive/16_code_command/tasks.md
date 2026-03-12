# Implementation Plan: Code Command

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements a single CLI module (`agent_fox/cli/code.py`) that wires
the existing orchestrator engine to a Click command. Task group 1 writes
failing tests, task group 2 implements the command and makes all tests pass.

## Test Commands

- Unit tests: `.venv/bin/python -m pytest tests/unit/cli/test_code.py -q`
- Property tests: `.venv/bin/python -m pytest tests/property/cli/test_code_props.py -q`
- All code command tests: `.venv/bin/python -m pytest tests/unit/cli/test_code.py tests/property/cli/test_code_props.py -q`
- Linter: `.venv/bin/python -m ruff check agent_fox/cli/code.py`
- Type check: `.venv/bin/python -m mypy agent_fox/cli/code.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory structure
    - Create `tests/unit/cli/test_code.py` with shared fixtures:
      mock orchestrator, mock config, mock plan file, CliRunner
    - Create `tests/property/cli/test_code_props.py`
    - _Test Spec: TS-16-1 through TS-16-8_

  - [x] 1.2 Write command registration and invocation tests
    - TS-16-1: Command is registered and help is accessible
    - TS-16-2: Successful execution prints summary and exits 0
    - _Test Spec: TS-16-1, TS-16-2_

  - [x] 1.3 Write CLI option override tests
    - TS-16-3: --parallel override applied
    - TS-16-4: --max-cost override applied
    - TS-16-5: --max-sessions override applied
    - _Test Spec: TS-16-3, TS-16-4, TS-16-5_

  - [x] 1.4 Write exit code tests
    - TS-16-6: Stalled exits 2
    - TS-16-7: Cost limit exits 3
    - TS-16-8: Interrupted exits 130
    - _Test Spec: TS-16-6, TS-16-7, TS-16-8_

  - [x] 1.5 Write edge case tests
    - TS-16-E1: Missing plan file exits 1
    - TS-16-E2: Unexpected exception exits 1
    - TS-16-E3: Empty plan prints message, exits 0
    - TS-16-E4: Unknown run status exits 1
    - _Test Spec: TS-16-E1, TS-16-E2, TS-16-E3, TS-16-E4_

  - [x] 1.6 Write property tests
    - TS-16-P1: Exit code mapping consistency
    - TS-16-P2: Override preservation
    - _Test Spec: TS-16-P1, TS-16-P2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `.venv/bin/python -m ruff check tests/unit/cli/test_code.py tests/property/cli/test_code_props.py`

- [x] 2. Implement the code command
  - [x] 2.1 Create `agent_fox/cli/code.py`
    - Click command with --parallel, --no-hooks, --max-cost, --max-sessions
    - `_apply_overrides()` helper to merge CLI options into OrchestratorConfig
    - `_exit_code_for_status()` helper for run status → exit code mapping
    - `_print_summary()` helper for compact execution summary
    - Session runner factory construction
    - Orchestrator construction and `asyncio.run()` invocation
    - Error handling: PlanError, AgentFoxError, unexpected exceptions
    - _Requirements: 16-REQ-1.1 through 16-REQ-5.2_

  - [x] 2.2 Register command in `agent_fox/cli/app.py`
    - Import `code_cmd` from `agent_fox.cli.code`
    - Add `main.add_command(code_cmd, name="code")`
    - _Requirements: 16-REQ-1.1_

  - [x] 2.V Verify task group 2
    - [x] All unit tests pass: `.venv/bin/python -m pytest tests/unit/cli/test_code.py -q`
    - [x] All property tests pass: `.venv/bin/python -m pytest tests/property/cli/test_code_props.py -q`
    - [x] All existing tests still pass: `.venv/bin/python -m pytest -q`
    - [x] No linter warnings: `.venv/bin/python -m ruff check agent_fox/cli/code.py`
    - [x] Type check passes: `.venv/bin/python -m mypy agent_fox/cli/code.py`
    - [x] Requirements 16-REQ-1.* through 16-REQ-5.* acceptance criteria met

- [x] 3. Checkpoint — Code Command Complete
  - Ensure all tests pass: `.venv/bin/python -m pytest tests/unit/cli/test_code.py tests/property/cli/test_code_props.py -q`
  - Verify `agent-fox code --help` works
  - Verify `agent-fox code` with a mock/real plan
  - Update checkbox states

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 16-REQ-1.1 | TS-16-1 | 2.1, 2.2 | tests/unit/cli/test_code.py |
| 16-REQ-1.2 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-1.3 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-1.4 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-1.E1 | TS-16-E1 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-1.E2 | TS-16-E2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-2.1 | TS-16-3, TS-16-P2 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-2.2 | TS-16-3 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-2.3 | TS-16-4, TS-16-P2 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-2.4 | TS-16-5, TS-16-P2 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-2.5 | TS-16-3, TS-16-P2 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-2.E1 | TS-16-3 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-3.1 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-3.2 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-3.E1 | TS-16-E3 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-4.1 | TS-16-2, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-4.2 | TS-16-E2, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-4.3 | TS-16-6, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-4.4 | TS-16-7, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-4.5 | TS-16-8, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-4.E1 | TS-16-E4, TS-16-P1 | 2.1 | tests/unit/cli/test_code.py, tests/property/cli/test_code_props.py |
| 16-REQ-5.1 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-5.2 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |
| 16-REQ-5.E1 | TS-16-E2 | 2.1 | tests/unit/cli/test_code.py |
| Property 1 | TS-16-P1 | 2.1 | tests/property/cli/test_code_props.py |
| Property 2 | TS-16-P2 | 2.1 | tests/property/cli/test_code_props.py |
| Property 3 | TS-16-2 | 2.1 | tests/unit/cli/test_code.py |

## Notes

- All tests mock the `Orchestrator` — no real sessions or LLM calls.
- Mock the session runner factory with a no-op callable.
- Use `click.testing.CliRunner` for all CLI tests.
- The `--no-hooks` flag is passed through to the orchestrator config but the
  hook skipping logic itself is in spec 06 — we only test that the flag is
  accepted and forwarded.
