# Implementation Plan: --dry-run Flag on plan Command

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The implementation adds a `--dry-run` dry-run flag to the `plan` command. A new
`graph/analyzer.py` module provides three pure analysis functions
(`compute_phases`, `critical_path`, `group_edges`). The CLI and `run_plan()` API
are updated to skip persistence when `dry_run=True`. A new formatter renders the
richer analysis output.

Task groups are ordered: tests first (group 1), then the analyzer module
(group 2), then CLI/API integration (group 3), then docs (group 4), then
wiring verification (group 5).

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/graph/test_analyzer.py tests/unit/graph/test_planner_analyze.py tests/integration/cli/test_plan_analyze.py`
- Unit tests: `uv run pytest -q tests/unit/graph/test_analyzer.py tests/unit/graph/test_planner_analyze.py`
- Property tests: `uv run pytest -q tests/unit/graph/test_analyzer.py -k property`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test file structure
    - Create `tests/unit/graph/test_analyzer.py` for analyzer unit + property tests
    - Create `tests/unit/graph/test_planner_analyze.py` for run_plan analyze tests
    - Create `tests/integration/cli/test_plan_analyze.py` for CLI integration tests
    - Use existing test framework conventions (pytest, Click CliRunner, hypothesis)
    - _Test Spec: TS-122-1 through TS-122-17, TS-122-E1 through TS-122-E7, TS-122-P1 through TS-122-P8, TS-122-SMOKE-1 through TS-122-SMOKE-4_

  - [ ] 1.2 Translate unit tests for analyzer functions
    - TS-122-4: compute_phases with diamond graph
    - TS-122-7: group_edges partitioning
    - TS-122-9: critical_path longest path
    - TS-122-11: critical_path deterministic tie-break
    - _Test Spec: TS-122-4, TS-122-7, TS-122-9, TS-122-11_

  - [ ] 1.3 Translate unit tests for formatter
    - TS-122-5: format_plan_analysis includes phase headings
    - TS-122-6: format_plan_analysis summary line
    - TS-122-8: edge display format
    - TS-122-10: critical path display
    - _Test Spec: TS-122-5, TS-122-6, TS-122-8, TS-122-10_

  - [ ] 1.4 Translate edge case tests
    - TS-122-E3: single node phases
    - TS-122-E4: no cross-spec edges
    - TS-122-E5: single node critical path
    - TS-122-E6: empty graph critical path
    - _Test Spec: TS-122-E3, TS-122-E4, TS-122-E5, TS-122-E6_

  - [ ] 1.5 Translate property tests
    - TS-122-P1: phase completeness
    - TS-122-P2: phase ordering respects dependencies
    - TS-122-P3: critical path is valid path
    - TS-122-P4: critical path is longest
    - TS-122-P5: analyze does not persist
    - TS-122-P6: edge grouping exhaustive
    - TS-122-P7: critical path determinism
    - TS-122-P8: phase determinism
    - _Test Spec: TS-122-P1 through TS-122-P8_

  - [ ] 1.6 Translate integration and smoke tests
    - TS-122-1: analyze skips persistence
    - TS-122-2: normal plan persists
    - TS-122-3: analyze exit codes
    - TS-122-12: analyze + fast
    - TS-122-13: analyze + spec
    - TS-122-14: analyze + json
    - TS-122-15: all flags combined
    - TS-122-16: run_plan dry_run=True
    - TS-122-17: run_plan dry_run=False
    - TS-122-E1: empty specs
    - TS-122-E2: cycle error
    - TS-122-E7: nonexistent spec
    - TS-122-SMOKE-1 through TS-122-SMOKE-4
    - _Test Spec: TS-122-1, TS-122-2, TS-122-3, TS-122-12 through TS-122-17, TS-122-E1, TS-122-E2, TS-122-E7, TS-122-SMOKE-1 through TS-122-SMOKE-4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Implement analyzer module
  - [ ] 2.1 Create `agent_fox/graph/analyzer.py` with data types
    - Define `Phase` and `GroupedEdges` dataclasses
    - _Requirements: 122-REQ-2.1, 122-REQ-3.1_

  - [ ] 2.2 Implement `compute_phases(graph)` function
    - Compute topological depth for each node using BFS from sources
    - Group nodes by depth into Phase objects
    - Sort node IDs within each phase lexicographically
    - _Requirements: 122-REQ-2.1_

  - [ ] 2.3 Implement `critical_path(graph)` function
    - Compute longest path using dynamic programming on topological order
    - Track predecessors for path reconstruction
    - Lexicographic tie-breaking at each step
    - _Requirements: 122-REQ-4.1, 122-REQ-4.3_

  - [ ] 2.4 Implement `group_edges(graph)` function
    - Partition graph.edges by `edge.kind` into intra_spec and cross_spec lists
    - _Requirements: 122-REQ-3.1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/graph/test_analyzer.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/graph/analyzer.py`
    - [ ] Requirements 122-REQ-2.1, 122-REQ-3.1, 122-REQ-4.1, 122-REQ-4.3 acceptance criteria met

- [ ] 3. Integrate into CLI and API
  - [ ] 3.1 Add `--dry-run` flag to `plan_cmd` in `cli/plan.py`
    - Add Click option `--dry-run` as a boolean flag
    - When `dry_run=True`: call `build_plan()`, then analyzer functions, then formatter/JSON; skip persistence
    - When `dry_run=False`: existing flow unchanged
    - _Requirements: 122-REQ-1.1, 122-REQ-1.2, 122-REQ-1.3_

  - [ ] 3.2 Implement `format_plan_analysis()` in `graph/planner.py`
    - Render standard summary, parallelism phases, critical path, dependency edges
    - Include phase summary line (total phases, peak parallelism)
    - Omit cross-spec section if no cross-spec edges exist
    - _Requirements: 122-REQ-2.2, 122-REQ-2.3, 122-REQ-3.2, 122-REQ-4.2, 122-REQ-3.E1_

  - [ ] 3.3 Add JSON analysis output in `cli/plan.py`
    - When `--dry-run --json`: emit JSON with phases, critical_path, grouped_edges
    - _Requirements: 122-REQ-5.3_

  - [ ] 3.4 Add `dry_run` parameter to `run_plan()` in `graph/planner.py`
    - When `dry_run=True`: skip `open_knowledge_store()` and `save_plan()`
    - When `dry_run=False`: existing behavior unchanged
    - _Requirements: 122-REQ-6.1, 122-REQ-6.2_

  - [ ] 3.5 Verify flag composability
    - Ensure `--dry-run` works with `--fast`, `--spec`, and `--json` in all combinations
    - _Requirements: 122-REQ-5.1, 122-REQ-5.2, 122-REQ-5.4_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/graph/test_planner_analyze.py tests/integration/cli/test_plan_analyze.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/cli/plan.py agent_fox/graph/planner.py`
    - [ ] Requirements 122-REQ-1.1 through 122-REQ-6.2 acceptance criteria met

- [ ] 4. Documentation
  - [ ] 4.1 Update CLI reference
    - Add `--dry-run` to the plan command options table in `docs/cli-reference.md`
    - Add description of the analysis output
    - _Requirements: all_

  - [ ] 4.V Verify task group 4
    - [ ] `docs/cli-reference.md` updated with --dry-run flag
    - [ ] All existing tests still pass: `uv run pytest -q`

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - For each path, verify the entry point actually calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-122-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-122-SMOKE-1 through TS-122-SMOKE-4_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 5.5 Cross-spec entry point verification
    - For each execution path whose entry point is owned by another spec
      (e.g., plan_cmd is defined by spec 02), grep the codebase to confirm
      the entry point is actually called from production code — not just tests
    - If the upstream caller does not exist, either implement it within this
      spec or file an issue and remove the path from design.md
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 122-REQ-1.1 | TS-122-1 | 3.1 | test_plan_analyze.py::test_analyze_skips_persistence |
| 122-REQ-1.2 | TS-122-2 | 3.1 | test_plan_analyze.py::test_normal_plan_persists |
| 122-REQ-1.3 | TS-122-3 | 3.1 | test_plan_analyze.py::test_analyze_exit_codes |
| 122-REQ-1.E1 | TS-122-E1 | 3.1 | test_plan_analyze.py::test_analyze_empty_specs |
| 122-REQ-1.E2 | TS-122-E2 | 3.1 | test_plan_analyze.py::test_analyze_cycle_error |
| 122-REQ-2.1 | TS-122-4 | 2.2 | test_analyzer.py::test_compute_phases_diamond |
| 122-REQ-2.2 | TS-122-5 | 3.2 | test_planner_analyze.py::test_format_phases |
| 122-REQ-2.3 | TS-122-6 | 3.2 | test_planner_analyze.py::test_format_phase_summary |
| 122-REQ-2.E1 | TS-122-E3 | 2.2 | test_analyzer.py::test_single_node_phases |
| 122-REQ-3.1 | TS-122-7 | 2.4 | test_analyzer.py::test_group_edges |
| 122-REQ-3.2 | TS-122-8 | 3.2 | test_planner_analyze.py::test_edge_display_format |
| 122-REQ-3.E1 | TS-122-E4 | 3.2 | test_planner_analyze.py::test_no_cross_spec_edges |
| 122-REQ-4.1 | TS-122-9 | 2.3 | test_analyzer.py::test_critical_path_longest |
| 122-REQ-4.2 | TS-122-10 | 3.2 | test_planner_analyze.py::test_critical_path_display |
| 122-REQ-4.3 | TS-122-11 | 2.3 | test_analyzer.py::test_critical_path_deterministic |
| 122-REQ-4.E1 | TS-122-E5 | 2.3 | test_analyzer.py::test_single_node_critical_path |
| 122-REQ-4.E2 | TS-122-E6 | 2.3 | test_analyzer.py::test_empty_graph_critical_path |
| 122-REQ-5.1 | TS-122-12 | 3.5 | test_plan_analyze.py::test_analyze_with_fast |
| 122-REQ-5.2 | TS-122-13 | 3.5 | test_plan_analyze.py::test_analyze_with_spec |
| 122-REQ-5.3 | TS-122-14 | 3.3 | test_plan_analyze.py::test_analyze_json |
| 122-REQ-5.4 | TS-122-15 | 3.5 | test_plan_analyze.py::test_analyze_all_flags |
| 122-REQ-5.E1 | TS-122-E7 | 3.5 | test_plan_analyze.py::test_analyze_nonexistent_spec |
| 122-REQ-6.1 | TS-122-16 | 3.4 | test_planner_analyze.py::test_run_plan_analyze_true |
| 122-REQ-6.2 | TS-122-17 | 3.4 | test_planner_analyze.py::test_run_plan_analyze_false |
| Property 1 | TS-122-P1 | 2.2 | test_analyzer.py::test_property_phase_completeness |
| Property 2 | TS-122-P2 | 2.2 | test_analyzer.py::test_property_phase_ordering |
| Property 3 | TS-122-P3 | 2.3 | test_analyzer.py::test_property_path_valid |
| Property 4 | TS-122-P4 | 2.3 | test_analyzer.py::test_property_path_longest |
| Property 5 | TS-122-P5 | 3.4 | test_planner_analyze.py::test_property_analyze_no_persist |
| Property 6 | TS-122-P6 | 2.4 | test_analyzer.py::test_property_edge_grouping |
| Property 7 | TS-122-P7 | 2.3 | test_analyzer.py::test_property_path_determinism |
| Property 8 | TS-122-P8 | 2.2 | test_analyzer.py::test_property_phase_determinism |

## Notes

- The `graph/analyzer.py` module previously existed but was deleted in spec 63.
  This is a clean reimplementation with a narrower scope (no caching concerns).
- Property tests use Hypothesis with a custom strategy for generating random
  DAGs as TaskGraph objects. The strategy should ensure acyclicity by assigning
  random topological positions to nodes and only adding edges from lower to
  higher positions.
- Integration tests use Click's `CliRunner` with `catch_exceptions=False` for
  clear error reporting.
