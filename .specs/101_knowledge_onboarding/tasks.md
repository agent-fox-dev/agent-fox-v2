# Implementation Plan: Knowledge Onboarding

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

The onboarding subsystem is built in six task groups. Group 1 writes failing
tests. Group 2 implements git pattern mining (deterministic). Group 3
implements LLM code analysis. Group 4 implements LLM documentation mining.
Group 5 creates the onboard orchestrator and CLI command, wiring all phases
together. Group 6 verifies wiring.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_git_mining.py tests/unit/knowledge/test_code_analysis.py tests/unit/knowledge/test_doc_mining.py tests/unit/knowledge/test_onboard.py tests/unit/cli/test_onboard_cmd.py`
- Property tests: `uv run pytest -q tests/property/knowledge/test_onboard_props.py`
- Smoke tests: `uv run pytest -q tests/integration/knowledge/test_onboard_smoke.py`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/knowledge/test_git_mining.py`
    - Git numstat parsing (TS-101-17)
    - File frequency computation (TS-101-18)
    - Co-change count computation (TS-101-19)
    - Fragile area detection (TS-101-7)
    - Co-change pattern detection (TS-101-8)
    - Minimum commit threshold (TS-101-10)
    - MiningResult fields (TS-101-15)
    - Duplicate fact prevention (TS-101-16)
    - _Test Spec: TS-101-7, TS-101-8, TS-101-10, TS-101-15, TS-101-16,
      TS-101-17, TS-101-18, TS-101-19_

  - [x] 1.2 Create `tests/unit/knowledge/test_code_analysis.py`
    - Code analysis creates facts (TS-101-20)
    - File prioritization (TS-101-21)
    - CodeAnalysisResult fields (TS-101-23)
    - Dedup skips analyzed files (TS-101-24)
    - Parse LLM facts (TS-101-31)
    - LLM failure per file (TS-101-E7)
    - Empty entity graph fallback (TS-101-E8)
    - Unparseable LLM response (TS-101-E9)
    - _Test Spec: TS-101-20, TS-101-21, TS-101-23, TS-101-24, TS-101-31,
      TS-101-E7, TS-101-E8, TS-101-E9_

  - [x] 1.3 Create `tests/unit/knowledge/test_doc_mining.py`
    - Doc mining creates facts (TS-101-25)
    - Doc file collection (TS-101-26)
    - DocMiningResult fields (TS-101-28)
    - Dedup skips mined docs (TS-101-29)
    - LLM failure per doc (TS-101-E10)
    - No documentation files (TS-101-E11)
    - Unparseable LLM response (TS-101-E12)
    - _Test Spec: TS-101-25, TS-101-26, TS-101-28, TS-101-29,
      TS-101-E10, TS-101-E11, TS-101-E12_

  - [x] 1.4 Create `tests/unit/knowledge/test_onboard.py`
    - Entity graph phase runs (TS-101-3)
    - Entity graph phase skippable (TS-101-4)
    - Ingestion phase runs (TS-101-5)
    - Ingestion phase skippable (TS-101-6)
    - Mining phase skippable (TS-101-9)
    - Code analysis skippable (TS-101-22)
    - Doc mining skippable (TS-101-27)
    - Embedding phase runs (TS-101-11)
    - Embedding phase skippable (TS-101-12)
    - OnboardResult fields (TS-101-13)
    - Model option forwarded (TS-101-30)
    - Not a git repo (TS-101-E2)
    - Entity graph failure (TS-101-E3)
    - Ingestion source failure (TS-101-E4)
    - Embedding failure (TS-101-E5)
    - Non-git ingestion (TS-101-E6)
    - _Test Spec: TS-101-3 through TS-101-6, TS-101-9, TS-101-11 through
      TS-101-13, TS-101-22, TS-101-27, TS-101-30, TS-101-E2 through
      TS-101-E6_

  - [x] 1.5 Create `tests/unit/cli/test_onboard_cmd.py`
    - Command registration (TS-101-1)
    - Default path (TS-101-2)
    - JSON output (TS-101-14)
    - Invalid path (TS-101-E1)
    - _Test Spec: TS-101-1, TS-101-2, TS-101-14, TS-101-E1_

  - [x] 1.6 Create `tests/property/knowledge/test_onboard_props.py`
    - Threshold monotonicity (TS-101-P1)
    - Onboard idempotency (TS-101-P2)
    - Mining fact validity (TS-101-P3)
    - Phase independence (TS-101-P4)
    - LLM fact validity (TS-101-P5)
    - _Test Spec: TS-101-P1 through TS-101-P5_

  - [x] 1.7 Create `tests/integration/knowledge/test_onboard_smoke.py`
    - Full pipeline smoke test (TS-101-SMOKE-1)
    - Git mining end-to-end (TS-101-SMOKE-2)
    - Code analysis end-to-end (TS-101-SMOKE-3)
    - Doc mining end-to-end (TS-101-SMOKE-4)
    - _Test Spec: TS-101-SMOKE-1 through TS-101-SMOKE-4_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [x] 2. Git pattern mining module
  - [x] 2.1 Create `agent_fox/knowledge/git_mining.py`
    - MiningResult dataclass (frozen)
    - `_parse_git_numstat(project_root, days)` — subprocess + parse
    - `_compute_file_frequencies(commit_files)` — per-file counts
    - `_compute_cochange_counts(commit_files)` — per-pair counts
    - `_is_mining_fact_exists(conn, fingerprint)` — dedup check via
      keyword query on memory_facts
    - `mine_git_patterns(project_root, conn, *, days, fragile_threshold,
      cochange_threshold)` — orchestrator that creates Fact objects and
      writes them directly to DuckDB
    - _Requirements: 101-REQ-4.1, 101-REQ-4.2, 101-REQ-4.3, 101-REQ-4.4,
      101-REQ-4.5, 101-REQ-4.6, 101-REQ-4.E1, 101-REQ-4.E2, 101-REQ-4.E3_
  - Also: migration v10 (keywords column — v9 reserved for spec 102 language
    column), run_migrations() in migrations.py, knowledge_conn fixture in
    conftest.py, docs/errata/101_keywords_schema_migration.md (updated to v10)

  - [x] 2.V Verify task group 2
    - [x] Mining tests pass: `uv run pytest -q tests/unit/knowledge/test_git_mining.py` (27 passed)
    - [-] Mining property tests: blocked by missing code_analysis/doc_mining/onboard modules (task groups 3-5)
    - [-] Mining smoke test: blocked by missing modules (task groups 3-5)
    - [x] No regressions: total failures improved from 65 (baseline) to 62
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/git_mining.py agent_fox/knowledge/migrations.py`

- [ ] 3. LLM code analysis module
  - [ ] 3.1 Create `agent_fox/knowledge/code_analysis.py`
    - CodeAnalysisResult dataclass (frozen)
    - CODE_ANALYSIS_PROMPT system prompt constant
    - SOURCE_EXTENSIONS constant — recognized source file extensions for
      all supported languages (.py, .go, .rs, .ts, .js, .java, etc.)
    - `_scan_source_files(project_root)` — scans for source files by
      recognized extensions, respects .gitignore, excludes non-source dirs
    - `_get_files_by_priority(conn, project_root)` — queries entity graph
      for file entities sorted by incoming import edge count, falls back
      to `_scan_source_files` if entity graph empty or doesn't cover
      the project's language
    - `_parse_llm_facts(raw_text, spec_name, file_path, source_type)` —
      parses LLM JSON response into Fact objects with fingerprint keywords
    - `analyze_code_with_llm(project_root, conn, *, model, max_files)` —
      async orchestrator that iterates files, calls `ai_call()` per file,
      parses response, writes facts
    - _Requirements: 101-REQ-5.1, 101-REQ-5.2, 101-REQ-5.3, 101-REQ-5.5,
      101-REQ-5.6, 101-REQ-5.E1, 101-REQ-5.E2, 101-REQ-5.E3_

  - [ ] 3.V Verify task group 3
    - [ ] Code analysis tests pass: `uv run pytest -q tests/unit/knowledge/test_code_analysis.py`
    - [ ] LLM fact validity property test passes: `uv run pytest -q tests/property/knowledge/test_onboard_props.py -k "llm_fact_validity"`
    - [ ] Code analysis smoke test passes: `uv run pytest -q tests/integration/knowledge/test_onboard_smoke.py -k "code_analysis"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/code_analysis.py`

- [ ] 4. Documentation mining module
  - [ ] 4.1 Create `agent_fox/knowledge/doc_mining.py`
    - DocMiningResult dataclass (frozen)
    - DOC_MINING_PROMPT system prompt constant
    - `_collect_doc_files(project_root)` — collects README.md,
      CONTRIBUTING.md, CHANGELOG.md from root plus docs/**/*.md excluding
      docs/adr/ and docs/errata/
    - `mine_docs_with_llm(project_root, conn, *, model)` — async
      orchestrator that iterates docs, calls `ai_call()` per doc, parses
      response, writes facts. Reuses `_parse_llm_facts` from code_analysis
      and `_is_mining_fact_exists` from git_mining
    - _Requirements: 101-REQ-6.1, 101-REQ-6.2, 101-REQ-6.4, 101-REQ-6.5,
      101-REQ-6.6, 101-REQ-6.E1, 101-REQ-6.E2, 101-REQ-6.E3_

  - [ ] 4.V Verify task group 4
    - [ ] Doc mining tests pass: `uv run pytest -q tests/unit/knowledge/test_doc_mining.py`
    - [ ] Doc mining smoke test passes: `uv run pytest -q tests/integration/knowledge/test_onboard_smoke.py -k "doc_mining"`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/doc_mining.py`

- [ ] 5. Onboard orchestrator and CLI command
  - [ ] 5.1 Create `agent_fox/knowledge/onboard.py`
    - OnboardResult dataclass
    - `_is_git_repo(path)` helper
    - `_generate_missing_embeddings(conn, embedder)` helper
    - `async run_onboard(project_root, config, db, *, skip_*, model,
      thresholds)` orchestrator with per-phase error handling, timing,
      and git-repo detection
    - _Requirements: 101-REQ-1.6, 101-REQ-2.1, 101-REQ-2.2, 101-REQ-2.E1,
      101-REQ-3.1, 101-REQ-3.2, 101-REQ-3.3, 101-REQ-3.E1, 101-REQ-4.7,
      101-REQ-5.4, 101-REQ-6.3, 101-REQ-7.1, 101-REQ-7.2, 101-REQ-7.E1,
      101-REQ-8.1, 101-REQ-8.2, 101-REQ-8.3, 101-REQ-1.E2_

  - [ ] 5.2 Create `agent_fox/cli/onboard.py`
    - `onboard_cmd` click command with options: --path, --skip-entities,
      --skip-ingestion, --skip-mining, --skip-code-analysis,
      --skip-doc-mining, --skip-embeddings, --model, --mining-days,
      --fragile-threshold, --cochange-threshold, --max-files
    - Config loading, DB opening, asyncio.run(run_onboard(...)),
      summary printing, JSON output mode
    - _Requirements: 101-REQ-1.1, 101-REQ-1.2, 101-REQ-1.3, 101-REQ-1.4,
      101-REQ-1.5, 101-REQ-1.6, 101-REQ-1.E1_

  - [ ] 5.3 Register `onboard_cmd` in `agent_fox/cli/app.py`
    - Import and add_command
    - _Requirements: 101-REQ-1.1_

  - [ ] 5.V Verify task group 5
    - [ ] Orchestrator tests pass: `uv run pytest -q tests/unit/knowledge/test_onboard.py`
    - [ ] CLI tests pass: `uv run pytest -q tests/unit/cli/test_onboard_cmd.py`
    - [ ] Property tests pass: `uv run pytest -q tests/property/knowledge/test_onboard_props.py`
    - [ ] Full smoke test passes: `uv run pytest -q tests/integration/knowledge/test_onboard_smoke.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/knowledge/onboard.py agent_fox/cli/onboard.py agent_fox/cli/app.py`

- [ ] 6. Wiring verification

  - [ ] 6.1 Trace every execution path from design.md end-to-end
    - Path 1: onboard_cmd → asyncio.run → run_onboard → six phases →
      OnboardResult
    - Path 2: onboard_cmd with skip flags → only non-skipped phases
    - Path 3: mine_git_patterns → _parse_git_numstat → _compute_* →
      MemoryStore.write_fact → MiningResult
    - Path 4: analyze_code_with_llm → _get_files_by_priority → ai_call →
      _parse_llm_facts → MemoryStore.write_fact → CodeAnalysisResult
    - Path 5: mine_docs_with_llm → _collect_doc_files → ai_call →
      _parse_llm_facts → MemoryStore.write_fact → DocMiningResult
    - Confirm no function in the chain is a stub
    - _Requirements: all_

  - [ ] 6.2 Verify return values propagate correctly
    - analyze_codebase → OnboardResult.entities_*
    - KnowledgeIngestor.ingest_* → OnboardResult.{adrs,errata,git_commits}_ingested
    - mine_git_patterns → OnboardResult.{fragile_areas,cochange_patterns}_created
    - analyze_code_with_llm → OnboardResult.code_*
    - mine_docs_with_llm → OnboardResult.doc_*
    - _generate_missing_embeddings → OnboardResult.embeddings_*
    - _Requirements: all_

  - [ ] 6.3 Run the integration smoke tests
    - TS-101-SMOKE-1 through TS-101-SMOKE-4 pass
    - `uv run pytest -q tests/integration/knowledge/test_onboard_smoke.py`
    - _Test Spec: TS-101-SMOKE-1 through TS-101-SMOKE-4_

  - [ ] 6.4 Stub / dead-code audit
    - Search touched files for stubs, TODOs, NotImplementedError
    - Verify no dead code introduced
    - _Requirements: all_

  - [ ] 6.5 Cross-spec entry point verification
    - Verify `analyze_codebase` (Spec 95) is importable and called from
      onboard.py
    - Verify `KnowledgeIngestor` (existing) is importable and called
    - Verify `EmbeddingGenerator` (existing) is importable and called
    - Verify `ai_call` (existing) is importable and called from
      code_analysis.py and doc_mining.py
    - Verify `_parse_llm_facts` is importable from code_analysis.py by
      doc_mining.py
    - Verify `_is_mining_fact_exists` is importable from git_mining.py by
      code_analysis.py and doc_mining.py
    - Confirm no circular imports introduced
    - _Requirements: all_

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec imports work without circular dependencies
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings: `uv run ruff check agent_fox/ tests/`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 101-REQ-1.1 | TS-101-1 | 5.2, 5.3 | test_onboard_cmd::test_command_registration |
| 101-REQ-1.2 | TS-101-2 | 5.2 | test_onboard_cmd::test_default_path |
| 101-REQ-1.3 | TS-101-2 | 5.2 | test_onboard_cmd::test_default_path |
| 101-REQ-1.4 | TS-101-SMOKE-1 | 5.2 | test_onboard_smoke::test_full_pipeline |
| 101-REQ-1.5 | TS-101-14 | 5.2 | test_onboard_cmd::test_json_output |
| 101-REQ-1.6 | TS-101-30 | 5.1, 5.2 | test_onboard::test_model_option |
| 101-REQ-1.E1 | TS-101-E1 | 5.2 | test_onboard_cmd::test_invalid_path |
| 101-REQ-1.E2 | TS-101-E2 | 5.1 | test_onboard::test_not_git_repo |
| 101-REQ-2.1 | TS-101-3 | 5.1 | test_onboard::test_entity_phase_runs |
| 101-REQ-2.2 | TS-101-4 | 5.1 | test_onboard::test_entity_phase_skippable |
| 101-REQ-2.E1 | TS-101-E3 | 5.1 | test_onboard::test_entity_phase_failure |
| 101-REQ-3.1 | TS-101-5 | 5.1 | test_onboard::test_ingestion_phase_runs |
| 101-REQ-3.2 | TS-101-6 | 5.1 | test_onboard::test_ingestion_phase_skippable |
| 101-REQ-3.3 | TS-101-E6 | 5.1 | test_onboard::test_non_git_ingestion |
| 101-REQ-3.E1 | TS-101-E4 | 5.1 | test_onboard::test_ingestion_source_failure |
| 101-REQ-4.1 | TS-101-7 | 2.1 | test_git_mining::test_fragile_areas |
| 101-REQ-4.2 | TS-101-8 | 2.1 | test_git_mining::test_cochange_patterns |
| 101-REQ-4.3 | TS-101-17 | 2.1 | test_git_mining::test_parse_numstat |
| 101-REQ-4.4 | TS-101-7 | 2.1 | test_git_mining::test_fragile_areas |
| 101-REQ-4.5 | TS-101-8 | 2.1 | test_git_mining::test_cochange_patterns |
| 101-REQ-4.6 | TS-101-15 | 2.1 | test_git_mining::test_mining_result_fields |
| 101-REQ-4.7 | TS-101-9 | 5.1 | test_onboard::test_mining_skippable |
| 101-REQ-4.E1 | TS-101-E2 | 2.1 | test_onboard::test_not_git_repo |
| 101-REQ-4.E2 | TS-101-10 | 2.1 | test_git_mining::test_min_commit_threshold |
| 101-REQ-4.E3 | TS-101-16 | 2.1 | test_git_mining::test_duplicate_prevention |
| 101-REQ-5.1 | TS-101-20 | 3.1 | test_code_analysis::test_creates_facts |
| 101-REQ-5.2 | TS-101-21 | 3.1 | test_code_analysis::test_file_prioritization |
| 101-REQ-5.3 | TS-101-30 | 3.1 | test_onboard::test_model_option |
| 101-REQ-5.4 | TS-101-22 | 5.1 | test_onboard::test_code_analysis_skippable |
| 101-REQ-5.5 | TS-101-23 | 3.1 | test_code_analysis::test_result_fields |
| 101-REQ-5.6 | TS-101-24 | 3.1 | test_code_analysis::test_dedup |
| 101-REQ-5.E1 | TS-101-E7 | 3.1 | test_code_analysis::test_llm_failure |
| 101-REQ-5.E2 | TS-101-E8 | 3.1 | test_code_analysis::test_empty_entity_graph |
| 101-REQ-5.E3 | TS-101-E9 | 3.1 | test_code_analysis::test_unparseable_response |
| 101-REQ-6.1 | TS-101-25 | 4.1 | test_doc_mining::test_creates_facts |
| 101-REQ-6.2 | TS-101-26 | 4.1 | test_doc_mining::test_file_collection |
| 101-REQ-6.3 | TS-101-27 | 5.1 | test_onboard::test_doc_mining_skippable |
| 101-REQ-6.4 | TS-101-28 | 4.1 | test_doc_mining::test_result_fields |
| 101-REQ-6.5 | TS-101-30 | 4.1 | test_onboard::test_model_option |
| 101-REQ-6.6 | TS-101-29 | 4.1 | test_doc_mining::test_dedup |
| 101-REQ-6.E1 | TS-101-E10 | 4.1 | test_doc_mining::test_llm_failure |
| 101-REQ-6.E2 | TS-101-E11 | 4.1 | test_doc_mining::test_no_docs |
| 101-REQ-6.E3 | TS-101-E12 | 4.1 | test_doc_mining::test_unparseable_response |
| 101-REQ-7.1 | TS-101-11 | 5.1 | test_onboard::test_embedding_phase |
| 101-REQ-7.2 | TS-101-12 | 5.1 | test_onboard::test_embedding_skippable |
| 101-REQ-7.E1 | TS-101-E5 | 5.1 | test_onboard::test_embedding_failure |
| 101-REQ-8.1 | TS-101-13 | 5.1 | test_onboard::test_onboard_result_fields |
| 101-REQ-8.2 | TS-101-16 | 2.1, 3.1, 4.1, 5.1 | test_git_mining::test_duplicate_prevention |
| 101-REQ-8.3 | TS-101-13 | 5.1 | test_onboard::test_onboard_result_fields |
| Property 1 | TS-101-P1 | 2.1 | test_onboard_props::test_threshold_monotonicity |
| Property 2 | TS-101-P2 | 5.1 | test_onboard_props::test_idempotency |
| Property 3 | TS-101-P3 | 2.1 | test_onboard_props::test_mining_fact_validity |
| Property 4 | TS-101-P4 | 5.1 | test_onboard_props::test_phase_independence |
| Property 5 | TS-101-P5 | 3.1 | test_onboard_props::test_llm_fact_validity |
| Path 1 | TS-101-SMOKE-1 | 5.1, 5.2 | test_onboard_smoke::test_full_pipeline |
| Path 3 | TS-101-SMOKE-2 | 2.1 | test_onboard_smoke::test_mining_end_to_end |
| Path 4 | TS-101-SMOKE-3 | 3.1 | test_onboard_smoke::test_code_analysis_end_to_end |
| Path 5 | TS-101-SMOKE-4 | 4.1 | test_onboard_smoke::test_doc_mining_end_to_end |

## Notes

- **Subprocess mocking:** All `git log` and `git rev-parse` calls in tests
  must mock `subprocess.run`. Tests should not depend on real git history.
- **LLM mocking:** All unit tests must mock `ai_call`. Use structured JSON
  responses matching the prompt templates. Smoke tests also mock `ai_call`
  (no real LLM calls in CI).
- **DuckDB fixtures:** Reuse existing DuckDB test fixtures with all
  migrations applied (through v8 for entity graph tables).
- **Hypothesis health checks:** Use
  `suppress_health_check=[HealthCheck.function_scoped_fixture]` for
  property tests using pytest fixtures.
- **Temp directories:** Smoke tests should create temporary directory trees
  with source files (any language), docs/adr/, and README.md as fixtures
  using `tmp_path`.
- **Embedding mocking:** Mock `EmbeddingGenerator` in unit tests. Smoke
  tests may use the real embedder if `sentence-transformers` is available,
  otherwise mock it.
- **Click testing:** Use `click.testing.CliRunner` for CLI command tests.
- **Async testing:** Use `pytest-asyncio` for async test functions. The
  orchestrator tests need `@pytest.mark.asyncio`.
- **Shared utilities:** `_parse_llm_facts` lives in `code_analysis.py` and
  is imported by `doc_mining.py`. `_is_mining_fact_exists` lives in
  `git_mining.py` and is imported by both LLM modules.
