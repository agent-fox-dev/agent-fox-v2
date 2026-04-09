

# Implementation Plan: Coder Session Scope Guard

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

This implementation builds four interlocking subsystems to prevent wasted coder sessions: stub enforcement, pre-flight scope checking, scope overlap detection, and no-op completion tracking. The implementation order follows data dependency: models first, then language-specific patterns, then parsing, then the subsystems that consume parsed data (stub validation, pre-flight checking, overlap detection), then prompt building, session classification, and finally telemetry persistence and querying.

Task group 1 writes all failing tests. Groups 2–7 progressively implement modules from leaf dependencies (models, patterns) up to integration points (telemetry, session classifier). Checkpoints verify coherence at logical boundaries.

## Test Commands

- Spec tests: `uv run pytest -q tests/test_scope_guard/`
- Unit tests: `uv run pytest -q tests/test_scope_guard/ -m "not integration and not smoke"`
- Property tests: `uv run pytest -q tests/test_scope_guard/ -m property`
- Integration tests: `uv run pytest -q tests/test_scope_guard/ -m integration`
- Smoke tests: `uv run pytest -q tests/test_scope_guard/ -m smoke`
- All tests: `uv run pytest -q`
- Linter: `uv run ruff check agent_fox/scope_guard/ tests/test_scope_guard/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Set up test file structure
    - Create `tests/test_scope_guard/` directory with `__init__.py`
    - Create test files: `test_stub_patterns.py`, `test_stub_validator.py`, `test_source_parser.py`, `test_preflight_checker.py`, `test_overlap_detector.py`, `test_prompt_builder.py`, `test_session_classifier.py`, `test_telemetry.py`, `test_integration.py`
    - Add pytest markers for `integration`, `smoke`, and `property` in `conftest.py`
    - Add shared fixtures for common `TaskGroup`, `SessionResult`, and DuckDB setup
    - _Test Spec: TS-87-1 through TS-87-20_

  - [x] 1.2 Translate acceptance-criterion tests from test_spec.md
    - `test_prompt_builder.py::test_stub_directive_in_test_writing_prompt` — _Test Spec: TS-87-1_
    - `test_stub_validator.py::test_validate_stubs_detects_non_stub` — _Test Spec: TS-87-2_
    - `test_session_classifier.py::test_stub_violation_flagged_in_outcome` — _Test Spec: TS-87-3_
    - `test_stub_patterns.py::test_is_stub_body_all_languages` — _Test Spec: TS-87-4_
    - `test_preflight_checker.py::test_per_deliverable_status` — _Test Spec: TS-87-5_
    - `test_preflight_checker.py::test_all_implemented_skip` — _Test Spec: TS-87-6_
    - `test_prompt_builder.py::test_reduced_scope_prompt` — _Test Spec: TS-87-7_
    - `test_preflight_checker.py::test_stub_detection_for_status` — _Test Spec: TS-87-8_
    - `test_telemetry.py::test_scope_check_telemetry_logging` — _Test Spec: TS-87-9_
    - `test_overlap_detector.py::test_detect_shared_deliverables` — _Test Spec: TS-87-10_
    - `test_overlap_detector.py::test_overlap_emits_warning` — _Test Spec: TS-87-11_
    - `test_overlap_detector.py::test_overlap_error_no_dependency` — _Test Spec: TS-87-12_
    - `test_overlap_detector.py::test_overlap_warning_with_dependency` — _Test Spec: TS-87-13_
    - `test_session_classifier.py::test_noop_zero_commits` — _Test Spec: TS-87-14_
    - `test_telemetry.py::test_preflight_skip_distinct_from_noop` — _Test Spec: TS-87-15_
    - `test_telemetry.py::test_noop_record_field_completeness` — _Test Spec: TS-87-16_
    - `test_telemetry.py::test_aggregate_waste_report` — _Test Spec: TS-87-17_
    - `test_prompt_builder.py::test_stub_directive_machine_parseable` — _Test Spec: TS-87-18_
    - `test_telemetry.py::test_prompt_persisted_and_retrievable` — _Test Spec: TS-87-19_
    - `test_stub_validator.py::test_violation_includes_prompt_directive` — _Test Spec: TS-87-20_
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-87-1 through TS-87-20_

  - [x] 1.3 Translate edge-case tests from test_spec.md
    - `test_stub_validator.py::test_inline_test_code_excluded` — stub enforcement only applies outside test-attributed blocks — _Test Spec: TS-87-E1_
    - `test_stub_patterns.py::test_stub_with_additional_statements_is_non_stub` — a `todo!()` preceded by setup logic is classified as non-stub — _Test Spec: TS-87-E2_
    - `test_stub_validator.py::test_unsupported_language_skipped_with_warning` — unsupported language files logged and skipped — _Test Spec: TS-87-E3_
    - `test_preflight_checker.py::test_nonexistent_file_classified_pending` — missing file/function → pending — _Test Spec: TS-87-E4_ (maps to 87-REQ-2.E1)
    - `test_preflight_checker.py::test_unparseable_file_classified_indeterminate` — syntax errors → indeterminate — _Test Spec: TS-87-E5_ (maps to 87-REQ-2.E2)
    - `test_preflight_checker.py::test_no_deliverables_indeterminate` — no enumerated deliverables → indeterminate with warning — _Test Spec: TS-87-E6_ (maps to 87-REQ-2.E3)
    - `test_overlap_detector.py::test_empty_deliverables_excluded` — empty deliverable list excluded from overlap analysis — _Test Spec: TS-87-E7_ (maps to 87-REQ-3.E1)
    - `test_overlap_detector.py::test_same_file_different_functions_no_overlap` — same file, different functions, no overlap — _Test Spec: TS-87-E8_ (maps to 87-REQ-3.E2)
    - `test_overlap_detector.py::test_single_task_group_no_overlap` — single task group → empty overlap list — _Test Spec: TS-87-E9_ (maps to 87-REQ-3.E3)
    - `test_session_classifier.py::test_whitespace_only_commits_noop` — whitespace/comment-only commits classified as no-op — _Test Spec: TS-87-E10_ (maps to 87-REQ-4.E1)
    - `test_session_classifier.py::test_harvest_error_not_noop` — git error → harvest-error, not no-op — _Test Spec: TS-87-E11_ (maps to 87-REQ-4.E2)
    - `test_session_classifier.py::test_error_exit_no_commits_is_failure` — error exit + no commits → failure, not no-op — _Test Spec: TS-87-E12_ (maps to 87-REQ-4.E3)
    - `test_telemetry.py::test_prompt_truncation` — prompt exceeding 100K chars truncated with flag — _Test Spec: TS-87-E13_ (maps to 87-REQ-5.E1)
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - _Test Spec: TS-87-E1 through TS-87-E13_

  - [x] 1.4 Translate property tests from test_spec.md
    - `test_stub_patterns.py::test_property_stub_body_purity` — Property 1: is_stub_body is True iff body is exactly one stub placeholder — _Test Spec: TS-87-P1_
    - `test_stub_validator.py::test_property_test_block_exclusion` — Property 2: test-block functions never appear in violations — _Test Spec: TS-87-P2_
    - `test_stub_validator.py::test_property_stub_validation_completeness` — Property 3: all non-stub non-test functions appear in violations — _Test Spec: TS-87-P3_
    - `test_preflight_checker.py::test_property_deliverable_status_correctness` — Property 4: pending/implemented/indeterminate classification — _Test Spec: TS-87-P4_
    - `test_preflight_checker.py::test_property_nonexistent_is_pending` — Property 5: missing function → pending — _Test Spec: TS-87-P5_
    - `test_overlap_detector.py::test_property_overlap_detection_precision` — Property 8: overlap iff same (file_path, function_id) — _Test Spec: TS-87-P8_
    - `test_overlap_detector.py::test_property_overlap_severity_classification` — Property 9: error if no dependency, warning if dependency — _Test Spec: TS-87-P9_
    - `test_overlap_detector.py::test_property_overlap_edge_cases` — Property 10: 0 or 1 task groups → empty overlaps — _Test Spec: TS-87-P10_
    - `test_session_classifier.py::test_property_classification_mutual_exclusivity` — Property 11: exactly one classification per session — _Test Spec: TS-87-P11_
    - `test_session_classifier.py::test_property_noop_vs_failure_distinction` — Property 12: no-op only if normal exit — _Test Spec: TS-87-P12_
    - `test_session_classifier.py::test_property_whitespace_commits_noop` — Property 13: whitespace-only → no-op — _Test Spec: TS-87-P13_
    - `test_session_classifier.py::test_property_harvest_error_classification` — Property 14: git error → harvest-error — _Test Spec: TS-87-P14_
    - `test_telemetry.py::test_property_telemetry_completeness` — Property 15: required fields present — _Test Spec: TS-87-P15_
    - `test_telemetry.py::test_property_waste_report_aggregation` — Property 16: aggregation sums match — _Test Spec: TS-87-P16_
    - `test_prompt_builder.py::test_property_stub_directive_injection` — Property 17: directive present iff test-writing — _Test Spec: TS-87-P17_
    - `test_telemetry.py::test_property_prompt_persistence` — Property 18: persisted prompt retrievable — _Test Spec: TS-87-P18_
    - Tests MUST fail (assert against not-yet-implemented behavior)
    - Use hypothesis for property-based generation
    - _Test Spec: TS-87-P1 through TS-87-P18_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid: `uv run python -m py_compile tests/test_scope_guard/test_stub_patterns.py` (repeat for each test file)
    - [x] All spec tests FAIL (red) — no implementation yet: `uv run pytest -q tests/test_scope_guard/ --tb=no`
    - [x] No linter warnings introduced: `uv run ruff check tests/test_scope_guard/`

- [x] 2. Models and stub patterns
  - [x] 2.1 Implement `scope_guard/models.py`
    - Define all dataclasses and enums from design.md: `Language`, `DeliverableStatus`, `SessionClassification`, `OverlapSeverity`, `Deliverable`, `FunctionBody`, `DeliverableCheckResult`, `ScopeCheckResult`, `OverlapRecord`, `OverlapResult`, `ViolationRecord`, `StubValidationResult`, `SessionOutcome`, `PromptRecord`, `SpecWasteSummary`, `WasteReport`, `TaskGroup`, `SpecGraph`, `FileChange`, `SessionResult`
    - _Requirements: all (foundational types)_

  - [x] 2.2 Implement `scope_guard/stub_patterns.py`
    - Implement `detect_language(file_path: str) -> Language` using file extension mapping
    - Implement `get_stub_patterns(language: Language) -> list[re.Pattern]` returning compiled regex patterns per language
    - Implement `is_stub_body(body: str, language: Language) -> bool` — strip comments/whitespace, check entire content matches single stub placeholder
    - Implement `is_test_block(body: str, file_path: str, language: Language) -> bool` — detect test-attributed blocks per language rules from design.md
    - _Requirements: 87-REQ-1.4, 87-REQ-1.E1, 87-REQ-1.E2_
    - _Test Spec: TS-87-4, TS-87-E2, TS-87-P1_

  - [x] 2.3 Create `scope_guard/__init__.py` with public API exports
    - Export all model types and module-level functions
    - _Requirements: all_

  - [x] 2.V Verify task group 2
    - [x] Spec tests for this group pass: `uv run pytest -q tests/test_scope_guard/test_stub_patterns.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check src/scope_guard/`
    - [x] Requirements 87-REQ-1.4, 87-REQ-1.E1, 87-REQ-1.E2 acceptance criteria met

- [x] 3. Source parser and stub validator
  - [x] 3.1 Implement `scope_guard/source_parser.py`
    - Implement `extract_function_body(file_path: Path, function_id: str) -> FunctionBody | None` — parse source file, locate function by ID, extract body text and metadata
    - Implement `extract_all_functions(file_path: Path) -> list[FunctionBody]` — extract all functions from a source file
    - Implement `extract_modified_functions(file_change: FileChange) -> list[FunctionBody]` — parse diff to identify and extract modified function bodies
    - Support Rust, Python, TypeScript/JavaScript parsing (use regex/heuristic-based extraction, not full AST)
    - Handle unparseable files by returning `None` or empty list
    - _Requirements: 87-REQ-1.2, 87-REQ-2.1, 87-REQ-2.4, 87-REQ-2.E2_

  - [x] 3.2 Implement `scope_guard/stub_validator.py`
    - Implement `validate_stubs(modified_files: list[FileChange], task_group: TaskGroup) -> StubValidationResult`
    - For each non-test file: extract functions via source_parser, check each body via `is_stub_body`, exclude test blocks via `is_test_block`
    - Collect violations for non-stub functions outside test blocks
    - Skip files with unsupported languages, add to `skipped_files` list with warning
    - Implement `_check_test_block_exclusion(file_change, function) -> bool`
    - Implement `_check_prompt_had_directive(session_id: str)` — query telemetry for prompt directive presence
    - _Requirements: 87-REQ-1.2, 87-REQ-1.3, 87-REQ-1.E1, 87-REQ-1.E2, 87-REQ-1.E3_
    - _Test Spec: TS-87-2, TS-87-3, TS-87-20, TS-87-E1, TS-87-E2, TS-87-E3, TS-87-P2, TS-87-P3_

  - [x] 3.V Verify task group 3
    - [x] Spec tests for this group pass: `uv run pytest -q tests/test_scope_guard/test_stub_validator.py tests/test_scope_guard/test_source_parser.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/scope_guard/`
    - [x] Requirements 87-REQ-1.2, 87-REQ-1.3, 87-REQ-1.E1, 87-REQ-1.E2, 87-REQ-1.E3 acceptance criteria met

- [x] 4. Checkpoint — Stub Enforcement Complete
  - Ensure all stub enforcement tests pass (TS-87-1 through TS-87-4, TS-87-E1 through TS-87-E3, TS-87-P1 through TS-87-P3).
  - Verify: `uv run pytest -q tests/test_scope_guard/test_stub_patterns.py tests/test_scope_guard/test_stub_validator.py`
  - Create or update documentation in README.md covering stub enforcement usage.

- [x] 5. Pre-flight checker and overlap detector
  - [x] 5.1 Implement `scope_guard/preflight_checker.py`
    - Implement `check_scope(task_group: TaskGroup, codebase_root: Path) -> ScopeCheckResult`
    - For each deliverable: use `source_parser.extract_function_body` to find function, use `stub_patterns.is_stub_body` to determine status
    - Classify as `PENDING` (stub or missing), `ALREADY_IMPLEMENTED` (non-stub), or `INDETERMINATE` (unparseable)
    - Derive `overall` from aggregate of deliverable statuses: all-pending, all-implemented, partially-implemented, indeterminate
    - Handle edge cases: nonexistent files/functions → pending; unparseable → indeterminate; no deliverables → indeterminate with warning
    - Track and return `check_duration_ms` and `deliverable_count`
    - _Requirements: 87-REQ-2.1, 87-REQ-2.2, 87-REQ-2.3, 87-REQ-2.4, 87-REQ-2.5, 87-REQ-2.E1, 87-REQ-2.E2, 87-REQ-2.E3_
    - _Test Spec: TS-87-5, TS-87-6, TS-87-8, TS-87-E4, TS-87-E5, TS-87-E6, TS-87-P4, TS-87-P5_

  - [x] 5.2 Implement `scope_guard/overlap_detector.py`
    - Implement `detect_overlaps(spec_graph: SpecGraph) -> OverlapResult`
    - Implement `_compare_deliverables(tg_a: TaskGroup, tg_b: TaskGroup) -> list[OverlapRecord]` — compare by `(file_path, function_id)` tuple
    - Implement `_classify_overlaps(overlaps, spec_graph) -> OverlapResult` — set severity to `ERROR` if no dependency, `WARNING` if dependency exists
    - Handle edge cases: single task group → empty; empty deliverable lists → exclude from analysis with warning
    - _Requirements: 87-REQ-3.1, 87-REQ-3.2, 87-REQ-3.3, 87-REQ-3.4, 87-REQ-3.E1, 87-REQ-3.E2, 87-REQ-3.E3_
    - _Test Spec: TS-87-10, TS-87-11, TS-87-12, TS-87-13, TS-87-E7, TS-87-E8, TS-87-E9, TS-87-P8, TS-87-P9, TS-87-P10_

  - [x] 5.V Verify task group 5
    - [x] Spec tests for this group pass: `uv run pytest -q tests/test_scope_guard/test_preflight_checker.py tests/test_scope_guard/test_overlap_detector.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/scope_guard/`
    - [x] Requirements 87-REQ-2.1–2.5, 87-REQ-2.E1–E3, 87-REQ-3.1–3.4, 87-REQ-3.E1–E3 acceptance criteria met

- [x] 6. Prompt builder and session classifier
  - [x] 6.1 Implement `scope_guard/prompt_builder.py`
    - Implement `build_prompt(task_group: TaskGroup, scope_result: ScopeCheckResult | None = None) -> str`
    - For test-writing archetypes: inject `<!-- SCOPE_GUARD:STUB_ONLY -->` directive block with stub-only constraint text
    - For non-test-writing archetypes: omit the directive block
    - When `scope_result` has mixed statuses: include pending deliverables in work section, already-implemented in context section
    - Implement `_filter_pending_deliverables(scope_result) -> list[Deliverable]`
    - Implement `_inject_stub_directive(prompt: str) -> str`
    - _Requirements: 87-REQ-1.1, 87-REQ-2.3, 87-REQ-5.1_
    - _Test Spec: TS-87-1, TS-87-7, TS-87-18, TS-87-P7, TS-87-P17_

  - [x] 6.2 Implement `scope_guard/session_classifier.py`
    - Implement `classify_session(session: SessionResult, task_group: TaskGroup) -> SessionOutcome`
    - Implement `_count_functional_commits(session: SessionResult) -> int` — filter out whitespace/comment-only commits
    - Classification logic: error exit → `FAILURE`; harvest error → `HARVEST_ERROR`; zero functional commits + normal exit → `NO_OP`; has commits + test-writing → run stub validation and flag violations; else → `SUCCESS`
    - Ensure mutual exclusivity of classifications
    - _Requirements: 87-REQ-1.3, 87-REQ-4.1, 87-REQ-4.E1, 87-REQ-4.E2, 87-REQ-4.E3_
    - _Test Spec: TS-87-3, TS-87-14, TS-87-E10, TS-87-E11, TS-87-E12, TS-87-P11, TS-87-P12, TS-87-P13, TS-87-P14_

  - [x] 6.V Verify task group 6
    - [x] Spec tests for this group pass: `uv run pytest -q tests/test_scope_guard/test_prompt_builder.py tests/test_scope_guard/test_session_classifier.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/scope_guard/`
    - [x] Requirements 87-REQ-1.1, 87-REQ-1.3, 87-REQ-2.3, 87-REQ-4.1, 87-REQ-4.E1–E3, 87-REQ-5.1 acceptance criteria met

- [x] 7. Telemetry persistence and querying
  - [x] 7.1 Implement `scope_guard/telemetry.py` — schema and session outcome recording
    - Implement DuckDB schema initialization: create `session_outcomes`, `session_prompts`, `scope_check_results` tables if not exist
    - Implement `record_session_outcome(outcome: SessionOutcome) -> None` — insert into `session_outcomes` table with JSON serialization for `violation_details`
    - _Requirements: 87-REQ-4.1, 87-REQ-4.2, 87-REQ-4.3_
    - _Test Spec: TS-87-15, TS-87-16, TS-87-P15_

  - [x] 7.2 Implement `scope_guard/telemetry.py` — prompt persistence and retrieval
    - Implement `persist_prompt(session_id: str, prompt_text: str) -> None` — store prompt with truncation logic (100K char limit, retain first 500 + last 500, set truncated flag)
    - Implement `get_session_prompt(session_id: str) -> PromptRecord | None` — retrieve prompt, detect `SCOPE_GUARD:STUB_ONLY` presence
    - _Requirements: 87-REQ-5.1, 87-REQ-5.2, 87-REQ-5.3, 87-REQ-5.E1_
    - _Test Spec: TS-87-19, TS-87-20, TS-87-E13, TS-87-P18_

  - [x] 7.3 Implement `scope_guard/telemetry.py` — scope check recording and waste reporting
    - Implement `record_scope_check(result: ScopeCheckResult) -> None` — insert into `scope_check_results` table
    - Implement `query_waste_report(spec_number: int | None = None) -> WasteReport` — aggregate no-op and pre-flight-skip counts, costs, durations per spec
    - _Requirements: 87-REQ-2.5, 87-REQ-4.4_
    - _Test Spec: TS-87-9, TS-87-17, TS-87-P16_

  - [x] 7.V Verify task group 7
    - [x] Spec tests for this group pass: `uv run pytest -q tests/test_scope_guard/test_telemetry.py`
    - [x] All existing tests still pass: `uv run pytest -q`
    - [x] No linter warnings introduced: `uv run ruff check agent_fox/scope_guard/`
    - [x] Requirements 87-REQ-2.5, 87-REQ-4.1–4.4, 87-REQ-5.1–5.3, 87-REQ-5.E1 acceptance criteria met

- [x] 8. Checkpoint — All Subsystems Complete
  - Ensure all spec tests pass: `uv run pytest -q tests/test_scope_guard/`
  - Verify all unit, property, and integration tests green.
  - Create or update documentation in README.md and `docs/scope_guard.md` covering:
    - Stub enforcement usage and supported languages
    - Pre-flight scope checking workflow
    - Overlap detection at spec finalization
    - No-op/pre-flight-skip telemetry and waste reporting
    - Configuration flags for rollout phases

- [ ] 9. Integration smoke tests
  - [ ] 9.1 Implement smoke test: overlap detection through warning/error emission
    - Test full Path 1 from design.md: `detect_overlaps(spec_graph)` → `OverlapResult` → caller checks `has_errors`
    - Must NOT mock: `overlap_detector.detect_overlaps`, `overlap_detector._compare_deliverables`, `overlap_detector._classify_overlaps`
    - Use a real `SpecGraph` with known overlapping deliverables
    - _Test Spec: TS-87-SMOKE-1_
    - _Requirements: 87-REQ-3.1, 87-REQ-3.2, 87-REQ-3.3, 87-REQ-3.4_

  - [ ] 9.2 Implement smoke test: pre-flight skip of fully-implemented task group
    - Test full Path 2: `check_scope` → all-implemented → `record_session_outcome(pre-flight-skip)` → verify DuckDB row
    - Must NOT mock: `preflight_checker.check_scope`, `source_parser.extract_function_body`, `stub_patterns.is_stub_body`, `telemetry.record_session_outcome`
    - Create temp codebase directory with fully-implemented functions
    - _Test Spec: TS-87-SMOKE-2_
    - _Requirements: 87-REQ-2.1, 87-REQ-2.2, 87-REQ-2.4, 87-REQ-2.5_

  - [ ] 9.3 Implement smoke test: reduced scope prompt for partially-implemented task group
    - Test full Path 3: `check_scope` → partially-implemented → `build_prompt` with pending-only deliverables → stub directive if test-writing
    - Must NOT mock: `preflight_checker.check_scope`, `prompt_builder.build_prompt`, `prompt_builder._filter_pending_deliverables`
    - _Test Spec: TS-87-SMOKE-3_
    - _Requirements: 87-REQ-2.3, 87-REQ-5.1_

  - [ ] 9.4 Implement smoke test: stub enforcement validates test-writing session output
    - Test full Path 4: `classify_session` → test-writing with commits → `validate_stubs` → violations detected → `record_session_outcome` with `stub_violation=True`
    - Must NOT mock: `session_classifier.classify_session`, `stub_validator.validate_stubs`, `source_parser.extract_modified_functions`, `stub_patterns.is_stub_body`, `telemetry.record_session_outcome`
    - _Test Spec: TS-87-SMOKE-4_
    - _Requirements: 87-REQ-1.2, 87-REQ-1.3_

  - [ ] 9.5 Implement smoke test: no-op and failure classification with telemetry recording
    - Test Paths 5 and 6: `classify_session` for zero-commit normal exit → no-op; zero-commit error exit → failure; both recorded in DuckDB
    - Must NOT mock: `session_classifier.classify_session`, `telemetry.record_session_outcome`
    - _Test Spec: TS-87-