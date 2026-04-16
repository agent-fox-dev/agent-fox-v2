# Implementation Plan: Hunt Scan Duplicate Detection and `af:ignore` Label

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation is split into 6 task groups plus a final wiring verification:

1. **Write failing spec tests** — translate all test_spec.md entries into
   executable failing tests.
2. **Label and config** — define `af:ignore` label constant, add to
   `REQUIRED_LABELS`, add `similarity_threshold` config field.
3. **Similarity computation** — implement `cosine_similarity()`, text
   representation builders, and embedding-based matching in `dedup.py`.
4. **Ignore filter** — implement `filter_ignored()` in new
   `nightshift/ignore_filter.py`.
5. **Knowledge ingestion** — implement `ingest_ignore_signals()` in new
   `nightshift/ignore_ingest.py`; enhance critic prompt with false positives.
6. **Engine wiring** — wire the enhanced pipeline in `engine.py`: ingestion
   pre-phase, false-positive query, similarity dedup, ignore filter.
7. **Wiring verification** — trace all execution paths, verify return value
   propagation, run smoke tests, audit stubs.

## Test Commands

- Spec tests: `uv run pytest -q tests/test_hunt_dedup_similarity.py tests/test_ignore_filter.py tests/test_ignore_ingest.py tests/test_critic_false_positives.py`
- Unit tests: `uv run pytest -q tests/ -k "dedup or ignore or critic_false"`
- Property tests: `uv run pytest -q tests/ -k "property"`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check .`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/test_hunt_dedup_similarity.py`
    - Unit tests for `cosine_similarity()`: TS-110-4, TS-110-E1
    - Unit tests for `build_finding_group_text()`: TS-110-5
    - Unit tests for `build_issue_text()`: TS-110-6
    - Integration tests for `filter_known_duplicates()` enhanced: TS-110-7, TS-110-8, TS-110-9
    - Edge case tests: TS-110-E2, TS-110-E3, TS-110-E8, TS-110-E9
    - Property tests: TS-110-P1, TS-110-P2, TS-110-P3, TS-110-P4, TS-110-P7, TS-110-P8
    - _Test Spec: TS-110-4 through TS-110-9, TS-110-E1 through TS-110-E3, TS-110-E8, TS-110-E9, TS-110-P1 through TS-110-P4, TS-110-P7, TS-110-P8_

  - [x] 1.2 Create `tests/test_ignore_filter.py`
    - Integration tests for `filter_ignored()`: TS-110-10, TS-110-11
    - Edge case tests: TS-110-E4
    - Property test: TS-110-P5
    - Smoke test: TS-110-SMOKE-1
    - _Test Spec: TS-110-10, TS-110-11, TS-110-E4, TS-110-P5, TS-110-SMOKE-1_

  - [x] 1.3 Create `tests/test_ignore_ingest.py`
    - Integration tests for `ingest_ignore_signals()`: TS-110-12, TS-110-13
    - Unit test for category extraction: TS-110-17
    - Edge case tests: TS-110-E5, TS-110-E6, TS-110-E7
    - Property test: TS-110-P6
    - Smoke test: TS-110-SMOKE-2
    - _Test Spec: TS-110-12, TS-110-13, TS-110-17, TS-110-E5 through TS-110-E7, TS-110-P6, TS-110-SMOKE-2_

  - [x] 1.4 Create `tests/test_critic_false_positives.py`
    - Unit tests for critic prompt enhancement: TS-110-14, TS-110-15
    - Property test: TS-110-P9
    - Smoke test: TS-110-SMOKE-3
    - _Test Spec: TS-110-14, TS-110-15, TS-110-P9, TS-110-SMOKE-3_

  - [x] 1.5 Create `tests/test_ignore_label.py`
    - Unit tests for label constants: TS-110-1, TS-110-2, TS-110-3
    - Unit test for config field: TS-110-16
    - _Test Spec: TS-110-1, TS-110-2, TS-110-3, TS-110-16_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings introduced: `uv run ruff check .`

- [x] 2. Label and configuration
  - [x] 2.1 Add `LABEL_IGNORE` and `LABEL_IGNORE_COLOR` to `platform/labels.py`
    - Define `LABEL_IGNORE: str = "af:ignore"`
    - Define `LABEL_IGNORE_COLOR: str = "999999"`
    - Add `LabelSpec(name=LABEL_IGNORE, color=LABEL_IGNORE_COLOR, description="Hunt findings marked as not-an-issue by the user")` to `REQUIRED_LABELS`
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Add `similarity_threshold` to `NightShiftConfig` in `core/config.py`
    - Add field: `similarity_threshold: Annotated[float, Clamped(ge=0.0, le=1.0)] = Field(default=0.85, description="...")`
    - _Requirements: 7.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest -q tests/test_ignore_label.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check .`
    - [x] Requirements 1.1, 1.2, 1.3, 1.4, 7.1 acceptance criteria met

- [x] 3. Similarity computation and enhanced dedup
  - [x] 3.1 Add `cosine_similarity()` to `nightshift/dedup.py`
    - Implement using `math.sqrt` and dot product
    - Handle None and empty vectors (return 0.0)
    - _Requirements: 2.4, 2.E1_

  - [x] 3.2 Add text representation builders to `nightshift/dedup.py`
    - `build_finding_group_text(group: FindingGroup) -> str`
    - `build_issue_text(issue: IssueResult) -> str`
    - _Requirements: 2.2, 2.3_

  - [x] 3.3 Enhance `filter_known_duplicates()` in `nightshift/dedup.py`
    - Change `state="open"` to `state="all"` in `list_issues_by_label` call
    - Add `similarity_threshold` and `embedder` parameters
    - After fingerprint check, compute embeddings for remaining groups and issues
    - Compare using `cosine_similarity()` and filter groups above threshold
    - Short-circuit: skip embedding comparison for groups already matched by fingerprint
    - Fail-open on embedding failure: fall back to fingerprint-only
    - Log INFO for each similarity-matched group with title, issue number, score
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.E1, 3.E2_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest -q tests/test_hunt_dedup_similarity.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check .`
    - [x] Requirements 2.1, 2.2, 2.3, 2.4, 3.1-3.5 acceptance criteria met

- [x] 4. Ignore filter
  - [x] 4.1 Create `nightshift/ignore_filter.py`
    - Implement `filter_ignored(groups, platform, *, similarity_threshold, embedder)`
    - Fetch `af:ignore` issues with `state="all"`
    - Compute embeddings for groups and ignored issues
    - Filter groups with similarity above threshold
    - Fail-open on platform or embedding failure
    - Log INFO for each suppressed group
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.E1, 4.E2, 4.E3_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest -q tests/test_ignore_filter.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check .`
    - [x] Requirements 4.1-4.4 acceptance criteria met

- [x] 5. Knowledge ingestion and critic enhancement
  - [x] 5.1 Create `nightshift/ignore_ingest.py`
    - Implement `ingest_ignore_signals(platform, conn, embedder, *, sink, run_id)`
    - Fetch `af:ignore` issues with `state="all"`
    - Detect ingestion marker (`<!-- af:knowledge-ingested -->`)
    - Extract category from issue body (`**Category:**` field parsing)
    - Build `Fact` with `category="anti_pattern"`, `spec_name="nightshift:ignore"`, `confidence=0.9`
    - Write fact to DuckDB via `_write_fact()`
    - Append marker to issue body via `platform.update_issue()`
    - Handle failures: skip on knowledge store unavailable, warn on update failure
    - Return count of newly ingested facts
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.E1, 5.E2, 5.E3_

  - [x] 5.2 Enhance `consolidate_findings()` in `nightshift/critic.py`
    - Add `false_positives: list[str] | None = None` parameter
    - When non-empty, append `Known False Positives` section to `_CRITIC_SYSTEM_PROMPT`
    - Pass through to `_run_critic()` (which uses the modified prompt)
    - When empty or None, do not modify the prompt
    - _Requirements: 6.1, 6.2, 6.E2_

  - [x] 5.V Verify task group 5
    - [x] Spec tests pass: `uv run pytest -q tests/test_ignore_ingest.py tests/test_critic_false_positives.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check .`
    - [x] Requirements 5.1-5.4, 6.1, 6.2 acceptance criteria met

- [x] 6. Engine wiring
  - [x] 6.1 Wire ingestion pre-phase in `engine.py`
    - Before `_run_hunt_scan_inner()`, call `ingest_ignore_signals()`
    - Handle knowledge store unavailability (skip, warn)
    - _Requirements: 5.1, 6.3_

  - [x] 6.2 Wire false-positive query in `engine.py`
    - After ingestion, query knowledge store for `anti_pattern` facts with
      `spec_name="nightshift:ignore"`
    - Pass result as `false_positives` to `consolidate_findings()`
    - Handle query failure (pass empty list, warn)
    - _Requirements: 6.3, 6.E1_

  - [x] 6.3 Wire similarity dedup and ignore filter in `engine.py`
    - Pass `similarity_threshold` from config to `filter_known_duplicates()`
    - Pass `embedder` to `filter_known_duplicates()`
    - Add `filter_ignored()` call after `filter_known_duplicates()`
    - Pass `similarity_threshold` and `embedder` to `filter_ignored()`
    - _Requirements: 4.1, 7.2_

  - [x] 6.V Verify task group 6
    - [x] Spec tests pass: `uv run pytest -q tests/test_hunt_dedup_similarity.py tests/test_ignore_filter.py tests/test_ignore_ingest.py tests/test_critic_false_positives.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check .`
    - [x] Requirements 4.1, 5.1, 6.3, 7.2 acceptance criteria met

- [ ] 7. Wiring verification

  - [ ] 7.1 Trace every execution path from design.md end-to-end
    - For Path 1 (hunt scan with enhanced dedup): verify `_run_hunt_scan` calls
      `ingest_ignore_signals`, queries knowledge store, calls `consolidate_findings`
      with `false_positives`, calls `filter_known_duplicates` with `similarity_threshold`
      and `embedder`, calls `filter_ignored`, then `create_issues_from_groups`
    - For Path 2 (knowledge ingestion): verify `ingest_ignore_signals` calls
      `list_issues_by_label`, `_is_ingested`, `_build_fact_from_issue`,
      `_write_fact`, `update_issue`
    - For Path 3 (critic with false positives): verify `consolidate_findings`
      passes `false_positives` to `_run_critic` which builds the enhanced prompt
    - Every path must be live in production code — no stubs or deferrals
    - _Requirements: all_

  - [ ] 7.2 Verify return values propagate correctly
    - `ingest_ignore_signals()` returns count → engine logs it
    - Knowledge store query returns `list[str]` → engine passes to `consolidate_findings()`
    - `filter_known_duplicates()` returns `list[FindingGroup]` → engine passes to `filter_ignored()`
    - `filter_ignored()` returns `list[FindingGroup]` → engine passes to `create_issues_from_groups()`
    - Grep for callers of each function; confirm none discards the return value
    - _Requirements: all_

  - [ ] 7.3 Run the integration smoke tests
    - All `TS-110-SMOKE-*` tests pass using real components (no stub bypass)
    - _Test Spec: TS-110-SMOKE-1, TS-110-SMOKE-2, TS-110-SMOKE-3_

  - [ ] 7.4 Stub / dead-code audit
    - Search all files touched by this spec for: `return []`, `return None`
      on non-Optional returns, `pass` in non-abstract methods, `# TODO`,
      `# stub`, `override point`, `NotImplementedError`
    - Each hit must be either: (a) justified with a comment explaining why it
      is intentional, or (b) replaced with a real implementation
    - Document any intentional stubs here with rationale

  - [ ] 7.5 Cross-spec entry point verification
    - `filter_known_duplicates()` is called from `engine.py:_run_hunt_scan()` — verify
    - `filter_ignored()` is called from `engine.py:_run_hunt_scan()` — verify
    - `ingest_ignore_signals()` is called from `engine.py:_run_hunt_scan()` — verify
    - `consolidate_findings()` with `false_positives` is called from `engine.py` — verify
    - All entry points are called from production code, not just tests
    - _Requirements: all_

  - [ ] 7.V Verify wiring group
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
| 110-REQ-1.1 | TS-110-1 | 2.1 | `tests/test_ignore_label.py::test_label_constant` |
| 110-REQ-1.2 | TS-110-2 | 2.1 | `tests/test_ignore_label.py::test_label_color` |
| 110-REQ-1.3 | TS-110-3 | 2.1 | `tests/test_ignore_label.py::test_label_in_required` |
| 110-REQ-1.4 | TS-110-3 | 2.1 | `tests/test_ignore_label.py::test_label_in_required` |
| 110-REQ-1.E1 | TS-110-3 | 2.1 | `tests/test_ignore_label.py::test_label_in_required` |
| 110-REQ-2.1 | TS-110-8 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_embedding_similarity_filters` |
| 110-REQ-2.2 | TS-110-5 | 3.2 | `tests/test_hunt_dedup_similarity.py::test_finding_group_text` |
| 110-REQ-2.3 | TS-110-6 | 3.2 | `tests/test_hunt_dedup_similarity.py::test_issue_text` |
| 110-REQ-2.4 | TS-110-4 | 3.1 | `tests/test_hunt_dedup_similarity.py::test_cosine_similarity` |
| 110-REQ-2.E1 | TS-110-E1 | 3.1 | `tests/test_hunt_dedup_similarity.py::test_cosine_none` |
| 110-REQ-2.E2 | TS-110-E2 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_no_embedder_fallback` |
| 110-REQ-3.1 | TS-110-7 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_fetches_all_states` |
| 110-REQ-3.2 | TS-110-7 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_fetches_all_states` |
| 110-REQ-3.3 | TS-110-8 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_embedding_similarity_filters` |
| 110-REQ-3.4 | TS-110-8 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_embedding_similarity_filters` |
| 110-REQ-3.5 | TS-110-9 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_fingerprint_short_circuits` |
| 110-REQ-3.E1 | TS-110-E2 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_no_embedder_fallback` |
| 110-REQ-3.E2 | TS-110-E3 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_platform_failure` |
| 110-REQ-4.1 | TS-110-10 | 4.1, 6.3 | `tests/test_ignore_filter.py::test_filter_ignored_suppresses` |
| 110-REQ-4.2 | TS-110-10 | 4.1 | `tests/test_ignore_filter.py::test_filter_ignored_suppresses` |
| 110-REQ-4.3 | TS-110-10, TS-110-11 | 4.1 | `tests/test_ignore_filter.py::test_filter_ignored_*` |
| 110-REQ-4.4 | TS-110-11 | 4.1 | `tests/test_ignore_filter.py::test_filter_ignored_passes` |
| 110-REQ-4.E1 | TS-110-E4 | 4.1 | `tests/test_ignore_filter.py::test_no_ignore_issues` |
| 110-REQ-4.E2 | TS-110-E3 | 4.1 | `tests/test_ignore_filter.py::test_platform_failure` |
| 110-REQ-4.E3 | TS-110-E2 | 4.1 | `tests/test_ignore_filter.py::test_embedding_failure` |
| 110-REQ-5.1 | TS-110-12 | 5.1 | `tests/test_ignore_ingest.py::test_ingest_creates_fact` |
| 110-REQ-5.2 | TS-110-12 | 5.1 | `tests/test_ignore_ingest.py::test_ingest_creates_fact` |
| 110-REQ-5.3 | TS-110-13 | 5.1 | `tests/test_ignore_ingest.py::test_ingest_appends_marker` |
| 110-REQ-5.4 | TS-110-17 | 5.1 | `tests/test_ignore_ingest.py::test_category_extraction` |
| 110-REQ-5.E1 | TS-110-E5 | 5.1 | `tests/test_ignore_ingest.py::test_marker_present_skips` |
| 110-REQ-5.E2 | TS-110-E6 | 5.1 | `tests/test_ignore_ingest.py::test_update_failure` |
| 110-REQ-5.E3 | TS-110-E7 | 5.1 | `tests/test_ignore_ingest.py::test_no_knowledge_store` |
| 110-REQ-6.1 | TS-110-14 | 5.2 | `tests/test_critic_false_positives.py::test_prompt_with_fps` |
| 110-REQ-6.2 | TS-110-14 | 5.2 | `tests/test_critic_false_positives.py::test_prompt_with_fps` |
| 110-REQ-6.3 | TS-110-SMOKE-3 | 6.2 | `tests/test_critic_false_positives.py::test_smoke_critic_fps` |
| 110-REQ-6.E1 | TS-110-15 | 6.2 | `tests/test_critic_false_positives.py::test_prompt_without_fps` |
| 110-REQ-6.E2 | TS-110-15 | 5.2 | `tests/test_critic_false_positives.py::test_prompt_without_fps` |
| 110-REQ-7.1 | TS-110-16 | 2.2 | `tests/test_ignore_label.py::test_config_threshold` |
| 110-REQ-7.2 | TS-110-8 | 6.3 | `tests/test_hunt_dedup_similarity.py::test_embedding_similarity_filters` |
| 110-REQ-7.E1 | TS-110-E8 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_threshold_zero` |
| 110-REQ-7.E2 | TS-110-E9 | 3.3 | `tests/test_hunt_dedup_similarity.py::test_threshold_one` |

## Notes

- **EmbeddingGenerator dependency:** The enhanced dedup and ignore filter
  require `EmbeddingGenerator` from `agent_fox.knowledge.embeddings`. This
  is a local model (`all-MiniLM-L6-v2`, 384 dimensions) with no API cost.
  If the model is not available, the system falls back to fingerprint-only
  matching.
- **DuckDB dependency for ingestion:** Knowledge ingestion requires a DuckDB
  connection. If the knowledge store is not configured, ingestion is skipped.
  The dedup and ignore filters do NOT require DuckDB — they work via
  platform API only.
- **Test isolation:** Integration tests should use `AsyncMock` for the
  platform protocol and a controlled `MockEmbedder` that returns
  predetermined vectors. Property tests for cosine similarity should use
  real math (no mocking).
- **Existing test compatibility:** The enhanced `filter_known_duplicates()`
  signature adds optional parameters with defaults. Existing tests that call
  the function without the new parameters should continue to work unchanged
  (fingerprint-only mode when `embedder=None`).
