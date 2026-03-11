# Requirements Document

## Introduction

This spec implements predictive planning and knowledge usage improvements for
agent-fox. It covers duration-based task ordering, review finding integration
into the causal graph, confidence-aware fact selection, pre-computed fact
rankings, a project model, critical path forecasting, cross-task-group finding
propagation, predictive file conflict detection, and learned blocking
thresholds.

## Glossary

| Term | Definition |
|------|------------|
| **Ready Set** | The set of task nodes whose status is `pending` and all dependencies are `completed`. Candidates for dispatch. |
| **Duration Hint** | A predicted execution duration in milliseconds for a task, derived from historical outcomes or preset defaults. |
| **Duration Presets** | Configurable default duration estimates per archetype and complexity tier, used when historical data is insufficient. |
| **Causal Graph** | A directed graph stored in the `fact_causes` DuckDB table linking memory facts by cause-effect relationships. |
| **Review Findings** | Skeptic, oracle, and verifier outputs stored in `review_findings`, `drift_findings`, and `verification_results` tables. |
| **Confidence Threshold** | A float value in `[0.0, 1.0]` below which facts are excluded from session context. Default: `0.5`. |
| **Ranked Fact Cache** | Pre-computed, per-spec fact relevance rankings stored at plan time to avoid per-session re-computation. |
| **Project Model** | An aggregate view of spec outcomes, module stability, and archetype effectiveness derived from execution history. |
| **Critical Path** | The longest-duration path through the task graph, determining the minimum total execution time. |
| **File Impact Matrix** | A mapping from task group to predicted set of modified files, extracted from spec documents. |
| **Blocking Threshold** | The number of critical findings that causes a skeptic or oracle to block a spec from proceeding. |

## Requirements

### Requirement 1: Duration-Based Task Ordering

**User Story:** As the orchestrator, I want ready tasks sorted by predicted
duration descending, so that long tasks start first in parallel batches and
wall-clock time is minimized.

#### Acceptance Criteria

1. [39-REQ-1.1] WHEN dispatching ready tasks, THE system SHALL sort them by predicted duration in descending order (longest first).
2. [39-REQ-1.2] WHEN historical execution data exists for a task's spec and archetype, THE system SHALL use the median historical duration as the prediction.
3. [39-REQ-1.3] WHEN no historical data exists, THE system SHALL fall back to duration presets, then to alphabetical ordering.
4. [39-REQ-1.4] THE system SHALL provide a `get_duration_hint()` function that returns a predicted duration in milliseconds for a given node.

#### Edge Cases

1. [39-REQ-1.E1] IF fewer than a configurable minimum number of outcomes exist (default: 10), THEN THE system SHALL use duration presets instead of historical medians.

### Requirement 2: Duration Regression Model

**User Story:** As the orchestrator, I want a regression model that predicts
task duration from feature vectors, so that predictions improve as more
execution data accumulates.

#### Acceptance Criteria

1. [39-REQ-2.1] WHEN sufficient execution outcomes exist (configurable threshold, default: 30), THE system SHALL train a duration regression model from feature vectors and historical durations.
2. [39-REQ-2.2] THE system SHALL use the regression model's prediction when available, falling back to median-based hints when the model is not trained.
3. [39-REQ-2.3] THE system SHALL retrain the model when new outcomes are recorded, using the same trigger mechanism as the existing tier classifier.

### Requirement 3: Link Review Findings to Causal Graph

**User Story:** As a session consumer, I want review findings linked to
related memory facts in the causal graph, so that downstream sessions
inherit richer context automatically.

#### Acceptance Criteria

1. [39-REQ-3.1] WHEN causal traversal occurs during context assembly, THE system SHALL also query `review_findings`, `drift_findings`, and `verification_results` tables for facts linked to the traversal seeds.
2. [39-REQ-3.2] THE system SHALL extend `traverse_causal_chain()` or add a companion function to include review findings in the traversal results.
3. [39-REQ-3.3] WHEN a review finding references a requirement ID that matches a memory fact's keywords, THE system SHALL treat them as causally related for traversal purposes.

### Requirement 4: Confidence-Aware Fact Selection

**User Story:** As a session consumer, I want low-confidence facts excluded
from my context, so that session prompts contain higher-quality information.

#### Acceptance Criteria

1. [39-REQ-4.1] WHEN selecting facts for a session, THE system SHALL exclude facts with `confidence < threshold` (configurable, default: `0.5`).
2. [39-REQ-4.2] THE system SHALL make the confidence threshold configurable via `config.toml` under a `[knowledge]` section.
3. [39-REQ-4.3] THE system SHALL apply confidence filtering before keyword scoring in `select_relevant_facts()`.

### Requirement 5: Pre-Computed Ranked Facts

**User Story:** As the orchestrator, I want fact rankings pre-computed at
plan time, so that per-session context assembly is faster.

#### Acceptance Criteria

1. [39-REQ-5.1] WHEN the planner runs, THE system SHALL pre-compute and cache ranked fact lists per spec.
2. [39-REQ-5.2] WHEN assembling session context, THE system SHALL use the cached rankings if available, falling back to live computation if the cache is stale or missing.
3. [39-REQ-5.3] THE system SHALL invalidate the fact cache when new facts are added or existing facts are superseded.

### Requirement 6: Cross-Task-Group Finding Propagation

**User Story:** As a coder in task group N, I want to see critical review
findings from task groups 1 through N-1, so that I don't repeat mistakes
flagged in earlier groups.

#### Acceptance Criteria

1. [39-REQ-6.1] WHEN assembling context for task group N, THE system SHALL include active review findings from all prior task groups (1 through N-1) of the same spec.
2. [39-REQ-6.2] THE system SHALL render propagated findings in a separate section labeled "Prior Group Findings" to distinguish them from the current group's findings.

### Requirement 7: Project Model

**User Story:** As a project operator, I want an aggregate project model
showing spec outcomes, module stability, and archetype effectiveness, so
that I can identify fragile areas and tune the orchestrator.

#### Acceptance Criteria

1. [39-REQ-7.1] THE system SHALL provide a `ProjectModel` class that aggregates spec-level metrics (average cost, duration, failure rate) from execution outcomes.
2. [39-REQ-7.2] THE system SHALL compute module stability scores from review finding density (findings per spec per session).
3. [39-REQ-7.3] THE system SHALL compute archetype effectiveness as the success rate per archetype type.
4. [39-REQ-7.4] THE system SHALL expose the project model via `agent-fox status --model` output.

### Requirement 8: Critical Path Forecasting

**User Story:** As the orchestrator, I want to identify the critical path
through the task graph using predicted durations, so that scheduling
decisions minimize total wall-clock time.

#### Acceptance Criteria

1. [39-REQ-8.1] THE system SHALL compute the critical path through the task graph using duration hints as edge weights.
2. [39-REQ-8.2] THE system SHALL report the critical path and estimated total duration in `agent-fox status` output.
3. [39-REQ-8.3] WHEN multiple paths have equal duration, THE system SHALL report all tied critical paths.

### Requirement 9: Predictive File Conflict Detection

**User Story:** As the orchestrator, I want to detect potential file conflicts
between parallel tasks before dispatch, so that conflicting tasks can be
serialized to avoid merge failures.

#### Acceptance Criteria

1. [39-REQ-9.1] THE system SHALL extract predicted file modification sets from `tasks.md` and `design.md` for each task group.
2. [39-REQ-9.2] WHEN two ready tasks have overlapping predicted file sets, THE system SHALL flag the overlap as a potential conflict.
3. [39-REQ-9.3] WHERE file conflict detection is enabled, THE system SHALL serialize conflicting task pairs (dispatch one, defer the other).

#### Edge Cases

1. [39-REQ-9.E1] IF the file extraction heuristic produces no results for a task, THEN THE system SHALL treat that task as non-conflicting (allow parallel dispatch).

### Requirement 10: Learned Blocking Thresholds

**User Story:** As a project operator, I want blocking thresholds to adapt
based on historical effectiveness, so that false-positive blocks decrease
over time.

#### Acceptance Criteria

1. [39-REQ-10.1] THE system SHALL track blocking decisions and their outcomes (did blocking prevent a failure? did non-blocking lead to a failure?).
2. [39-REQ-10.2] WHEN sufficient blocking history exists (configurable, default: 20 decisions), THE system SHALL compute an optimal threshold that minimizes false positives while maintaining a configurable false negative rate.
3. [39-REQ-10.3] THE system SHALL store learned thresholds in DuckDB and surface them in `agent-fox status --model`.
