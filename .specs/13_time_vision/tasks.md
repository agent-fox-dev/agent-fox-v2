# Implementation Plan: Time Vision -- Temporal Reasoning

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec adds temporal reasoning to the agent-fox knowledge system: causal
graph operations, temporal queries, predictive pattern detection, timeline
rendering, enriched fact extraction, and causal context enhancement. Task
groups are ordered tests-first, then infrastructure outward to CLI and
integration points.

## Dependencies

| Spec | What Must Be Complete |
|------|----------------------|
| 11 (DuckDB Knowledge Store) | `fact_causes` table exists, `KnowledgeDB` connection manager, `memory_facts` and `session_outcomes` tables |
| 12 (Fox Ball) | Fact extraction pipeline, embedding generation, vector search, `ask` command infrastructure |

## Test Commands

- Unit tests: `uv run pytest tests/unit/knowledge/ -q`
- Property tests: `uv run pytest tests/property/knowledge/ -q`
- All tests: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
- Linter: `uv run ruff check agent_fox/knowledge/ agent_fox/cli/patterns.py agent_fox/memory/ agent_fox/session/`
- Type check: `uv run mypy agent_fox/knowledge/ agent_fox/cli/patterns.py`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test fixtures
    - `tests/unit/knowledge/conftest.py`: shared `causal_db` fixture with
      in-memory DuckDB, schema creation, seeded facts, seeded causal links,
      and seeded session outcomes (as defined in test_spec.md fixtures)
    - Helper functions: `create_empty_db()`, `create_schema(conn)`,
      `seed_facts(conn)`, `seed_causal_links(conn)`,
      `seed_session_outcomes(conn)`

  - [x] 1.2 Write causal graph tests
    - `tests/unit/knowledge/test_causal.py`:
      TS-13-1 (add link), TS-13-2 (reject non-existent), TS-13-3 (get causes),
      TS-13-4 (get effects), TS-13-5 (traverse forward), TS-13-6 (traverse
      backward), TS-13-7 (max depth), TS-13-8 (isolated fact)
    - _Test Spec: TS-13-1 through TS-13-8_

  - [x] 1.3 Write temporal query and timeline tests
    - `tests/unit/knowledge/test_temporal.py`:
      TS-13-9 (build timeline), TS-13-10 (render plain text)
    - _Test Spec: TS-13-9, TS-13-10_

  - [x] 1.4 Write pattern detection tests
    - `tests/unit/knowledge/test_patterns.py`:
      TS-13-11 (detect patterns), TS-13-12 (insufficient data),
      TS-13-13 (render patterns)
    - _Test Spec: TS-13-11, TS-13-12, TS-13-13_

  - [x] 1.5 Write extraction enrichment tests
    - `tests/unit/knowledge/test_extraction_causal.py`:
      TS-13-14 (enrich prompt), TS-13-15 (parse links),
      TS-13-16 (malformed input)
    - _Test Spec: TS-13-14, TS-13-15, TS-13-16_

  - [x] 1.6 Write context enhancement tests
    - `tests/unit/knowledge/test_context_causal.py`:
      TS-13-17 (adds causal facts), TS-13-18 (respects budget),
      TS-13-19 (fact provenance)
    - _Test Spec: TS-13-17, TS-13-18, TS-13-19_

  - [x] 1.7 Write edge case tests
    - Add to relevant test files:
      TS-13-E1 (duplicate link) in `test_causal.py`
      TS-13-E2 (empty extraction) in `test_extraction_causal.py`
      TS-13-E3 (invalid JSON) in `test_extraction_causal.py`
      TS-13-E4 (timeline no links) in `test_temporal.py`
      TS-13-E5 (patterns empty store) in `test_patterns.py`
    - _Test Spec: TS-13-E1 through TS-13-E5_

  - [x] 1.8 Write property tests
    - `tests/property/knowledge/test_causal_props.py`:
      TS-13-P1 (idempotency), TS-13-P2 (depth bound), TS-13-P6 (referential
      integrity)
    - `tests/property/knowledge/test_temporal_props.py`:
      TS-13-P3 (timeline ordering)
    - `tests/property/knowledge/test_patterns_props.py`:
      TS-13-P4 (minimum threshold)
    - `tests/property/knowledge/test_context_props.py`:
      TS-13-P5 (budget compliance)
    - _Test Spec: TS-13-P1 through TS-13-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) -- no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Implement causal graph operations
  - [ ] 2.1 Create causal module
    - `agent_fox/knowledge/causal.py`: `CausalLink` and `CausalFact`
      dataclasses, `add_causal_link()` function with referential integrity
      check and idempotent insert
    - _Requirements: 13-REQ-3.1, 13-REQ-3.E1, 13-REQ-2.E2_

  - [ ] 2.2 Implement cause/effect queries
    - `agent_fox/knowledge/causal.py`: `get_causes()` and `get_effects()`
      functions with DuckDB joins to `memory_facts`
    - _Requirements: 13-REQ-3.2, 13-REQ-3.3_

  - [ ] 2.3 Implement causal chain traversal
    - `agent_fox/knowledge/causal.py`: `traverse_causal_chain()` with BFS,
      configurable max depth, direction control, cycle detection via visited
      set
    - _Requirements: 13-REQ-3.4_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_causal.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_causal_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/causal.py`
    - [ ] Requirements 13-REQ-3.* acceptance criteria met

- [ ] 3. Implement temporal queries and timeline rendering
  - [ ] 3.1 Create temporal module
    - `agent_fox/knowledge/temporal.py`: `TimelineNode` and `Timeline`
      dataclasses, `build_timeline()` function that traverses causal chains
      from seed facts, deduplicates, and sorts by timestamp
    - _Requirements: 13-REQ-4.1, 13-REQ-6.1, 13-REQ-6.2_

  - [ ] 3.2 Implement timeline rendering
    - `agent_fox/knowledge/temporal.py`: `Timeline.render()` method with
      indented text output, provenance display, and TTY-aware color control
    - _Requirements: 13-REQ-6.1, 13-REQ-6.2, 13-REQ-6.3_

  - [ ] 3.3 Implement temporal query function
    - `agent_fox/knowledge/temporal.py`: `temporal_query()` that combines
      vector search results with causal graph traversal to build a timeline
    - _Requirements: 13-REQ-4.1, 13-REQ-4.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_temporal.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_temporal_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/temporal.py`
    - [ ] Requirements 13-REQ-4.*, 13-REQ-6.* acceptance criteria met

- [ ] 4. Implement pattern detection and CLI command
  - [ ] 4.1 Create patterns module
    - `agent_fox/knowledge/patterns.py`: `Pattern` dataclass,
      `detect_patterns()` function with co-occurrence analysis across
      `session_outcomes` and `fact_causes`, confidence assignment
    - _Requirements: 13-REQ-5.1, 13-REQ-5.2, 13-REQ-5.E1_

  - [ ] 4.2 Implement pattern rendering
    - `agent_fox/knowledge/patterns.py`: `render_patterns()` function with
      plain text output and TTY-aware color control
    - _Requirements: 13-REQ-5.3_

  - [ ] 4.3 Create patterns CLI command
    - `agent_fox/cli/patterns.py`: `patterns_cmd` Click command with
      `--min-occurrences` option, registered in the CLI group
    - Wire up to `agent_fox/cli/app.py` command group
    - _Requirements: 13-REQ-5.3_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_patterns.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_patterns_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/patterns.py agent_fox/cli/patterns.py`
    - [ ] Requirements 13-REQ-5.* acceptance criteria met

- [ ] 5. Implement extraction enrichment and context enhancement
  - [ ] 5.1 Enrich extraction prompt
    - Extend `agent_fox/memory/extraction.py`:
      `CAUSAL_EXTRACTION_ADDENDUM` template,
      `enrich_extraction_with_causal()` function,
      `parse_causal_links()` function with robust error handling
    - _Requirements: 13-REQ-2.1, 13-REQ-2.2, 13-REQ-2.E1_

  - [ ] 5.2 Implement context enhancement
    - Extend `agent_fox/session/context.py`:
      `select_context_with_causal()` function that queries the causal graph
      for linked facts, deduplicates with keyword results, and respects the
      max_facts budget
    - _Requirements: 13-REQ-7.1, 13-REQ-7.2_

  - [ ] 5.3 Ensure fact provenance is populated
    - Verify that the fact storage path (from spec 12) populates
      `spec_name`, `session_id`, and `commit_sha` columns in `memory_facts`.
      Add provenance population if missing.
    - _Requirements: 13-REQ-1.1, 13-REQ-1.2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_extraction_causal.py tests/unit/knowledge/test_context_causal.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_context_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/extraction.py agent_fox/session/context.py`
    - [ ] Requirements 13-REQ-1.*, 13-REQ-2.*, 13-REQ-7.* acceptance criteria met

- [ ] 6. Checkpoint -- Time Vision Complete
  - All tests pass: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
  - Linter clean: `uv run ruff check agent_fox/knowledge/ agent_fox/cli/patterns.py agent_fox/memory/ agent_fox/session/`
  - Type check clean: `uv run mypy agent_fox/knowledge/ agent_fox/cli/patterns.py`
  - Verify `agent-fox patterns` works end-to-end with seeded data
  - Verify temporal `ask` queries traverse the causal graph

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 13-REQ-1.1 | TS-13-19 | 5.3 | tests/unit/knowledge/test_context_causal.py |
| 13-REQ-1.2 | TS-13-19 | 5.3 | tests/unit/knowledge/test_context_causal.py |
| 13-REQ-2.1 | TS-13-14 | 5.1 | tests/unit/knowledge/test_extraction_causal.py |
| 13-REQ-2.2 | TS-13-15 | 5.1 | tests/unit/knowledge/test_extraction_causal.py |
| 13-REQ-2.E1 | TS-13-16, TS-13-E2, TS-13-E3 | 5.1 | tests/unit/knowledge/test_extraction_causal.py |
| 13-REQ-2.E2 | TS-13-2, TS-13-P6 | 2.1 | tests/unit/knowledge/test_causal.py, tests/property/knowledge/test_causal_props.py |
| 13-REQ-3.1 | TS-13-1, TS-13-2, TS-13-P6 | 2.1 | tests/unit/knowledge/test_causal.py, tests/property/knowledge/test_causal_props.py |
| 13-REQ-3.2 | TS-13-3 | 2.2 | tests/unit/knowledge/test_causal.py |
| 13-REQ-3.3 | TS-13-4 | 2.2 | tests/unit/knowledge/test_causal.py |
| 13-REQ-3.4 | TS-13-5, TS-13-6, TS-13-7, TS-13-8, TS-13-P2 | 2.3 | tests/unit/knowledge/test_causal.py, tests/property/knowledge/test_causal_props.py |
| 13-REQ-3.E1 | TS-13-E1, TS-13-P1 | 2.1 | tests/unit/knowledge/test_causal.py, tests/property/knowledge/test_causal_props.py |
| 13-REQ-4.1 | TS-13-9, TS-13-E4 | 3.1, 3.3 | tests/unit/knowledge/test_temporal.py |
| 13-REQ-4.2 | TS-13-9 | 3.3 | tests/unit/knowledge/test_temporal.py |
| 13-REQ-5.1 | TS-13-11, TS-13-P4 | 4.1 | tests/unit/knowledge/test_patterns.py, tests/property/knowledge/test_patterns_props.py |
| 13-REQ-5.2 | TS-13-11, TS-13-P4 | 4.1 | tests/unit/knowledge/test_patterns.py, tests/property/knowledge/test_patterns_props.py |
| 13-REQ-5.3 | TS-13-13 | 4.2, 4.3 | tests/unit/knowledge/test_patterns.py |
| 13-REQ-5.E1 | TS-13-12, TS-13-E5 | 4.1 | tests/unit/knowledge/test_patterns.py |
| 13-REQ-6.1 | TS-13-9, TS-13-10, TS-13-P3 | 3.2 | tests/unit/knowledge/test_temporal.py, tests/property/knowledge/test_temporal_props.py |
| 13-REQ-6.2 | TS-13-9, TS-13-P3 | 3.2 | tests/unit/knowledge/test_temporal.py, tests/property/knowledge/test_temporal_props.py |
| 13-REQ-6.3 | TS-13-10 | 3.2 | tests/unit/knowledge/test_temporal.py |
| 13-REQ-7.1 | TS-13-17 | 5.2 | tests/unit/knowledge/test_context_causal.py |
| 13-REQ-7.2 | TS-13-17, TS-13-18, TS-13-P5 | 5.2 | tests/unit/knowledge/test_context_causal.py, tests/property/knowledge/test_context_props.py |
| Property 1 | TS-13-P6 | 2.1 | tests/property/knowledge/test_causal_props.py |
| Property 2 | TS-13-P1 | 2.1 | tests/property/knowledge/test_causal_props.py |
| Property 3 | TS-13-P2 | 2.3 | tests/property/knowledge/test_causal_props.py |
| Property 5 | TS-13-P3 | 3.1 | tests/property/knowledge/test_temporal_props.py |
| Property 6 | TS-13-P4 | 4.1 | tests/property/knowledge/test_patterns_props.py |
| Property 7 | TS-13-P5 | 5.2 | tests/property/knowledge/test_context_props.py |
| Property 8 | TS-13-E2, TS-13-E3 | 5.1 | tests/unit/knowledge/test_extraction_causal.py |

## Notes

- All DuckDB tests use in-memory databases (`duckdb.connect(":memory:")`) with
  seeded data. No tests touch the real knowledge store.
- Extraction tests use mock model responses -- no real Anthropic API calls.
- The `fact_causes` table is created by spec 11; this spec only populates it.
- The `patterns` CLI command must be registered in the existing Click group
  from spec 01.
- Context enhancement is additive to the existing keyword matching from REQ-061;
  it does not replace it.
- Causal chain traversal uses application-level BFS, not recursive SQL CTEs,
  for precise depth control and cycle detection.
