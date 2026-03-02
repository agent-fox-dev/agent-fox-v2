# Implementation Plan: Error Auto-Fix

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the `agent-fox fix` command: an iterative auto-fix loop
that detects quality checks, runs them, clusters failures by root cause,
generates fix specifications, runs coding sessions, and iterates. Task groups
are ordered: tests first, then detector+collector, then clusterer, then
spec_gen+loop, then report+CLI.

## Test Commands

- Unit tests: `uv run pytest tests/unit/fix/ -q`
- Property tests: `uv run pytest tests/unit/fix/ -q -k "property or prop"`
- All tests: `uv run pytest tests/unit/fix/ -q`
- Linter: `uv run ruff check agent_fox/fix/`
- Type check: `uv run mypy agent_fox/fix/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test directory and conftest
    - Create `tests/unit/fix/__init__.py`
    - Create `tests/unit/fix/conftest.py` with shared fixtures:
      `tmp_project` (temp dir with config files), `check_descriptor_pytest`,
      `ruff_check_descriptor`, `sample_failure_record`,
      `sample_failure_cluster`, `mock_config` (AgentFoxConfig with defaults)
    - _Fixtures support all test cases below_

  - [x] 1.2 Write detector tests
    - `tests/unit/fix/test_detector.py`: TS-08-1 (pytest detection),
      TS-08-2 (ruff+mypy detection), TS-08-3 (npm test+lint detection),
      TS-08-4 (make test detection), TS-08-5 (cargo test detection)
    - _Test Spec: TS-08-1, TS-08-2, TS-08-3, TS-08-4, TS-08-5_

  - [x] 1.3 Write collector tests
    - `tests/unit/fix/test_collector.py`: TS-08-6 (failure capture),
      TS-08-7 (all passing)
    - _Test Spec: TS-08-6, TS-08-7_

  - [x] 1.4 Write clusterer tests
    - `tests/unit/fix/test_clusterer.py`: TS-08-8 (fallback clustering),
      TS-08-9 (AI clustering)
    - _Test Spec: TS-08-8, TS-08-9_

  - [x] 1.5 Write spec generator tests
    - `tests/unit/fix/test_spec_gen.py`: TS-08-10 (spec generation)
    - _Test Spec: TS-08-10_

  - [x] 1.6 Write loop tests
    - `tests/unit/fix/test_loop.py`: TS-08-11 (all fixed termination),
      TS-08-12 (max passes termination)
    - _Test Spec: TS-08-11, TS-08-12_

  - [x] 1.7 Write report tests
    - `tests/unit/fix/test_report.py`: TS-08-13 (report rendering)
    - _Test Spec: TS-08-13_

  - [x] 1.8 Write edge case tests
    - `tests/unit/fix/test_detector.py`: TS-08-E1 (no checks), TS-08-E2
      (unparseable config)
    - `tests/unit/fix/test_collector.py`: TS-08-E3 (timeout)
    - `tests/unit/fix/test_clusterer.py`: TS-08-E4 (unparseable AI response)
    - `tests/unit/fix/test_spec_gen.py`: TS-08-E6 (cleanup)
    - `tests/unit/fix/test_loop.py`: TS-08-E5 (max_passes clamping)
    - _Test Spec: TS-08-E1, TS-08-E2, TS-08-E3, TS-08-E4, TS-08-E5, TS-08-E6_

  - [x] 1.9 Write property tests
    - `tests/unit/fix/test_detector_props.py`: TS-08-P1 (detection
      determinism)
    - `tests/unit/fix/test_collector_props.py`: TS-08-P2 (collector
      completeness)
    - `tests/unit/fix/test_clusterer_props.py`: TS-08-P3 (cluster coverage)
    - `tests/unit/fix/test_loop_props.py`: TS-08-P4 (loop termination)
    - `tests/unit/fix/test_report_props.py`: TS-08-P5 (report consistency)
    - _Test Spec: TS-08-P1, TS-08-P2, TS-08-P3, TS-08-P4, TS-08-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/fix/`

- [ ] 2. Implement detector and collector
  - [ ] 2.1 Create fix package
    - `agent_fox/fix/__init__.py`: package init
    - Export public types: `CheckDescriptor`, `CheckCategory`,
      `FailureRecord`

  - [ ] 2.2 Implement detector
    - `agent_fox/fix/detector.py`: `CheckCategory` enum, `CheckDescriptor`
      dataclass, `detect_checks()` function
    - Implement `_inspect_pyproject()`: parse with `tomllib`, check for
      `[tool.pytest]`, `[tool.pytest.ini_options]`, `[tool.ruff]`,
      `[tool.mypy]` sections
    - Implement `_inspect_package_json()`: parse with `json`, check for
      `scripts.test`, `scripts.lint`
    - Implement `_inspect_makefile()`: scan for lines matching `^test:` regex
    - Implement `_inspect_cargo_toml()`: parse with `tomllib`, check for
      `[package]` section
    - Handle parse errors: log warning, return empty list for that file
    - _Requirements: 08-REQ-1.1, 08-REQ-1.2, 08-REQ-1.3, 08-REQ-1.E2_

  - [ ] 2.3 Implement collector
    - `agent_fox/fix/collector.py`: `FailureRecord` dataclass, `run_checks()`
      function
    - Run each check via `subprocess.run()` with `capture_output=True`,
      `text=True`, `timeout=300`, `cwd=project_root`
    - Handle `subprocess.TimeoutExpired`: create FailureRecord with timeout
      message
    - Partition results into failures (exit != 0) and passed (exit == 0)
    - _Requirements: 08-REQ-2.1, 08-REQ-2.2, 08-REQ-2.3, 08-REQ-2.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/fix/test_detector.py tests/unit/fix/test_collector.py -q`
    - [ ] Property tests pass: `uv run pytest tests/unit/fix/test_detector_props.py tests/unit/fix/test_collector_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/fix/detector.py agent_fox/fix/collector.py`
    - [ ] Requirements 08-REQ-1.*, 08-REQ-2.* acceptance criteria met

- [ ] 3. Implement clusterer
  - [ ] 3.1 Implement fallback clustering
    - `agent_fox/fix/clusterer.py`: `FailureCluster` dataclass,
      `_fallback_cluster()` function
    - Group failures by `check.name`, use check name as cluster label
    - Set `suggested_approach` to a generic message per check category
    - _Requirements: 08-REQ-3.3_

  - [ ] 3.2 Implement AI clustering
    - `agent_fox/fix/clusterer.py`: `_ai_cluster()` function
    - Build prompt with numbered failure outputs (truncated to reasonable
      length, e.g., 2000 chars per failure)
    - Call STANDARD model via Anthropic SDK
    - Parse JSON response into FailureCluster objects
    - Validate response: all failure indices present, no duplicates
    - On any error (API, parse, validation), fall back to
      `_fallback_cluster()`
    - _Requirements: 08-REQ-3.1, 08-REQ-3.2_

  - [ ] 3.3 Implement cluster_failures entry point
    - `agent_fox/fix/clusterer.py`: `cluster_failures()` function
    - Try `_ai_cluster()` first, catch exceptions, fall back to
      `_fallback_cluster()`
    - _Requirements: 08-REQ-3.1, 08-REQ-3.3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/fix/test_clusterer.py -q`
    - [ ] Property tests pass: `uv run pytest tests/unit/fix/test_clusterer_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/fix/clusterer.py`
    - [ ] Requirements 08-REQ-3.* acceptance criteria met

- [ ] 4. Implement spec generator and fix loop
  - [ ] 4.1 Implement spec generator
    - `agent_fox/fix/spec_gen.py`: `FixSpec` dataclass,
      `generate_fix_spec()` function, `cleanup_fix_specs()` function
    - Sanitize cluster label for filesystem-safe directory name
    - Write requirements.md: describe what is broken (include failure output)
    - Write design.md: suggested approach from cluster
    - Write tasks.md: single task group with fix instructions
    - Assemble task_prompt: combine all fix context into a session prompt
    - cleanup_fix_specs: `shutil.rmtree()` on output_dir contents
    - _Requirements: 08-REQ-4.1, 08-REQ-4.2_

  - [ ] 4.2 Implement fix loop
    - `agent_fox/fix/loop.py`: `TerminationReason` enum, `FixResult`
      dataclass, `run_fix_loop()` async function
    - Step 1: call `detect_checks()`, error if empty (08-REQ-1.E1)
    - Step 2: loop up to max_passes (clamp to >= 1):
      a. `run_checks()` to collect failures
      b. If no failures, set reason ALL_FIXED and break
      c. `cluster_failures()` to group failures
      d. `generate_fix_spec()` for each cluster
      e. Run a coding session for each cluster via SessionRunner
      f. Increment sessions_consumed, track cost
      g. Check cost limit, break if exceeded
    - Step 3: final `run_checks()` to determine resolution counts
    - Handle KeyboardInterrupt: set reason INTERRUPTED
    - Clean up fix specs after loop
    - _Requirements: 08-REQ-5.1, 08-REQ-5.2, 08-REQ-5.3, 08-REQ-7.E1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/fix/test_spec_gen.py tests/unit/fix/test_loop.py -q`
    - [ ] Property tests pass: `uv run pytest tests/unit/fix/test_loop_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/fix/spec_gen.py agent_fox/fix/loop.py`
    - [ ] Requirements 08-REQ-4.*, 08-REQ-5.* acceptance criteria met

- [ ] 5. Implement report and CLI command
  - [ ] 5.1 Implement fix report
    - `agent_fox/fix/report.py`: `render_fix_report()` function
    - Use Rich Table to display: passes completed, clusters resolved,
      clusters remaining, sessions consumed, termination reason
    - If failures remain, list a summary of each remaining failure
    - Color-code termination reason: green for ALL_FIXED, yellow for
      MAX_PASSES, red for COST_LIMIT or INTERRUPTED
    - _Requirements: 08-REQ-6.1, 08-REQ-6.2_

  - [ ] 5.2 Implement CLI command
    - `agent_fox/cli/fix.py`: `fix_cmd` Click command
    - Accept `--max-passes` option (int, default 3)
    - Load config from Click context
    - Call `run_fix_loop()` via `asyncio.run()`
    - Call `render_fix_report()` with result
    - Exit with code 0 if ALL_FIXED, code 1 otherwise
    - Handle empty detect_checks: print error, exit 1
    - _Requirements: 08-REQ-7.1, 08-REQ-7.2, 08-REQ-7.E1_

  - [ ] 5.3 Register CLI command
    - Add `from agent_fox.cli.fix import fix_cmd` to `agent_fox/cli/app.py`
    - Register `main.add_command(fix_cmd)` so `agent-fox fix` is available
    - Verify `agent-fox --help` lists "fix"

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/fix/ -q`
    - [ ] All property tests pass: `uv run pytest tests/unit/fix/ -q -k "prop"`
    - [ ] No linter warnings: `uv run ruff check agent_fox/fix/ agent_fox/cli/fix.py`
    - [ ] Type check passes: `uv run mypy agent_fox/fix/ agent_fox/cli/fix.py`
    - [ ] CLI is invocable: `uv run agent-fox --help` lists "fix"
    - [ ] All requirements 08-REQ-* acceptance criteria met

- [ ] 6. Checkpoint -- Error Auto-Fix Complete
  - Ensure all tests pass: `uv run pytest tests/unit/fix/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/fix/ agent_fox/cli/fix.py tests/unit/fix/`
  - Ensure type check clean: `uv run mypy agent_fox/fix/`
  - Verify no regressions: `uv run pytest tests/ -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 08-REQ-1.1 | TS-08-1 | 2.2 | tests/unit/fix/test_detector.py |
| 08-REQ-1.2 | TS-08-1, TS-08-2, TS-08-3, TS-08-4, TS-08-5 | 2.2 | tests/unit/fix/test_detector.py |
| 08-REQ-1.3 | TS-08-2 | 2.2 | tests/unit/fix/test_detector.py |
| 08-REQ-1.E1 | TS-08-E1 | 4.2, 5.2 | tests/unit/fix/test_detector.py |
| 08-REQ-1.E2 | TS-08-E2 | 2.2 | tests/unit/fix/test_detector.py |
| 08-REQ-2.1 | TS-08-6 | 2.3 | tests/unit/fix/test_collector.py |
| 08-REQ-2.2 | TS-08-6 | 2.3 | tests/unit/fix/test_collector.py |
| 08-REQ-2.3 | TS-08-7 | 2.3 | tests/unit/fix/test_collector.py |
| 08-REQ-2.E1 | TS-08-E3 | 2.3 | tests/unit/fix/test_collector.py |
| 08-REQ-3.1 | TS-08-9 | 3.2, 3.3 | tests/unit/fix/test_clusterer.py |
| 08-REQ-3.2 | TS-08-9 | 3.2 | tests/unit/fix/test_clusterer.py |
| 08-REQ-3.3 | TS-08-8 | 3.1, 3.3 | tests/unit/fix/test_clusterer.py |
| 08-REQ-4.1 | TS-08-10 | 4.1 | tests/unit/fix/test_spec_gen.py |
| 08-REQ-4.2 | TS-08-10, TS-08-E6 | 4.1 | tests/unit/fix/test_spec_gen.py |
| 08-REQ-5.1 | TS-08-11, TS-08-12 | 4.2 | tests/unit/fix/test_loop.py |
| 08-REQ-5.2 | TS-08-11, TS-08-12 | 4.2 | tests/unit/fix/test_loop.py |
| 08-REQ-5.3 | TS-08-11 | 4.2 | tests/unit/fix/test_loop.py |
| 08-REQ-6.1 | TS-08-13 | 5.1 | tests/unit/fix/test_report.py |
| 08-REQ-6.2 | TS-08-13 | 5.1 | tests/unit/fix/test_report.py |
| 08-REQ-7.1 | TS-08-E1 (CLI) | 5.2, 5.3 | tests/unit/fix/test_detector.py |
| 08-REQ-7.2 | TS-08-E5 | 5.2 | tests/unit/fix/test_loop.py |
| 08-REQ-7.E1 | TS-08-E5 | 4.2, 5.2 | tests/unit/fix/test_loop.py |
| Property 1 | TS-08-P1 | 2.2 | tests/unit/fix/test_detector_props.py |
| Property 2 | TS-08-P2 | 2.3 | tests/unit/fix/test_collector_props.py |
| Property 3 | TS-08-P3 | 3.1 | tests/unit/fix/test_clusterer_props.py |
| Property 4 | TS-08-P4 | 4.2 | tests/unit/fix/test_loop_props.py |
| Property 5 | TS-08-P5 | 5.1 | tests/unit/fix/test_report_props.py |

## Notes

- All subprocess calls in tests are mocked via `unittest.mock.patch` on
  `subprocess.run`. No real processes are spawned during testing.
- All AI model calls in tests are mocked via `unittest.mock.patch` on the
  Anthropic client. No API calls are made during testing.
- The fix loop's integration with SessionRunner is tested with a mock
  SessionRunner that returns predetermined outcomes.
- Use `tmp_path` pytest fixture for all filesystem-dependent tests.
- Use `pytest.mark.asyncio` for async loop tests.
- The `conftest.py` should provide reusable fixtures for check descriptors,
  failure records, and clusters to reduce boilerplate across test files.
