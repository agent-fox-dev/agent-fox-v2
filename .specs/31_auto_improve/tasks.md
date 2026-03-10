# Implementation Plan: Auto-Improve

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec extends `agent-fox fix` with a `--auto` flag that adds an iterative
improvement phase (Phase 2) after the existing repair loop (Phase 1). Task
groups are ordered: tests first, then analyzer module, then improve loop, then
report + CLI integration.

## Test Commands

- Unit tests: `uv run pytest tests/unit/fix/ -q -k "improve or analyzer or combined"`
- Property tests: `uv run pytest tests/unit/fix/ -q -k "prop"`
- All fix tests: `uv run pytest tests/unit/fix/ -q`
- Linter: `uv run ruff check agent_fox/fix/ agent_fox/cli/fix.py`
- Type check: `uv run mypy agent_fox/fix/ agent_fox/cli/fix.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures for auto-improve
    - Extend `tests/unit/fix/conftest.py` with new fixtures:
      `sample_improvement` (Improvement dataclass with defaults),
      `sample_analyzer_result` (AnalyzerResult with 2 improvements),
      `sample_improve_result` (ImproveResult with defaults),
      `valid_analyzer_json` (valid JSON string for analyzer response),
      `valid_verifier_json` (valid JSON string for verifier verdict),
      `mock_improve_session_runner` (async callable returning cost + status)
    - _Fixtures support all test cases below_

  - [x] 1.2 Write analyzer tests
    - `tests/unit/fix/test_analyzer.py`:
      TS-31-6 (prompt includes conventions),
      TS-31-7 (prompt includes oracle context),
      TS-31-8 (prompt omits oracle when unavailable),
      TS-31-9 (parse valid JSON),
      TS-31-10 (parse invalid JSON),
      TS-31-11 (parse missing fields),
      TS-31-12 (filter excludes low confidence),
      TS-31-13 (filter sorts by tier),
      TS-31-29 (oracle context query),
      TS-31-30 (oracle unavailable)
    - _Test Spec: TS-31-6 through TS-31-13, TS-31-29, TS-31-30_

  - [x] 1.3 Write verifier verdict tests
    - `tests/unit/fix/test_improve_verifier.py`:
      TS-31-14 (PASS verdict),
      TS-31-15 (FAIL verdict),
      TS-31-16 (invalid JSON)
    - _Test Spec: TS-31-14, TS-31-15, TS-31-16_

  - [x] 1.4 Write rollback tests
    - `tests/unit/fix/test_rollback.py`:
      TS-31-17 (git reset on FAIL),
      TS-31-18 (rollback failure raises error)
    - _Test Spec: TS-31-17, TS-31-18_

  - [x] 1.5 Write improve loop tests
    - `tests/unit/fix/test_improve_loop.py`:
      TS-31-19 (diminishing returns),
      TS-31-20 (zero actionable improvements),
      TS-31-21 (pass limit),
      TS-31-22 (verifier FAIL + rollback),
      TS-31-23 (cost limit),
      TS-31-24 (analyzer failure),
      TS-31-25 (coder failure)
    - _Test Spec: TS-31-19 through TS-31-25_

  - [x] 1.6 Write report tests
    - `tests/unit/fix/test_improve_report.py`:
      TS-31-26 (combined report),
      TS-31-27 (Phase 2 omitted),
      TS-31-28 (JSON mode)
    - _Test Spec: TS-31-26, TS-31-27, TS-31-28_

  - [x] 1.7 Write CLI tests
    - `tests/unit/fix/test_cli_auto.py`:
      TS-31-1 (--auto enables Phase 2),
      TS-31-2 (Phase 2 skipped when not all-green),
      TS-31-3 (--improve-passes without --auto),
      TS-31-4 (--improve-passes clamped),
      TS-31-5 (--dry-run with --auto)
    - _Test Spec: TS-31-1 through TS-31-5_

  - [x] 1.8 Write property tests
    - `tests/unit/fix/test_improve_loop_props.py`: TS-31-P1 (termination bound)
    - `tests/unit/fix/test_analyzer_props.py`: TS-31-P2 (filtering soundness),
      TS-31-P3 (tier priority ordering)
    - `tests/unit/fix/test_improve_cost_props.py`: TS-31-P4 (cost monotonicity)
    - `tests/unit/fix/test_improve_report_props.py`: TS-31-P5 (report consistency)
    - _Test Spec: TS-31-P1 through TS-31-P5_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/fix/`

- [x] 2. Implement analyzer module
  - [x] 2.1 Implement data models
    - `agent_fox/fix/analyzer.py`: `Improvement` frozen dataclass,
      `AnalyzerResult` dataclass
    - Fields per design.md: id, tier, title, description, files, impact,
      confidence for Improvement; improvements, summary, diminishing_returns,
      raw_response for AnalyzerResult
    - _Requirements: 31-REQ-3.3_

  - [x] 2.2 Implement response parser
    - `agent_fox/fix/analyzer.py`: `parse_analyzer_response()` function
    - Parse JSON, validate required fields (improvements list, summary string,
      diminishing_returns bool)
    - Validate each improvement has required fields (id, tier, title,
      description, files, impact, confidence)
    - Raise ValueError on invalid JSON or missing fields
    - _Requirements: 31-REQ-3.3, 31-REQ-3.E1_

  - [x] 2.3 Implement improvement filter
    - `agent_fox/fix/analyzer.py`: `filter_improvements()` function
    - Exclude items with `confidence == "low"`
    - Sort by tier priority: quick_win (0) < structural (1) < design_level (2)
    - _Requirements: 31-REQ-3.4, 31-REQ-3.5_

  - [x] 2.4 Implement oracle context query
    - `agent_fox/fix/analyzer.py`: `query_oracle_context()` function
    - Create EmbeddingGenerator and VectorSearch from config
    - Instantiate Oracle, call `oracle.ask()` with seed question
    - Format top-k results with provenance as markdown
    - On any error (KnowledgeStoreError, missing DB, embedding failure),
      return empty string and log info
    - _Requirements: 31-REQ-4.1, 31-REQ-4.2, 31-REQ-4.3, 31-REQ-4.E1_

  - [x] 2.5 Implement review context loader
    - `agent_fox/fix/analyzer.py`: `load_review_context()` function
    - Query DuckDB for active skeptic/verifier findings
    - Format as markdown under "## Prior Review Findings"
    - Return empty string if DuckDB unavailable
    - _Requirements: 31-REQ-3.2_

  - [x] 2.6 Implement prompt builder
    - `agent_fox/fix/analyzer.py`: `build_analyzer_prompt()` function
    - Build system prompt: role, guardrails, project conventions (read
      CLAUDE.md/AGENTS.md/README.md), oracle context, review findings
    - Build task prompt: scope (entire repo), file tree, Phase 1 diff,
      previous pass results, JSON format instructions
    - Omit `## Project Knowledge` section when oracle_context is empty
    - _Requirements: 31-REQ-3.1, 31-REQ-3.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/fix/test_analyzer.py -q`
    - [x] Property tests pass: `uv run pytest tests/unit/fix/test_analyzer_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/fix/analyzer.py`
    - [x] Requirements 31-REQ-3.*, 31-REQ-4.* acceptance criteria met

- [x] 3. Implement improve loop and rollback
  - [x] 3.1 Implement verifier verdict parser
    - `agent_fox/fix/improve.py`: verifier verdict parsing
    - Parse JSON with fields: quality_gates, improvement_valid, verdict,
      evidence
    - Raise ValueError on invalid JSON or missing fields
    - _Requirements: 31-REQ-6.2, 31-REQ-6.E2_

  - [x] 3.2 Implement rollback function
    - `agent_fox/fix/improve.py`: `rollback_improvement_pass()` function
    - Run `git reset --hard HEAD~1` via subprocess
    - Log the rollback action with commit hash and reason
    - Raise on non-zero exit from git
    - _Requirements: 31-REQ-7.1, 31-REQ-7.3, 31-REQ-7.E1_

  - [x] 3.3 Implement discard function
    - `agent_fox/fix/improve.py`: `discard_partial_changes()` function
    - Run `git checkout -- .` via subprocess to discard uncommitted changes
    - Log the action; do not raise on failure (best-effort cleanup)
    - _Requirements: 31-REQ-5.E1_

  - [x] 3.4 Implement improve loop data models
    - `agent_fox/fix/improve.py`: `ImproveTermination` enum,
      `ImprovePassResult` dataclass, `ImproveResult` dataclass
    - Fields per design.md
    - _Requirements: 31-REQ-8.2_

  - [x] 3.5 Implement improve loop
    - `agent_fox/fix/improve.py`: `run_improve_loop()` async function
    - For each pass (up to max_passes):
      a. Check cost budget (compare remaining_budget vs estimated pass cost)
      b. Build analyzer prompt (call build_analyzer_prompt with oracle/review
         context)
      c. Run analyzer session, parse response
      d. If diminishing_returns or zero actionable improvements: CONVERGED
      e. Run coder session with filtered plan
      f. Create git commit: `refactor: auto-improve pass {N} - {summary}`
      g. Run verifier session, parse verdict
      h. If PASS: record pass, continue
      i. If FAIL: rollback, terminate with VERIFIER_FAIL
    - Handle analyzer/coder session failures: ANALYZER_ERROR / CODER_ERROR
    - Handle KeyboardInterrupt: INTERRUPTED
    - Track per-pass costs and aggregate into ImproveResult
    - _Requirements: 31-REQ-2.2, 31-REQ-2.3, 31-REQ-5.1, 31-REQ-5.2,
      31-REQ-5.4, 31-REQ-6.1, 31-REQ-6.3, 31-REQ-7.2, 31-REQ-8.1,
      31-REQ-8.3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/fix/test_improve_loop.py tests/unit/fix/test_rollback.py tests/unit/fix/test_improve_verifier.py -q`
    - [x] Property tests pass: `uv run pytest tests/unit/fix/test_improve_loop_props.py tests/unit/fix/test_improve_cost_props.py -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/fix/improve.py`
    - [x] Requirements 31-REQ-5.* through 31-REQ-8.* acceptance criteria met

- [ ] 4. Implement report and CLI integration
  - [ ] 4.1 Implement combined report rendering
    - `agent_fox/fix/improve_report.py`: `render_combined_report()` function
    - Phase 1 section: passes completed, clusters resolved/remaining,
      sessions consumed, termination reason (reuse format from report.py)
    - Phase 2 section (if improve_result is not None): passes completed
      (of max), improvements applied, improvements by tier, verifier
      verdicts, sessions consumed (by role), termination reason
    - Total cost line
    - Omit Phase 2 section entirely when improve_result is None
    - _Requirements: 31-REQ-9.1, 31-REQ-9.2, 31-REQ-9.E1_

  - [ ] 4.2 Implement JSON report builder
    - `agent_fox/fix/improve_report.py`: `build_combined_json()` function
    - Return dict with `event: "complete"` and nested summary with phase1,
      phase2 (if present), and total_cost
    - _Requirements: 31-REQ-9.3_

  - [ ] 4.3 Extend CLI with --auto and --improve-passes
    - `agent_fox/cli/fix.py`: add `--auto` (is_flag, default False) and
      `--improve-passes` (int, default 3) Click options
    - Validate: `--improve-passes` without `--auto` is an error (emit error,
      exit 1)
    - Clamp `--improve-passes` to >= 1 when <= 0, log warning
    - `--dry-run` with `--auto`: log info that Phase 2 is skipped
    - _Requirements: 31-REQ-1.1, 31-REQ-1.2, 31-REQ-1.3, 31-REQ-1.E1,
      31-REQ-1.E2_

  - [ ] 4.4 Wire Phase 2 into fix_cmd
    - After Phase 1 completes:
      a. If not `--auto` or Phase 1 reason != ALL_FIXED: use existing report
      b. If `--auto` and ALL_FIXED:
         - Compute remaining budget: `max_cost - phase1_cost`
         - Capture Phase 1 diff: `git diff HEAD~{phase1_commits}..HEAD`
         - Build improve session runner (wrapping `run_session`)
         - Call `run_improve_loop()`
         - Compute total cost: phase1 + phase2
      c. Use `render_combined_report` or `build_combined_json` for output
      d. Exit 0 if Phase 2 succeeded, 1 if verifier failed
    - _Requirements: 31-REQ-1.4, 31-REQ-2.1, 31-REQ-2.3, 31-REQ-10.1,
      31-REQ-10.2, 31-REQ-10.3_

  - [ ] 4.5 Handle JSON mode for Phase 2
    - Read stdin JSON in json_mode for improve_passes override
    - Emit JSONL events during Phase 2 (pass completion, final summary)
    - Use `build_combined_json` for the complete event
    - _Requirements: 31-REQ-9.3_

  - [ ] 4.V Verify task group 4
    - [ ] All spec tests pass: `uv run pytest tests/unit/fix/ -q -k "improve or analyzer or combined or cli_auto"`
    - [ ] All property tests pass: `uv run pytest tests/unit/fix/ -q -k "prop"`
    - [ ] No linter warnings: `uv run ruff check agent_fox/fix/ agent_fox/cli/fix.py`
    - [ ] Type check passes: `uv run mypy agent_fox/fix/ agent_fox/cli/fix.py`
    - [ ] All requirements 31-REQ-* acceptance criteria met

- [ ] 5. Checkpoint — Auto-Improve Complete
  - [ ] Ensure all new tests pass: `uv run pytest tests/unit/fix/ -q`
  - [ ] Ensure all existing tests pass (no regressions): `uv run pytest tests/ -q`
  - [ ] Ensure linter clean: `uv run ruff check agent_fox/fix/ agent_fox/cli/fix.py tests/unit/fix/`
  - [ ] Ensure type check clean: `uv run mypy agent_fox/fix/`
  - [ ] Verify `agent-fox fix --help` shows --auto and --improve-passes options

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 31-REQ-1.1 | TS-31-1 | 4.3 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-1.2 | TS-31-1 | 4.3 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-1.3 | TS-31-3 | 4.3 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-1.4 | TS-31-2 | 4.4 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-1.E1 | TS-31-4 | 4.3 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-1.E2 | TS-31-5 | 4.3 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-2.1 | TS-31-1, TS-31-2 | 4.4 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-2.2 | — | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-2.3 | TS-31-23 | 3.5, 4.4 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-3.1 | TS-31-6 | 2.6 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.2 | TS-31-6, TS-31-7 | 2.5, 2.6 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.3 | TS-31-9 | 2.1, 2.2 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.4 | TS-31-12 | 2.3 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.5 | TS-31-13 | 2.3 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.E1 | TS-31-10, TS-31-11 | 2.2 | tests/unit/fix/test_analyzer.py |
| 31-REQ-3.E2 | TS-31-24 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-4.1 | TS-31-29 | 2.4 | tests/unit/fix/test_analyzer.py |
| 31-REQ-4.2 | TS-31-29 | 2.4 | tests/unit/fix/test_analyzer.py |
| 31-REQ-4.3 | TS-31-8, TS-31-30 | 2.4, 2.6 | tests/unit/fix/test_analyzer.py |
| 31-REQ-4.E1 | TS-31-30 | 2.4 | tests/unit/fix/test_analyzer.py |
| 31-REQ-5.1 | TS-31-21 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-5.2 | TS-31-21 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-5.3 | TS-31-13 | 2.3 | tests/unit/fix/test_analyzer.py |
| 31-REQ-5.4 | — | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-5.E1 | TS-31-25 | 3.3, 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-6.1 | TS-31-22 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-6.2 | TS-31-14, TS-31-15 | 3.1 | tests/unit/fix/test_improve_verifier.py |
| 31-REQ-6.3 | — | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-6.E1 | TS-31-22 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-6.E2 | TS-31-16 | 3.1 | tests/unit/fix/test_improve_verifier.py |
| 31-REQ-7.1 | TS-31-17, TS-31-22 | 3.2 | tests/unit/fix/test_rollback.py |
| 31-REQ-7.2 | TS-31-22 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-7.3 | TS-31-17 | 3.2 | tests/unit/fix/test_rollback.py |
| 31-REQ-7.E1 | TS-31-18 | 3.2 | tests/unit/fix/test_rollback.py |
| 31-REQ-8.1 | TS-31-19 through TS-31-23 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-8.2 | TS-31-19 | 3.4 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-8.3 | TS-31-23 | 3.5 | tests/unit/fix/test_improve_loop.py |
| 31-REQ-9.1 | TS-31-26 | 4.1 | tests/unit/fix/test_improve_report.py |
| 31-REQ-9.2 | TS-31-26 | 4.1 | tests/unit/fix/test_improve_report.py |
| 31-REQ-9.3 | TS-31-28 | 4.2, 4.5 | tests/unit/fix/test_improve_report.py |
| 31-REQ-9.E1 | TS-31-27 | 4.1 | tests/unit/fix/test_improve_report.py |
| 31-REQ-10.1 | TS-31-1 | 4.4 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-10.2 | TS-31-2, TS-31-22 | 4.4 | tests/unit/fix/test_cli_auto.py |
| 31-REQ-10.3 | — | 4.4 | tests/unit/fix/test_cli_auto.py |
| Property 2 | TS-31-P1 | 3.5 | tests/unit/fix/test_improve_loop_props.py |
| Property 4 | TS-31-P4 | 3.5 | tests/unit/fix/test_improve_cost_props.py |
| Property 5 | TS-31-P2 | 2.3 | tests/unit/fix/test_analyzer_props.py |
| Property 6 | TS-31-P3 | 2.3 | tests/unit/fix/test_analyzer_props.py |
| Property 7 | TS-31-P5 | 4.1 | tests/unit/fix/test_improve_report_props.py |

## Notes

- All session invocations are mocked. The improve loop's integration with
  `run_session` is tested with mock session runners returning predetermined
  outcomes and costs.
- All git commands (commit, reset, checkout, diff) are mocked via
  `unittest.mock.patch` on `subprocess.run`.
- Oracle queries are mocked by patching the `Oracle` class. No API calls
  or DuckDB access in tests.
- Use `tmp_path` pytest fixture for filesystem-dependent tests.
- Use `pytest.mark.asyncio` for async improve loop tests.
- The conftest fixtures extend (not replace) existing fix test fixtures.
- New test files are placed in the existing `tests/unit/fix/` directory.
