# Implementation Plan: Confidence Normalization

<!-- AGENT INSTRUCTIONS
- Implement exactly ONE top-level task group per session
- Task group 1 writes failing tests from test_spec.md — all subsequent groups
  implement code to make those tests pass
- Follow the git-flow: feature branch from develop -> implement -> test -> merge to develop -> push
- Update checkbox states as you go: [-] in progress, [x] complete
-->

## Overview

Implementation proceeds in four groups: (1) write failing tests, (2) add
`parse_confidence()` and update `Fact` dataclass + extraction + rendering,
(3) DuckDB migration and JSONL backward compatibility, (4) update knowledge
query and auto-improve analyzer types.

The ordering ensures the core parser and type change land first, then storage
compatibility, then downstream consumers.

## Test Commands

- Spec tests: `uv run pytest tests/unit/memory/test_confidence.py tests/unit/knowledge/test_confidence_migration.py tests/unit/knowledge/test_query_confidence.py tests/unit/fix/test_analyzer_confidence.py -v`
- Property tests: `uv run pytest tests/property/memory/test_confidence_props.py -v`
- All tests: `uv run pytest -x -q`
- Linter: `uv run ruff check agent_fox/ tests/`

## Tasks

- [x] 1. Write failing spec tests
  - [x] 1.1 Create `tests/unit/memory/test_confidence.py`
    - Test class `TestParseConfidence` with TS-37-1, TS-37-2, TS-37-E1, TS-37-E2, TS-37-E4
    - Test class `TestFactConfidenceType` with TS-37-3
    - Test class `TestExtractionConfidence` with TS-37-4
    - Test class `TestRenderConfidence` with TS-37-13
    - Test class `TestJsonlConfidence` with TS-37-7, TS-37-8
    - _Test Spec: TS-37-1 through TS-37-4, TS-37-7, TS-37-8, TS-37-13, TS-37-E1, TS-37-E2, TS-37-E4_

  - [x] 1.2 Create `tests/unit/knowledge/test_confidence_migration.py`
    - Test class `TestConfidenceMigration` with TS-37-5, TS-37-6, TS-37-E3
    - _Test Spec: TS-37-5, TS-37-6, TS-37-E3_

  - [x] 1.3 Create `tests/unit/knowledge/test_query_confidence.py`
    - Test class `TestOracleAnswerConfidence` with TS-37-9
    - Test class `TestPatternConfidence` with TS-37-10
    - _Test Spec: TS-37-9, TS-37-10_

  - [x] 1.4 Create `tests/unit/fix/test_analyzer_confidence.py`
    - Test class `TestImprovementConfidence` with TS-37-11
    - Test class `TestConfidenceFilter` with TS-37-12
    - _Test Spec: TS-37-11, TS-37-12_

  - [x] 1.5 Create `tests/property/memory/test_confidence_props.py`
    - Property tests TS-37-P1 through TS-37-P6
    - _Test Spec: TS-37-P1 through TS-37-P6_

  - [x] 1.V Verify task group 1
    - [x] All spec tests exist and are syntactically valid
    - [x] All spec tests FAIL (red) — no implementation yet
    - [x] No linter warnings: `uv run ruff check tests/unit/memory/test_confidence.py tests/unit/knowledge/test_confidence_migration.py tests/unit/knowledge/test_query_confidence.py tests/unit/fix/test_analyzer_confidence.py tests/property/memory/test_confidence_props.py`

- [x] 2. Core confidence parser and Fact type update
  - [x] 2.1 Add `parse_confidence()` to `agent_fox/memory/types.py`
    - Add `CONFIDENCE_MAP` dict and `DEFAULT_CONFIDENCE` constant
    - Implement `parse_confidence(value: str | float | int | None) -> float`
    - Handle string lookup, numeric clamping, None default
    - Log warning for unrecognized strings
    - _Requirements: 37-REQ-1.2, 37-REQ-1.3, 37-REQ-1.E1, 37-REQ-1.E2_

  - [x] 2.2 Update `Fact` dataclass in `agent_fox/memory/types.py`
    - Change `confidence: str` to `confidence: float`
    - Set default to `DEFAULT_CONFIDENCE` (0.6)
    - Remove or deprecate `ConfidenceLevel` enum
    - _Requirements: 37-REQ-1.4_

  - [x] 2.3 Update extraction in `agent_fox/memory/extraction.py`
    - Call `parse_confidence()` when building Fact from LLM output
    - Replace existing string validation with float conversion
    - _Requirements: 37-REQ-1.1, 37-REQ-1.2_

  - [x] 2.4 Update rendering in `agent_fox/memory/render.py`
    - Format confidence as `f"{fact.confidence:.2f}"` in `render_fact()`
    - _Requirements: 37-REQ-6.1_

  - [x] 2.V Verify task group 2
    - [x] Spec tests pass: `uv run pytest tests/unit/memory/test_confidence.py -v`
    - [x] Property tests pass: `uv run pytest tests/property/memory/test_confidence_props.py::TestConfidenceAlwaysInRange tests/property/memory/test_confidence_props.py::TestCanonicalMappingDeterministic -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/memory/types.py agent_fox/memory/extraction.py agent_fox/memory/render.py`
    - [x] Requirements 37-REQ-1.*, 37-REQ-6.1 met

- [x] 3. Storage compatibility (DuckDB migration + JSONL)
  - [x] 3.1 Add DuckDB migration in `agent_fox/knowledge/migrations.py`
    - New migration (v5): convert `memory_facts.confidence` TEXT → DOUBLE
    - Use canonical mapping for existing string values
    - Default NULL to 0.6
    - _Requirements: 37-REQ-2.1, 37-REQ-2.2, 37-REQ-2.3, 37-REQ-2.E1_

  - [x] 3.2 Update `memory_facts` CREATE TABLE in `agent_fox/knowledge/db.py`
    - Change `confidence TEXT DEFAULT 'high'` to `confidence DOUBLE DEFAULT 0.6`
    - _Requirements: 37-REQ-2.1_

  - [x] 3.3 Update JSONL serialization in `agent_fox/memory/memory.py`
    - Deserialization: call `parse_confidence()` on loaded value
    - Serialization: write float directly
    - (Already implemented in task group 2)
    - _Requirements: 37-REQ-3.1, 37-REQ-3.2, 37-REQ-3.3_

  - [x] 3.4 Update DuckDB fact sync in `agent_fox/engine/knowledge_harvest.py`
    - Ensure float confidence is written when syncing facts to DuckDB
    - (Already passes float via fact.confidence after task group 2)
    - _Requirements: 37-REQ-1.1_

  - [x] 3.V Verify task group 3
    - [x] Spec tests pass: `uv run pytest tests/unit/knowledge/test_confidence_migration.py tests/unit/memory/test_confidence.py::TestJsonlConfidence -v`
    - [x] Property tests pass: `uv run pytest tests/property/memory/test_confidence_props.py::TestJsonlRoundTrip tests/property/memory/test_confidence_props.py::TestMigrationPreservesRowCount tests/property/memory/test_confidence_props.py::TestBackwardCompatStringLoading -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/migrations.py agent_fox/knowledge/db.py agent_fox/memory/memory.py agent_fox/engine/knowledge_harvest.py`
    - [x] Requirements 37-REQ-2.*, 37-REQ-3.* met

- [x] 4. Knowledge query and analyzer updates
  - [x] 4.1 Update `OracleAnswer` in `agent_fox/knowledge/query.py`
    - Change `confidence: str` to `confidence: float`
    - Update `_determine_confidence()` to return float
    - _Requirements: 37-REQ-4.1, 37-REQ-4.2_

  - [x] 4.2 Update `Pattern` in `agent_fox/knowledge/query.py`
    - Change `confidence: str` to `confidence: float`
    - Update `_assign_confidence()` to return float (5+ → 0.9, 3-4 → 0.7, 2 → 0.4)
    - _Requirements: 37-REQ-4.3, 37-REQ-4.4_

  - [x] 4.3 Update `Improvement` in `agent_fox/fix/analyzer.py`
    - Change `confidence: str` to `confidence: float`
    - Update LLM response parsing to call `parse_confidence()`
    - Update filter from `!= "low"` to `< 0.5`
    - _Requirements: 37-REQ-5.1, 37-REQ-5.2, 37-REQ-5.3_

  - [x] 4.4 Update documentation
    - Update `docs/cli-reference.md` if confidence is user-visible
    - Update `docs/memory.md` if it references confidence format
    - _Requirements: documentation_

  - [x] 4.V Verify task group 4
    - [x] Spec tests pass: `uv run pytest tests/unit/knowledge/test_query_confidence.py tests/unit/fix/test_analyzer_confidence.py -v`
    - [x] Property tests pass: `uv run pytest tests/property/memory/test_confidence_props.py::TestThresholdFilterCorrectness -v`
    - [x] All existing tests still pass: `uv run pytest -x -q`
    - [x] No linter warnings: `uv run ruff check agent_fox/knowledge/query.py agent_fox/fix/analyzer.py`
    - [x] Requirements 37-REQ-4.*, 37-REQ-5.* met

## Traceability

| Requirement | Test Spec Entry | Implemented By Task | Verified By Test |
|-------------|-----------------|---------------------|------------------|
| 37-REQ-1.1 | TS-37-4 | 2.3 | `test_confidence.py::TestExtractionConfidence` |
| 37-REQ-1.2 | TS-37-1 | 2.1 | `test_confidence.py::TestParseConfidence::test_string_mapping` |
| 37-REQ-1.3 | TS-37-2 | 2.1 | `test_confidence.py::TestParseConfidence::test_numeric` |
| 37-REQ-1.4 | TS-37-3 | 2.2 | `test_confidence.py::TestFactConfidenceType` |
| 37-REQ-1.E1 | TS-37-E1, TS-37-E4 | 2.1 | `test_confidence.py::TestParseConfidence::test_unknown_string` |
| 37-REQ-1.E2 | TS-37-E2 | 2.1 | `test_confidence.py::TestParseConfidence::test_clamping` |
| 37-REQ-2.1 | TS-37-5 | 3.1, 3.2 | `test_confidence_migration.py::TestConfidenceMigration::test_column_type` |
| 37-REQ-2.2 | TS-37-5 | 3.1 | `test_confidence_migration.py::TestConfidenceMigration::test_value_conversion` |
| 37-REQ-2.3 | TS-37-6 | 3.1 | `test_confidence_migration.py::TestConfidenceMigration::test_row_count` |
| 37-REQ-2.E1 | TS-37-E3 | 3.1 | `test_confidence_migration.py::TestConfidenceMigration::test_null_default` |
| 37-REQ-3.1 | TS-37-7 | 3.3 | `test_confidence.py::TestJsonlConfidence::test_load_string` |
| 37-REQ-3.2 | TS-37-7 | 3.3 | `test_confidence.py::TestJsonlConfidence::test_load_string` |
| 37-REQ-3.3 | TS-37-8 | 3.3 | `test_confidence.py::TestJsonlConfidence::test_write_float` |
| 37-REQ-4.1 | TS-37-9 | 4.1 | `test_query_confidence.py::TestOracleAnswerConfidence` |
| 37-REQ-4.2 | TS-37-9 | 4.1 | `test_query_confidence.py::TestOracleAnswerConfidence` |
| 37-REQ-4.3 | TS-37-10 | 4.2 | `test_query_confidence.py::TestPatternConfidence` |
| 37-REQ-4.4 | TS-37-10 | 4.2 | `test_query_confidence.py::TestPatternConfidence` |
| 37-REQ-5.1 | TS-37-11 | 4.3 | `test_analyzer_confidence.py::TestImprovementConfidence` |
| 37-REQ-5.2 | TS-37-11 | 4.3 | `test_analyzer_confidence.py::TestImprovementConfidence` |
| 37-REQ-5.3 | TS-37-12 | 4.3 | `test_analyzer_confidence.py::TestConfidenceFilter` |
| 37-REQ-6.1 | TS-37-13 | 2.4 | `test_confidence.py::TestRenderConfidence` |
| Property 1 | TS-37-P1 | 2.1 | `test_confidence_props.py::TestConfidenceAlwaysInRange` |
| Property 2 | TS-37-P2 | 2.1 | `test_confidence_props.py::TestCanonicalMappingDeterministic` |
| Property 3 | TS-37-P4 | 3.1 | `test_confidence_props.py::TestMigrationPreservesRowCount` |
| Property 4 | TS-37-P3 | 3.3 | `test_confidence_props.py::TestJsonlRoundTrip` |
| Property 5 | TS-37-P5 | 3.3 | `test_confidence_props.py::TestBackwardCompatStringLoading` |
| Property 6 | TS-37-P6 | 4.3 | `test_confidence_props.py::TestThresholdFilterCorrectness` |

## Notes

- The `ConfidenceLevel` enum in `memory/types.py` can be removed entirely if
  no external code references it. If external tooling uses it, deprecate it
  and keep it as a reference mapping only.
- The DuckDB migration version must be checked against the latest existing
  migration to avoid collisions. Current latest is v5 (from spec 34 token
  tracking). This spec adds v6.
- Existing tests that construct `Fact` objects with `confidence="high"` will
  need updating to use `confidence=0.9` (or the appropriate float).
- The extraction prompt in `extraction.py` can optionally be updated to
  request numeric confidence directly from the LLM, but the parser must
  still handle string responses for robustness.
