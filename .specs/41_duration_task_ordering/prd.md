# PRD: Duration-Based Task Ordering

## Problem Statement

agent-fox dispatches ready tasks to parallel agent sessions. Currently,
`ready_tasks()` returns tasks sorted alphabetically, which means task dispatch
order is arbitrary with respect to execution time. When long-running tasks are
dispatched late in a parallel batch, they become the bottleneck -- short tasks
finish early and agents sit idle waiting for the straggler.

Optimal parallel scheduling dispatches the longest tasks first (Longest
Processing Time scheduling), so that shorter tasks fill in the gaps as longer
ones complete. Without duration estimates, the orchestrator cannot make
informed dispatch ordering decisions.

## Source

Extracted from spec 39 (Predictive Planning and Knowledge). Spec 39 bundled
10 features into a single spec; this extraction isolates duration-based task
ordering as a focused, independently deliverable unit.

## Goals

1. Predict task execution duration using historical data, regression models,
   and configurable presets.
2. Order ready tasks by predicted duration descending (longest first) to
   minimise parallel batch completion time.
3. Provide sensible fallback estimates when insufficient history exists.
4. Make duration ordering configurable and non-disruptive (graceful fallback
   on errors).

## Feature Description

### Duration Hints

A **duration hint** is a predicted execution time (in milliseconds) for a task
node, produced from one of four sources with strict precedence:

1. **Regression model** -- a LinearRegression trained on historical feature
   vectors and actual durations. Highest fidelity but requires sufficient
   data (configurable threshold, default 30 outcomes).
2. **Historical median** -- median duration from past execution outcomes for
   the same spec+archetype pair. Requires a configurable minimum number of
   outcomes (default 10).
3. **Preset** -- static default estimates per archetype and complexity tier.
   Provides reasonable estimates with zero history.
4. **Default** -- a flat 300-second (300,000 ms) fallback when no other
   source applies.

### Duration Presets

A lookup table of archetype x tier -> estimated duration in milliseconds.
Presets are intentionally conservative (overestimates are better than
underestimates for LPT scheduling). Covers all six archetypes (coder, skeptic,
oracle, verifier, librarian, cartographer) across three tiers (STANDARD,
ADVANCED, MAX).

### Duration Ordering

`ready_tasks()` accepts optional duration hints and sorts ready tasks by
predicted duration descending. Ties are broken alphabetically. Tasks without
hints are placed last, sorted alphabetically.

### Regression Model

When sufficient execution outcomes exist (>= `min_outcomes_for_regression`,
default 30), a `LinearRegression` model is trained from feature vectors
(subtask count, spec word count, property test presence, edge case count,
dependency count) paired with actual `duration_ms` from the
`execution_outcomes` table.

The model is trained lazily when the orchestrator first computes duration
hints and is reused for the duration of the run.

### Configuration

A `[planning]` section in `config.toml` controls:

- `duration_ordering` (bool, default: true) -- enable/disable duration-based
  ordering.
- `min_outcomes_for_historical` (int, default: 10, range: 1-1000) -- minimum
  outcomes before using historical median.
- `min_outcomes_for_regression` (int, default: 30, range: 5-10000) -- minimum
  outcomes before training the regression model.

### Integration

The orchestrator's dispatch loop calls `_compute_duration_hints()` before
`ready_tasks()`, passing the resulting hint map to enable duration ordering.
Duration hints are computed for all pending nodes using the assessment
pipeline's DuckDB connection and optional trained duration model.

## Scope

**In scope:**
- `DurationHint` dataclass and `get_duration_hint()` function
- `order_by_duration()` sorting function
- `train_duration_model()` regression training
- `DURATION_PRESETS` and `DEFAULT_DURATION_MS` constants
- `PlanningConfig` pydantic model with duration fields
- `ready_tasks()` duration_hints parameter
- Orchestrator `_compute_duration_hints()` integration

**Out of scope:**
- Confidence filtering and fact caching (separate spec)
- Project model and critical path analysis (separate spec)
- File conflict detection (separate spec)
- Learned blocking thresholds (separate spec)

## Dependencies

- **Spec 38 (DuckDB Hardening)**: Non-optional DuckDB connections. Duration
  hint queries rely on `execution_outcomes` and `complexity_assessments`
  tables being available through a required DuckDB connection.
- **scikit-learn**: `LinearRegression` is already a project dependency (used
  by adaptive routing calibration).

## Success Metrics

- Ready tasks are dispatched in duration-descending order when history exists.
- Parallel batch wall-clock time decreases as duration estimates improve.
- Zero regressions in existing orchestrator behaviour when duration ordering
  is disabled.

## Risks

- **Cold start**: New projects have no history, so preset fallbacks must be
  reasonable. Presets are intentionally conservative.
- **Stale data**: Historical medians may drift if task complexity changes.
  Regression models partially mitigate this by incorporating feature vectors.
- **Query cost**: Duration hint queries add DuckDB round-trips per dispatch
  cycle. Acceptable because DuckDB is embedded (in-process, sub-millisecond
  queries).
