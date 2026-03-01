# Implementation Plan: Planning Engine

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the planning engine: specification discovery, task
parsing, task graph construction, dependency resolution, fast-mode filtering,
and the `agent-fox plan` CLI command. Task groups build up from tests to
working planner.

## Test Commands

- Unit tests: `uv run pytest tests/unit/spec/ tests/unit/graph/ -q`
- Property tests: `uv run pytest tests/property/graph/ -q`
- Integration tests: `uv run pytest tests/integration/test_plan.py -q`
- All spec tests: `uv run pytest tests/unit/spec/ tests/unit/graph/ tests/property/graph/ tests/integration/test_plan.py -q`
- Linter: `uv run ruff check agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`
- Type check: `uv run mypy agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create test fixtures
    - `tests/unit/spec/conftest.py`: fixtures that create temporary `.specs/`
      directories with sample `tasks.md` and `prd.md` files
    - `tests/unit/graph/conftest.py`: fixtures that build sample `TaskGraph`
      objects (acyclic, cyclic, with optional nodes)
    - Fixtures for sample `tasks.md` content: standard groups, optional
      markers, non-contiguous numbers, empty files

  - [ ] 1.2 Write discovery tests
    - `tests/unit/spec/test_discovery.py`: TS-02-1 (sorted discovery),
      TS-02-2 (filter), TS-02-E1 (no specs dir), TS-02-E2 (filter miss),
      TS-02-E3 (no tasks.md)
    - _Test Spec: TS-02-1, TS-02-2, TS-02-E1, TS-02-E2, TS-02-E3_

  - [ ] 1.3 Write parser tests
    - `tests/unit/spec/test_parser.py`: TS-02-3 (parse groups),
      TS-02-4 (optional marker), TS-02-E7 (empty tasks.md),
      TS-02-E8 (non-contiguous numbers)
    - _Test Spec: TS-02-3, TS-02-4, TS-02-E7, TS-02-E8_

  - [ ] 1.4 Write graph builder tests
    - `tests/unit/graph/test_builder.py`: TS-02-5 (intra-spec edges),
      TS-02-6 (cross-spec edges), TS-02-E5 (dangling ref)
    - _Test Spec: TS-02-5, TS-02-6, TS-02-E5_

  - [ ] 1.5 Write resolver tests
    - `tests/unit/graph/test_resolver.py`: TS-02-7 (topo sort),
      TS-02-E4 (cycle detection)
    - _Test Spec: TS-02-7, TS-02-E4_

  - [ ] 1.6 Write fast-mode tests
    - `tests/unit/graph/test_fast_mode.py`: TS-02-8 (remove optional),
      TS-02-9 (rewire deps)
    - _Test Spec: TS-02-8, TS-02-9_

  - [ ] 1.7 Write property tests
    - `tests/property/graph/test_resolver_props.py`: TS-02-P1 (topo order),
      TS-02-P4 (cycle detection)
    - `tests/property/graph/test_fast_mode_props.py`: TS-02-P2 (dep
      preservation), TS-02-P3 (node ID uniqueness)
    - `tests/property/spec/test_discovery_props.py`: TS-02-P5 (sort order)
    - _Test Spec: TS-02-P1, TS-02-P2, TS-02-P3, TS-02-P4, TS-02-P5_

  - [ ] 1.8 Write integration tests
    - `tests/integration/test_plan.py`: TS-02-10 (plan persist/load),
      TS-02-11 (CLI end-to-end), TS-02-E6 (corrupted plan.json)
    - _Test Spec: TS-02-10, TS-02-11, TS-02-E6_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/spec/ tests/unit/graph/ tests/property/graph/ tests/property/spec/`

- [ ] 2. Implement graph types and spec discovery
  - [ ] 2.1 Create graph types module
    - `agent_fox/graph/__init__.py`, `agent_fox/graph/types.py`:
      `NodeStatus` enum, `Node`, `Edge`, `PlanMetadata`, `TaskGraph`
      dataclasses with `predecessors()`, `successors()`, `ready_nodes()`
    - _Requirements: 02-REQ-3.3, 02-REQ-3.4_

  - [ ] 2.2 Create spec discovery module
    - `agent_fox/spec/__init__.py`, `agent_fox/spec/discovery.py`:
      `SpecInfo` dataclass, `discover_specs()` function
    - Scan `.specs/` for `NN_name/` pattern, sort by prefix
    - Handle missing directory, empty directory, filter
    - _Requirements: 02-REQ-1.1, 02-REQ-1.2, 02-REQ-1.3_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/spec/test_discovery.py tests/unit/graph/ -k "types or discovery" -q`
    - [ ] Property tests pass: `uv run pytest tests/property/spec/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/spec/ agent_fox/graph/`
    - [ ] Requirements 02-REQ-1.*, 02-REQ-3.3, 02-REQ-3.4 met

- [ ] 3. Implement task parser and graph builder
  - [ ] 3.1 Create task parser
    - `agent_fox/spec/parser.py`: `SubtaskDef`, `TaskGroupDef`,
      `CrossSpecDep` dataclasses, `parse_tasks()`, `parse_cross_deps()`
    - Parse checkbox markdown with regex
    - Detect optional `*` marker
    - Extract subtasks, title, body
    - Parse cross-spec dependency table from prd.md
    - _Requirements: 02-REQ-2.1, 02-REQ-2.2, 02-REQ-2.3, 02-REQ-2.4_

  - [ ] 3.2 Create graph builder
    - `agent_fox/graph/builder.py`: `build_graph()` function
    - Create nodes from parsed task groups
    - Add intra-spec sequential edges
    - Add cross-spec edges from dependency declarations
    - Validate: no dangling references
    - _Requirements: 02-REQ-3.1, 02-REQ-3.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/spec/test_parser.py tests/unit/graph/test_builder.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/spec/parser.py agent_fox/graph/builder.py`
    - [ ] Requirements 02-REQ-2.*, 02-REQ-3.1, 02-REQ-3.2 met

- [ ] 4. Implement resolver, fast mode, and plan persistence
  - [ ] 4.1 Implement dependency resolver
    - `agent_fox/graph/resolver.py`: `resolve_order()` using Kahn's
      algorithm with deterministic tie-breaking (spec prefix, then group
      number)
    - Cycle detection: raise PlanError listing cycle nodes
    - _Requirements: 02-REQ-4.1, 02-REQ-4.2_

  - [ ] 4.2 Implement fast-mode filter
    - `agent_fox/graph/fast_mode.py`: `apply_fast_mode()` function
    - Remove optional nodes, rewire dependencies (A -> B* -> C becomes
      A -> C), set removed nodes to SKIPPED status
    - _Requirements: 02-REQ-5.1, 02-REQ-5.2, 02-REQ-5.3_

  - [ ] 4.3 Implement plan persistence
    - Add `save_plan(graph, path)` and `load_plan(path)` functions to
      `agent_fox/graph/types.py` (or a new `agent_fox/graph/persistence.py`)
    - Serialize/deserialize TaskGraph to/from JSON
    - Handle corrupted files gracefully
    - _Requirements: 02-REQ-6.1, 02-REQ-6.2, 02-REQ-6.3, 02-REQ-6.4_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/graph/ -q`
    - [ ] Property tests pass: `uv run pytest tests/property/graph/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/graph/`
    - [ ] Requirements 02-REQ-4.*, 02-REQ-5.*, 02-REQ-6.* met

- [ ] 5. Implement plan CLI command and integration
  - [ ] 5.1 Create plan command
    - `agent_fox/cli/plan.py`: Click command with `--fast`, `--spec`,
      `--reanalyze`, `--verify` options
    - Wire up discovery -> parsing -> building -> resolving -> fast mode
      -> persistence pipeline
    - Print summary: specs found, total tasks, dependencies, execution
      order
    - Handle `--verify` with "not yet implemented" message
    - Register command with `main` group in `app.py`
    - _Requirements: 02-REQ-7.1, 02-REQ-7.2, 02-REQ-7.3, 02-REQ-7.4,
      02-REQ-7.5_

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/spec/ tests/unit/graph/ tests/property/graph/ tests/property/spec/ tests/integration/test_plan.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`
    - [ ] Type check passes: `uv run mypy agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`
    - [ ] Requirements 02-REQ-7.* met
    - [ ] CLI is invocable: `uv run agent-fox plan --help`

- [ ] 6. Checkpoint -- Planning Engine Complete
  - Ensure all tests pass: `uv run pytest tests/unit/spec/ tests/unit/graph/ tests/property/graph/ tests/property/spec/ tests/integration/test_plan.py -q`
  - Ensure linter clean: `uv run ruff check agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`
  - Ensure type check clean: `uv run mypy agent_fox/spec/ agent_fox/graph/ agent_fox/cli/plan.py`
  - Verify `uv run agent-fox plan` works end-to-end with the project's
    own `.specs/` directory

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 02-REQ-1.1 | TS-02-1 | 2.2 | tests/unit/spec/test_discovery.py |
| 02-REQ-1.2 | TS-02-2 | 2.2 | tests/unit/spec/test_discovery.py |
| 02-REQ-1.3 | TS-02-E3 | 2.2 | tests/unit/spec/test_discovery.py |
| 02-REQ-1.E1 | TS-02-E1 | 2.2 | tests/unit/spec/test_discovery.py |
| 02-REQ-1.E2 | TS-02-E2 | 2.2 | tests/unit/spec/test_discovery.py |
| 02-REQ-2.1 | TS-02-3 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-2.2 | TS-02-3 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-2.3 | TS-02-4 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-2.4 | TS-02-3 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-2.E1 | TS-02-E7 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-2.E2 | TS-02-E8 | 3.1 | tests/unit/spec/test_parser.py |
| 02-REQ-3.1 | TS-02-5 | 3.2 | tests/unit/graph/test_builder.py |
| 02-REQ-3.2 | TS-02-6 | 3.2 | tests/unit/graph/test_builder.py |
| 02-REQ-3.3 | TS-02-5 | 2.1 | tests/unit/graph/test_builder.py |
| 02-REQ-3.4 | TS-02-5 | 2.1 | tests/unit/graph/test_builder.py |
| 02-REQ-3.E1 | TS-02-E5 | 3.2 | tests/unit/graph/test_builder.py |
| 02-REQ-3.E2 | TS-02-E4 | 4.1 | tests/unit/graph/test_resolver.py |
| 02-REQ-4.1 | TS-02-7 | 4.1 | tests/unit/graph/test_resolver.py |
| 02-REQ-4.2 | TS-02-7 | 4.1 | tests/unit/graph/test_resolver.py |
| 02-REQ-4.E1 | TS-02-E7 | 4.1 | tests/unit/graph/test_resolver.py |
| 02-REQ-5.1 | TS-02-8 | 4.2 | tests/unit/graph/test_fast_mode.py |
| 02-REQ-5.2 | TS-02-9 | 4.2 | tests/unit/graph/test_fast_mode.py |
| 02-REQ-5.3 | TS-02-8 | 4.2 | tests/unit/graph/test_fast_mode.py |
| 02-REQ-6.1 | TS-02-10 | 4.3 | tests/integration/test_plan.py |
| 02-REQ-6.2 | TS-02-10 | 4.3 | tests/integration/test_plan.py |
| 02-REQ-6.3 | TS-02-10 | 4.3 | tests/integration/test_plan.py |
| 02-REQ-6.4 | TS-02-11 | 4.3 | tests/integration/test_plan.py |
| 02-REQ-6.E1 | TS-02-E6 | 4.3 | tests/integration/test_plan.py |
| 02-REQ-7.1 | TS-02-11 | 5.1 | tests/integration/test_plan.py |
| 02-REQ-7.2 | TS-02-11 | 5.1 | tests/integration/test_plan.py |
| 02-REQ-7.3 | TS-02-11 | 5.1 | tests/integration/test_plan.py |
| 02-REQ-7.4 | TS-02-11 | 5.1 | tests/integration/test_plan.py |
| 02-REQ-7.5 | TS-02-11 | 5.1 | tests/integration/test_plan.py |
| Property 1 | TS-02-P1 | 4.1 | tests/property/graph/test_resolver_props.py |
| Property 2 | TS-02-P2 | 4.2 | tests/property/graph/test_fast_mode_props.py |
| Property 3 | TS-02-P3 | 2.1, 3.2 | tests/property/graph/test_fast_mode_props.py |
| Property 4 | TS-02-P4 | 4.1 | tests/property/graph/test_resolver_props.py |
| Property 5 | TS-02-P5 | 2.2 | tests/property/spec/test_discovery_props.py |

## Notes

- This spec depends on spec 01 for CLI framework (`main` group, `BannerGroup`),
  config system (`load_config`, `AgentFoxConfig`), and error types (`PlanError`).
- The `NodeStatus` enum in `graph/types.py` is also referenced by
  `core/types.py` from spec 01 -- ensure they are the same type, not
  duplicates. Prefer defining it in `graph/types.py` and re-exporting from
  `core/types.py` if needed.
- Cross-spec dependency parsing reads the dependency table from each spec's
  `prd.md`. The table format is `| This Spec | Depends On | What It Uses |`.
  The builder interprets this as: the last group of the depended-on spec must
  complete before the first group of this spec.
- The `--verify` flag (REQ-016) is a placeholder. Accept the flag, print
  a message, and exit. Full implementation is deferred.
- Use `click.testing.CliRunner` for CLI integration tests.
- Use `tmp_path` fixtures for filesystem-dependent tests.
