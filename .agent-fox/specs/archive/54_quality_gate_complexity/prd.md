# PRD: Post-Session Quality Gate & Complexity Enrichment

> Source: post-run analysis of parking-fee-service knowledge.duckdb
> (2026-03-17 runs). No external validation of coder output; complexity
> prediction was uniform despite 5x duration variance.

## Problem Statement

Two independent problems observed in the parking-fee-service run:

1. **No post-session validation.** A coder session is marked "completed" based
   on the coder's self-assessment, with no external validation. The project
   defines `make check` (lint + tests) as its quality gate, but no mechanism
   runs it after each session. A green coder session can produce code that
   fails lint or tests.

2. **No complexity calibration.** All 27 tasks were predicted STANDARD with
   0.6 confidence, yet wall-clock duration varied 5x (118 s to 1353 s). The
   feature vector (6 fields: `subtask_count`, `spec_word_count`,
   `has_property_tests`, `edge_case_count`, `dependency_count`, `archetype`)
   lacks signals that would discriminate these tasks.

## Goals

1. **A configurable quality gate runs after each coder session** and its
   pass/fail result is recorded as an execution signal.
2. **Complexity prediction uses richer signals** so predicted tier better
   correlates with actual cost and duration.

## Non-Goals

- Blocking the run on quality gate failure (it is a signal, not a hard gate).
- Replacing the heuristic assessor with a trained model.
- Adding new DuckDB tables.
- Changing the embedding model or vector dimensions.
- Knowledge harvest fixes (see spec 52).
- Review archetype persistence (see spec 53).

## Clarifications

- **Quality gate timeout**: On timeout, the engine sends SIGTERM, waits 5s,
  then SIGKILL. The result is recorded as a gate failure with exit code -1.
- **Schema impact**: The `quality_gate` field is added to `OrchestratorConfig`
  (Pydantic model in `core/config.py`). The `completed_with_gate_failure`
  status is a new value in the session status enum. No new DuckDB tables are
  added, but the `quality_gate.result` audit event is stored in the existing
  `audit_events` table.
- **Feature vector location**: `FeatureVector` dataclass in `routing/core.py`
  (line 42), extraction logic in `routing/features.py`.
- **Historical duration**: Uses **median** (not mean) of successful execution
  durations for the same spec, to reduce sensitivity to outliers.
- **Language set encoding**: Represented as a sorted list of strings in the
  feature vector (e.g., `["go", "proto"]`). Serialized as a JSON array in
  the `feature_vector` column of `complexity_assessments`.

## Requirements

### 1. Post-Session Quality Gate

| ID | Requirement |
|----|-------------|
| QGC-1.1 | THE engine SHALL support a `quality_gate` configuration field (string, shell command) in `[orchestrator]`. WHEN set, THE engine SHALL execute the command after every successful coder session, in the project root directory. |
| QGC-1.2 | THE quality gate command SHALL run with a configurable timeout (`quality_gate_timeout`, default 300 seconds). IF the command does not exit within the timeout, THE engine SHALL send SIGTERM, wait 5 seconds, then SIGKILL. The result SHALL be recorded as a gate failure. |
| QGC-1.3 | WHEN the quality gate completes, THE engine SHALL emit a `quality_gate.result` audit event containing: exit code, stdout tail (last 50 lines), stderr tail (last 50 lines), duration in milliseconds, and pass/fail status. |
| QGC-1.4 | IF the quality gate fails (non-zero exit or timeout), THEN THE session status SHALL be set to `completed_with_gate_failure`. This status SHALL be visible in `session_outcomes` and in the run summary. |
| QGC-1.5 | A quality gate failure SHALL NOT block subsequent sessions. It is an informational signal. |
| QGC-1.6 | WHEN `quality_gate` is not configured, THE engine SHALL skip quality gate execution. Behavior SHALL be identical to the current implementation. |

### 2. Complexity Feature Vector Enrichment

| ID | Requirement |
|----|-------------|
| QGC-2.1 | THE feature vector SHALL include `file_count_estimate`: the count of file paths mentioned in the task group's description in `tasks.md`. |
| QGC-2.2 | THE feature vector SHALL include `cross_spec_integration`: a boolean indicating whether the task group's description references spec names other than its own. |
| QGC-2.3 | THE feature vector SHALL include `language_count`: the number of distinct programming languages involved in the task group, derived from file extensions mentioned in `tasks.md`. |
| QGC-2.4 | THE feature vector SHALL include `historical_median_duration_ms`: the median duration of successful execution outcomes for the same spec, or None if no prior outcomes exist. |
| QGC-2.5 | THE heuristic assessor SHALL use the new signals: tasks with `cross_spec_integration=True` or `file_count_estimate >= 8` SHALL be assessed as ADVANCED (confidence 0.7) unless the statistical model overrides. |
| QGC-2.6 | ALL feature vector fields (existing and new) SHALL be serialized in the `feature_vector` JSON column of `complexity_assessments`. |

## Dependencies

This spec has no cross-spec dependencies. The quality gate integrates into
the existing session lifecycle, and the feature vector extends existing
routing infrastructure.

## Out of Scope

- Knowledge harvest pipeline (spec 52).
- Review archetype persistence (spec 53).
- Review-only run mode (spec 53).
- Training a statistical complexity model.
- Adding new DuckDB tables.
