# Implementation Plan: Fix Issue Ordering and Dependency Detection

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 6 groups: tests first, then data models, then
each functional layer (reference parsing, dependency graph, AI triage, engine
integration with staleness). Each layer is independently testable.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/test_fix_ordering.py tests/property/test_fix_ordering.py tests/integration/test_fix_ordering.py`
- Unit tests: `uv run pytest -q tests/unit/test_fix_ordering.py`
- Property tests: `uv run pytest -q tests/property/test_fix_ordering.py`
- Integration tests: `uv run pytest -q tests/integration/test_fix_ordering.py`
- All tests: `uv run pytest -q`
- Linter: `ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create unit test file `tests/unit/test_fix_ordering.py`
    - Test classes for base ordering (TS-71-1, TS-71-2)
    - Test classes for reference parsing (TS-71-3, TS-71-4, TS-71-5)
    - Test classes for AI triage (TS-71-6, TS-71-7, TS-71-8, TS-71-9, TS-71-10)
    - Test classes for dependency graph (TS-71-11, TS-71-12, TS-71-13)
    - Test classes for staleness (TS-71-14, TS-71-15, TS-71-16, TS-71-17)
    - Test classes for observability (TS-71-18, TS-71-19, TS-71-20)
    - _Test Spec: TS-71-1 through TS-71-20_

  - [x] 1.2 Create edge case tests (in `tests/unit/test_fix_ordering.py`)
    - TS-71-E1 through TS-71-E9
    - _Test Spec: TS-71-E1 through TS-71-E9_

  - [x] 1.3 Create property test file `tests/property/test_fix_ordering.py`
    - TS-71-P1 through TS-71-P7
    - Include Hypothesis strategies for generating issue batches and edge sets
    - _Test Spec: TS-71-P1 through TS-71-P7_

  - [x] 1.4 Create integration test file `tests/integration/test_fix_ordering.py`
    - End-to-end `_run_issue_check()` with mocked platform and AI
    - _Test Spec: TS-71-1, TS-71-17_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `ruff check tests/unit/test_fix_ordering.py tests/property/test_fix_ordering.py tests/integration/test_fix_ordering.py`

- [ ] 2. Data models and platform extension
  - [ ] 2.1 Create `DependencyEdge` dataclass
    - Fields: from_issue, to_issue, source, rationale
    - File: `agent_fox/nightshift/dep_graph.py`
    - _Requirements: 2.1, 2.2, 3.3_

  - [ ] 2.2 Create `TriageResult` and `StalenessResult` dataclasses
    - File: `agent_fox/nightshift/triage.py`, `agent_fox/nightshift/staleness.py`
    - _Requirements: 3.3, 5.1_

  - [ ] 2.3 Add `sort` and `direction` params to `list_issues_by_label()`
    - Default: `sort="created"`, `direction="asc"`
    - Update both `GitHubPlatform` and `PlatformProtocol`
    - Files: `agent_fox/platform/github.py`, `agent_fox/platform/protocol.py`
    - _Requirements: 1.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/test_fix_ordering.py -k "ascending or sort or dataclass"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/nightshift/ agent_fox/platform/`
    - [ ] Requirements 71-REQ-1.1, 71-REQ-1.E1 acceptance criteria met

- [ ] 3. Reference parsing and dependency graph
  - [ ] 3.1 Implement `parse_text_references()`
    - Case-insensitive pattern matching for dependency hints
    - Filter edges to batch-only issue numbers
    - File: `agent_fox/nightshift/reference_parser.py`
    - _Requirements: 2.1, 2.3, 2.E1_

  - [ ] 3.2 Implement `fetch_github_relationships()`
    - Query GitHub timeline/relationship API
    - Convert to DependencyEdge objects
    - File: `agent_fox/nightshift/reference_parser.py`
    - _Requirements: 2.2_

  - [ ] 3.3 Implement `build_graph()` with topological sort
    - Kahn's algorithm with tie-breaking by ascending issue number
    - File: `agent_fox/nightshift/dep_graph.py`
    - _Requirements: 4.1, 4.2, 4.E1_

  - [ ] 3.4 Implement cycle detection and breaking
    - Detect cycles, break at edge pointing to oldest issue, log warning
    - File: `agent_fox/nightshift/dep_graph.py`
    - _Requirements: 4.3, 2.E2, 6.3_

  - [ ] 3.5 Implement `merge_edges()` with explicit precedence
    - Explicit edges override conflicting AI edges
    - File: `agent_fox/nightshift/dep_graph.py`
    - _Requirements: 3.4_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/test_fix_ordering.py -k "reference or graph or cycle or merge or topo"`
    - [ ] Property tests pass: `uv run pytest -q tests/property/test_fix_ordering.py -k "P1 or P2 or P3 or P4"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/nightshift/`
    - [ ] Requirements 71-REQ-2.*, 71-REQ-4.* acceptance criteria met

- [ ] 4. Checkpoint - Graph Layer Complete
  - [ ] 4.1 Run full test suite and linter
  - [ ] 4.2 Verify reference parsing handles all four text patterns
  - [ ] 4.3 Verify cycle breaking with property tests

- [ ] 5. AI triage and staleness
  - [ ] 5.1 Implement `run_batch_triage()`
    - Construct triage prompt with issue titles, bodies, and explicit edges
    - Parse AI JSON response into TriageResult
    - Use ADVANCED model tier
    - File: `agent_fox/nightshift/triage.py`
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 5.2 Implement batch size gate
    - Skip triage for batch < 3 issues
    - File: `agent_fox/nightshift/triage.py`
    - _Requirements: 3.5_

  - [ ] 5.3 Implement `check_staleness()`
    - AI evaluation of remaining issues against fix diff
    - GitHub API verification (re-fetch issues)
    - Close obsolete issues with comment
    - File: `agent_fox/nightshift/staleness.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 5.4 Implement triage and staleness error handling
    - Triage failure: fall back to explicit refs + number order
    - Staleness AI failure: fall back to GitHub API only
    - Staleness GitHub failure: log warning, continue
    - Files: `agent_fox/nightshift/triage.py`, `agent_fox/nightshift/staleness.py`
    - _Requirements: 3.E1, 3.E2, 5.E1, 5.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/test_fix_ordering.py -k "triage or staleness or batch_size or obsolete"`
    - [ ] Property tests pass: `uv run pytest -q tests/property/test_fix_ordering.py -k "P5 or P6 or P7"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/nightshift/`
    - [ ] Requirements 71-REQ-3.*, 71-REQ-5.* acceptance criteria met

- [ ] 6. Engine integration and observability
  - [ ] 6.1 Modify `_run_issue_check()` to build dependency graph
    - Parse refs, fetch GitHub relationships, run triage if batch >= 3
    - Sort by resolved order, process sequentially
    - File: `agent_fox/nightshift/engine.py`
    - _Requirements: 1.1, 1.2, 3.1, 4.1_

  - [ ] 6.2 Wire post-fix staleness into processing loop
    - After each successful fix, call `check_staleness()`
    - Remove obsolete issues from queue
    - Skip staleness on fix failure
    - File: `agent_fox/nightshift/engine.py`
    - _Requirements: 5.1, 5.4, 5.E3_

  - [ ] 6.3 Add observability: logging and audit events
    - Log resolved order at INFO
    - Emit audit event on staleness closure
    - Log cycle breaks at WARNING
    - File: `agent_fox/nightshift/engine.py`
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ] 6.4 Local sort fallback
    - Sort fetched issues by number ascending after fetch
    - File: `agent_fox/nightshift/engine.py`
    - _Requirements: 1.E1_

  - [ ] 6.V Verify task group 6
    - [ ] All spec tests pass: `uv run pytest -q tests/unit/test_fix_ordering.py tests/property/test_fix_ordering.py tests/integration/test_fix_ordering.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `ruff check agent_fox/`
    - [ ] All requirements 71-REQ-*.* acceptance criteria met

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
| 71-REQ-1.1 | TS-71-1 | 2.3, 6.1 | test_fix_ordering.py::TestBaseOrdering |
| 71-REQ-1.2 | TS-71-2 | 6.1 | test_fix_ordering.py::TestBaseOrdering |
| 71-REQ-1.E1 | TS-71-E9 | 6.4 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-2.1 | TS-71-3 | 3.1 | test_fix_ordering.py::TestReferenceParsing |
| 71-REQ-2.2 | TS-71-4 | 3.2 | test_fix_ordering.py::TestReferenceParsing |
| 71-REQ-2.3 | TS-71-5 | 3.1 | test_fix_ordering.py::TestReferenceParsing |
| 71-REQ-2.E1 | TS-71-E1 | 3.1 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-2.E2 | TS-71-E2 | 3.4 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-3.1 | TS-71-6 | 5.1, 6.1 | test_fix_ordering.py::TestAITriage |
| 71-REQ-3.2 | TS-71-7 | 5.1 | test_fix_ordering.py::TestAITriage |
| 71-REQ-3.3 | TS-71-8 | 5.1 | test_fix_ordering.py::TestAITriage |
| 71-REQ-3.4 | TS-71-9 | 3.5 | test_fix_ordering.py::TestEdgeMerging |
| 71-REQ-3.5 | TS-71-10 | 5.2, 6.1 | test_fix_ordering.py::TestAITriage |
| 71-REQ-3.E1 | TS-71-E3 | 5.4, 6.1 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-3.E2 | TS-71-E4 | 3.5 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-4.1 | TS-71-11 | 3.3 | test_fix_ordering.py::TestDepGraph |
| 71-REQ-4.2 | TS-71-12 | 3.3 | test_fix_ordering.py::TestDepGraph |
| 71-REQ-4.3 | TS-71-13 | 3.4 | test_fix_ordering.py::TestDepGraph |
| 71-REQ-4.E1 | TS-71-E5 | 3.3 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-5.1 | TS-71-14 | 5.3, 6.2 | test_fix_ordering.py::TestStaleness |
| 71-REQ-5.2 | TS-71-15 | 5.3 | test_fix_ordering.py::TestStaleness |
| 71-REQ-5.3 | TS-71-16 | 5.3 | test_fix_ordering.py::TestStaleness |
| 71-REQ-5.4 | TS-71-17 | 5.3, 6.2 | test_fix_ordering.py::TestStaleness |
| 71-REQ-5.E1 | TS-71-E6 | 5.4 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-5.E2 | TS-71-E7 | 5.4 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-5.E3 | TS-71-E8 | 6.2 | test_fix_ordering.py::TestEdgeCases |
| 71-REQ-6.1 | TS-71-18 | 6.3 | test_fix_ordering.py::TestObservability |
| 71-REQ-6.2 | TS-71-19 | 6.3 | test_fix_ordering.py::TestObservability |
| 71-REQ-6.3 | TS-71-20 | 3.4, 6.3 | test_fix_ordering.py::TestObservability |
| Property 1 | TS-71-P1 | 3.3 | test_fix_ordering.py (property) |
| Property 2 | TS-71-P2 | 3.3 | test_fix_ordering.py (property) |
| Property 3 | TS-71-P3 | 3.5 | test_fix_ordering.py (property) |
| Property 4 | TS-71-P4 | 3.4 | test_fix_ordering.py (property) |
| Property 5 | TS-71-P5 | 5.4 | test_fix_ordering.py (property) |
| Property 6 | TS-71-P6 | 5.3, 6.2 | test_fix_ordering.py (property) |
| Property 7 | TS-71-P7 | 5.2 | test_fix_ordering.py (property) |

## Notes

- All AI and platform calls must be mocked in tests (AsyncMock).
- Use Hypothesis composite strategies to generate acyclic and cyclic graphs.
- The `merge_edges()` function is the key correctness boundary between
  explicit and AI-detected dependencies.
- Staleness check receives a diff string — in tests, use a fixture diff.
- GitHub's timeline API for relationship metadata may not be available on
  all GitHub Enterprise instances; `fetch_github_relationships()` must
  handle 404/403 gracefully.
