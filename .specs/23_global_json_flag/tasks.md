# Implementation Plan: Global --json Flag

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into six groups: (1) write failing tests, (2) build
the JsonOutput helper and global flag infrastructure, (3) remove --format and
YAML support, (4) add JSON output to batch commands, (5) add JSON/JSONL
output to streaming commands + stdin input, (6) checkpoint.

Groups 3 and 4 are the core work — removing the old format system and wiring
JSON into each command. Group 5 handles the more complex streaming and stdin
cases.

## Test Commands

- Unit tests: `uv run pytest tests/unit/cli/test_json_io.py -q`
- Integration tests: `uv run pytest tests/integration/test_json_flag.py -q`
- Property tests: `uv run pytest tests/property/cli/test_json_props.py -q`
- All spec tests: `uv run pytest tests/unit/cli/test_json_io.py tests/integration/test_json_flag.py tests/property/cli/test_json_props.py -q`
- Full suite: `uv run pytest tests/ -q`
- Linter: `uv run ruff check agent_fox/cli/ agent_fox/reporting/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit tests for JsonOutput helper
    - Create `tests/unit/cli/test_json_io.py`
    - Test `emit()`, `emit_line()`, `emit_error()`, `read_stdin()`
    - _Test Spec: TS-23-19, TS-23-20, TS-23-24_

  - [x] 1.2 Create integration tests for global flag and batch commands
    - Create `tests/integration/test_json_flag.py`
    - Test `--json` on status, standup, lint-spec, plan, patterns, compact,
      ingest, init, reset
    - Test --format removal
    - _Test Spec: TS-23-1 through TS-23-13, TS-23-21 through TS-23-23_

  - [x] 1.3 Create integration tests for streaming commands and errors
    - Test code, ask, fix with --json
    - Test error envelope, exit code preservation
    - _Test Spec: TS-23-14 through TS-23-18_

  - [x] 1.4 Create edge case tests
    - --json + --verbose, stderr logs, empty data, interrupts, stdin errors
    - _Test Spec: TS-23-E1 through TS-23-E8_

  - [x] 1.5 Create property tests
    - Create `tests/property/cli/test_json_props.py`
    - JSON exclusivity, error envelope structure, exit code preservation
    - _Test Spec: TS-23-P1 through TS-23-P4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings: `uv run ruff check tests/`

- [ ] 2. Implement JsonOutput helper and global flag
  - [ ] 2.1 Create `agent_fox/cli/json_io.py`
    - Implement `emit(data)` — JSON object to stdout
    - Implement `emit_line(data)` — compact JSONL to stdout
    - Implement `emit_error(message)` — error envelope to stdout
    - Implement `read_stdin()` — parse JSON from non-TTY stdin
    - _Requirements: 23-REQ-6.1, 23-REQ-7.1, 23-REQ-7.3_

  - [ ] 2.2 Add `--json` flag to `main` group in `app.py`
    - Add `@click.option("--json", "json_mode", is_flag=True)`
    - Store `ctx.obj["json"] = json_mode`
    - Suppress banner when `json_mode` is True
    - _Requirements: 23-REQ-1.1, 23-REQ-1.2, 23-REQ-2.1_

  - [ ] 2.3 Modify `BannerGroup.invoke` for JSON error handling
    - Catch exceptions, emit error envelope when `ctx.obj.get("json")`
    - Preserve exit codes
    - _Requirements: 23-REQ-6.1, 23-REQ-6.2, 23-REQ-6.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Unit tests for json_io pass: `uv run pytest tests/unit/cli/test_json_io.py -q`
    - [ ] Global flag integration tests pass: `uv run pytest tests/integration/test_json_flag.py -k "global" -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/cli/json_io.py agent_fox/cli/app.py`
    - [ ] Requirements 23-REQ-1.*, 23-REQ-2.*, 23-REQ-6.*, 23-REQ-7.* met

- [ ] 3. Remove --format and YAML support
  - [ ] 3.1 Remove `--format` from `status` command
    - Remove Click option, use `ctx.obj["json"]` to branch
    - Emit JSON via `json_io.emit()` when active
    - _Requirements: 23-REQ-8.1, 23-REQ-3.1_

  - [ ] 3.2 Remove `--format` from `standup` command
    - Same pattern as status
    - _Requirements: 23-REQ-8.2, 23-REQ-3.2_

  - [ ] 3.3 Remove `--format` from `lint-spec` command
    - Replace `output_format` parameter with `ctx.obj["json"]` check
    - Remove `format_yaml()` function
    - _Requirements: 23-REQ-8.3, 23-REQ-3.3_

  - [ ] 3.4 Clean up formatters module
    - Remove `OutputFormat.YAML` from enum
    - Remove YAML formatter class and imports
    - Update `get_formatter()` to only handle TABLE and JSON
    - _Requirements: 23-REQ-8.4, 23-REQ-8.5_

  - [ ] 3.5 Update existing tests
    - Update `tests/unit/reporting/` and `tests/integration/test_lint_spec.py`
      that reference `--format` or YAML
    - _Requirements: 23-REQ-8.E1_

  - [ ] 3.V Verify task group 3
    - [ ] --format removal tests pass: `uv run pytest tests/integration/test_json_flag.py -k "format_removed" -q`
    - [ ] All existing tests still pass: `uv run pytest tests/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/cli/ agent_fox/reporting/`
    - [ ] Requirements 23-REQ-8.* met

- [ ] 4. Add JSON output to batch commands
  - [ ] 4.1 Add JSON output to `plan` command
    - Serialize TaskGraph/plan data as JSON when `ctx.obj["json"]`
    - _Requirements: 23-REQ-3.4_

  - [ ] 4.2 Add JSON output to `patterns` command
    - Serialize pattern results as JSON
    - _Requirements: 23-REQ-3.5_

  - [ ] 4.3 Add JSON output to `compact` and `ingest` commands
    - Serialize compaction/ingestion stats as JSON
    - _Requirements: 23-REQ-3.6, 23-REQ-3.7_

  - [ ] 4.4 Add JSON output to `init` and `reset` commands
    - Emit `{"status": "ok"}` for init, summary dict for reset
    - _Requirements: 23-REQ-4.1, 23-REQ-4.2_

  - [ ] 4.V Verify task group 4
    - [ ] Batch command tests pass: `uv run pytest tests/integration/test_json_flag.py -k "batch" -q`
    - [ ] All existing tests still pass: `uv run pytest tests/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/cli/`
    - [ ] Requirements 23-REQ-3.*, 23-REQ-4.* met

- [ ] 5. Add JSONL output for streaming commands and stdin input
  - [ ] 5.1 Add JSONL output to `code` command
    - Emit progress events as JSONL via `json_io.emit_line()`
    - Handle SIGINT with final `{"status": "interrupted"}`
    - _Requirements: 23-REQ-5.1, 23-REQ-5.E1_

  - [ ] 5.2 Add JSON output to `ask` command
    - Emit answer + sources as JSON object
    - Accept `{"question": "..."}` from stdin
    - _Requirements: 23-REQ-5.2, 23-REQ-7.2_

  - [ ] 5.3 Add JSONL output to `fix` command
    - Emit progress events as JSONL
    - Handle SIGINT with final status
    - _Requirements: 23-REQ-5.3_

  - [ ] 5.4 Wire stdin JSON input into commands
    - Call `read_stdin()` in each command when JSON mode active
    - Merge stdin fields with CLI params (CLI takes precedence)
    - _Requirements: 23-REQ-7.1, 23-REQ-7.2, 23-REQ-7.E1, 23-REQ-7.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Streaming tests pass: `uv run pytest tests/integration/test_json_flag.py -k "streaming" -q`
    - [ ] All existing tests still pass: `uv run pytest tests/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/cli/`
    - [ ] Requirements 23-REQ-5.*, 23-REQ-7.* met

- [ ] 6. Checkpoint — Global JSON Flag Complete
  - Ensure all tests pass: `uv run pytest tests/ -q`
  - All lints clean: `uv run ruff check agent_fox/ tests/`
  - Type check clean: `uv run mypy agent_fox/cli/`
  - Update `docs/cli-reference.md` with `--json` documentation

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 23-REQ-1.1 | TS-23-1 | 2.2 | `test_json_flag.py::test_global_flag_accepted` |
| 23-REQ-1.2 | TS-23-1 | 2.2 | `test_json_flag.py::test_flag_in_ctx_obj` |
| 23-REQ-1.3 | TS-23-2 | 2.2 | `test_json_flag.py::test_default_mode_unchanged` |
| 23-REQ-1.E1 | TS-23-E1 | 2.2 | `test_json_flag.py::test_json_with_verbose` |
| 23-REQ-2.1 | TS-23-3 | 2.2 | `test_json_flag.py::test_banner_suppressed` |
| 23-REQ-2.2 | TS-23-4 | 2.2 | `test_json_flag.py::test_no_non_json_stdout` |
| 23-REQ-2.E1 | TS-23-E2 | 2.2 | `test_json_flag.py::test_logs_to_stderr` |
| 23-REQ-3.1 | TS-23-5 | 3.1 | `test_json_flag.py::test_status_json` |
| 23-REQ-3.2 | TS-23-6 | 3.2 | `test_json_flag.py::test_standup_json` |
| 23-REQ-3.3 | TS-23-7 | 3.3 | `test_json_flag.py::test_lint_spec_json` |
| 23-REQ-3.4 | TS-23-8 | 4.1 | `test_json_flag.py::test_plan_json` |
| 23-REQ-3.5 | TS-23-9 | 4.2 | `test_json_flag.py::test_patterns_json` |
| 23-REQ-3.6 | TS-23-10 | 4.3 | `test_json_flag.py::test_compact_json` |
| 23-REQ-3.7 | TS-23-11 | 4.3 | `test_json_flag.py::test_ingest_json` |
| 23-REQ-3.E1 | TS-23-E3 | 4.1 | `test_json_flag.py::test_empty_data_valid_json` |
| 23-REQ-4.1 | TS-23-12 | 4.4 | `test_json_flag.py::test_init_json` |
| 23-REQ-4.2 | TS-23-13 | 4.4 | `test_json_flag.py::test_reset_json` |
| 23-REQ-5.1 | TS-23-14 | 5.1 | `test_json_flag.py::test_code_jsonl` |
| 23-REQ-5.2 | TS-23-15 | 5.2 | `test_json_flag.py::test_ask_json` |
| 23-REQ-5.3 | TS-23-16 | 5.3 | `test_json_flag.py::test_fix_jsonl` |
| 23-REQ-5.E1 | TS-23-E4 | 5.1 | `test_json_flag.py::test_streaming_interrupted` |
| 23-REQ-6.1 | TS-23-17 | 2.3 | `test_json_flag.py::test_error_envelope` |
| 23-REQ-6.2 | TS-23-18 | 2.3 | `test_json_flag.py::test_exit_code_preserved` |
| 23-REQ-6.3 | TS-23-17 | 2.3 | `test_json_flag.py::test_no_text_on_error` |
| 23-REQ-6.E1 | TS-23-E5 | 2.3 | `test_json_flag.py::test_unhandled_exception_envelope` |
| 23-REQ-7.1 | TS-23-19 | 5.4 | `test_json_io.py::test_read_stdin_json` |
| 23-REQ-7.2 | TS-23-19 | 5.4 | `test_json_io.py::test_stdin_parsed` |
| 23-REQ-7.3 | TS-23-20 | 2.1 | `test_json_io.py::test_stdin_tty_no_block` |
| 23-REQ-7.E1 | TS-23-E6 | 5.4 | `test_json_io.py::test_invalid_stdin_json` |
| 23-REQ-7.E2 | TS-23-E7 | 5.4 | `test_json_io.py::test_unknown_fields_ignored` |
| 23-REQ-8.1 | TS-23-21 | 3.1 | `test_json_flag.py::test_format_removed_status` |
| 23-REQ-8.2 | TS-23-22 | 3.2 | `test_json_flag.py::test_format_removed_standup` |
| 23-REQ-8.3 | TS-23-23 | 3.3 | `test_json_flag.py::test_format_removed_lint_spec` |
| 23-REQ-8.4 | TS-23-24 | 3.4 | `test_json_io.py::test_yaml_removed_from_enum` |
| 23-REQ-8.5 | TS-23-24 | 3.4 | `test_json_io.py::test_yaml_formatter_removed` |
| 23-REQ-8.E1 | TS-23-E8 | 3.5 | `test_json_flag.py::test_format_usage_error` |
| Property 1 | TS-23-P1 | 4.* | `test_json_props.py::test_json_exclusivity` |
| Property 2 | TS-23-P2 | 2.3 | `test_json_props.py::test_error_envelope_structure` |
| Property 3 | TS-23-P3 | 2.3 | `test_json_props.py::test_exit_code_preservation` |
| Property 4 | TS-23-P4 | 5.4 | `test_json_props.py::test_flag_precedence` |

## Notes

- All integration tests use Click's `CliRunner` with mocked dependencies.
- The `--format` removal is a breaking change — document in release notes.
- JSONL streaming tests need careful mocking of async event emission.
- The `json_io.py` module is deliberately small and stateless — no classes.
