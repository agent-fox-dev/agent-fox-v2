# Implementation Plan: ADR Ingestion

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation follows the errata pattern: a self-contained module
(`knowledge/adr.py`) with dataclasses, pure functions, and DB operations;
a DuckDB migration; and integration through `FoxKnowledgeProvider`. Task
group 1 writes all failing tests, groups 2-4 implement the code to make
them pass, and group 5 verifies end-to-end wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_adr.py tests/property/knowledge/test_adr_props.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/test_adr.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_adr_props.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file structure
    - Create `tests/unit/knowledge/test_adr.py`
    - Create `tests/property/knowledge/test_adr_props.py`
    - Add MADR fixture constants (valid content, invalid content, synonym variants)
    - Use project test conventions (pytest, in-memory DuckDB, Hypothesis)
    - _Test Spec: TS-117-1 through TS-117-22_

  - [x] 1.2 Translate acceptance-criterion tests
    - TS-117-1: detect ADR paths in touched_files
    - TS-117-2: no ADR paths returns empty list
    - TS-117-3: parse valid MADR content
    - TS-117-4: parse YAML frontmatter status
    - TS-117-5: parse status from H2 section
    - TS-117-6: default status when absent
    - TS-117-7: parse synonym section headings
    - TS-117-8: parse Decision Outcome chosen option
    - TS-117-9: validation passes with 3+ options
    - TS-117-10: validation fails with < 3 options
    - TS-117-11: validation fails with empty chosen option
    - TS-117-12: store ADR entry in DuckDB
    - TS-117-13: content hash is SHA-256
    - TS-117-14: supersede on content change
    - TS-117-15: skip duplicate ingestion
    - TS-117-16: query ADRs by spec_refs match
    - TS-117-17: format ADR for prompt
    - TS-117-18: FoxKnowledgeProvider.retrieve includes ADRs
    - TS-117-19: extract spec refs from content
    - TS-117-20: extract keywords from title
    - TS-117-21: validation warning emits audit event
    - TS-117-22: successful ingestion emits audit event
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-117-1 through TS-117-22_

  - [x] 1.3 Translate edge-case tests
    - TS-117-E1: empty touched_files
    - TS-117-E2: non-.md ADR path excluded
    - TS-117-E3: no H1 heading parse failure
    - TS-117-E4: empty title validation failure
    - TS-117-E5: DB unavailable during store
    - TS-117-E6: adr_entries table missing during query
    - TS-117-E7: no matching ADRs
    - TS-117-E8: superseded file_path with new content
    - _Test Spec: TS-117-E1 through TS-117-E8_

  - [x] 1.4 Translate property tests
    - TS-117-P1: detection accuracy
    - TS-117-P2: parse completeness
    - TS-117-P3: validation consistency
    - TS-117-P4: supersession idempotency
    - TS-117-P5: retrieval excludes superseded
    - TS-117-P6: summary format compliance
    - TS-117-P7: content hash determinism
    - _Test Spec: TS-117-P1 through TS-117-P7_

  - [x] 1.5 Write integration smoke tests
    - TS-117-SMOKE-1: full ingest pipeline
    - TS-117-SMOKE-2: full retrieve pipeline
    - _Test Spec: TS-117-SMOKE-1, TS-117-SMOKE-2_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/unit/knowledge/test_adr.py tests/property/knowledge/test_adr_props.py`

- [x] 2. MADR parser and validator
  - [x] 2.1 Create `agent_fox/knowledge/adr.py` with data types
    - Define `ADREntry` and `ADRValidationResult` dataclasses
    - Define `_STOP_WORDS` set and `_ADR_PATH_PATTERN` regex
    - _Requirements: 2.1, 3.1_

  - [x] 2.2 Implement `detect_adr_changes()`
    - Filter paths matching `docs/adr/*.md` (one level, .md only)
    - Handle empty/None input gracefully
    - _Requirements: 1.1, 1.2, 1.E1, 1.E2_

  - [x] 2.3 Implement `parse_madr()`
    - Extract H1 title, YAML frontmatter, H2 sections
    - Parse Considered Options bullets, Decision Outcome chosen option
    - Handle section heading synonyms
    - Handle Status from frontmatter, H2 section, or default
    - Return None on parse failure (no H1, no parseable content)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.E1, 2.E2_

  - [x] 2.4 Implement `validate_madr()`
    - Check mandatory sections present (context, options, decision)
    - Check ≥ 3 considered options
    - Check non-empty chosen_option and title
    - Return `ADRValidationResult(passed, diagnostics)`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.E1_

  - [x] 2.5 Implement `extract_spec_refs()` and `extract_keywords()`
    - Regex extraction: `(\d+)-REQ-`, `spec[_\s]+(\d+)`, `(\d{1,3}_[a-z][a-z_]+)`
    - Title keyword extraction: split, lowercase, filter stopwords/short
    - _Requirements: 6.4, 6.5_

  - [x] 2.6 Implement `generate_adr_summary()`
    - Format: `{title}: Chose "{chosen}" over {others}. {justification}`
    - _Requirements: 6.2_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_adr.py -k "detect or parse or validate or extract or format or keyword or spec_ref or summary"`
    - [x] Property tests pass: `uv run pytest -q tests/property/knowledge/test_adr_props.py -k "P1 or P2 or P3 or P6 or P7"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/adr.py`
    - [x] Requirements 1.*, 2.*, 3.*, 6.2, 6.4, 6.5 acceptance criteria met

- [x] 3. ADR storage, supersession, and migration
  - [x] 3.1 Add DuckDB migration `_migrate_v22()` in `migrations.py`
    - Create `adr_entries` table with schema from design.md
    - Register in `MIGRATIONS` list
    - _Requirements: 4.3_

  - [x] 3.2 Implement `store_adr()`
    - Insert row into `adr_entries`
    - Handle supersession: check existing active entry, set superseded_at
    - Handle duplicate content_hash: skip insertion
    - Handle missing table / closed connection gracefully
    - _Requirements: 4.1, 4.2, 4.4, 4.E1, 4.E2, 5.1, 5.2, 5.3, 5.E1_

  - [x] 3.3 Implement `ingest_adr()`
    - Read file from project_root / file_path
    - Compute SHA-256 content_hash
    - Call parse_madr → validate_madr → store_adr pipeline
    - Emit audit events for validation failure and successful ingestion
    - Log WARNING on validation failure, skip ingestion
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.E1_

  - [x] 3.4 Add audit event types to `audit.py`
    - Add `ADR_VALIDATION_FAILED = "adr.validation_failed"` to `AuditEventType`
    - Add `ADR_INGESTED = "adr.ingested"` to `AuditEventType`
    - _Requirements: 7.2, 7.4_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_adr.py -k "store or ingest or supersede or duplicate or migration or audit"`
    - [x] Property tests pass: `uv run pytest -q tests/property/knowledge/test_adr_props.py -k "P4 or P7"`
    - [x] Smoke test 1 passes: `uv run pytest -q tests/unit/knowledge/test_adr.py -k "smoke_1 or SMOKE_1"`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/adr.py agent_fox/knowledge/migrations.py agent_fox/knowledge/audit.py`
    - [x] Requirements 4.*, 5.*, 7.* acceptance criteria met

- [ ] 4. ADR retrieval and FoxKnowledgeProvider integration
  - [ ] 4.1 Implement `query_adrs()`
    - Query active entries (superseded_at IS NULL)
    - Match by spec_refs: extract spec number from spec_name, check overlap
    - Match by keywords: extract words from task_description, check overlap
    - Handle missing table gracefully
    - _Requirements: 6.1, 6.E1, 6.E2_

  - [ ] 4.2 Implement `format_adrs_for_prompt()`
    - Format: `[ADR] {summary}` using generate_adr_summary output
    - Return list of formatted strings
    - _Requirements: 6.2_

  - [ ] 4.3 Update `FoxKnowledgeProvider.ingest()` in `fox_provider.py`
    - Extract `touched_files` and `project_root` from context dict
    - Call `detect_adr_changes(touched_files)`
    - For each ADR path, call `ingest_adr(conn, path, project_root)`
    - Pass sink and run_id for audit events (add to FoxKnowledgeProvider.__init__ or context)
    - _Requirements: 1.1, 7.4_

  - [ ] 4.4 Update `FoxKnowledgeProvider.retrieve()` in `fox_provider.py`
    - Add `_query_adrs()` helper method
    - Call `query_adrs()` and `format_adrs_for_prompt()`
    - Include ADR results alongside reviews and errata, capped at max_items
    - _Requirements: 6.1, 6.3_

  - [ ] 4.5 Update `_ingest_knowledge()` in `session_lifecycle.py`
    - Add `"project_root": str(repo_root)` to the context dict
    - _Requirements: (enables 4.3)_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_adr.py -k "query or retrieve or provider or format_prompt"`
    - [ ] Property tests pass: `uv run pytest -q tests/property/knowledge/test_adr_props.py -k "P5 or P6"`
    - [ ] Smoke test 2 passes: `uv run pytest -q tests/unit/knowledge/test_adr.py -k "smoke_2 or SMOKE_2"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/adr.py agent_fox/knowledge/fox_provider.py agent_fox/engine/session_lifecycle.py`
    - [ ] Requirements 6.* acceptance criteria met

- [ ] 5. Wiring verification

  - [ ] 5.1 Trace every execution path from design.md end-to-end
    - Path 1 (ingest): Verify `_ingest_knowledge` → `FoxKnowledgeProvider.ingest` →
      `detect_adr_changes` → `ingest_adr` → `parse_madr` → `validate_madr` → `store_adr`
      is live in production code (no stubs, no missing calls)
    - Path 2 (retrieve): Verify `_build_prompts` → `FoxKnowledgeProvider.retrieve` →
      `_query_adrs` → `query_adrs` → `format_adrs_for_prompt` is live
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 5.2 Verify return values propagate correctly
    - `detect_adr_changes` returns list[str] → consumed by `ingest()` loop
    - `ingest_adr` returns ADREntry | None → consumed by ingest for audit logging
    - `query_adrs` returns list[ADREntry] → consumed by `format_adrs_for_prompt`
    - `format_adrs_for_prompt` returns list[str] → consumed by `retrieve()` aggregation
    - Grep for callers of each function; confirm none discards the return
    - _Requirements: all_

  - [ ] 5.3 Run the integration smoke tests
    - TS-117-SMOKE-1 (ingest pipeline) passes with real components
    - TS-117-SMOKE-2 (retrieve pipeline) passes with real components
    - _Test Spec: TS-117-SMOKE-1, TS-117-SMOKE-2_

  - [ ] 5.4 Stub / dead-code audit
    - Search `agent_fox/knowledge/adr.py` for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be either justified or replaced
    - Document any intentional stubs here with rationale

  - [ ] 5.5 Cross-spec entry point verification
    - Verify `FoxKnowledgeProvider.ingest()` is called from
      `session_lifecycle.py:_ingest_knowledge()` in production code
    - Verify `FoxKnowledgeProvider.retrieve()` is called from
      `session_lifecycle.py:_build_prompts()` in production code
    - Both callers already exist (spec 114); verify the ADR code path
      is reachable from them
    - _Requirements: all_

  - [ ] 5.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

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
| 117-REQ-1.1 | TS-117-1 | 2.2 | test_detect_adr_paths |
| 117-REQ-1.2 | TS-117-2 | 2.2 | test_detect_no_adr_paths |
| 117-REQ-1.E1 | TS-117-E1 | 2.2 | test_detect_empty_input |
| 117-REQ-1.E2 | TS-117-E2 | 2.2 | test_detect_non_md_excluded |
| 117-REQ-1.3 | TS-117-SMOKE-1 | 3.3 | test_smoke_ingest |
| 117-REQ-2.1 | TS-117-3 | 2.3 | test_parse_valid_madr |
| 117-REQ-2.2 | TS-117-4 | 2.3 | test_parse_yaml_frontmatter |
| 117-REQ-2.3 | TS-117-5 | 2.3 | test_parse_status_section |
| 117-REQ-2.4 | TS-117-6 | 2.3 | test_parse_default_status |
| 117-REQ-2.5 | TS-117-7 | 2.3 | test_parse_synonym_headings |
| 117-REQ-2.6 | TS-117-8 | 2.3 | test_parse_decision_outcome |
| 117-REQ-2.E1 | TS-117-E3 | 2.3 | test_parse_no_h1 |
| 117-REQ-2.E2 | TS-117-SMOKE-1 | 2.3 | test_smoke_ingest |
| 117-REQ-3.1 | TS-117-9 | 2.4 | test_validate_passes |
| 117-REQ-3.2 | TS-117-10 | 2.4 | test_validate_fails_few_options |
| 117-REQ-3.3 | TS-117-11 | 2.4 | test_validate_fails_no_chosen |
| 117-REQ-3.4 | TS-117-9 | 2.4 | test_validate_passes |
| 117-REQ-3.E1 | TS-117-E4 | 2.4 | test_validate_empty_title |
| 117-REQ-4.1 | TS-117-12 | 3.2 | test_store_adr |
| 117-REQ-4.2 | TS-117-13 | 3.2 | test_content_hash |
| 117-REQ-4.3 | TS-117-SMOKE-1 | 3.1 | test_smoke_ingest |
| 117-REQ-4.4 | TS-117-12 | 3.2 | test_store_adr |
| 117-REQ-4.E1 | TS-117-E5 | 3.2 | test_store_db_unavailable |
| 117-REQ-4.E2 | TS-117-15 | 3.2 | test_skip_duplicate |
| 117-REQ-5.1 | TS-117-14 | 3.2 | test_supersede |
| 117-REQ-5.2 | TS-117-15 | 3.2 | test_skip_duplicate |
| 117-REQ-5.3 | TS-117-14 | 3.2 | test_supersede |
| 117-REQ-5.E1 | TS-117-E8 | 3.2 | test_superseded_with_new |
| 117-REQ-6.1 | TS-117-16 | 4.1 | test_query_spec_refs |
| 117-REQ-6.2 | TS-117-17 | 4.2 | test_format_prompt |
| 117-REQ-6.3 | TS-117-18 | 4.4 | test_provider_retrieve |
| 117-REQ-6.4 | TS-117-19 | 2.5 | test_extract_spec_refs |
| 117-REQ-6.5 | TS-117-20 | 2.5 | test_extract_keywords |
| 117-REQ-6.E1 | TS-117-E6 | 4.1 | test_query_no_table |
| 117-REQ-6.E2 | TS-117-E7 | 4.1 | test_query_no_match |
| 117-REQ-7.1 | TS-117-21 | 3.3 | test_validation_warning |
| 117-REQ-7.2 | TS-117-21 | 3.3, 3.4 | test_validation_warning |
| 117-REQ-7.3 | TS-117-21 | 3.3 | test_validation_warning |
| 117-REQ-7.4 | TS-117-22 | 3.3, 3.4 | test_ingestion_audit |
| 117-REQ-7.E1 | TS-117-21 | 3.3 | test_validation_warning |

## Notes

- Follow the errata module pattern (`knowledge/errata.py`) for code style
  and error handling conventions.
- Use `uuid.uuid4()` for ADREntry IDs, consistent with other knowledge tables.
- The `_ADR_PATH_PATTERN` should use `re.compile` for the docs/adr/*.md glob.
- Property tests should use Hypothesis `@given` with appropriate strategies.
- DuckDB integration tests should use `duckdb.connect(":memory:")` with
  `run_migrations(conn)` for setup.
