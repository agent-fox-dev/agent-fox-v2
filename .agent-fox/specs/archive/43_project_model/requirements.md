# Requirements Document: Project Model

## Introduction

This spec provides aggregate project visibility, critical path forecasting,
file conflict detection, and learned blocking thresholds. It extracts and
formalizes four components that were previously part of spec 39 (package
consolidation) and adds dedicated acceptance criteria, test contracts, and
implementation tasks.

## Glossary

| Term | Definition |
|------|------------|
| **Project Model** | A read-only aggregate view of project health computed from DuckDB execution history. Contains spec outcomes, module stability, and archetype effectiveness. |
| **SpecMetrics** | Per-specification aggregate: average cost, average duration, failure rate, session count. Computed from `execution_outcomes` joined with `complexity_assessments`. |
| **Module Stability** | Finding density per spec: total review findings divided by total sessions. Lower is more stable. |
| **Archetype Effectiveness** | Success rate per archetype type: fraction of sessions with outcome "completed". |
| **Critical Path** | The longest-duration path through the task graph DAG when duration hints are used as edge weights. |
| **Duration Hint** | A predicted execution duration in milliseconds assigned to each task node (from spec 41). |
| **Tied Paths** | Multiple critical paths with equal total duration. All are reported. |
| **File Impact** | A predicted set of files that a task group will modify, extracted from backtick-quoted paths in spec documents. |
| **File Conflict** | Two parallel tasks with overlapping predicted file modification sets. |
| **Blocking Decision** | A recorded event where a skeptic or oracle reviewer evaluated whether to block a spec from proceeding based on critical finding count. |
| **Learned Threshold** | An optimal blocking threshold computed from historical decisions that minimizes false positives while bounding false negatives. |

## Requirements

### Requirement 1: Project Model Aggregation

**User Story:** As a project operator, I want to see aggregate metrics for
each spec (cost, duration, failure rate, session count), module stability,
and archetype effectiveness so that I can identify problem areas.

#### Acceptance Criteria

1. [43-REQ-1.1] WHEN `build_project_model()` is called with a DuckDB connection, THE system SHALL return a `ProjectModel` containing per-spec `SpecMetrics` with avg_cost, avg_duration_ms, failure_rate, and session_count computed from `execution_outcomes` joined with `complexity_assessments`.
2. [43-REQ-1.2] WHEN `build_project_model()` is called, THE system SHALL compute module stability as finding density (review findings count / session count) per spec.
3. [43-REQ-1.3] WHEN `build_project_model()` is called, THE system SHALL compute archetype effectiveness as success rate (completed sessions / total sessions) per archetype.
4. [43-REQ-1.4] WHEN `format_project_model()` is called, THE system SHALL return a human-readable string containing spec outcomes, module stability, archetype effectiveness, and active drift areas.

#### Edge Cases

1. [43-REQ-1.E1] IF there are no execution outcomes in DuckDB, THEN `build_project_model()` SHALL return a ProjectModel with empty dictionaries and lists.
2. [43-REQ-1.E2] IF a spec has review findings but no execution outcomes, THEN module stability SHALL use the finding count directly (density = findings / 1).

### Requirement 2: Critical Path Computation

**User Story:** As a project operator, I want to see the critical path
through remaining work and its estimated total duration so that I can
understand schedule risk.

#### Acceptance Criteria

1. [43-REQ-2.1] WHEN `compute_critical_path()` is called with nodes, edges, and duration hints, THE system SHALL return a `CriticalPathResult` containing the longest-duration path and total duration in milliseconds.
2. [43-REQ-2.2] WHEN `format_critical_path()` is called with a CriticalPathResult, THE system SHALL return a human-readable string showing the path as "node1 -> node2 -> node3" and the total duration.
3. [43-REQ-2.3] WHEN multiple paths tie for the longest duration, THE system SHALL report all tied paths in `CriticalPathResult.tied_paths`.

#### Edge Cases

1. [43-REQ-2.E1] IF the node set is empty, THEN `compute_critical_path()` SHALL return a CriticalPathResult with an empty path and total_duration_ms of 0.
2. [43-REQ-2.E2] IF a node has no duration hint, THE system SHALL treat its duration as 0 milliseconds.
3. [43-REQ-2.E3] IF the graph has disconnected components, THE system SHALL still compute the longest path across the entire graph.

### Requirement 3: File Conflict Detection

**User Story:** As a project operator, I want the system to detect when
parallel tasks are predicted to modify the same files so that conflicting
tasks can be serialized to prevent merge conflicts.

#### Acceptance Criteria

1. [43-REQ-3.1] WHEN `extract_file_impacts()` is called with a spec directory and task group number, THE system SHALL return a set of predicted file paths extracted from backtick-quoted references in tasks.md and design.md.
2. [43-REQ-3.2] WHEN `detect_conflicts()` is called with a list of FileImpact objects, THE system SHALL return all pairs of nodes with overlapping predicted files, with each pair reported once (lower node_id first).
3. [43-REQ-3.3] WHEN `filter_conflicts_from_dispatch()` is called with ready tasks and file impacts, THE system SHALL return only the tasks safe to dispatch in parallel (first task in each conflicting pair is kept, others deferred).
4. [43-REQ-3.4] THE file_conflict_detection config flag SHALL default to `false` in `PlanningConfig`.

#### Edge Cases

1. [43-REQ-3.E1] IF a task has no predicted file impacts (empty set), THEN it SHALL be treated as non-conflicting and always safe to dispatch.
2. [43-REQ-3.E2] IF tasks.md or design.md does not exist in the spec directory, THEN `extract_file_impacts()` SHALL return an empty set for missing files.

### Requirement 4: Learned Blocking Thresholds

**User Story:** As a project operator, I want the system to learn optimal
blocking thresholds from historical decisions so that false positives are
minimized while maintaining acceptable false negative rates.

#### Acceptance Criteria

1. [43-REQ-4.1] WHEN `record_blocking_decision()` is called, THE system SHALL insert a record into the `blocking_history` DuckDB table with spec_name, archetype, critical_count, threshold, blocked, and outcome.
2. [43-REQ-4.2] WHEN `compute_optimal_threshold()` is called with at least `min_decisions` (default: 20) recorded decisions for an archetype, THE system SHALL return the threshold that minimizes false positives while keeping the false negative rate at or below `max_false_negative_rate`.
3. [43-REQ-4.3] WHEN fewer than `min_decisions` exist for an archetype, `compute_optimal_threshold()` SHALL return None.
4. [43-REQ-4.4] THE learn_thresholds config flag SHALL default to `false` in `BlockingConfig`.
5. [43-REQ-4.5] WHEN `store_learned_threshold()` is called, THE system SHALL upsert the threshold into the `learned_thresholds` DuckDB table.
6. [43-REQ-4.6] WHEN `get_learned_threshold()` is called for an archetype with a stored threshold, THE system SHALL return the stored integer threshold.
7. [43-REQ-4.7] WHEN `format_learned_thresholds()` is called, THE system SHALL return a human-readable string listing all learned thresholds.

#### Edge Cases

1. [43-REQ-4.E1] IF blocking_history table does not exist when queried, `compute_optimal_threshold()` SHALL return None (not raise).
2. [43-REQ-4.E2] IF all historical decisions have the same outcome (all correct_block or all correct_pass), THE system SHALL still compute a valid threshold.
