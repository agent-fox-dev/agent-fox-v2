# Requirements Document: Duration-Based Task Ordering

## Introduction

Duration-based task ordering predicts execution times for ready tasks and
dispatches them longest-first to minimise parallel batch wall-clock time.
Duration predictions use a cascading source precedence: regression model,
historical median, preset defaults, and a flat fallback.

## Glossary

- **Duration Hint**: A predicted execution time in milliseconds for a task
  node, with a source label indicating how it was derived.
- **LPT Scheduling**: Longest Processing Time first -- a scheduling heuristic
  that dispatches the longest task first to minimise makespan.
- **Historical Median**: The median `duration_ms` from past `execution_outcomes`
  for a given spec+archetype pair.
- **Duration Preset**: A static default duration estimate indexed by archetype
  and complexity tier.
- **Feature Vector**: Numeric attributes extracted from a task group's spec
  content (subtask count, word count, property test presence, edge case count,
  dependency count), used as regression model input.
- **Regression Model**: A `LinearRegression` trained on feature vectors and
  actual durations from `execution_outcomes`.

## Requirements

### Requirement 1: Duration-Based Ordering

**User Story:** As an operator running parallel sessions, I want ready tasks
dispatched longest-first, so that short tasks fill gaps around long tasks and
total batch time is minimised.

#### Acceptance Criteria

1. [41-REQ-1.1] WHEN duration hints are provided to `ready_tasks()`, THE
   system SHALL return tasks sorted by predicted duration descending (longest
   first).

2. [41-REQ-1.2] WHEN two tasks have equal predicted duration, THE system SHALL
   break ties by sorting alphabetically on node_id (ascending).

3. [41-REQ-1.3] WHEN a task has no duration hint, THE system SHALL place it
   after all tasks with hints, sorted alphabetically.

4. [41-REQ-1.4] WHEN duration hints are not provided (None), THE system SHALL
   return tasks sorted alphabetically (existing behaviour preserved).

#### Edge Cases

1. [41-REQ-1.E1] IF computing duration hints raises an exception, THEN THE
   system SHALL fall back to alphabetical ordering and log a warning.

2. [41-REQ-1.E2] IF the duration hints dict is empty, THE system SHALL treat
   it as None and return alphabetical ordering.

---

### Requirement 2: Historical Median Lookup

**User Story:** As an operator with accumulated execution data, I want duration
predictions based on actual past performance for the same spec and archetype.

#### Acceptance Criteria

1. [41-REQ-2.1] WHEN at least `min_outcomes_for_historical` execution outcomes
   exist for a spec+archetype pair, THE system SHALL compute the median
   `duration_ms` and return it as a historical duration hint.

2. [41-REQ-2.2] WHEN fewer than `min_outcomes_for_historical` outcomes exist,
   THE system SHALL NOT use historical median and SHALL fall through to the
   next source in precedence.

3. [41-REQ-2.3] THE historical median SHALL be computed as the middle value
   for odd counts, or the integer average of the two middle values for even
   counts.

#### Edge Cases

1. [41-REQ-2.E1] IF the DuckDB query for historical outcomes fails, THEN THE
   system SHALL return None for that source and fall through to presets.

---

### Requirement 3: Duration Presets

**User Story:** As an operator on a new project with no execution history, I
want reasonable duration estimates so that ordering still works.

#### Acceptance Criteria

1. [41-REQ-3.1] THE system SHALL provide preset duration estimates for all
   six archetypes (coder, skeptic, oracle, verifier, librarian, cartographer)
   across three tiers (STANDARD, ADVANCED, MAX).

2. [41-REQ-3.2] WHEN a preset exists for the given archetype+tier, THE system
   SHALL use it as the duration hint with source "preset".

3. [41-REQ-3.3] WHEN no preset exists for the archetype+tier combination, THE
   system SHALL use `DEFAULT_DURATION_MS` (300,000 ms) with source "default".

4. [41-REQ-3.4] Preset values SHALL be conservative (overestimates preferred)
   because LPT scheduling benefits from earlier dispatch of potentially long
   tasks.

---

### Requirement 4: Regression Model

**User Story:** As an operator with a large execution history, I want a
trained model that accounts for task features to produce more accurate
duration predictions than simple medians.

#### Acceptance Criteria

1. [41-REQ-4.1] WHEN at least `min_outcomes_for_regression` outcomes with
   valid feature vectors exist, THE `train_duration_model()` function SHALL
   return a trained `LinearRegression` model.

2. [41-REQ-4.2] WHEN fewer than `min_outcomes_for_regression` valid outcomes
   exist, THE function SHALL return None.

3. [41-REQ-4.3] THE regression model SHALL use the following features:
   subtask_count, spec_word_count, has_property_tests (as 0/1),
   edge_case_count, dependency_count.

4. [41-REQ-4.4] WHEN a trained model is available, THE `get_duration_hint()`
   function SHALL prefer regression predictions over all other sources.

5. [41-REQ-4.5] THE regression prediction SHALL be clamped to a minimum of
   1 ms (no zero or negative predictions).

#### Edge Cases

1. [41-REQ-4.E1] IF the regression model's `predict()` call raises an
   exception, THEN THE system SHALL fall through to historical median and
   log a warning.

2. [41-REQ-4.E2] IF scikit-learn or numpy is not importable, THEN THE system
   SHALL skip regression entirely and fall through to historical/preset sources.

3. [41-REQ-4.E3] IF no feature vector can be extracted for regression input,
   THEN THE system SHALL fall through to historical median.

---

### Requirement 5: Configuration and Integration

**User Story:** As an operator, I want to configure duration ordering behaviour
and have it integrated into the orchestrator dispatch loop.

#### Acceptance Criteria

1. [41-REQ-5.1] THE `[planning]` config section SHALL include:
   - `duration_ordering` (bool, default: true)
   - `min_outcomes_for_historical` (int, default: 10, clamped to 1-1000)
   - `min_outcomes_for_regression` (int, default: 30, clamped to 5-10000)

2. [41-REQ-5.2] WHEN `duration_ordering` is false, THE orchestrator SHALL
   NOT compute duration hints and SHALL use alphabetical ordering.

3. [41-REQ-5.3] WHEN `duration_ordering` is true, THE orchestrator SHALL
   call `_compute_duration_hints()` before each `ready_tasks()` call and
   pass the result to enable duration-based ordering.

4. [41-REQ-5.4] THE `_compute_duration_hints()` method SHALL compute hints
   for all pending nodes using `get_duration_hint()` with the assessment
   pipeline's DuckDB connection and optional trained duration model.

#### Edge Cases

1. [41-REQ-5.E1] IF out-of-range values are provided for
   `min_outcomes_for_historical` or `min_outcomes_for_regression`, THEN THE
   system SHALL clamp to the nearest valid bound and log a warning.

2. [41-REQ-5.E2] IF the assessment pipeline or its DB connection is
   unavailable, THEN `_compute_duration_hints()` SHALL return None and the
   system SHALL fall back to alphabetical ordering.
