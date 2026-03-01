# Implementation Plan: Structured Memory

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the structured memory system for agent-fox v2. Task
groups are ordered: tests first, then types and store, then extraction, then
context selection, then compaction and rendering.

## Test Commands

- Unit tests: `uv run pytest tests/unit/memory/ -q`
- Property tests: `uv run pytest tests/property/memory/ -q`
- All memory tests: `uv run pytest tests/unit/memory/ tests/property/memory/ -q`
- Linter: `uv run ruff check agent_fox/memory/`
- Type check: `uv run mypy agent_fox/memory/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Write type and store tests
    - `tests/unit/memory/test_types.py`: TS-05-1 (fact creation), TS-05-2
      (category enum)
    - `tests/unit/memory/test_store.py`: TS-05-4 (append/load round-trip),
      TS-05-5 (create file if missing), TS-05-12 (load by spec)
    - _Test Spec: TS-05-1, TS-05-2, TS-05-4, TS-05-5, TS-05-12_

  - [ ] 1.2 Write extraction tests
    - `tests/unit/memory/test_extraction.py`: TS-05-3 (valid LLM response)
    - Mock LLM client to return predetermined JSON responses
    - _Test Spec: TS-05-3_

  - [ ] 1.3 Write filter tests
    - `tests/unit/memory/test_filter.py`: TS-05-6 (select by spec name),
      TS-05-7 (keyword ranking), TS-05-8 (budget enforcement)
    - _Test Spec: TS-05-6, TS-05-7, TS-05-8_

  - [ ] 1.4 Write compaction tests
    - `tests/unit/memory/test_compaction.py`: TS-05-9 (dedup by content hash),
      TS-05-10 (supersession chain resolution)
    - _Test Spec: TS-05-9, TS-05-10_

  - [ ] 1.5 Write render tests
    - `tests/unit/memory/test_render.py`: TS-05-11 (markdown generation)
    - _Test Spec: TS-05-11_

  - [ ] 1.6 Write edge case tests
    - `tests/unit/memory/test_extraction.py`: TS-05-E1 (invalid JSON),
      TS-05-E2 (zero facts), TS-05-E3 (unknown category)
    - `tests/unit/memory/test_store.py`: TS-05-E4 (nonexistent file)
    - `tests/unit/memory/test_filter.py`: TS-05-E5 (no matching facts)
    - `tests/unit/memory/test_compaction.py`: TS-05-E6 (empty knowledge base)
    - `tests/unit/memory/test_render.py`: TS-05-E7 (create docs dir),
      TS-05-E8 (empty knowledge base)
    - _Test Spec: TS-05-E1..TS-05-E8_

  - [ ] 1.7 Write property tests
    - `tests/property/memory/test_filter_props.py`: TS-05-P1 (budget
      enforcement)
    - `tests/property/memory/test_compaction_props.py`: TS-05-P2
      (idempotency), TS-05-P4 (dedup determinism), TS-05-P6 (supersession
      chains)
    - `tests/property/memory/test_store_props.py`: TS-05-P3 (serialization
      round-trip)
    - `tests/property/memory/test_types_props.py`: TS-05-P5 (category
      completeness)
    - _Test Spec: TS-05-P1..TS-05-P6_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/memory/ tests/property/memory/`

- [ ] 2. Implement types and store
  - [ ] 2.1 Create memory package
    - `agent_fox/memory/__init__.py`: package init
    - `agent_fox/memory/types.py`: Fact dataclass, Category enum (6 values),
      ConfidenceLevel enum (high, medium, low)
    - _Requirements: 05-REQ-2.1, 05-REQ-3.2_

  - [ ] 2.2 Implement JSONL store
    - `agent_fox/memory/store.py`: `append_facts()`, `load_all_facts()`,
      `load_facts_by_spec()`, `write_facts()`, `_fact_to_dict()`,
      `_dict_to_fact()`
    - Handle file creation, parent directory creation, missing file
    - Log errors on write failure without raising
    - _Requirements: 05-REQ-3.1, 05-REQ-3.2, 05-REQ-3.3, 05-REQ-3.E1,
      05-REQ-3.E2_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/memory/test_types.py tests/unit/memory/test_store.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/memory/test_store_props.py tests/property/memory/test_types_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/`
    - [ ] Requirements 05-REQ-2.1, 05-REQ-3.* acceptance criteria met

- [ ] 3. Implement extraction
  - [ ] 3.1 Implement fact extraction
    - `agent_fox/memory/extraction.py`: `extract_facts()`,
      `_parse_extraction_response()`
    - Define EXTRACTION_PROMPT with structured JSON output instructions
    - Call the configured SIMPLE model via the Anthropic SDK
    - Parse JSON response into Fact objects with UUID and timestamp
    - Handle invalid JSON (log warning, return empty list)
    - Handle unknown categories (log warning, default to gotcha)
    - Handle empty response (log debug, return empty list)
    - _Requirements: 05-REQ-1.1, 05-REQ-1.2, 05-REQ-1.3, 05-REQ-1.E1,
      05-REQ-1.E2, 05-REQ-2.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/memory/test_extraction.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/extraction.py`
    - [ ] Requirements 05-REQ-1.* acceptance criteria met

- [ ] 4. Implement context selection (filter)
  - [ ] 4.1 Implement filter
    - `agent_fox/memory/filter.py`: `select_relevant_facts()`,
      `_compute_relevance_score()`
    - Match by spec_name exact match and keyword overlap (case-insensitive)
    - Score = keyword_match_count + recency_bonus (0.0 to 1.0)
    - Return top-scoring facts up to budget (default: 50)
    - Return empty list for no matches or missing file
    - _Requirements: 05-REQ-4.1, 05-REQ-4.2, 05-REQ-4.3, 05-REQ-4.E1,
      05-REQ-4.E2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/memory/test_filter.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/memory/test_filter_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/filter.py`
    - [ ] Requirements 05-REQ-4.* acceptance criteria met

- [ ] 5. Implement compaction and render
  - [ ] 5.1 Implement compaction
    - `agent_fox/memory/compaction.py`: `compact()`,
      `_content_hash()`, `_deduplicate_by_content()`,
      `_resolve_supersession()`
    - SHA-256 content hash for deduplication (keep earliest)
    - Supersession chain resolution (keep terminal facts only)
    - Rewrite JSONL file in place with surviving facts
    - Handle empty or missing file (return 0, 0)
    - _Requirements: 05-REQ-5.1, 05-REQ-5.2, 05-REQ-5.3, 05-REQ-5.E1,
      05-REQ-5.E2_

  - [ ] 5.2 Implement render
    - `agent_fox/memory/render.py`: `render_summary()`,
      `_render_fact()`, `_render_empty_summary()`, `CATEGORY_TITLES`
    - Generate markdown organized by category with fact content, spec name,
      and confidence
    - Create output directory if missing
    - Handle empty knowledge base with "no facts" message
    - _Requirements: 05-REQ-6.1, 05-REQ-6.2, 05-REQ-6.3, 05-REQ-6.E1,
      05-REQ-6.E2_

  - [ ] 5.V Verify task group 5
    - [ ] All spec tests pass: `uv run pytest tests/unit/memory/ -q`
    - [ ] All property tests pass: `uv run pytest tests/property/memory/ -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/`
    - [ ] Type check passes: `uv run mypy agent_fox/memory/`
    - [ ] Requirements 05-REQ-5.*, 05-REQ-6.* acceptance criteria met

- [ ] 6. Checkpoint -- Structured Memory Complete
  - Ensure all tests pass: `uv run pytest tests/unit/memory/ tests/property/memory/ -q`
  - Ensure linter clean: `uv run ruff check agent_fox/memory/ tests/unit/memory/ tests/property/memory/`
  - Ensure type check clean: `uv run mypy agent_fox/memory/`
  - Verify end-to-end: create test facts, append, filter, compact, render

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 05-REQ-1.1 | TS-05-3 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-1.2 | TS-05-3 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-1.3 | TS-05-3 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-1.E1 | TS-05-E1 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-1.E2 | TS-05-E2 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-2.1 | TS-05-2 | 2.1 | tests/unit/memory/test_types.py |
| 05-REQ-2.2 | TS-05-E3 | 3.1 | tests/unit/memory/test_extraction.py |
| 05-REQ-3.1 | TS-05-4 | 2.2 | tests/unit/memory/test_store.py |
| 05-REQ-3.2 | TS-05-1 | 2.1, 2.2 | tests/unit/memory/test_types.py, tests/unit/memory/test_store.py |
| 05-REQ-3.3 | TS-05-4 | 2.2 | tests/unit/memory/test_store.py |
| 05-REQ-3.E1 | TS-05-5 | 2.2 | tests/unit/memory/test_store.py |
| 05-REQ-3.E2 | — | 2.2 | tests/unit/memory/test_store.py |
| 05-REQ-4.1 | TS-05-6, TS-05-12 | 4.1 | tests/unit/memory/test_filter.py, tests/unit/memory/test_store.py |
| 05-REQ-4.2 | TS-05-7 | 4.1 | tests/unit/memory/test_filter.py |
| 05-REQ-4.3 | TS-05-8 | 4.1 | tests/unit/memory/test_filter.py |
| 05-REQ-4.E1 | TS-05-E5 | 4.1 | tests/unit/memory/test_filter.py |
| 05-REQ-4.E2 | TS-05-E4 | 2.2 | tests/unit/memory/test_store.py |
| 05-REQ-5.1 | TS-05-9 | 5.1 | tests/unit/memory/test_compaction.py |
| 05-REQ-5.2 | TS-05-10 | 5.1 | tests/unit/memory/test_compaction.py |
| 05-REQ-5.3 | TS-05-9, TS-05-10 | 5.1 | tests/unit/memory/test_compaction.py |
| 05-REQ-5.E1 | TS-05-E6 | 5.1 | tests/unit/memory/test_compaction.py |
| 05-REQ-5.E2 | TS-05-P2 | 5.1 | tests/property/memory/test_compaction_props.py |
| 05-REQ-6.1 | TS-05-11 | 5.2 | tests/unit/memory/test_render.py |
| 05-REQ-6.2 | TS-05-11 | 5.2 | tests/unit/memory/test_render.py |
| 05-REQ-6.3 | — | 5.2 | (sync barrier integration) |
| 05-REQ-6.E1 | TS-05-E7 | 5.2 | tests/unit/memory/test_render.py |
| 05-REQ-6.E2 | TS-05-E8 | 5.2 | tests/unit/memory/test_render.py |
| Property 1 | TS-05-P1 | 4.1 | tests/property/memory/test_filter_props.py |
| Property 2 | TS-05-P2 | 5.1 | tests/property/memory/test_compaction_props.py |
| Property 3 | TS-05-P5 | 2.1 | tests/property/memory/test_types_props.py |
| Property 4 | TS-05-P3 | 2.2 | tests/property/memory/test_store_props.py |
| Property 5 | TS-05-P4 | 5.1 | tests/property/memory/test_compaction_props.py |
| Property 6 | TS-05-P6 | 5.1 | tests/property/memory/test_compaction_props.py |

## Notes

- All tests that call the LLM must use a mock. No real API calls in tests.
  Use `unittest.mock.AsyncMock` to mock the Anthropic client.
- Use `tmp_path` fixture for all file-system tests (store, compaction, render).
- The `conftest.py` at `tests/unit/memory/conftest.py` should define shared
  fixtures: sample facts, temporary memory paths, and mock LLM responses.
- The extraction module uses `async/await` for the LLM call. Use
  `pytest-asyncio` for async test support.
- Property tests for compaction should generate facts with Hypothesis
  strategies that produce realistic duplicates and supersession chains.
