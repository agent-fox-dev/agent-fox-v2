# Implementation Plan: Pluggable Knowledge Provider

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This spec implements the `KnowledgeProvider` protocol (defined in spec 114)
with a concrete `FoxKnowledgeProvider`. The plan builds bottom-up: schema
migration first, then store modules, then the provider, then engine wiring.
Each group produces testable artifacts that accumulate into the full provider.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_fox_provider.py tests/unit/knowledge/test_gotcha_store.py tests/unit/knowledge/test_errata_store.py tests/unit/knowledge/test_gotcha_extraction.py`
- Unit tests: `uv run pytest -q tests/unit/`
- Property tests: `uv run pytest -q tests/property/knowledge/test_fox_provider_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [ ] 1. Write failing spec tests
  - [ ] 1.1 Create provider unit tests
    - Create `tests/unit/knowledge/test_fox_provider.py`
    - Tests for protocol conformance (TS-115-1, TS-115-2, TS-115-3)
    - Tests for retrieval composition, caps, ordering (TS-115-20, TS-115-21, TS-115-22)
    - Tests for review carry-forward (TS-115-13, TS-115-14, TS-115-15)
    - Edge case tests (TS-115-E1, TS-115-E5 through TS-115-E12)
    - _Test Spec: TS-115-1, TS-115-2, TS-115-3, TS-115-13, TS-115-14, TS-115-15, TS-115-20, TS-115-21, TS-115-22, TS-115-E1, TS-115-E5, TS-115-E6, TS-115-E7, TS-115-E8, TS-115-E9, TS-115-E10, TS-115-E11, TS-115-E12_

  - [ ] 1.2 Create gotcha store and extraction tests
    - Create `tests/unit/knowledge/test_gotcha_store.py`
    - Tests for gotcha CRUD (TS-115-7, TS-115-9, TS-115-10, TS-115-11, TS-115-12)
    - Tests for deduplication (TS-115-E2)
    - Tests for TTL behavior (TS-115-23, TS-115-24)
    - Create `tests/unit/knowledge/test_gotcha_extraction.py`
    - Tests for LLM extraction (TS-115-4, TS-115-5, TS-115-6, TS-115-8)
    - Tests for extraction edge cases (TS-115-E3, TS-115-E4)
    - _Test Spec: TS-115-4, TS-115-5, TS-115-6, TS-115-7, TS-115-8, TS-115-9, TS-115-10, TS-115-11, TS-115-12, TS-115-23, TS-115-24, TS-115-E2, TS-115-E3, TS-115-E4_

  - [ ] 1.3 Create errata store tests
    - Create `tests/unit/knowledge/test_errata_store.py`
    - Tests for errata CRUD (TS-115-16, TS-115-17, TS-115-18, TS-115-19)
    - _Test Spec: TS-115-16, TS-115-17, TS-115-18, TS-115-19_

  - [ ] 1.4 Create config and migration tests
    - Add to `tests/unit/knowledge/test_fox_provider.py` or create separate file
    - Tests for KnowledgeProviderConfig (TS-115-25, TS-115-26, TS-115-27)
    - Tests for schema migration (TS-115-28, TS-115-29, TS-115-30, TS-115-31)
    - Tests for engine integration (TS-115-32, TS-115-33, TS-115-34)
    - _Test Spec: TS-115-25, TS-115-26, TS-115-27, TS-115-28, TS-115-29, TS-115-30, TS-115-31, TS-115-32, TS-115-33, TS-115-34_

  - [ ] 1.5 Create property tests and smoke tests
    - Create `tests/property/knowledge/test_fox_provider_props.py`
    - Property tests (TS-115-P1 through TS-115-P9)
    - Create `tests/integration/knowledge/test_fox_provider_smoke.py`
    - Smoke tests (TS-115-SMOKE-1 through TS-115-SMOKE-4)
    - _Test Spec: TS-115-P1 through TS-115-P9, TS-115-SMOKE-1 through TS-115-SMOKE-4_

  - [ ] 1.V Verify task group 1
    - [ ] All spec tests exist and are syntactically valid
    - [ ] All spec tests FAIL (red) — no implementation yet
    - [ ] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Schema migration and configuration
  - [ ] 2.1 Add `KnowledgeProviderConfig` to `agent_fox/core/config.py`
    - Define `KnowledgeProviderConfig` with `max_items`, `gotcha_ttl_days`, `model_tier`
    - Add `provider: KnowledgeProviderConfig` field to `KnowledgeConfig`
    - Set `ConfigDict(extra="ignore")`
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ] 2.2 Add migration v17 to `agent_fox/knowledge/migrations.py`
    - Create `gotchas` table with: id, spec_name, category, text, content_hash, session_id, created_at
    - Create `errata_index` table with: spec_name, file_path, created_at, PK(spec_name, file_path)
    - Use `CREATE TABLE IF NOT EXISTS` for idempotency
    - Register in `MIGRATIONS` list
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_fox_provider.py -k "config or migration"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/core/config.py agent_fox/knowledge/migrations.py`
    - [ ] Requirements 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4 acceptance criteria met

- [ ] 3. Gotcha store and errata store modules
  - [ ] 3.1 Create `agent_fox/knowledge/gotcha_store.py`
    - Implement `GotchaRecord` dataclass
    - Implement `compute_content_hash(text)` — SHA-256 of lowered, whitespace-collapsed text
    - Implement `store_gotchas(conn, spec_name, session_id, candidates)` with content-hash dedup
    - Implement `query_gotchas(conn, spec_name, ttl_days, limit)` with TTL filter and recency ordering
    - _Requirements: 2.4, 2.E1, 3.1, 3.2, 3.3, 3.4, 7.1, 7.2_

  - [ ] 3.2 Create `agent_fox/knowledge/errata_store.py`
    - Implement `ErrataEntry` dataclass
    - Implement `register_errata(conn, spec_name, file_path)` — idempotent insert, returns `ErrataEntry`
    - Implement `unregister_errata(conn, spec_name, file_path)` — returns bool
    - Implement `query_errata(conn, spec_name)` — returns formatted `[ERRATA]` strings
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.E1, 5.E2_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_gotcha_store.py tests/unit/knowledge/test_errata_store.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/gotcha_store.py agent_fox/knowledge/errata_store.py`
    - [ ] Requirements 2.4, 2.E1, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 7.1, 7.2 acceptance criteria met

- [ ] 4. Gotcha extraction module
  - [ ] 4.1 Create `agent_fox/knowledge/gotcha_extraction.py`
    - Implement `GotchaCandidate` dataclass
    - Implement gotcha extraction prompt template
    - Implement `extract_gotchas(context, model_tier)` — calls LLM, parses response, caps at 3
    - Handle LLM failures gracefully (return empty list)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.E2, 2.E3_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_gotcha_extraction.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/gotcha_extraction.py`
    - [ ] Requirements 2.1, 2.2, 2.3, 2.5, 2.E2, 2.E3 acceptance criteria met

- [ ] 5. Checkpoint - Store modules complete
  - Ensure all store-level tests pass.
  - Gotcha store, errata store, and gotcha extraction are individually tested.
  - Config and migration are in place.

- [ ] 6. FoxKnowledgeProvider implementation
  - [ ] 6.1 Create `agent_fox/knowledge/fox_provider.py`
    - Implement `FoxKnowledgeProvider` class implementing `KnowledgeProvider` protocol
    - Constructor: accepts `KnowledgeDB` and `KnowledgeProviderConfig`
    - `retrieve()`: queries errata, review findings, gotchas; composes with priority ordering and cap
    - `ingest()`: checks session_status, calls `extract_gotchas`, calls `store_gotchas`
    - _Requirements: 1.1, 1.2, 1.3, 1.E1_

  - [ ] 6.2 Implement `_compose_results` method
    - Merge errata (first), review findings (second), gotchas (last)
    - Apply max_items cap: trim gotchas first
    - Handle reviews+errata exceeding cap (include all, omit gotchas)
    - _Requirements: 6.1, 6.2, 6.3, 6.E1, 6.E2_

  - [ ] 6.3 Implement review carry-forward in `retrieve()`
    - Query `review_store.query_active_findings()` for spec
    - Filter to critical/major severity
    - Format with `[REVIEW] ` prefix including severity, category, description
    - Handle missing `review_findings` table gracefully
    - _Requirements: 4.1, 4.2, 4.3, 4.E1, 4.E2_

  - [ ] 6.V Verify task group 6
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_fox_provider.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/knowledge/fox_provider.py`
    - [ ] Requirements 1.1, 1.2, 1.3, 1.E1, 4.1, 4.2, 4.3, 4.E1, 4.E2, 6.1, 6.2, 6.3, 6.E1, 6.E2 acceptance criteria met

- [ ] 7. Engine wiring
  - [ ] 7.1 Update `engine/run.py` to construct `FoxKnowledgeProvider`
    - Import `FoxKnowledgeProvider` from `agent_fox.knowledge.fox_provider`
    - Read `KnowledgeProviderConfig` from `config.knowledge.provider`
    - Construct `FoxKnowledgeProvider(knowledge_db, provider_config)` instead of `NoOpKnowledgeProvider`
    - Add to infrastructure dict as `knowledge_provider`
    - _Requirements: 10.1, 10.2_

  - [ ] 7.2 Verify engine import boundary
    - Confirm engine modules only import from the allowed knowledge module set
    - `fox_provider` is added to the allowed set (imported only in `run.py`)
    - _Requirements: 10.3_

  - [ ] 7.V Verify task group 7
    - [ ] Spec tests for this group pass: `uv run pytest -q tests/unit/knowledge/test_fox_provider.py -k "engine or startup or boundary"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/engine/run.py`
    - [ ] Requirements 10.1, 10.2, 10.3 acceptance criteria met

- [ ] 8. Wiring verification

  - [ ] 8.1 Trace every execution path from design.md end-to-end
    - Path 1 (retrieval): `_build_prompts` → `FoxKnowledgeProvider.retrieve` → `query_errata` + `query_active_findings` + `query_gotchas` → `_compose_results`
    - Path 2 (ingestion): `_ingest_knowledge` → `FoxKnowledgeProvider.ingest` → `extract_gotchas` → `store_gotchas`
    - Path 3 (errata registration): `register_errata` → DuckDB insert
    - Path 4 (startup): `_setup_infrastructure` → `FoxKnowledgeProvider(...)` → infrastructure dict
    - For each path, verify the entry point actually calls the next function in the chain
    - Confirm no function in the chain is a stub
    - _Requirements: all_

  - [ ] 8.2 Verify return values propagate correctly
    - `FoxKnowledgeProvider.retrieve()` → returned list flows to `assemble_context` in session_lifecycle
    - `register_errata()` → returned `ErrataEntry` available to caller
    - `store_gotchas()` → returned count used for logging
    - `extract_gotchas()` → returned candidates consumed by `store_gotchas`
    - _Requirements: all_

  - [ ] 8.3 Run the integration smoke tests
    - All `TS-115-SMOKE-*` tests pass using real components (no stub bypass)
    - `uv run pytest -q tests/integration/knowledge/test_fox_provider_smoke.py`
    - _Test Spec: TS-115-SMOKE-1 through TS-115-SMOKE-4_

  - [ ] 8.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None` on non-Optional returns, `pass` in non-abstract methods, `# TODO`, `# stub`, `NotImplementedError`
    - Each hit must be either: (a) justified, or (b) replaced with real implementation
    - `query_gotchas` returning `[]` for empty spec is intentional (no gotchas)
    - `query_errata` returning `[]` for empty spec is intentional (no errata)

  - [ ] 8.5 Cross-spec entry point verification
    - Verify `engine/run.py` constructs `FoxKnowledgeProvider` and passes it via factory — this is the entry point from spec 114
    - Verify `engine/session_lifecycle.py` calls `retrieve()` and `ingest()` via the protocol — these are the call sites defined in spec 114
    - Confirm `FoxKnowledgeProvider` is called from production code, not just tests
    - _Requirements: all_

  - [ ] 8.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `make check`

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
| 115-REQ-1.1 | TS-115-1 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_protocol_definition |
| 115-REQ-1.2 | TS-115-2 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_isinstance_check |
| 115-REQ-1.3 | TS-115-3 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_constructor |
| 115-REQ-1.E1 | TS-115-E1 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_closed_db |
| 115-REQ-2.1 | TS-115-4 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_extraction |
| 115-REQ-2.2 | TS-115-5 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_model_tier |
| 115-REQ-2.3 | TS-115-6 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_zero_candidates |
| 115-REQ-2.4 | TS-115-7 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_record_fields |
| 115-REQ-2.5 | TS-115-8 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_skip_non_completed |
| 115-REQ-2.E1 | TS-115-E2 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_dedup |
| 115-REQ-2.E2 | TS-115-E3 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_llm_failure |
| 115-REQ-2.E3 | TS-115-E4 | 4.1 | tests/unit/knowledge/test_gotcha_extraction.py::test_cap_at_3 |
| 115-REQ-3.1 | TS-115-9 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_query_by_spec |
| 115-REQ-3.2 | TS-115-10 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_ttl_exclusion |
| 115-REQ-3.3 | TS-115-11 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_max_5 |
| 115-REQ-3.4 | TS-115-12 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_gotcha_prefix |
| 115-REQ-3.E1 | TS-115-E5 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_no_gotchas |
| 115-REQ-4.1 | TS-115-13 | 6.3 | tests/unit/knowledge/test_fox_provider.py::test_review_carry_forward |
| 115-REQ-4.2 | TS-115-14 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_review_not_limited |
| 115-REQ-4.3 | TS-115-15 | 6.3 | tests/unit/knowledge/test_fox_provider.py::test_review_prefix |
| 115-REQ-4.E1 | TS-115-E6 | 6.3 | tests/unit/knowledge/test_fox_provider.py::test_no_findings |
| 115-REQ-4.E2 | TS-115-E7 | 6.3 | tests/unit/knowledge/test_fox_provider.py::test_missing_review_table |
| 115-REQ-5.1 | TS-115-16 | 3.2 | tests/unit/knowledge/test_errata_store.py::test_storage |
| 115-REQ-5.2 | TS-115-17 | 3.2 | tests/unit/knowledge/test_errata_store.py::test_retrieval |
| 115-REQ-5.3 | TS-115-18 | 3.2 | tests/unit/knowledge/test_errata_store.py::test_prefix |
| 115-REQ-5.4 | TS-115-19 | 3.2 | tests/unit/knowledge/test_errata_store.py::test_register_unregister |
| 115-REQ-5.E1 | TS-115-E8 | 6.1 | tests/unit/knowledge/test_fox_provider.py::test_no_errata |
| 115-REQ-5.E2 | TS-115-E9 | 3.2 | tests/unit/knowledge/test_errata_store.py::test_missing_file |
| 115-REQ-6.1 | TS-115-20 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_total_cap |
| 115-REQ-6.2 | TS-115-21 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_gotchas_trimmed |
| 115-REQ-6.3 | TS-115-22 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_category_order |
| 115-REQ-6.E1 | TS-115-E10 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_all_empty |
| 115-REQ-6.E2 | TS-115-E11 | 6.2 | tests/unit/knowledge/test_fox_provider.py::test_reviews_errata_exceed |
| 115-REQ-7.1 | TS-115-23 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_ttl_config |
| 115-REQ-7.2 | TS-115-24 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_expired_not_deleted |
| 115-REQ-7.E1 | TS-115-E12 | 3.1 | tests/unit/knowledge/test_gotcha_store.py::test_ttl_zero |
| 115-REQ-8.1 | TS-115-25 | 2.1 | tests/unit/knowledge/test_fox_provider.py::test_config_fields |
| 115-REQ-8.2 | TS-115-26 | 2.1 | tests/unit/knowledge/test_fox_provider.py::test_config_nested |
| 115-REQ-8.3 | TS-115-27 | 2.1 | tests/unit/knowledge/test_fox_provider.py::test_config_extra_ignore |
| 115-REQ-9.1 | TS-115-28 | 2.2 | tests/unit/knowledge/test_fox_provider.py::test_gotchas_schema |
| 115-REQ-9.2 | TS-115-29 | 2.2 | tests/unit/knowledge/test_fox_provider.py::test_errata_schema |
| 115-REQ-9.3 | TS-115-30 | 2.2 | tests/unit/knowledge/test_fox_provider.py::test_migration_framework |
| 115-REQ-9.4 | TS-115-31 | 2.2 | tests/unit/knowledge/test_fox_provider.py::test_idempotent_migration |
| 115-REQ-10.1 | TS-115-32 | 7.1 | tests/unit/knowledge/test_fox_provider.py::test_startup_construction |
| 115-REQ-10.2 | TS-115-33 | 7.1 | tests/unit/knowledge/test_fox_provider.py::test_replaces_noop |
| 115-REQ-10.3 | TS-115-34 | 7.2 | tests/unit/knowledge/test_fox_provider.py::test_import_boundary |
| Property 1 | TS-115-P1 | 6.1 | tests/property/knowledge/test_fox_provider_props.py::test_protocol |
| Property 2 | TS-115-P2 | 3.1 | tests/property/knowledge/test_fox_provider_props.py::test_dedup |
| Property 3 | TS-115-P3 | 3.1 | tests/property/knowledge/test_fox_provider_props.py::test_ttl |
| Property 4 | TS-115-P4 | 6.2 | tests/property/knowledge/test_fox_provider_props.py::test_cap |
| Property 5 | TS-115-P5 | 6.2 | tests/property/knowledge/test_fox_provider_props.py::test_order |
| Property 6 | TS-115-P6 | 4.1 | tests/property/knowledge/test_fox_provider_props.py::test_extraction_cap |
| Property 7 | TS-115-P7 | 4.1 | tests/property/knowledge/test_fox_provider_props.py::test_skip_failed |
| Property 8 | TS-115-P8 | 3.1 | tests/property/knowledge/test_fox_provider_props.py::test_hash |
| Property 9 | TS-115-P9 | 6.3 | tests/property/knowledge/test_fox_provider_props.py::test_review_prefix |

## Notes

- All store modules use the existing DuckDB connection from `KnowledgeDB` — no new database files.
- The gotcha extraction module requires an LLM call. Tests mock the LLM; smoke tests use a mock LLM that returns canned responses.
- The `review_store.query_active_findings()` function returns findings for all severities. The provider must filter to critical/major severity after querying.
- The `errata_store` is independent of LLM calls — purely database-driven.
- Migration v17 must be idempotent (`CREATE TABLE IF NOT EXISTS`) since the migration framework runs on every database open.
- The dependency on spec 114 is for the `KnowledgeProvider` protocol and the engine wiring point in `run.py`. This spec adds `FoxKnowledgeProvider` as the concrete implementation.
