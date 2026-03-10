# Implementation Plan: Token-Efficient File Tools & MCP Server

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in 8 task groups: failing tests first, then core
library modules bottom-up (hashing → outline → read/search → edit), backend
protocol extension with config wiring, MCP server + CLI, and a final
checkpoint.

The core library has no external coupling, so tools can be implemented and
tested in isolation. Backend integration and MCP server are thin wrappers
added last.

## Test Commands

- Spec tests: `uv run pytest tests/unit/tools/ tests/integration/tools/ -q`
- Property tests: `uv run pytest tests/property/tools/ -q`
- Unit tests: `uv run pytest tests/unit/ -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check . && uv run ruff format --check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure and fixtures
    - Create `tests/unit/tools/` package with `conftest.py`
    - Create `tests/property/tools/` package
    - Create `tests/integration/tools/` package
    - Add fixture files: `fixtures/sample.py`, `fixtures/sample.js`,
      `fixtures/sample.rs`, `fixtures/sample.go`, `fixtures/sample.java`,
      `fixtures/sample.ts` with known declarations
    - Add conftest helpers: `make_temp_file()`, `make_temp_file_with_lines()`
    - _Test Spec: TS-29-1 through TS-29-28_

  - [x] 1.2 Write hashing unit tests
    - `tests/unit/tools/test_hashing.py`
    - TS-29-15 (xxh3_64 format), TS-29-16 (deterministic), TS-29-17 (sensitive)
    - TS-29-E13 (blake2b fallback)
    - _Test Spec: TS-29-15, TS-29-16, TS-29-17, TS-29-E13_

  - [x] 1.3 Write outline unit tests
    - `tests/unit/tools/test_outline.py`
    - TS-29-1 (symbols), TS-29-2 (imports), TS-29-3 (summary), TS-29-4 (languages)
    - TS-29-E1 (missing file), TS-29-E2 (empty file), TS-29-E3 (binary file)
    - _Test Spec: TS-29-1, TS-29-2, TS-29-3, TS-29-4, TS-29-E1, TS-29-E2, TS-29-E3_

  - [x] 1.4 Write read and search unit tests
    - `tests/unit/tools/test_read.py`
    - TS-29-5 (ranges), TS-29-6 (multiple ranges), TS-29-7 (hash correctness)
    - TS-29-E4 (missing file), TS-29-E5 (beyond EOF), TS-29-E6 (invalid range)
    - `tests/unit/tools/test_search.py`
    - TS-29-12 (matches), TS-29-13 (context), TS-29-14 (merge)
    - TS-29-E10 (missing file), TS-29-E11 (bad regex), TS-29-E12 (no matches)
    - _Test Spec: TS-29-5 through TS-29-7, TS-29-12 through TS-29-14, TS-29-E4 through TS-29-E6, TS-29-E10 through TS-29-E12_

  - [x] 1.5 Write edit unit tests
    - `tests/unit/tools/test_edit.py`
    - TS-29-8 (hash verify), TS-29-9 (atomicity), TS-29-10 (reverse order),
      TS-29-11 (delete)
    - TS-29-E7 (mismatch), TS-29-E8 (missing file), TS-29-E9 (overlap)
    - _Test Spec: TS-29-8 through TS-29-11, TS-29-E7 through TS-29-E9_

  - [x] 1.6 Write backend, config, and MCP tests
    - `tests/unit/tools/test_registry.py` — TS-29-18 through TS-29-21,
      TS-29-E14, TS-29-E15
    - `tests/unit/core/test_config_tools.py` — TS-29-26 through TS-29-28,
      TS-29-E18
    - `tests/integration/tools/test_mcp_server.py` — TS-29-22 through TS-29-25,
      TS-29-E16, TS-29-E17
    - _Test Spec: TS-29-18 through TS-29-28, TS-29-E14 through TS-29-E18_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] Property test files created (can be empty stubs for now)
    - [x] No linter warnings introduced: `uv run ruff check . && uv run ruff format --check .`

- [x] 2. Core types and hashing module
  - [x] 2.1 Create `agent_fox/tools/__init__.py` package
    - Empty init file establishing the package
    - _Requirements: N/A (structural)_

  - [x] 2.2 Implement `agent_fox/tools/types.py`
    - Frozen dataclasses: `HashedLine`, `Symbol`, `OutlineResult`, `ReadResult`,
      `EditOperation`, `EditResult`, `SearchMatch`, `SearchResult`
    - _Requirements: 29-REQ-1.1, 29-REQ-2.1, 29-REQ-3.1, 29-REQ-4.1_

  - [x] 2.3 Implement `agent_fox/tools/hashing.py`
    - `hash_line(content: bytes) -> str` using xxh3_64
    - blake2b fallback with warning on ImportError
    - 16-char lowercase hex output
    - _Requirements: 29-REQ-5.1, 29-REQ-5.2, 29-REQ-5.3, 29-REQ-5.E1_

  - [x] 2.4 Write property tests for hashing
    - `tests/property/tools/test_hashing_props.py`
    - TS-29-P1 (determinism), TS-29-P2 (sensitivity)
    - _Test Spec: TS-29-P1, TS-29-P2_

  - [x] 2.V Verify task group 2
    - [x] Hashing tests pass: `uv run pytest tests/unit/tools/test_hashing.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/tools/test_hashing_props.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 29-REQ-5.1 through 29-REQ-5.E1 met

- [x] 3. File outline tool
  - [x] 3.1 Implement heuristic parser in `agent_fox/tools/outline.py`
    - Language detection from file extension
    - Per-language regex pattern sets (Python, JS/TS, Rust, Go, Java)
    - Fallback pattern set for unknown extensions
    - Import block detection and collapsing
    - _Requirements: 29-REQ-1.1, 29-REQ-1.2, 29-REQ-1.4_

  - [x] 3.2 Implement end-line detection
    - Indentation-based heuristic for Python
    - Brace-matching heuristic for brace languages
    - Fallback: next declaration start - 1, or EOF
    - _Requirements: 29-REQ-1.1_

  - [x] 3.3 Implement `fox_outline()` function
    - Read file, detect binary, parse symbols, format OutlineResult
    - Handle edge cases: missing file, empty file, binary file
    - Summary line with symbol count and total lines
    - _Requirements: 29-REQ-1.1, 29-REQ-1.3, 29-REQ-1.E1, 29-REQ-1.E2, 29-REQ-1.E3_

  - [x] 3.4 Write property test for outline completeness
    - `tests/property/tools/test_outline_props.py`
    - TS-29-P6 (Python completeness)
    - _Test Spec: TS-29-P6_

  - [x] 3.V Verify task group 3
    - [x] Outline tests pass: `uv run pytest tests/unit/tools/test_outline.py -q`
    - [x] Property test passes: `uv run pytest tests/property/tools/test_outline_props.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 29-REQ-1.1 through 29-REQ-1.E3 met

- [x] 4. Read and search tools
  - [x] 4.1 Implement `agent_fox/tools/read.py`
    - `fox_read()` function: file reading, range extraction, hash annotation
    - Multiple disjoint ranges sorted by ascending line number
    - Edge cases: missing file, range beyond EOF, invalid range
    - _Requirements: 29-REQ-2.1, 29-REQ-2.2, 29-REQ-2.3, 29-REQ-2.E1, 29-REQ-2.E2, 29-REQ-2.E3_

  - [x] 4.2 Implement `agent_fox/tools/search.py`
    - `fox_search()` function: regex matching, context lines, hash annotation
    - Context range merging for overlapping matches
    - Edge cases: missing file, invalid regex, no matches
    - _Requirements: 29-REQ-4.1, 29-REQ-4.2, 29-REQ-4.3, 29-REQ-4.E1, 29-REQ-4.E2, 29-REQ-4.E3_

  - [x] 4.3 Write property test for search context merge
    - `tests/property/tools/test_search_props.py`
    - TS-29-P7 (no duplicate lines in merged context)
    - _Test Spec: TS-29-P7_

  - [x] 4.V Verify task group 4
    - [x] Read tests pass: `uv run pytest tests/unit/tools/test_read.py -q`
    - [x] Search tests pass: `uv run pytest tests/unit/tools/test_search.py -q`
    - [x] Property test passes: `uv run pytest tests/property/tools/test_search_props.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 29-REQ-2.x and 29-REQ-4.x met

- [x] 5. Edit tool
  - [x] 5.1 Implement `agent_fox/tools/edit.py`
    - `fox_edit()` function: hash verification, atomic write, reverse-order
      processing
    - Overlap detection (pre-validation before any I/O)
    - Line deletion (empty new_content)
    - Atomic write via temp file + rename
    - _Requirements: 29-REQ-3.1, 29-REQ-3.2, 29-REQ-3.3, 29-REQ-3.4_

  - [x] 5.2 Implement edit error paths
    - Hash mismatch: list all mismatched lines with expected/actual hashes
    - Missing/non-writable file
    - Overlapping range detection
    - _Requirements: 29-REQ-3.E1, 29-REQ-3.E2, 29-REQ-3.E3_

  - [x] 5.3 Write property tests for edit
    - `tests/property/tools/test_edit_props.py`
    - TS-29-P3 (read-edit round-trip), TS-29-P4 (atomicity),
      TS-29-P5 (stale hash rejection)
    - _Test Spec: TS-29-P3, TS-29-P4, TS-29-P5_

  - [x] 5.V Verify task group 5
    - [x] Edit tests pass: `uv run pytest tests/unit/tools/test_edit.py -q`
    - [x] Property tests pass: `uv run pytest tests/property/tools/test_edit_props.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 29-REQ-3.x met

- [x] 6. Checkpoint — Core Tools Complete
  - Ensure all core tool tests pass: `uv run pytest tests/unit/tools/ tests/property/tools/ -q`
  - All 1438+ existing tests still pass.
  - Ask the user if questions arise.

- [x] 7. Backend protocol, config, and registry
  - [x] 7.1 Extend `AgentBackend` protocol with `tools` parameter
    - Add `ToolDefinition` dataclass to `protocol.py`
    - Add optional `tools: list[ToolDefinition] | None = None` to `execute()`
    - _Requirements: 29-REQ-6.1, 29-REQ-6.E1_

  - [x] 7.2 Update `ClaudeBackend` to handle `ToolDefinition` objects
    - Map `ToolDefinition` list to SDK's in-process MCP server
      (`McpSdkServerConfig`) or equivalent mechanism
    - Pass through `permission_callback` for custom tool gating
    - Catch handler exceptions, return error to agent
    - _Requirements: 29-REQ-6.2, 29-REQ-6.3, 29-REQ-6.4, 29-REQ-6.E2_

  - [x] 7.3 Add `ToolsConfig` to config system
    - New `ToolsConfig` pydantic model with `fox_tools: bool = False`
    - Add `tools: ToolsConfig` field to `AgentFoxConfig`
    - _Requirements: 29-REQ-8.1, 29-REQ-8.E1_

  - [x] 7.4 Implement `agent_fox/tools/registry.py`
    - `build_fox_tool_definitions()` returns `list[ToolDefinition]`
    - JSON Schema for each tool, handler wrapping core functions
    - _Requirements: 29-REQ-8.2_

  - [x] 7.5 Wire session runner to pass tools when enabled
    - In `run_session()` / `_execute_query()`: check `config.tools.fox_tools`,
      build tool definitions, pass to `backend.execute()`
    - TS-29-P8 (backward compat) — tools=None when disabled
    - _Requirements: 29-REQ-8.2, 29-REQ-8.3_

  - [x] 7.V Verify task group 7
    - [x] Backend tests pass: `uv run pytest tests/unit/tools/test_registry.py -q`
    - [x] Config tests pass: `uv run pytest tests/unit/core/test_config_tools.py -q`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [x] Requirements 29-REQ-6.x and 29-REQ-8.x met

- [ ] 8. MCP server and CLI command
  - [ ] 8.1 Implement `agent_fox/tools/server.py`
    - `create_mcp_server(allowed_dirs)` using `mcp` Python SDK
    - Register all four fox tools as MCP tools
    - Path sandboxing via `allowed_dirs` validation
    - `run_server()` blocking entry point for stdio transport
    - _Requirements: 29-REQ-7.1, 29-REQ-7.2, 29-REQ-7.4, 29-REQ-7.E1, 29-REQ-7.E2_

  - [ ] 8.2 Implement `agent_fox/cli/serve_tools.py`
    - Click command `serve-tools` with `--allowed-dirs` option
    - Register with `main.add_command()` in `app.py`
    - _Requirements: 29-REQ-7.3_

  - [ ] 8.3 Write MCP integration tests
    - TS-29-P9 (MCP/in-process equivalence)
    - Finalize `tests/integration/tools/test_mcp_server.py`
    - _Test Spec: TS-29-P9, TS-29-22 through TS-29-25, TS-29-E16, TS-29-E17_

  - [ ] 8.V Verify task group 8
    - [ ] MCP tests pass: `uv run pytest tests/integration/tools/ -q`
    - [ ] CLI test passes: `uv run pytest tests/unit/tools/test_registry.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] Requirements 29-REQ-7.x met

- [ ] 9. Final checkpoint
  - [ ] 9.1 Update README.md with fox tools documentation
    - Usage instructions for `[tools]` config section
    - Usage instructions for `agent-fox serve-tools` CLI command

  - [ ] 9.2 Create ADR `docs/adr/token-efficient-file-tools.md`
    - Document decision to use regex heuristics over tree-sitter
    - Document dual consumption path (in-process vs MCP)

  - [ ] 9.V Verify task group 9
    - [ ] All spec tests pass: `uv run pytest tests/unit/tools/ tests/property/tools/ tests/integration/tools/ -q`
    - [ ] Full test suite passes: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check . && uv run ruff format --check .`
    - [ ] All 55 test spec entries covered and green

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
| 29-REQ-1.1 | TS-29-1 | 3.1, 3.3 | `test_outline.py::test_returns_symbols` |
| 29-REQ-1.2 | TS-29-2 | 3.1 | `test_outline.py::test_collapses_imports` |
| 29-REQ-1.3 | TS-29-3 | 3.3 | `test_outline.py::test_summary_line` |
| 29-REQ-1.4 | TS-29-4 | 3.1 | `test_outline.py::test_multi_language` |
| 29-REQ-1.E1 | TS-29-E1 | 3.3 | `test_outline.py::test_missing_file` |
| 29-REQ-1.E2 | TS-29-E2 | 3.3 | `test_outline.py::test_empty_file` |
| 29-REQ-1.E3 | TS-29-E3 | 3.3 | `test_outline.py::test_binary_file` |
| 29-REQ-2.1 | TS-29-5 | 4.1 | `test_read.py::test_returns_hashed_lines` |
| 29-REQ-2.2 | TS-29-6 | 4.1 | `test_read.py::test_multiple_ranges_ordered` |
| 29-REQ-2.3 | TS-29-7 | 4.1 | `test_read.py::test_xxh3_hashes` |
| 29-REQ-2.E1 | TS-29-E4 | 4.1 | `test_read.py::test_missing_file` |
| 29-REQ-2.E2 | TS-29-E5 | 4.1 | `test_read.py::test_range_beyond_eof` |
| 29-REQ-2.E3 | TS-29-E6 | 4.1 | `test_read.py::test_invalid_range` |
| 29-REQ-3.1 | TS-29-8 | 5.1 | `test_edit.py::test_verifies_hashes` |
| 29-REQ-3.2 | TS-29-9 | 5.1 | `test_edit.py::test_atomic_batch` |
| 29-REQ-3.3 | TS-29-10 | 5.1 | `test_edit.py::test_reverse_order` |
| 29-REQ-3.4 | TS-29-11 | 5.1 | `test_edit.py::test_line_deletion` |
| 29-REQ-3.E1 | TS-29-E7 | 5.2 | `test_edit.py::test_hash_mismatch_rejects` |
| 29-REQ-3.E2 | TS-29-E8 | 5.2 | `test_edit.py::test_missing_file` |
| 29-REQ-3.E3 | TS-29-E9 | 5.2 | `test_edit.py::test_overlapping_ranges` |
| 29-REQ-4.1 | TS-29-12 | 4.2 | `test_search.py::test_returns_matches` |
| 29-REQ-4.2 | TS-29-13 | 4.2 | `test_search.py::test_context_lines` |
| 29-REQ-4.3 | TS-29-14 | 4.2 | `test_search.py::test_context_merge` |
| 29-REQ-4.E1 | TS-29-E10 | 4.2 | `test_search.py::test_missing_file` |
| 29-REQ-4.E2 | TS-29-E11 | 4.2 | `test_search.py::test_invalid_regex` |
| 29-REQ-4.E3 | TS-29-E12 | 4.2 | `test_search.py::test_no_matches` |
| 29-REQ-5.1 | TS-29-15 | 2.3 | `test_hashing.py::test_xxh3_format` |
| 29-REQ-5.2 | TS-29-16 | 2.3 | `test_hashing.py::test_deterministic` |
| 29-REQ-5.3 | TS-29-17 | 2.3 | `test_hashing.py::test_different_content` |
| 29-REQ-5.E1 | TS-29-E13 | 2.3 | `test_hashing.py::test_blake2b_fallback` |
| 29-REQ-6.1 | TS-29-18 | 7.1 | `test_registry.py::test_backend_accepts_tools` |
| 29-REQ-6.2 | TS-29-19 | 7.2 | `test_registry.py::test_tools_available` |
| 29-REQ-6.3 | TS-29-20 | 7.2 | `test_registry.py::test_handler_called` |
| 29-REQ-6.4 | TS-29-21 | 7.2 | `test_registry.py::test_permission_callback` |
| 29-REQ-6.E1 | TS-29-E14 | 7.1 | `test_registry.py::test_no_tools_no_change` |
| 29-REQ-6.E2 | TS-29-E15 | 7.2 | `test_registry.py::test_handler_exception` |
| 29-REQ-7.1 | TS-29-22 | 8.1 | `test_mcp_server.py::test_four_tools_registered` |
| 29-REQ-7.2 | TS-29-23 | 8.1 | `test_mcp_server.py::test_delegates_to_core` |
| 29-REQ-7.3 | TS-29-24 | 8.2 | `test_mcp_server.py::test_cli_command` |
| 29-REQ-7.4 | TS-29-25 | 8.1 | `test_mcp_server.py::test_allowed_dirs` |
| 29-REQ-7.E1 | TS-29-E16 | 8.1 | `test_mcp_server.py::test_path_blocked` |
| 29-REQ-7.E2 | TS-29-E17 | 8.1 | `test_mcp_server.py::test_clean_shutdown` |
| 29-REQ-8.1 | TS-29-26 | 7.3 | `test_config_tools.py::test_default_false` |
| 29-REQ-8.2 | TS-29-27 | 7.4, 7.5 | `test_config_tools.py::test_tools_enabled` |
| 29-REQ-8.3 | TS-29-28 | 7.5 | `test_config_tools.py::test_tools_disabled` |
| 29-REQ-8.E1 | TS-29-E18 | 7.3 | `test_config_tools.py::test_invalid_value` |
| Property 1 | TS-29-P1 | 2.4 | `test_hashing_props.py::test_determinism` |
| Property 2 | TS-29-P2 | 2.4 | `test_hashing_props.py::test_sensitivity` |
| Property 3 | TS-29-P3 | 5.3 | `test_edit_props.py::test_round_trip` |
| Property 4 | TS-29-P4 | 5.3 | `test_edit_props.py::test_atomicity` |
| Property 5 | TS-29-P5 | 5.3 | `test_edit_props.py::test_stale_rejection` |
| Property 6 | TS-29-P6 | 3.4 | `test_outline_props.py::test_python_completeness` |
| Property 7 | TS-29-P7 | 4.3 | `test_search_props.py::test_context_merge` |
| Property 8 | TS-29-P8 | 7.1 | `test_registry.py::test_backward_compat` |
| Property 9 | TS-29-P9 | 8.3 | `test_mcp_server.py::test_equivalence` |

## Notes

- **xxhash dependency:** Add `xxhash>=3.0` to `pyproject.toml` in task group 2.
  The blake2b fallback is for environments where xxhash can't be installed.
- **MCP SDK:** Already a transitive dependency via `claude-agent-sdk`. Add
  explicit `mcp>=1.0` to `pyproject.toml` in task group 8.
- **Fixture files:** Keep fixture files small (20-50 lines each) with known
  declaration counts for deterministic tests.
- **Claude SDK in-process tools:** The exact SDK mechanism for registering
  in-process tools (McpSdkServerConfig or equivalent) should be verified
  against the current SDK version during task group 7 implementation.
