# Implementation Plan: Rich Memory Rendering

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation modifies approximately 100-140 lines in
`agent_fox/knowledge/rendering.py` plus test files. All enrichment data
already exists in DuckDB tables. No schema changes needed.

Three task groups: (1) write failing tests, (2) implement enrichment loading
and rich rendering, (3) wiring verification.

## Test Commands

- Unit tests: `uv run pytest tests/unit/knowledge/test_rich_rendering.py -q`
- Property tests: `uv run pytest tests/property/knowledge/test_rich_rendering_props.py -q`
- Integration tests: `uv run pytest tests/integration/knowledge/test_rich_rendering_smoke.py -q`
- All spec tests: `uv run pytest tests/unit/knowledge/test_rich_rendering.py tests/property/knowledge/test_rich_rendering_props.py tests/integration/knowledge/test_rich_rendering_smoke.py -q`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/knowledge/rendering.py tests/unit/knowledge/test_rich_rendering.py tests/property/knowledge/test_rich_rendering_props.py tests/integration/knowledge/test_rich_rendering_smoke.py`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create unit test file
    - Create `tests/unit/knowledge/test_rich_rendering.py`
    - Test `_format_relative_age()`, `_render_fact()`, `load_enrichments()`,
      `render_summary()` with mocked DuckDB connections
    - _Test Spec: TS-111-1 through TS-111-25_

  - [ ] 1.2 Create property tests
    - Create `tests/property/knowledge/test_rich_rendering_props.py`
    - Age format correctness, sort stability, sub-bullet bounds, enrichment
      independence, graceful degradation, truncation boundary
    - _Test Spec: TS-111-P1 through TS-111-P6_

  - [ ] 1.3 Create integration smoke tests
    - Create `tests/integration/knowledge/test_rich_rendering_smoke.py`
    - Full rendering path with in-memory DuckDB and seeded enrichment data
    - _Test Spec: TS-111-SMOKE-1, TS-111-SMOKE-2_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/knowledge/test_rich_rendering.py tests/property/knowledge/test_rich_rendering_props.py tests/integration/knowledge/test_rich_rendering_smoke.py`

- [ ] 2. Implement enrichment loading and rich rendering
  - [ ] 2.1 Add constants and `Enrichments` dataclass to `rendering.py`
    - Add `_MAX_CAUSES = 2`, `_MAX_EFFECTS = 2`, `_MAX_ENTITY_PATHS = 3`,
      `_CAUSE_TRUNCATE = 60`, `_SUPERSEDED_TRUNCATE = 80`
    - Add `Enrichments` dataclass with `causes`, `effects`, `entity_paths`,
      `superseded` fields
    - _Requirements: 111-REQ-4.2, 111-REQ-5.1, 111-REQ-5.2, 111-REQ-6.1_

  - [ ] 2.2 Implement `_format_relative_age()` in `rendering.py`
    - Parse ISO timestamp, compute delta from `now`
    - Return "Xd ago" / "Xmo ago" / "Xy ago" based on day thresholds
    - Return `None` on parse failure
    - _Requirements: 111-REQ-2.1, 111-REQ-2.2, 111-REQ-2.E1_

  - [ ] 2.3 Implement `load_enrichments()` in `rendering.py`
    - Execute 4 batch queries (causes, effects, entity paths, superseded)
    - Each query wrapped in try/except with warning log on failure
    - Return empty `Enrichments` when `conn is None`
    - _Requirements: 111-REQ-7.1, 111-REQ-7.2, 111-REQ-7.E1, 111-REQ-7.E2_

  - [ ] 2.4 Update `_render_fact()` in `rendering.py`
    - Add `enrichments` and `now` parameters
    - Include relative age in metadata parenthetical
    - Render cause, effect, files, and replaces sub-bullets with limits and
      truncation
    - _Requirements: 111-REQ-2.3, 111-REQ-4.1, 111-REQ-4.2, 111-REQ-5.1,
      111-REQ-5.2, 111-REQ-6.1, 111-REQ-4.E1, 111-REQ-5.E1, 111-REQ-5.E2,
      111-REQ-6.E1_

  - [ ] 2.5 Update `render_summary()` in `rendering.py`
    - Add summary header line with fact count and last-updated date
    - Sort facts by confidence desc, created_at desc before grouping
    - Call `load_enrichments()` and pass to `_render_fact()`
    - Pass `datetime.now(UTC)` for age computation
    - _Requirements: 111-REQ-1.1, 111-REQ-1.2, 111-REQ-1.E1, 111-REQ-3.1,
      111-REQ-3.E1_

  - [ ] 2.V Verify task group 2
    - [ ] All spec tests pass: `uv run pytest tests/unit/knowledge/test_rich_rendering.py tests/property/knowledge/test_rich_rendering_props.py tests/integration/knowledge/test_rich_rendering_smoke.py -q`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/rendering.py`
    - [ ] Requirements 111-REQ-1.* through 111-REQ-7.* acceptance criteria met

- [ ] 3. Wiring verification

  - [ ] 3.1 Trace execution paths from design.md
    - Verify `render_summary()` calls `load_enrichments()` which executes 4
      batch queries
    - Verify `_render_fact()` receives and uses enrichment data
    - Verify `_format_relative_age()` is called for each fact
    - _Requirements: all_

  - [ ] 3.2 Verify existing callers of `render_summary()` still work
    - Grep for all call sites of `render_summary()`
    - Confirm the signature change (no new required params) is backward
      compatible
    - _Requirements: all_

  - [ ] 3.3 Run the integration smoke tests
    - All `TS-111-SMOKE-*` tests pass with real DuckDB (no stub bypass)
    - _Test Spec: TS-111-SMOKE-1, TS-111-SMOKE-2_

  - [ ] 3.4 Stub / dead-code audit
    - Search `rendering.py` for: `return []`, `return None` on non-Optional
      returns, `pass` in non-abstract methods, `# TODO`, `# stub`,
      `NotImplementedError`
    - Each hit must be justified or replaced
    - Document any intentional stubs here with rationale

  - [ ] 3.5 Output quality check
    - Generate `docs/memory.md` from the actual knowledge database
    - Verify the output is valid, readable markdown
    - Verify sub-bullets render correctly and are not excessive
    - _Requirements: all_

  - [ ] 3.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in `rendering.py`
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] `render_summary()` signature is backward compatible
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 111-REQ-1.1 | TS-111-1 | 2.5 | `test_rich_rendering.py::test_summary_header` |
| 111-REQ-1.2 | TS-111-1 | 2.5 | `test_rich_rendering.py::test_summary_header` |
| 111-REQ-1.E1 | TS-111-2 | 2.5 | `test_rich_rendering.py::test_summary_header_unparseable_dates` |
| 111-REQ-2.1 | TS-111-3 | 2.2 | `test_rich_rendering.py::test_relative_age_days` |
| 111-REQ-2.2 | TS-111-3..6 | 2.2 | `test_rich_rendering.py::test_relative_age_*` |
| 111-REQ-2.3 | TS-111-8 | 2.4 | `test_rich_rendering.py::test_metadata_with_age` |
| 111-REQ-2.E1 | TS-111-7, TS-111-9 | 2.2, 2.4 | `test_rich_rendering.py::test_relative_age_missing`, `test_metadata_without_age` |
| 111-REQ-3.1 | TS-111-10 | 2.5 | `test_rich_rendering.py::test_fact_ordering` |
| 111-REQ-3.E1 | TS-111-11 | 2.5 | `test_rich_rendering.py::test_fact_ordering_stability` |
| 111-REQ-4.1 | TS-111-12 | 2.4 | `test_rich_rendering.py::test_entity_path_subbullets` |
| 111-REQ-4.2 | TS-111-13 | 2.4 | `test_rich_rendering.py::test_entity_path_overflow` |
| 111-REQ-4.E1 | TS-111-14 | 2.4 | `test_rich_rendering.py::test_no_entity_paths` |
| 111-REQ-5.1 | TS-111-15, TS-111-17 | 2.4 | `test_rich_rendering.py::test_cause_subbullets`, `test_cause_effect_limit` |
| 111-REQ-5.2 | TS-111-16, TS-111-17 | 2.4 | `test_rich_rendering.py::test_effect_subbullets`, `test_cause_effect_limit` |
| 111-REQ-5.E1 | TS-111-18 | 2.4 | `test_rich_rendering.py::test_no_causal_links` |
| 111-REQ-5.E2 | TS-111-15 | 2.4 | `test_rich_rendering.py::test_cause_subbullets` |
| 111-REQ-6.1 | TS-111-19 | 2.4 | `test_rich_rendering.py::test_supersession_subbullet` |
| 111-REQ-6.E1 | TS-111-20 | 2.4 | `test_rich_rendering.py::test_no_supersession` |
| 111-REQ-7.1 | TS-111-21 | 2.3 | `test_rich_rendering.py::test_enrichment_loading` |
| 111-REQ-7.2 | TS-111-21 | 2.3 | `test_rich_rendering.py::test_enrichment_loading` |
| 111-REQ-7.E1 | TS-111-22 | 2.3 | `test_rich_rendering.py::test_enrichment_query_failure_isolation` |
| 111-REQ-7.E2 | TS-111-23 | 2.3 | `test_rich_rendering.py::test_enrichment_none_connection` |
| Property 1 | TS-111-P1 | 2.2 | `test_rich_rendering_props.py::test_age_format_correctness` |
| Property 2 | TS-111-P2 | 2.5 | `test_rich_rendering_props.py::test_sort_stability` |
| Property 3 | TS-111-P3 | 2.4 | `test_rich_rendering_props.py::test_subbullet_bounds` |
| Property 4 | TS-111-P4 | 2.3 | `test_rich_rendering_props.py::test_enrichment_independence` |
| Property 5 | TS-111-P5 | 2.5 | `test_rich_rendering_props.py::test_graceful_degradation` |
| Property 6 | TS-111-P6 | 2.4 | `test_rich_rendering_props.py::test_truncation_boundary` |
| Path 1 | TS-111-SMOKE-1 | 3.3 | `test_rich_rendering_smoke.py::test_end_to_end_rich_rendering` |
| Path 2 | TS-111-SMOKE-2 | 3.3 | `test_rich_rendering_smoke.py::test_rendering_empty_enrichments` |

## Notes

- All enrichment data already exists in DuckDB -- no schema migrations needed.
- The implementation touches only `agent_fox/knowledge/rendering.py`.
- The `render_summary()` signature is unchanged (same params, same defaults),
  so all existing call sites remain compatible.
- Enrichment queries follow existing patterns from `causal.py` and
  `entity_query.py` for UUID casting and JOIN structure.
- The `Enrichments` dataclass is internal to `rendering.py` and not exported.
