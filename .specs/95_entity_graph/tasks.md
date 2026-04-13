# Implementation Plan: Entity Graph

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The entity graph subsystem is built bottom-up: schema and data models first,
then DuckDB operations, then tree-sitter analysis, then fact-entity linking,
and finally graph queries. Each group builds on the previous one. The subsystem
is standalone -- no wiring into the knowledge harvest pipeline or context
builder.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_entity_store.py tests/unit/knowledge/test_entity_query.py tests/unit/knowledge/test_static_analysis.py tests/unit/knowledge/test_entity_linker.py tests/integration/knowledge/test_entity_graph_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/test_entity_store.py tests/unit/knowledge/test_entity_query.py tests/unit/knowledge/test_static_analysis.py tests/unit/knowledge/test_entity_linker.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_entity_graph_props.py`
- All tests: `uv run pytest -q`
- Linter: `make lint`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Set up test file structure
    - Create `tests/unit/knowledge/test_entity_store.py` for TS-95-1 through
      TS-95-11, TS-95-E1 through TS-95-E4, TS-95-E12, TS-95-E13
    - Create `tests/unit/knowledge/test_static_analysis.py` for TS-95-12
      through TS-95-17, TS-95-E5 through TS-95-E7
    - Create `tests/unit/knowledge/test_entity_linker.py` for TS-95-18
      through TS-95-21, TS-95-E8, TS-95-E9
    - Create `tests/unit/knowledge/test_entity_query.py` for TS-95-22
      through TS-95-26, TS-95-E10, TS-95-E11
    - Create `tests/property/knowledge/test_entity_graph_props.py` for
      TS-95-P1 through TS-95-P6
    - Create `tests/integration/knowledge/test_entity_graph_smoke.py` for
      TS-95-SMOKE-1 through TS-95-SMOKE-4
    - Use existing conftest.py fixtures for DuckDB connections where available;
      create new fixtures as needed
    - _Test Spec: TS-95-1 through TS-95-28, TS-95-E1 through TS-95-E13,
      TS-95-P1 through TS-95-P6, TS-95-SMOKE-1 through TS-95-SMOKE-4_

  - [ ] 1.2 Translate acceptance-criterion tests from test_spec.md
    - One test function per TS-95-{N} entry (28 tests)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - Import from `agent_fox.knowledge.entities`,
      `agent_fox.knowledge.entity_store`, `agent_fox.knowledge.static_analysis`,
      `agent_fox.knowledge.entity_linker`, `agent_fox.knowledge.entity_query`
    - _Test Spec: TS-95-1 through TS-95-28_

  - [ ] 1.3 Translate edge-case tests from test_spec.md
    - One test function per TS-95-E{N} entry (13 tests)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-95-E1 through TS-95-E13_

  - [ ] 1.4 Translate property tests from test_spec.md
    - One property test per TS-95-P{N} entry (6 tests)
    - Use Hypothesis with `suppress_health_check=[HealthCheck.function_scoped_fixture]`
    - _Test Spec: TS-95-P1 through TS-95-P6_

  - [ ] 1.5 Translate integration smoke tests from test_spec.md
    - One test per TS-95-SMOKE-{N} entry (4 tests)
    - Use real DuckDB connections, real tree-sitter parser
    - Mock only subprocess (git) calls
    - _Test Spec: TS-95-SMOKE-1 through TS-95-SMOKE-4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `make lint`

- [ ] 2. Schema, data models, and entity store
  - [ ] 2.1 Create `agent_fox/knowledge/entities.py`
    - Define `EntityType(StrEnum)`, `EdgeType(StrEnum)`, `Entity`,
      `EntityEdge`, `AnalysisResult`, `LinkResult` dataclasses
    - Define `normalize_path(path, repo_root=None)` utility function
    - _Requirements: 95-REQ-1.2, 95-REQ-1.3, 95-REQ-1.4, 95-REQ-2.2_

  - [ ] 2.2 Add migration v8 to `agent_fox/knowledge/migrations.py`
    - Create `entity_graph`, `entity_edges`, `fact_entities` tables
    - Create indexes: natural key, deleted_at, entity_path, edge source/target,
      fact_entity entity
    - Register migration in the `MIGRATIONS` list
    - _Requirements: 95-REQ-1.1, 95-REQ-2.1, 95-REQ-3.1_

  - [ ] 2.3 Create `agent_fox/knowledge/entity_store.py`
    - Implement `upsert_entities()`: UUID assignment, natural key dedup,
      soft-delete restoration
    - Implement `upsert_edges()`: referential integrity check, self-edge
      rejection, duplicate ignore
    - Implement `create_fact_entity_links()`: referential integrity check,
      duplicate ignore
    - Implement `find_entities_by_path()` and `find_entities_by_paths()`
    - Implement `soft_delete_missing()`: set `deleted_at` for entities not in
      the found set
    - Implement `gc_stale_entities()`: retention_days validation, cascade delete
      edges and links, hard-delete entities
    - _Requirements: 95-REQ-1.E1, 95-REQ-1.E2, 95-REQ-2.3, 95-REQ-2.4,
      95-REQ-2.E1, 95-REQ-3.2, 95-REQ-3.3, 95-REQ-3.E1, 95-REQ-7.1,
      95-REQ-7.2, 95-REQ-7.E1, 95-REQ-7.E2_

  - [ ] 2.4 Add `tree-sitter` and `tree-sitter-python` to project dependencies
    - Update `pyproject.toml` dependencies
    - Run `uv sync --group dev`
    - _Requirements: (infrastructure for 95-REQ-4.*)_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_entity_store.py -k "schema or uuid or path_norm or entity_type or edge_table or relationship or referential or dedup or self_ref or soft_del or gc or fact_entity"`
    - [ ] Property tests P1, P2, P5, P6 pass: `uv run pytest -q tests/property/knowledge/test_entity_graph_props.py -k "normalization or idempotency or integrity or cascade"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 95-REQ-1.*, 95-REQ-2.*, 95-REQ-3.*, 95-REQ-7.* acceptance criteria met

- [ ] 3. Tree-sitter static analysis
  - [ ] 3.1 Create `agent_fox/knowledge/static_analysis.py`
    - Implement `_scan_python_files(repo_root)`: walk directory tree, respect
      `.gitignore`, collect `*.py` files
    - Implement `_build_module_map(repo_root, py_files)`: map dotted Python
      paths to repo-relative file paths, identify `__init__.py`-based packages
    - _Requirements: 95-REQ-4.1, 95-REQ-4.6_

  - [ ] 3.2 Implement tree-sitter entity extraction
    - Implement `_parse_file(file_path, parser)`: parse a Python file with
      tree-sitter, return Tree or None on error
    - Implement `_extract_entities(tree, rel_path)`: extract file, class, and
      function entities from parsed tree, use qualified names for methods
    - _Requirements: 95-REQ-4.2, 95-REQ-4.E1_

  - [ ] 3.3 Implement tree-sitter edge extraction
    - Implement `_extract_edges(tree, rel_path, entities, module_map)`: extract
      contains, imports, and extends edges
    - Resolve imports via module map, log warning for unresolvable imports
    - Extract extends edges from class base lists
    - _Requirements: 95-REQ-4.3, 95-REQ-4.6_

  - [ ] 3.4 Implement `analyze_codebase()` orchestrator
    - Scan files, build module map, extract module entities from packages
    - Parse each file, extract entities and edges
    - Call `upsert_entities()`, `upsert_edges()`, `soft_delete_missing()`
    - Return `AnalysisResult` with counts
    - Validate repo_root exists and is a directory
    - _Requirements: 95-REQ-4.4, 95-REQ-4.5, 95-REQ-4.E2, 95-REQ-4.E3_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_static_analysis.py`
    - [ ] Smoke test 1 passes: `uv run pytest -q tests/integration/knowledge/test_entity_graph_smoke.py -k "SMOKE_1 or smoke_1 or analysis"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 95-REQ-4.* acceptance criteria met

- [ ] 4. Fact-entity linking and graph queries
  - [ ] 4.1 Create `agent_fox/knowledge/entity_linker.py`
    - Implement `_extract_paths_from_diff(commit_sha, repo_root)`: run
      `git diff --name-only` via subprocess, return repo-relative paths
    - Implement `link_facts(conn, facts, repo_root)`: iterate facts, extract
      paths, look up entities, create links, return `LinkResult`
    - Handle missing commit_sha (skip), failed git diff (warn + skip),
      unmatched paths (skip)
    - _Requirements: 95-REQ-5.1, 95-REQ-5.2, 95-REQ-5.3, 95-REQ-5.4,
      95-REQ-5.E1, 95-REQ-5.E2_

  - [ ] 4.2 Create `agent_fox/knowledge/entity_query.py`
    - Implement `traverse_neighbors()`: recursive CTE BFS, max_depth,
      max_entities, relationship_types filter, soft-delete exclusion
    - Implement `get_facts_for_entities()`: join fact_entities with
      memory_facts, exclude superseded
    - Implement `find_related_facts()`: convenience function composing
      find_entities_by_path + traverse_neighbors + get_facts_for_entities
    - _Requirements: 95-REQ-6.1, 95-REQ-6.2, 95-REQ-6.3, 95-REQ-6.4,
      95-REQ-6.5, 95-REQ-6.E1, 95-REQ-6.E2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_entity_linker.py tests/unit/knowledge/test_entity_query.py`
    - [ ] Property tests P3 and P4 pass: `uv run pytest -q tests/property/knowledge/test_entity_graph_props.py -k "traversal or soft_delete"`
    - [ ] Smoke tests 2, 3, 4 pass: `uv run pytest -q tests/integration/knowledge/test_entity_graph_smoke.py -k "SMOKE_2 or SMOKE_3 or SMOKE_4 or linking or query or gc"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `make lint`
    - [ ] Requirements 95-REQ-5.*, 95-REQ-6.* acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - For each of the 4 paths, verify the entry point calls the next function
      in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code -- errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Grep for callers of each such function; confirm none discards the return
    - Key return value chains:
      - `_extract_entities()` -> `analyze_codebase()` -> `upsert_entities()`
      - `_extract_paths_from_diff()` -> `link_facts()` -> `find_entities_by_paths()` -> `create_fact_entity_links()`
      - `find_entities_by_path()` -> `traverse_neighbors()` -> `get_facts_for_entities()` -> `find_related_facts()`
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - All `TS-95-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/knowledge/test_entity_graph_smoke.py`
    - _Test Spec: TS-95-SMOKE-1 through TS-95-SMOKE-4_

  - [ ] 5.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 5.5 Cross-spec entry point verification
    - This spec is standalone (no cross-spec callers expected). Verify that
      all four public entry points (`analyze_codebase`, `link_facts`,
      `find_related_facts`, `gc_stale_entities`) are importable and callable
      from outside the knowledge package
    - Confirm no circular imports are introduced
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All public entry points are importable without circular imports
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 95-REQ-1.1 | TS-95-1 | 2.2 | test_entity_store::test_entity_table_schema |
| 95-REQ-1.2 | TS-95-2 | 2.1, 2.3 | test_entity_store::test_entity_uuid |
| 95-REQ-1.3 | TS-95-3 | 2.1 | test_entity_store::test_path_normalization |
| 95-REQ-1.4 | TS-95-4 | 2.1, 2.3 | test_entity_store::test_entity_types |
| 95-REQ-1.E1 | TS-95-E1 | 2.3 | test_entity_store::test_upsert_existing_active |
| 95-REQ-1.E2 | TS-95-E2 | 2.3 | test_entity_store::test_upsert_restores_deleted |
| 95-REQ-2.1 | TS-95-5 | 2.2 | test_entity_store::test_edge_table_schema |
| 95-REQ-2.2 | TS-95-6 | 2.1, 2.3 | test_entity_store::test_edge_relationship_types |
| 95-REQ-2.3 | TS-95-7 | 2.3 | test_entity_store::test_edge_referential_integrity |
| 95-REQ-2.4 | TS-95-8 | 2.3 | test_entity_store::test_edge_dedup |
| 95-REQ-2.E1 | TS-95-E3 | 2.3 | test_entity_store::test_self_edge_rejected |
| 95-REQ-3.1 | TS-95-9 | 2.2 | test_entity_store::test_fact_entity_schema |
| 95-REQ-3.2 | TS-95-10 | 2.3 | test_entity_store::test_fact_entity_integrity |
| 95-REQ-3.3 | TS-95-11 | 2.3 | test_entity_store::test_fact_entity_dedup |
| 95-REQ-3.E1 | TS-95-E4 | 2.3 | test_entity_store::test_link_to_soft_deleted |
| 95-REQ-4.1 | TS-95-12 | 3.1 | test_static_analysis::test_scan_python_files |
| 95-REQ-4.2 | TS-95-13 | 3.2 | test_static_analysis::test_extract_entities |
| 95-REQ-4.3 | TS-95-14 | 3.3 | test_static_analysis::test_extract_edges |
| 95-REQ-4.4 | TS-95-15 | 3.4 | test_static_analysis::test_analysis_result_counts |
| 95-REQ-4.5 | TS-95-16 | 3.4 | test_static_analysis::test_soft_delete_on_reanalysis |
| 95-REQ-4.6 | TS-95-17 | 3.1, 3.3 | test_static_analysis::test_import_resolution |
| 95-REQ-4.E1 | TS-95-E5 | 3.2 | test_static_analysis::test_unparseable_file |
| 95-REQ-4.E2 | TS-95-E6 | 3.4 | test_static_analysis::test_nonexistent_root |
| 95-REQ-4.E3 | TS-95-E7 | 3.4 | test_static_analysis::test_empty_repo |
| 95-REQ-5.1 | TS-95-18 | 4.1 | test_entity_linker::test_git_diff_extraction |
| 95-REQ-5.2 | TS-95-19 | 4.1 | test_entity_linker::test_fact_entity_link_creation |
| 95-REQ-5.3 | TS-95-20 | 4.1 | test_entity_linker::test_link_result_counts |
| 95-REQ-5.4 | TS-95-21 | 4.1 | test_entity_linker::test_skip_no_commit_sha |
| 95-REQ-5.E1 | TS-95-E8 | 4.1 | test_entity_linker::test_missing_commit |
| 95-REQ-5.E2 | TS-95-E9 | 4.1 | test_entity_linker::test_unmatched_paths |
| 95-REQ-6.1 | TS-95-22 | 4.2 | test_entity_query::test_traversal_max_depth |
| 95-REQ-6.2 | TS-95-23 | 4.2 | test_entity_query::test_traversal_max_entities |
| 95-REQ-6.3 | TS-95-24 | 4.2 | test_entity_query::test_traversal_relationship_filter |
| 95-REQ-6.4 | TS-95-25 | 4.2 | test_entity_query::test_get_facts_for_entities |
| 95-REQ-6.5 | TS-95-26 | 4.2 | test_entity_query::test_find_related_facts |
| 95-REQ-6.E1 | TS-95-E10 | 4.2 | test_entity_query::test_no_matching_entities |
| 95-REQ-6.E2 | TS-95-E11 | 4.2 | test_entity_query::test_exclude_soft_deleted |
| 95-REQ-7.1 | TS-95-27 | 2.3 | test_entity_store::test_soft_delete_preserves |
| 95-REQ-7.2 | TS-95-28 | 2.3 | test_entity_store::test_gc_cascade |
| 95-REQ-7.E1 | TS-95-E12 | 2.3 | test_entity_store::test_gc_invalid_retention |
| 95-REQ-7.E2 | TS-95-E13 | 2.3 | test_entity_store::test_gc_no_eligible |
| Property 1 | TS-95-P1 | 2.1 | test_entity_graph_props::test_path_normalization |
| Property 2 | TS-95-P2 | 2.3 | test_entity_graph_props::test_upsert_idempotency |
| Property 3 | TS-95-P3 | 4.2 | test_entity_graph_props::test_traversal_bound |
| Property 4 | TS-95-P4 | 4.2 | test_entity_graph_props::test_soft_delete_exclusion |
| Property 5 | TS-95-P5 | 2.3 | test_entity_graph_props::test_referential_integrity |
| Property 6 | TS-95-P6 | 2.3 | test_entity_graph_props::test_gc_cascade_completeness |
| Path 1 | TS-95-SMOKE-1 | 3.4 | test_entity_graph_smoke::test_full_analysis |
| Path 2 | TS-95-SMOKE-2 | 4.1 | test_entity_graph_smoke::test_fact_linking |
| Path 3 | TS-95-SMOKE-3 | 4.2 | test_entity_graph_smoke::test_graph_query |
| Path 4 | TS-95-SMOKE-4 | 2.3 | test_entity_graph_smoke::test_gc |

## Notes

- **tree-sitter dependency:** `tree-sitter` and `tree-sitter-python` are new
  dependencies. Add them to `pyproject.toml` in task group 2 and verify they
  install cleanly with `uv sync`.
- **Hypothesis health checks:** Use
  `suppress_health_check=[HealthCheck.function_scoped_fixture]` for property
  tests that use pytest fixtures.
- **subprocess mocking:** All `git diff` calls in tests should mock
  `subprocess.run` to avoid requiring a real git history.
- **Temp directories:** Static analysis tests should create temporary directory
  trees with Python files as fixtures. Use `tmp_path` from pytest.
- **Standalone delivery:** This spec delivers a callable library. No production
  code outside `agent_fox/knowledge/` calls these functions yet. The wiring
  verification confirms the APIs are importable and the code paths are
  complete, but does not verify production callers (there are none by design).
