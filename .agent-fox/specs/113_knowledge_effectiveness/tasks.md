# Implementation Plan: Knowledge System Effectiveness

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in seven groups. Group 1 writes failing tests from the
test specification. Groups 2-3 implement the six core changes in dependency
order: transcript reconstruction and compaction improvements first (no
cross-module dependencies), then entity signal activation, cold-start skip,
git extraction, and audit consumption (which depend on earlier groups or
require async LLM calls). Group 4 adds retrieval quality validation. Group 5
is a checkpoint. Group 6 wires audit findings into fresh coder prompts. Group
7 is the mandatory wiring verification.

The `ingest_git_commits` method becomes async in group 3, so callers
(`run_background_ingestion`) must be updated in the same group.

## Test Commands

- Spec tests: `uv run pytest -q tests/unit/knowledge/test_transcript_reconstruction.py tests/unit/knowledge/test_git_extraction.py tests/unit/knowledge/test_entity_signal_activation.py tests/unit/knowledge/test_audit_consumption.py tests/unit/knowledge/test_compaction_improvements.py tests/unit/knowledge/test_cold_start.py tests/unit/knowledge/test_retrieval_quality.py tests/integration/test_knowledge_effectiveness_smoke.py`
- Unit tests: `uv run pytest -q tests/unit/knowledge/`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create test file structure
    - Create `tests/unit/knowledge/test_transcript_reconstruction.py` for
      Suite 1 tests (TS-1.1 through TS-1.5)
    - Create `tests/unit/knowledge/test_git_extraction.py` for Suite 2
      tests (TS-2.1 through TS-2.5)
    - Create `tests/unit/knowledge/test_entity_signal_activation.py` for
      Suite 3 tests (TS-3.1 through TS-3.4)
    - Create `tests/unit/knowledge/test_audit_consumption.py` for Suite 4
      tests (TS-4.1 through TS-4.4)
    - Create `tests/unit/knowledge/test_compaction_improvements.py` for
      Suite 5 tests (TS-5.1 through TS-5.5)
    - Create `tests/unit/knowledge/test_cold_start.py` for Suite 6
      tests (TS-6.1 through TS-6.4)
    - Create `tests/unit/knowledge/test_retrieval_quality.py` for Suite 7
      tests (TS-7.1 through TS-7.3)
    - Create `tests/integration/test_knowledge_effectiveness_smoke.py` for
      integration smoke tests
    - _Test Spec: TS-1.1 through TS-7.3_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - One test function per TS entry from Suites 1-7
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - Use `unittest.mock.AsyncMock` for LLM calls, `tmp_path` for JSONL files
    - Use existing `duckdb_conn` / `knowledge_db` fixtures for DB tests
    - _Test Spec: TS-1.1 through TS-7.3_

  - [x] 1.3 Write integration smoke tests
    - One smoke test per execution path from design.md (Paths 1-7)
    - Stub only LLM calls and filesystem; use real DuckDB and real module code
    - _Test Spec: smoke tests for Paths 1-7_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check tests/`

- [ ] 2. Transcript reconstruction + compaction improvements
  - [ ] 2.1 Add `reconstruct_transcript` to `agent_trace.py`
    - Add module-level function `reconstruct_transcript(audit_dir, run_id,
      node_id) -> str` that reads `agent_{run_id}.jsonl`, filters
      `assistant.message` events matching `node_id`, and returns concatenated
      content
    - Handle missing file (return empty string, log warning) and zero matches
      (return empty string)
    - _Requirements: 113-REQ-1.1, 113-REQ-1.E1, 113-REQ-1.E2_
    - _Test Spec: TS-1.1, TS-1.2, TS-1.3_

  - [ ] 2.2 Modify `_extract_knowledge_and_findings` in `session_lifecycle.py`
    - Before falling back to session summary, call `reconstruct_transcript()`
      with the audit_dir, run_id, and node_id
    - If reconstructed transcript is non-empty and exceeds the minimum char
      threshold, use it as the transcript parameter
    - If empty, fall back to existing `_build_fallback_input` path
    - Continue using session summary for the log message
    - _Requirements: 113-REQ-1.1, 113-REQ-1.2, 113-REQ-1.3_
    - _Test Spec: TS-1.4, TS-1.5_

  - [ ] 2.3 Add `_filter_minimum_length` to `compaction.py`
    - Add function `_filter_minimum_length(facts, min_length=50)` that removes
      facts with `len(content) < min_length`
    - Returns `(surviving_facts, filtered_count)`
    - _Requirements: 113-REQ-5.2_
    - _Test Spec: TS-5.2_

  - [ ] 2.4 Add `_substring_supersede` to `compaction.py`
    - Add function that identifies facts whose content is a substring of
      another fact with equal or higher confidence
    - Mark the shorter fact as superseded by the longer
    - Returns `(surviving_facts, superseded_count)`
    - _Requirements: 113-REQ-5.1_
    - _Test Spec: TS-5.1_

  - [ ] 2.5 Integrate new compaction steps into `compact()`
    - Add `_filter_minimum_length` call before existing `_deduplicate_by_content`
    - Add `_substring_supersede` call after content-hash dedup
    - Update confidence-aware dedup to keep higher confidence (ties broken by
      recency) per 113-REQ-5.3
    - Add info log when compaction reduces facts by > 50%
    - _Requirements: 113-REQ-5.1, 113-REQ-5.2, 113-REQ-5.3, 113-REQ-5.E1_
    - _Test Spec: TS-5.3, TS-5.4, TS-5.5_

  - [ ] 2.V Verify task group 2
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_transcript_reconstruction.py tests/unit/knowledge/test_compaction_improvements.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 113-REQ-1.*, 113-REQ-5.* acceptance criteria met

- [ ] 3. Entity signal, cold-start, git extraction, audit consumption
  - [ ] 3.1 Add `_query_prior_touched_files` to `NodeSessionRunner`
    - Add method on `NodeSessionRunner` that queries `session_outcomes` for
      `touched_path` from prior completed sessions with the same `spec_name`
    - Split comma-delimited `touched_path` values, deduplicate, limit to 50
      most recently touched paths (by `created_at`)
    - Return empty list if no prior sessions exist
    - _Requirements: 113-REQ-3.1, 113-REQ-3.2, 113-REQ-3.E1_
    - _Test Spec: TS-3.1, TS-3.2, TS-3.3_

  - [ ] 3.2 Wire touched files into `_build_prompts`
    - In `_build_prompts`, call `_query_prior_touched_files(self._spec_name)`
      and pass the result to `retriever.retrieve(touched_files=...)` instead
      of the hardcoded `[]`
    - _Requirements: 113-REQ-3.1_
    - _Test Spec: TS-3.4_

  - [ ] 3.3 Add cold-start detection to `AdaptiveRetriever.retrieve`
    - Add `_count_available_facts(spec_name, confidence_threshold)` method
      that runs `SELECT COUNT(*) FROM memory_facts WHERE (spec_name = ? OR
      confidence >= ?) AND supersedes IS NULL`
    - If count == 0, return `RetrievalResult(cold_start=True, ...)` with
      debug log "Skipping retrieval: no facts available (cold start)"
    - If count query fails (database error), log warning and proceed with
      normal retrieval
    - Add `cold_start: bool = False` field to `RetrievalResult`
    - _Requirements: 113-REQ-6.1, 113-REQ-6.2, 113-REQ-6.E1_
    - _Test Spec: TS-6.1, TS-6.2, TS-6.3, TS-6.4_

  - [ ] 3.4 Add LLM-powered git commit extraction
    - Add `GIT_EXTRACTION_PROMPT` constant to `extraction.py`
    - Add async method `_extract_git_facts_llm(batch, model_name)` to
      `KnowledgeIngestor` that calls the LLM with batched commit messages
      and parses the response into `Fact` objects with variable confidence
    - Make `ingest_git_commits` async; batch commits into groups of 20,
      skip messages < 20 chars, call `_extract_git_facts_llm` per batch
    - On LLM failure, skip batch and log warning
    - When LLM returns empty array, store zero facts for that batch
    - Update `run_background_ingestion` to await the async call
    - _Requirements: 113-REQ-2.1, 113-REQ-2.2, 113-REQ-2.3, 113-REQ-2.E1,
      113-REQ-2.E2_
    - _Test Spec: TS-2.1, TS-2.2, TS-2.3, TS-2.4, TS-2.5_

  - [ ] 3.5 Add audit finding persistence to review pathway
    - In the audit-review persistence path (review_persistence.py), after
      `persist_auditor_results` writes the markdown report, also call
      `insert_findings(conn, findings)` with `category='audit'` for each
      non-PASS entry in the `AuditResult`
    - Parse `AuditResult.entries` into `ReviewFinding` objects with severity
      derived from the entry verdict
    - If parsing fails, log warning and retain raw report file
    - _Requirements: 113-REQ-4.1, 113-REQ-4.3, 113-REQ-4.E1_
    - _Test Spec: TS-4.1, TS-4.3, TS-4.4_

  - [ ] 3.V Verify task group 3
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_entity_signal_activation.py tests/unit/knowledge/test_cold_start.py tests/unit/knowledge/test_git_extraction.py tests/unit/knowledge/test_audit_consumption.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 113-REQ-2.*, 113-REQ-3.*, 113-REQ-4.1/4.3/4.E1,
      113-REQ-6.* acceptance criteria met

- [ ] 4. Retrieval quality validation + audit prompt injection
  - [ ] 4.1 Add `KNOWLEDGE_RETRIEVAL` audit event type
    - Add `KNOWLEDGE_RETRIEVAL = "knowledge.retrieval"` to `AuditEventType`
      enum in `audit.py`
    - _Requirements: 113-REQ-7.1_

  - [ ] 4.2 Emit retrieval audit event from `AdaptiveRetriever.retrieve`
    - After RRF fusion, emit `knowledge.retrieval` event via the
      `SinkDispatcher` (passed through constructor or method parameter)
    - Event payload: `spec_name`, `node_id`, `facts_returned`, `signals_active`
      (list of signal names with non-empty results), `cold_start`, `token_budget_used`
    - Wrap in try/except to ensure emission failure doesn't block retrieval
    - Add `token_budget_used: int = 0` field to `RetrievalResult`
    - _Requirements: 113-REQ-7.1, 113-REQ-7.E1_
    - _Test Spec: TS-7.1, TS-7.3_

  - [ ] 4.3 Add `retrieval_summary` to session outcomes
    - Add `retrieval_summary TEXT` column to `session_outcomes` via schema
      migration (next version)
    - After retrieval in `_build_prompts`, store a JSON summary dict
      `{"facts_injected": int, "signals_active": list[str]}` and persist it
      when recording the session outcome
    - _Requirements: 113-REQ-7.2_
    - _Test Spec: TS-7.2_

  - [ ] 4.4 Inject audit findings into first-attempt coder prompts
    - Extend `_build_prompts` to query and inject audit findings for all
      coder attempts (not just retries)
    - Use the same `query_active_findings` / `build_retry_context` mechanism
      but call it for `attempt >= 1` (currently gated on `attempt > 1`)
    - Audit findings (category='audit') are already returned by
      `query_active_findings` since it queries all non-superseded findings
    - _Requirements: 113-REQ-4.2_
    - _Test Spec: TS-4.2_

  - [ ] 4.V Verify task group 4
    - [ ] Spec tests pass: `uv run pytest -q tests/unit/knowledge/test_retrieval_quality.py tests/unit/knowledge/test_audit_consumption.py`
    - [ ] All existing tests still pass: `uv run pytest -q`
    - [ ] No linter warnings introduced: `uv run ruff check agent_fox/ tests/`
    - [ ] Requirements 113-REQ-4.2, 113-REQ-7.* acceptance criteria met

- [ ] 5. Checkpoint — all spec tests green
  - [ ] 5.1 Run full spec test suite
    - All tests from Suites 1-7 pass
    - All integration smoke tests pass
    - `uv run pytest -q tests/unit/knowledge/test_transcript_reconstruction.py tests/unit/knowledge/test_git_extraction.py tests/unit/knowledge/test_entity_signal_activation.py tests/unit/knowledge/test_audit_consumption.py tests/unit/knowledge/test_compaction_improvements.py tests/unit/knowledge/test_cold_start.py tests/unit/knowledge/test_retrieval_quality.py tests/integration/test_knowledge_effectiveness_smoke.py`

  - [ ] 5.2 Run full regression suite
    - `uv run pytest -q`
    - Zero regressions in existing tests

  - [ ] 5.3 Update `docs/memory.md` with implementation notes

- [ ] 6. Wiring verification
  - [ ] 6.1 Trace every execution path from design.md end-to-end
    - For each of the 7 paths, verify the entry point actually calls the next
      function in the chain (read the calling code, do not assume)
    - Confirm no function in the chain is a stub (`return []`, `return None`,
      `pass`, `raise NotImplementedError`) that was never replaced
    - Every path must be live in production code — errata or deferrals do not
      satisfy this check
    - _Requirements: all_

  - [ ] 6.2 Verify return values propagate correctly
    - For every function in this spec that returns data consumed by a caller,
      confirm the caller receives and uses the return value
    - Key returns: `reconstruct_transcript` -> `_extract_knowledge_and_findings`,
      `_query_prior_touched_files` -> `_build_prompts`,
      `_count_available_facts` -> `retrieve`, `_extract_git_facts_llm` ->
      `ingest_git_commits`, `_substring_supersede` -> `compact`
    - _Requirements: all_

  - [ ] 6.3 Run the integration smoke tests
    - All smoke tests pass using real components (no stub bypass)
    - _Test Spec: smoke tests for Paths 1-7_

  - [ ] 6.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation

  - [ ] 6.5 Cross-spec entry point verification
    - Verify that `reconstruct_transcript` is called from
      `_extract_knowledge_and_findings` (session_lifecycle.py)
    - Verify that `_query_prior_touched_files` is called from `_build_prompts`
    - Verify that `ingest_git_commits` (now async) is still called from
      `run_background_ingestion` (ingest.py)
    - Verify that audit findings flow from `review_persistence.py` through
      `insert_findings` to `query_active_findings` to `_build_prompts`
    - _Requirements: all_

  - [ ] 6.V Verify wiring group
    - [ ] All smoke tests pass
    - [ ] No unjustified stubs remain in touched files
    - [ ] All execution paths from design.md are live (traceable in code)
    - [ ] All cross-spec entry points are called from production code
    - [ ] All existing tests still pass: `uv run pytest -q`

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 113-REQ-1.1 | TS-1.1, TS-1.4 | 2.1, 2.2 | test_transcript_reconstruction.py |
| 113-REQ-1.2 | TS-1.4 | 2.2 | test_transcript_reconstruction.py |
| 113-REQ-1.3 | TS-1.4, TS-1.5 | 2.2 | test_transcript_reconstruction.py |
| 113-REQ-1.E1 | TS-1.2, TS-1.5 | 2.1, 2.2 | test_transcript_reconstruction.py |
| 113-REQ-1.E2 | TS-1.3 | 2.1 | test_transcript_reconstruction.py |
| 113-REQ-2.1 | TS-2.1, TS-2.5 | 3.4 | test_git_extraction.py |
| 113-REQ-2.2 | TS-2.2 | 3.4 | test_git_extraction.py |
| 113-REQ-2.3 | TS-2.1 | 3.4 | test_git_extraction.py |
| 113-REQ-2.E1 | TS-2.3 | 3.4 | test_git_extraction.py |
| 113-REQ-2.E2 | TS-2.4 | 3.4 | test_git_extraction.py |
| 113-REQ-3.1 | TS-3.1, TS-3.4 | 3.1, 3.2 | test_entity_signal_activation.py |
| 113-REQ-3.2 | TS-3.2 | 3.1 | test_entity_signal_activation.py |
| 113-REQ-3.E1 | TS-3.3 | 3.1 | test_entity_signal_activation.py |
| 113-REQ-4.1 | TS-4.1 | 3.5 | test_audit_consumption.py |
| 113-REQ-4.2 | TS-4.2 | 4.4 | test_audit_consumption.py |
| 113-REQ-4.3 | TS-4.3 | 3.5 | test_audit_consumption.py |
| 113-REQ-4.E1 | TS-4.4 | 3.5 | test_audit_consumption.py |
| 113-REQ-5.1 | TS-5.1 | 2.4, 2.5 | test_compaction_improvements.py |
| 113-REQ-5.2 | TS-5.2 | 2.3, 2.5 | test_compaction_improvements.py |
| 113-REQ-5.3 | TS-5.3, TS-5.4 | 2.5 | test_compaction_improvements.py |
| 113-REQ-5.E1 | TS-5.5 | 2.5 | test_compaction_improvements.py |
| 113-REQ-6.1 | TS-6.1, TS-6.4 | 3.3 | test_cold_start.py |
| 113-REQ-6.2 | TS-6.1, TS-6.2 | 3.3 | test_cold_start.py |
| 113-REQ-6.E1 | TS-6.3 | 3.3 | test_cold_start.py |
| 113-REQ-7.1 | TS-7.1 | 4.1, 4.2 | test_retrieval_quality.py |
| 113-REQ-7.2 | TS-7.2 | 4.3 | test_retrieval_quality.py |
| 113-REQ-7.E1 | TS-7.3 | 4.2 | test_retrieval_quality.py |

## Notes

- **Async migration**: `ingest_git_commits` becomes async in task 3.4. All
  callers (`run_background_ingestion` and tests) must be updated in the same
  task to avoid broken imports.
- **No schema-breaking changes**: The only schema change is adding a nullable
  `retrieval_summary` column to `session_outcomes` (task 4.3). This is
  backward-compatible.
- **LLM mocking**: All tests that call LLM extraction use `AsyncMock`. The
  mock returns well-formed JSON matching the extraction prompt's expected
  format.
- **Existing review finding injection**: The `_build_retry_context` / 
  `query_active_findings` mechanism already works for pre-review findings.
  Task 4.4 extends it to fire on first attempts too, and audit findings are
  automatically included because `query_active_findings` returns all active
  findings regardless of category.
