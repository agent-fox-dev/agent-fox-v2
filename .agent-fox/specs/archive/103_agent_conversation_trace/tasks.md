# Implementation Plan: Agent Conversation Trace

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds an `AgentTraceSink` that captures agent–model
conversations to JSONL, replaces the old `JsonlSink`, and wires the new sink
into the session runner. The plan follows test-first development: group 1
writes failing tests, group 2 implements the core sink and truncation helper,
group 3 wires the sink into the session runner and removes the old sink,
and group 4 verifies end-to-end wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_agent_trace.py tests/unit/knowledge/test_agent_trace_removal.py tests/property/knowledge/test_agent_trace_props.py tests/integration/test_agent_trace_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/`
- Integration tests: `uv run pytest -q tests/integration/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file for AgentTraceSink
    - Create `tests/unit/knowledge/test_agent_trace.py`
    - Translate TS-103-1 through TS-103-11 into pytest test functions
    - Tests import `AgentTraceSink` and `truncate_tool_input` from
      `agent_fox.knowledge.agent_trace` (module does not exist yet — tests
      will fail at import)
    - _Test Spec: TS-103-1, TS-103-2, TS-103-3, TS-103-4, TS-103-5,
      TS-103-6, TS-103-7, TS-103-8, TS-103-9, TS-103-10, TS-103-11_

  - [x] 1.2 Create unit test file for JsonlSink removal verification
    - Create `tests/unit/knowledge/test_agent_trace_removal.py`
    - Translate TS-103-12 and TS-103-13 into pytest tests
    - TS-103-12: assert `agent_fox/knowledge/jsonl_sink.py` does not exist
    - TS-103-13: grep source tree for `jsonl_sink` imports (must be zero)
    - These tests will PASS prematurely if run now (file still exists), so
      write them to assert the file DOES exist for now — they'll be inverted
      in group 3
    - _Test Spec: TS-103-12, TS-103-13_

  - [x] 1.3 Create unit test for audit retention preservation
    - Add test to `tests/unit/knowledge/test_agent_trace.py` (or a separate
      file if preferred)
    - Translate TS-103-14: set up DuckDB with two runs, create both
      `audit_*.jsonl` and `agent_*.jsonl` files, run retention with
      `max_runs=1`, assert agent files survive
    - _Test Spec: TS-103-14_

  - [x] 1.4 Create property tests
    - Create `tests/property/knowledge/test_agent_trace_props.py`
    - Translate TS-103-P1 (event completeness), TS-103-P2 (truncation
      invariants), TS-103-P3 (file location)
    - Use Hypothesis strategies for dict generation and sequence generation
    - _Test Spec: TS-103-P1, TS-103-P2, TS-103-P3_

  - [x] 1.5 Create integration smoke tests
    - Create `tests/integration/test_agent_trace_smoke.py`
    - Translate TS-103-SMOKE-1: mock backend yielding a sequence of canonical
      messages, real `AgentTraceSink`, real `_execute_query`, verify trace
      file contents
    - Translate TS-103-SMOKE-2: verify no legacy `.agent-fox/*.jsonl` files
      are created
    - _Test Spec: TS-103-SMOKE-1, TS-103-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Implement AgentTraceSink and truncate_tool_input
  - [x] 2.1 Create `agent_fox/knowledge/agent_trace.py`
    - Implement `truncate_tool_input(tool_input, max_len=10_000)` helper
    - Implement `AgentTraceSink` class satisfying the `SessionSink` protocol
    - Methods: `record_session_init`, `record_assistant_message`,
      `record_tool_use`, `record_tool_error_trace`, `record_session_result`
    - Protocol no-ops: `record_session_outcome`, `record_tool_call`,
      `record_tool_error`, `emit_audit_event`
    - `close()`: flush and close file handle
    - All writes wrapped in try/except with warning log (103-REQ-1.E2)
    - Directory creation on first write (103-REQ-1.E1)
    - _Requirements: 1.1, 1.2, 1.3, 1.E1, 1.E2, 2.1, 2.2, 3.1, 3.2,
      4.1, 4.2, 4.3, 4.E1, 5.1, 6.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_agent_trace.py`
    - [x] Property tests pass: `uv run pytest -q tests/property/knowledge/test_agent_trace_props.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 1.*, 2.*, 3.*, 4.*, 5.*, 6.* acceptance criteria met

- [x] 3. Wire sink into session runner, remove old JsonlSink
  - [x] 3.1 Modify `agent_fox/session/session.py` — emit trace events
    - In `_execute_query`: emit `session.init` event before the backend
      message stream loop (requires passing `AgentTraceSink` or using
      the `SinkDispatcher` with a new method)
    - In the message loop: emit `assistant.message` for `AssistantMessage`,
      `tool.use` for `ToolUseMessage`, `session.result` for `ResultMessage`
    - For `tool.error`: emit when `is_error=True` and `last_tool_name` is set
    - Design decision: add trace-specific methods to `SinkDispatcher` that
      delegate to any registered `AgentTraceSink` (duck-typed — check for
      method existence with `hasattr`)
    - _Requirements: 2.1, 3.1, 4.1, 5.1, 6.1_

  - [x] 3.2 Modify `agent_fox/engine/run.py` — replace JsonlSink with AgentTraceSink
    - In `_setup_infrastructure`: when `debug=True`, create
      `AgentTraceSink(AUDIT_DIR, "")` instead of `JsonlSink`
    - The `run_id` is not yet known at setup time — the sink will receive
      it via method calls (run_id is a parameter on each record method)
    - Remove the `JsonlSink` import
    - _Requirements: 1.1, 7.2_

  - [x] 3.3 Delete `agent_fox/knowledge/jsonl_sink.py`
    - Remove the module entirely
    - _Requirements: 7.1_

  - [x] 3.4 Update all remaining imports of `JsonlSink`
    - Search for `jsonl_sink` across the codebase
    - Update or remove any imports in test files that reference the old module
    - Remove old test files that tested `JsonlSink` exclusively
      (`tests/unit/knowledge/test_jsonl_sink.py`,
      `tests/unit/knowledge/test_jsonl_response.py`)
    - Also fixed: `tests/unit/knowledge/test_sink.py`,
      `tests/integration/test_review_visibility_smoke.py`,
      `tests/property/knowledge/test_sink_props.py`
    - _Requirements: 7.E1_

  - [x] 3.5 Update removal verification tests
    - In `tests/unit/knowledge/test_agent_trace_removal.py`, flip assertions
      so they now assert the file does NOT exist and imports are gone
    - _Test Spec: TS-103-12, TS-103-13_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_agent_trace.py tests/unit/knowledge/test_agent_trace_removal.py`
    - [x] Integration smoke tests pass: `uv run pytest -q tests/integration/test_agent_trace_smoke.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 7.* acceptance criteria met
    - [x] `agent_fox/knowledge/jsonl_sink.py` does not exist
    - [x] `grep -r jsonl_sink agent_fox/` returns zero matches (only local var in engine.py)

- [x] 4. Wiring verification
  - [x] 4.1 Trace every execution path from design.md end-to-end
    - Path 1: Verify `code_command` → `_setup_infrastructure` →
      `AgentTraceSink` creation → `_execute_query` → trace event emission →
      file write. Read the calling code at each step.
    - Path 2: Verify no `JsonlSink` instantiation path remains anywhere in
      the codebase.
    - Confirm no function in the chain is a stub.
    - _Requirements: all_

  - [x] 4.2 Verify return values propagate correctly
    - `truncate_tool_input` returns a dict consumed by `record_tool_use`
    - `AgentTraceSink` methods are called by `SinkDispatcher` delegation
    - Grep for callers; confirm none discards return values
    - _Requirements: all_

  - [x] 4.3 Run the integration smoke tests
    - All `TS-103-SMOKE-*` tests pass using real components
    - _Test Spec: TS-103-SMOKE-1, TS-103-SMOKE-2_

  - [x] 4.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be justified or replaced
    - _Requirements: all_

  - [x] 4.5 Cross-spec entry point verification
    - `AgentTraceSink` is instantiated in `_setup_infrastructure` (this spec)
      and called from `_execute_query` (this spec modifies it)
    - Verify both callers exist in production code
    - _Requirements: all_

  - [x] 4.V Verify wiring group
    - [x] All smoke tests pass
    - [x] No unjustified stubs remain in touched files
    - [x] All execution paths from design.md are live (traceable in code)
    - [x] All cross-spec entry points are called from production code
    - [x] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 103-REQ-1.1 | TS-103-SMOKE-1 | 3.2 | `tests/integration/test_agent_trace_smoke.py::test_full_session_trace` |
| 103-REQ-1.2 | TS-103-1 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_creates_file_on_first_write` |
| 103-REQ-1.3 | TS-103-2 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_jsonl_format` |
| 103-REQ-1.E1 | TS-103-3 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_creates_missing_directory` |
| 103-REQ-1.E2 | TS-103-4 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_write_failure_logged` |
| 103-REQ-2.1 | TS-103-5 | 2.1, 3.1 | `tests/unit/knowledge/test_agent_trace.py::test_session_init_prompts` |
| 103-REQ-2.2 | TS-103-5 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_session_init_prompts` |
| 103-REQ-3.1 | TS-103-6 | 2.1, 3.1 | `tests/unit/knowledge/test_agent_trace.py::test_assistant_message_content` |
| 103-REQ-3.2 | TS-103-6 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_assistant_message_content` |
| 103-REQ-4.1 | TS-103-7 | 2.1, 3.1 | `tests/unit/knowledge/test_agent_trace.py::test_tool_use_truncation` |
| 103-REQ-4.2 | TS-103-7 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_tool_use_truncation` |
| 103-REQ-4.3 | TS-103-8 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_tool_use_non_string_preserved` |
| 103-REQ-4.E1 | TS-103-9 | 2.1 | `tests/unit/knowledge/test_agent_trace.py::test_tool_use_empty_input` |
| 103-REQ-5.1 | TS-103-10 | 2.1, 3.1 | `tests/unit/knowledge/test_agent_trace.py::test_tool_error_event` |
| 103-REQ-6.1 | TS-103-11 | 2.1, 3.1 | `tests/unit/knowledge/test_agent_trace.py::test_session_result_metrics` |
| 103-REQ-7.1 | TS-103-12 | 3.3 | `tests/unit/knowledge/test_agent_trace_removal.py::test_jsonl_sink_module_removed` |
| 103-REQ-7.2 | TS-103-SMOKE-1 | 3.2 | `tests/integration/test_agent_trace_smoke.py::test_full_session_trace` |
| 103-REQ-7.3 | TS-103-SMOKE-2 | 3.2, 3.3 | `tests/integration/test_agent_trace_smoke.py::test_no_legacy_trace_files` |
| 103-REQ-7.E1 | TS-103-13 | 3.4 | `tests/unit/knowledge/test_agent_trace_removal.py::test_no_jsonl_sink_imports` |
| 103-REQ-8.1 | TS-103-14 | (no code change) | `tests/unit/knowledge/test_agent_trace.py::test_retention_preserves_agent_files` |
| 103-REQ-8.2 | TS-103-14 | (no code change) | `tests/unit/knowledge/test_agent_trace.py::test_retention_preserves_agent_files` |
| 103-REQ-8.E1 | TS-103-14 | (no code change) | `tests/unit/knowledge/test_agent_trace.py::test_retention_preserves_agent_files` |
| Property 1 | TS-103-P1 | 2.1 | `tests/property/knowledge/test_agent_trace_props.py::test_event_completeness` |
| Property 2 | TS-103-P2 | 2.1 | `tests/property/knowledge/test_agent_trace_props.py::test_truncation_invariants` |
| Property 3 | TS-103-P3 | 2.1 | `tests/property/knowledge/test_agent_trace_props.py::test_file_location` |

## Notes

- The `SinkDispatcher` currently dispatches only `SessionSink` protocol
  methods. The new trace methods (`record_session_init`, etc.) are specific
  to `AgentTraceSink`. The dispatcher will use `hasattr` checks to call
  trace methods on sinks that support them, keeping the `SessionSink`
  protocol unchanged.
- The `run_id` is not known at `_setup_infrastructure` time — it's generated
  in `Orchestrator._init_run`. Each trace method receives `run_id` as a
  parameter, and the sink uses it on first write to create the file. The
  `run_id` passed to `AgentTraceSink.__init__` can be empty and is only used
  as a fallback filename component.
- Existing tests for `JsonlSink` (`test_jsonl_sink.py`, `test_jsonl_response.py`)
  will be removed in task group 3 since the module they test is deleted.
- The audit retention function (`enforce_audit_retention`) already only deletes
  `audit_{run_id}.jsonl` files, so `agent_*.jsonl` files are naturally
  preserved without code changes. The test (TS-103-14) verifies this existing
  behavior as a regression guard.
