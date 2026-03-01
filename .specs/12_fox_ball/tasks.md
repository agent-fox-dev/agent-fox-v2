# Implementation Plan: Fox Ball -- Semantic Knowledge Oracle

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec builds the Fox Ball: embedding generation, vector similarity
search, dual-write fact persistence, the oracle RAG pipeline, additional
source ingestion, the `agent-fox ask` CLI command, contradiction detection,
and supersession tracking. Task groups are ordered: tests first, then
embeddings, search, dual-write, oracle + CLI, and finally ingestion.

## Test Commands

- Unit tests: `uv run pytest tests/unit/knowledge/ -q`
- Property tests: `uv run pytest tests/property/knowledge/ -q`
- All knowledge tests: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ -q`
- Linter: `uv run ruff check agent_fox/knowledge/ agent_fox/cli/ask.py agent_fox/memory/`
- Type check: `uv run mypy agent_fox/knowledge/ agent_fox/cli/ask.py agent_fox/memory/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Set up test fixtures and mocks
    - Create `tests/unit/knowledge/__init__.py`
    - Create `tests/unit/knowledge/conftest.py` with shared fixtures:
      - `inmemory_db`: in-memory DuckDB with full schema (from spec 11)
      - `mock_embedder`: mocked `EmbeddingGenerator` returning 1024-dim vectors
      - `mock_anthropic_client`: mocked Anthropic client for synthesis
      - `knowledge_config`: `KnowledgeConfig` with defaults
      - `sample_facts`: list of sample `MemoryFact` objects with provenance
    - Create `tests/property/knowledge/__init__.py`
    - Create `tests/property/knowledge/conftest.py` with Hypothesis strategies

  - [ ] 1.2 Write embedding tests
    - `tests/unit/knowledge/test_embeddings.py`:
      TS-12-1 (single embed), TS-12-2 (batch embed), TS-12-3 (embed failure)
    - _Test Spec: TS-12-1, TS-12-2, TS-12-3_

  - [ ] 1.3 Write vector search tests
    - `tests/unit/knowledge/test_search.py`:
      TS-12-4 (sorted results), TS-12-5 (excludes unembedded),
      TS-12-6 (excludes superseded), TS-12-7 (empty store),
      TS-12-18 (has_embeddings)
    - _Test Spec: TS-12-4, TS-12-5, TS-12-6, TS-12-7, TS-12-18_

  - [ ] 1.4 Write dual-write tests
    - `tests/unit/knowledge/test_dual_write.py`:
      TS-12-8 (writes both), TS-12-9 (continues on DuckDB failure),
      TS-12-10 (stores without embedding), TS-12-17 (supersession)
    - _Test Spec: TS-12-8, TS-12-9, TS-12-10, TS-12-17_

  - [ ] 1.5 Write oracle tests
    - `tests/unit/knowledge/test_oracle.py`:
      TS-12-11 (grounded answer), TS-12-12 (single API call),
      TS-12-13 (contradiction detection), TS-12-E3 (embed failure on query),
      TS-12-E5 (confidence levels)
    - _Test Spec: TS-12-11, TS-12-12, TS-12-13, TS-12-E3, TS-12-E5_

  - [ ] 1.6 Write ingestion tests
    - `tests/unit/knowledge/test_ingest.py`:
      TS-12-15 (ADR ingestion), TS-12-16 (git commit ingestion),
      TS-12-E4 (missing ADR directory)
    - _Test Spec: TS-12-15, TS-12-16, TS-12-E4_

  - [ ] 1.7 Write CLI ask command tests
    - `tests/unit/cli/test_ask.py`:
      TS-12-14 (renders answer), TS-12-E1 (empty store),
      TS-12-E2 (unavailable store)
    - _Test Spec: TS-12-14, TS-12-E1, TS-12-E2_

  - [ ] 1.8 Write property tests
    - `tests/property/knowledge/test_dual_write_props.py`:
      TS-12-P1 (dual-write consistency), TS-12-P2 (embedding non-fatality)
    - `tests/property/knowledge/test_search_props.py`:
      TS-12-P3 (search result ordering)
    - `tests/property/knowledge/test_ingest_props.py`:
      TS-12-P4 (ingestion idempotency)
    - _Test Spec: TS-12-P1, TS-12-P2, TS-12-P3, TS-12-P4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) -- no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/unit/knowledge/ tests/property/knowledge/`

- [ ] 2. Implement embedding generator
  - [ ] 2.1 Create embeddings module
    - `agent_fox/knowledge/embeddings.py`: `EmbeddingGenerator` class
    - `embed_text(text)`: single text -> 1024-dim vector or None
    - `embed_batch(texts)`: list of texts -> parallel list of vectors/None
    - Lazy Anthropic client initialization
    - Graceful error handling: catch API errors, log warning, return None
    - _Requirements: 12-REQ-2.1, 12-REQ-2.2, 12-REQ-2.E1_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_embeddings.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/embeddings.py`
    - [ ] Type check passes: `uv run mypy agent_fox/knowledge/embeddings.py`
    - [ ] Requirements 12-REQ-2.* acceptance criteria met

- [ ] 3. Implement vector search
  - [ ] 3.1 Create search module
    - `agent_fox/knowledge/search.py`: `SearchResult` dataclass,
      `VectorSearch` class
    - `search(query_embedding, top_k, exclude_superseded)`:
      cosine similarity query against `memory_embeddings` joined with
      `memory_facts`
    - `has_embeddings()`: check for any rows in `memory_embeddings`
    - Excludes superseded facts by default
    - Returns results sorted by descending similarity
    - _Requirements: 12-REQ-3.1, 12-REQ-3.2, 12-REQ-3.3, 12-REQ-3.E1,
      12-REQ-7.2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_search.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_search_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/search.py`
    - [ ] Type check passes: `uv run mypy agent_fox/knowledge/search.py`
    - [ ] Requirements 12-REQ-3.* acceptance criteria met

- [ ] 4. Implement dual-write store extension
  - [ ] 4.1 Extend memory store with dual-write
    - `agent_fox/memory/store.py`: extend `MemoryStore` with DuckDB
      dual-write capability
    - `write_fact(fact)`: writes to JSONL (always), then DuckDB
      `memory_facts` (best-effort), then generates and stores embedding
      (best-effort)
    - `mark_superseded(old_fact_id, new_fact_id)`: updates
      `superseded_by` column
    - JSONL write is never skipped, even if DuckDB fails
    - Embedding failure is non-fatal: fact written without embedding
    - _Requirements: 12-REQ-1.1, 12-REQ-1.2, 12-REQ-1.3, 12-REQ-1.E1,
      12-REQ-2.E1, 12-REQ-7.1_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_dual_write.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_dual_write_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/memory/store.py`
    - [ ] Type check passes: `uv run mypy agent_fox/memory/store.py`
    - [ ] Requirements 12-REQ-1.*, 12-REQ-7.1 acceptance criteria met

- [ ] 5. Implement oracle and CLI ask command
  - [ ] 5.1 Create oracle module
    - `agent_fox/knowledge/oracle.py`: `OracleAnswer` dataclass,
      `Oracle` class
    - `ask(question)`: full RAG pipeline (embed -> search -> assemble
      context -> synthesize -> parse response)
    - `_assemble_context(results)`: format facts with provenance for
      synthesis prompt
    - `_build_synthesis_prompt(question, context)`: instruct model to
      answer from context, cite sources, flag contradictions, indicate
      confidence
    - `_determine_confidence(results)`: high/medium/low based on count
      and similarity scores
    - `_parse_synthesis_response(response_text, results)`: extract
      answer, contradictions, sources from model output
    - Single API call via `client.messages.create()` (not streaming)
    - _Requirements: 12-REQ-5.1, 12-REQ-5.2, 12-REQ-5.3, 12-REQ-6.1,
      12-REQ-8.1_

  - [ ] 5.2 Create CLI ask command
    - `agent_fox/cli/ask.py`: Click command `ask` with question argument
      and `--top-k` option
    - Register command in `agent_fox/cli/app.py`
    - Wire up: open knowledge store -> create embedder -> create search ->
      create oracle -> call `ask` -> render answer with sources,
      contradictions, confidence
    - Handle empty store (informational message, exit 0)
    - Handle unavailable store (error message, exit 1)
    - Handle embedding failure on query (error message, exit 1)
    - _Requirements: 12-REQ-5.1, 12-REQ-5.E1, 12-REQ-5.E2, 12-REQ-2.E2_

  - [ ] 5.V Verify task group 5
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_oracle.py tests/unit/cli/test_ask.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/oracle.py agent_fox/cli/ask.py`
    - [ ] Type check passes: `uv run mypy agent_fox/knowledge/oracle.py agent_fox/cli/ask.py`
    - [ ] Requirements 12-REQ-5.*, 12-REQ-6.1, 12-REQ-8.1 acceptance criteria met

- [ ] 6. Implement knowledge source ingestion
  - [ ] 6.1 Create ingestion module
    - `agent_fox/knowledge/ingest.py`: `IngestResult` dataclass,
      `KnowledgeIngestor` class
    - `ingest_adrs(adr_dir)`: parse ADR markdown files -> create facts
      with `category="adr"` -> embed and store
    - `ingest_git_commits(limit, since)`: run `git log` -> create facts
      with `category="git"` and `commit_sha` -> embed and store
    - `_parse_adr(path)`: extract title and body from ADR markdown
    - `_is_already_ingested(category, identifier)`: skip duplicates
    - Idempotent: skips already-ingested sources
    - Missing ADR directory returns 0 facts, no error
    - Git log failure logs warning, returns 0 facts
    - _Requirements: 12-REQ-4.1, 12-REQ-4.2, 12-REQ-4.3_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests pass: `uv run pytest tests/unit/knowledge/test_ingest.py -q`
    - [ ] Property tests pass: `uv run pytest tests/property/knowledge/test_ingest_props.py -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/ingest.py`
    - [ ] Type check passes: `uv run mypy agent_fox/knowledge/ingest.py`
    - [ ] Requirements 12-REQ-4.* acceptance criteria met

- [ ] 7. Checkpoint -- Fox Ball Complete
  - Ensure all tests pass: `uv run pytest tests/unit/knowledge/ tests/property/knowledge/ tests/unit/cli/test_ask.py -q`
  - Ensure linter clean: `uv run ruff check agent_fox/knowledge/ agent_fox/cli/ask.py agent_fox/memory/`
  - Ensure type check clean: `uv run mypy agent_fox/knowledge/ agent_fox/cli/ask.py agent_fox/memory/`
  - Verify no regressions in existing tests: `uv run pytest tests/ -q`
  - Verify `agent-fox ask` is registered and displays help:
    `uv run agent-fox ask --help`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 12-REQ-1.1 | TS-12-8, TS-12-P1 | 4.1 | tests/unit/knowledge/test_dual_write.py |
| 12-REQ-1.2 | TS-12-P1 | 4.1 | tests/property/knowledge/test_dual_write_props.py |
| 12-REQ-1.3 | TS-12-8 | 4.1 | tests/unit/knowledge/test_dual_write.py |
| 12-REQ-1.E1 | TS-12-9, TS-12-P1 | 4.1 | tests/unit/knowledge/test_dual_write.py |
| 12-REQ-2.1 | TS-12-1 | 2.1 | tests/unit/knowledge/test_embeddings.py |
| 12-REQ-2.2 | TS-12-2 | 2.1 | tests/unit/knowledge/test_embeddings.py |
| 12-REQ-2.E1 | TS-12-3, TS-12-10, TS-12-P2 | 2.1, 4.1 | tests/unit/knowledge/test_embeddings.py, tests/property/knowledge/test_dual_write_props.py |
| 12-REQ-2.E2 | TS-12-E3 | 5.1 | tests/unit/knowledge/test_oracle.py |
| 12-REQ-3.1 | TS-12-4, TS-12-P3 | 3.1 | tests/unit/knowledge/test_search.py, tests/property/knowledge/test_search_props.py |
| 12-REQ-3.2 | TS-12-4 | 3.1 | tests/unit/knowledge/test_search.py |
| 12-REQ-3.3 | TS-12-5 | 3.1 | tests/unit/knowledge/test_search.py |
| 12-REQ-3.E1 | TS-12-7 | 3.1 | tests/unit/knowledge/test_search.py |
| 12-REQ-4.1 | TS-12-15, TS-12-P4, TS-12-E4 | 6.1 | tests/unit/knowledge/test_ingest.py, tests/property/knowledge/test_ingest_props.py |
| 12-REQ-4.2 | TS-12-16, TS-12-P4 | 6.1 | tests/unit/knowledge/test_ingest.py, tests/property/knowledge/test_ingest_props.py |
| 12-REQ-4.3 | TS-12-15, TS-12-16 | 6.1 | tests/unit/knowledge/test_ingest.py |
| 12-REQ-5.1 | TS-12-11, TS-12-14 | 5.1, 5.2 | tests/unit/knowledge/test_oracle.py, tests/unit/cli/test_ask.py |
| 12-REQ-5.2 | TS-12-11 | 5.1 | tests/unit/knowledge/test_oracle.py |
| 12-REQ-5.3 | TS-12-12 | 5.1 | tests/unit/knowledge/test_oracle.py |
| 12-REQ-5.E1 | TS-12-18, TS-12-E1 | 5.1, 5.2 | tests/unit/knowledge/test_search.py, tests/unit/cli/test_ask.py |
| 12-REQ-5.E2 | TS-12-E2 | 5.2 | tests/unit/cli/test_ask.py |
| 12-REQ-6.1 | TS-12-13 | 5.1 | tests/unit/knowledge/test_oracle.py |
| 12-REQ-7.1 | TS-12-17 | 4.1 | tests/unit/knowledge/test_dual_write.py |
| 12-REQ-7.2 | TS-12-6 | 3.1 | tests/unit/knowledge/test_search.py |
| 12-REQ-8.1 | TS-12-E5 | 5.1 | tests/unit/knowledge/test_oracle.py |
| Property 1 | TS-12-P1 | 4.1 | tests/property/knowledge/test_dual_write_props.py |
| Property 2 | TS-12-P2 | 4.1 | tests/property/knowledge/test_dual_write_props.py |
| Property 3 | TS-12-P3 | 3.1 | tests/property/knowledge/test_search_props.py |
| Property 7 | TS-12-P4 | 6.1 | tests/property/knowledge/test_ingest_props.py |

## Notes

- All Anthropic API calls are mocked in tests. No network calls.
- All DuckDB tests use in-memory databases (`duckdb.connect(":memory:")`).
  The test fixtures must create the full schema (from spec 11) including
  `memory_facts`, `memory_embeddings`, and related tables.
- The `EmbeddingGenerator` uses the same Anthropic API key as the coding
  models. No additional credentials are required.
- The `memory/store.py` extension must be backward-compatible: if no DuckDB
  connection is provided, the store falls back to JSONL-only (existing
  spec 05 behavior).
- Mock embedding vectors should use deterministic, low-dimensional patterns
  (e.g., normalized random vectors with a fixed seed) to make similarity
  assertions predictable.
- Use `click.testing.CliRunner` for CLI tests.
- Use `tmp_path` for JSONL and ADR file fixtures.
- Use `monkeypatch` or `unittest.mock.patch` for mocking `subprocess.run`
  (git log) and the Anthropic client.
