# Design Document: Duration-Based Task Ordering

## Overview

Duration-based task ordering adds predicted execution times to the
orchestrator's task dispatch system. Ready tasks are sorted by predicted
duration descending (LPT scheduling) to minimise parallel batch wall-clock
time. Duration predictions cascade through four sources with strict
precedence: regression model, historical median, presets, default.

All duration logic lives in two new modules under `agent_fox/routing/`.
Integration into the orchestrator is minimal: one method
(`_compute_duration_hints()`) computes hints, and `ready_tasks()` accepts
an optional hint dict.

## Architecture

```
Orchestrator._compute_duration_hints()
    |
    v
get_duration_hint(conn, node_id, spec_name, archetype, tier, ...)
    |
    +--> _predict_from_model()     [source: regression]
    |        |
    |        +--> query complexity_assessments for feature vector
    |        +--> model.predict(feature_array)
    |
    +--> _get_historical_median()  [source: historical]
    |        |
    |        +--> query execution_outcomes JOIN complexity_assessments
    |        +--> compute median duration_ms
    |
    +--> DURATION_PRESETS lookup    [source: preset]
    |
    +--> DEFAULT_DURATION_MS       [source: default]
    |
    v
DurationHint(node_id, predicted_ms, source)
    |
    v
ready_tasks(duration_hints={node_id: predicted_ms, ...})
    |
    v
order_by_duration(node_ids, duration_hints)
    --> sorted descending by duration, ties alphabetical
```

```
train_duration_model(conn, min_outcomes=30)
    |
    +--> query execution_outcomes JOIN complexity_assessments
    +--> extract feature vectors + duration_ms
    +--> fit LinearRegression(X, y)
    |
    v
LinearRegression model (or None)
```

## Module Responsibilities

### `agent_fox/routing/duration.py`

Core duration hint computation module.

**Public API:**

| Symbol | Kind | Description |
|--------|------|-------------|
| `DurationHint` | dataclass | Prediction result: `node_id`, `predicted_ms`, `source` |
| `get_duration_hint()` | function | Cascading duration lookup (regression > historical > preset > default) |
| `train_duration_model()` | function | Train LinearRegression from execution outcomes |
| `order_by_duration()` | function | Sort node IDs by predicted duration descending |

**Internal functions:**

| Symbol | Description |
|--------|-------------|
| `_get_historical_median()` | Query median duration from execution_outcomes |
| `_predict_from_model()` | Extract features and call model.predict() |
| `_feature_vector_to_array()` | Convert JSON feature vector to float array |

### `agent_fox/routing/duration_presets.py`

Static preset configuration.

| Symbol | Kind | Description |
|--------|------|-------------|
| `DURATION_PRESETS` | dict | Archetype -> tier -> estimated ms |
| `DEFAULT_DURATION_MS` | int | Flat fallback (300,000 ms) |

### `agent_fox/core/config.py` (modified)

`PlanningConfig` pydantic model with:

| Field | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| `duration_ordering` | bool | true | -- | Enable duration-based ordering |
| `min_outcomes_for_historical` | int | 10 | 1-1000 | Min outcomes for historical median |
| `min_outcomes_for_regression` | int | 30 | 5-10000 | Min outcomes for regression training |

### `agent_fox/engine/graph_sync.py` (modified)

`GraphSync.ready_tasks()` accepts `duration_hints: dict[str, int] | None`.
When provided and non-empty, delegates to `order_by_duration()`. Otherwise,
returns alphabetical sort (existing behaviour).

### `agent_fox/engine/engine.py` (modified)

`Orchestrator._compute_duration_hints()` method:
1. Check `planning_config.duration_ordering` -- return None if disabled.
2. Get DB connection from assessment pipeline -- return None if unavailable.
3. For each pending node, call `get_duration_hint()` with spec metadata.
4. Return `{node_id: predicted_ms}` dict.
5. Catch all exceptions, log warning, return None.

## Data Model

### DurationHint

```python
@dataclass
class DurationHint:
    node_id: str
    predicted_ms: int  # always >= 1
    source: str  # "regression" | "historical" | "preset" | "default"
```

### Database Tables (existing)

Duration hints query two existing tables created by spec 30 (Adaptive Model
Routing):

**`complexity_assessments`**: Contains feature vectors and spec metadata.
- `id` (VARCHAR) -- assessment identifier
- `spec_name` (VARCHAR) -- specification name
- `feature_vector` (VARCHAR) -- JSON-encoded feature dict
- `created_at` (TIMESTAMP)

**`execution_outcomes`**: Contains actual execution results.
- `assessment_id` (VARCHAR) -- FK to complexity_assessments.id
- `duration_ms` (INTEGER) -- actual execution time
- `status` (VARCHAR) -- outcome status

## Source Precedence

The `get_duration_hint()` function evaluates sources in strict order and
returns the first successful result:

1. **Regression** (`source="regression"`): If a trained model is provided,
   extract the most recent feature vector for the spec+archetype from
   `complexity_assessments`, convert to a numeric array, and call
   `model.predict()`. Clamp result to min 1 ms. Skip on any error.

2. **Historical** (`source="historical"`): Query all `duration_ms` values
   from `execution_outcomes` joined with `complexity_assessments` for the
   matching spec+archetype. If count >= `min_outcomes`, compute and return
   the median. Skip if insufficient data or query error.

3. **Preset** (`source="preset"`): Look up `DURATION_PRESETS[archetype][tier]`.
   Return if found.

4. **Default** (`source="default"`): Return `DEFAULT_DURATION_MS` (300,000 ms).

## Ordering Algorithm

`order_by_duration(node_ids, duration_hints)`:

1. Partition `node_ids` into two groups:
   - `with_hints`: nodes present in `duration_hints`
   - `without_hints`: nodes not present in `duration_hints`
2. Sort `with_hints` by `(-duration, node_id)` -- descending duration, then
   ascending alphabetical.
3. Sort `without_hints` alphabetically.
4. Return `with_hints + without_hints`.

## Regression Model

`train_duration_model(conn, min_outcomes=30)`:

1. Query all `(feature_vector, duration_ms)` pairs from `execution_outcomes`
   joined with `complexity_assessments`.
2. Convert each feature vector JSON to a 5-element float array.
3. Discard rows with unparseable feature vectors.
4. If fewer than `min_outcomes` valid rows remain, return None.
5. Fit `LinearRegression` on the feature matrix `X` and target vector `y`.
6. Return the trained model.

Feature vector encoding:

| Index | Feature | Type |
|-------|---------|------|
| 0 | subtask_count | float |
| 1 | spec_word_count | float |
| 2 | has_property_tests | float (0.0 or 1.0) |
| 3 | edge_case_count | float |
| 4 | dependency_count | float |

## Correctness Properties

**CP-1: Source precedence is strict.** If a higher-precedence source produces
a valid result, lower-precedence sources are never consulted.

**CP-2: Ordering is deterministic.** Given the same set of node IDs and
duration hints, `order_by_duration()` always returns the same ordering.

**CP-3: Ordering preserves set membership.** The output of
`order_by_duration()` contains exactly the same elements as the input.

**CP-4: Duration predictions are positive.** `predicted_ms` is always >= 1.

**CP-5: Graceful degradation.** Any failure in duration computation results
in alphabetical ordering, never a crash or missing tasks.

**CP-6: Preset completeness.** Every archetype in the archetype registry has
presets for all three tiers.

## Error Handling

- DuckDB query failures in `_get_historical_median()`: return None, fall
  through to presets.
- DuckDB query failures in `_predict_from_model()`: return None, fall through
  to historical.
- `model.predict()` failures: log warning, return None, fall through.
- `_feature_vector_to_array()` parse failures: return None.
- `_compute_duration_hints()` top-level: catch all exceptions, log warning,
  return None (alphabetical fallback).
- Missing scikit-learn/numpy: skip regression entirely.

## Performance

Duration hint computation adds one DuckDB round-trip per pending node (for
historical median) plus one for regression feature lookup. DuckDB is
embedded (in-process), so these are sub-millisecond operations. The total
overhead per dispatch cycle is negligible (< 10ms even with 50 nodes).

Regression model training queries the full `execution_outcomes` table once
per orchestrator run. This is acceptable because training happens at most
once and the table size is bounded by the number of completed sessions.
