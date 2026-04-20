# Test Specification: Duration-Based Task Ordering

## Overview

Tests are organized into three categories: acceptance criterion tests (one per
requirement criterion), property tests (one per design correctness property),
and edge case tests. All tests use pytest. Property tests use Hypothesis.
Integration tests use an in-memory DuckDB instance with the required schema.

## Test Cases

### TS-41-1: Descending Duration Ordering

**Requirement:** 41-REQ-1.1
**Type:** unit
**Description:** Verify tasks are sorted by predicted duration descending.

**Preconditions:**
- Three node IDs: "a", "b", "c".

**Input:**
- `duration_hints = {"a": 100, "b": 500, "c": 300}`

**Expected:**
- Output order: `["b", "c", "a"]` (500 > 300 > 100).

**Assertion pseudocode:**
```
result = order_by_duration(["a", "b", "c"], {"a": 100, "b": 500, "c": 300})
ASSERT result == ["b", "c", "a"]
```

---

### TS-41-2: Alphabetical Tie-Breaking

**Requirement:** 41-REQ-1.2
**Type:** unit
**Description:** Verify alphabetical tie-breaking when durations are equal.

**Preconditions:**
- Three node IDs with two sharing the same duration.

**Input:**
- `duration_hints = {"alpha": 200, "beta": 200, "gamma": 500}`

**Expected:**
- Output order: `["gamma", "alpha", "beta"]` (500, then 200 tie broken a < b).

**Assertion pseudocode:**
```
result = order_by_duration(["alpha", "beta", "gamma"], {"alpha": 200, "beta": 200, "gamma": 500})
ASSERT result == ["gamma", "alpha", "beta"]
```

---

### TS-41-3: Tasks Without Hints Placed Last

**Requirement:** 41-REQ-1.3
**Type:** unit
**Description:** Verify tasks without hints are placed after hinted tasks.

**Preconditions:**
- Four node IDs, two with hints and two without.

**Input:**
- `node_ids = ["d", "c", "b", "a"]`
- `duration_hints = {"a": 100, "c": 300}`

**Expected:**
- Output: `["c", "a", "b", "d"]` (hinted desc, then unhinted alpha).

**Assertion pseudocode:**
```
result = order_by_duration(["d", "c", "b", "a"], {"a": 100, "c": 300})
ASSERT result == ["c", "a", "b", "d"]
```

---

### TS-41-4: No Hints Returns Alphabetical

**Requirement:** 41-REQ-1.4
**Type:** unit
**Description:** Verify `ready_tasks()` returns alphabetical order when no
duration hints are provided.

**Preconditions:**
- GraphSync with three pending nodes "c", "a", "b" and no dependencies.

**Input:**
- `ready_tasks(duration_hints=None)`

**Expected:**
- Output: `["a", "b", "c"]`.

**Assertion pseudocode:**
```
gs = GraphSync({"a": "pending", "b": "pending", "c": "pending"}, {})
result = gs.ready_tasks(duration_hints=None)
ASSERT result == ["a", "b", "c"]
```

---

### TS-41-5: Historical Median With Sufficient Data

**Requirement:** 41-REQ-2.1
**Type:** unit (with in-memory DuckDB)
**Description:** Verify historical median is used when enough outcomes exist.

**Preconditions:**
- In-memory DuckDB with `complexity_assessments` and `execution_outcomes` tables.
- 15 outcomes for spec "myspec" + archetype "coder" with known durations.

**Input:**
- `get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)`

**Expected:**
- `source == "historical"` and `predicted_ms` equals the median of the 15
  durations.

**Assertion pseudocode:**
```
# Insert 15 outcomes with durations [100, 200, ..., 1500]
hint = get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)
ASSERT hint.source == "historical"
ASSERT hint.predicted_ms == 800  # median of 100..1500
```

---

### TS-41-6: Historical Median Insufficient Data

**Requirement:** 41-REQ-2.2
**Type:** unit (with in-memory DuckDB)
**Description:** Verify fallthrough when fewer than min_outcomes exist.

**Preconditions:**
- In-memory DuckDB with 5 outcomes for spec "myspec" + archetype "coder".

**Input:**
- `get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)`

**Expected:**
- `source` is NOT "historical" (falls through to preset or default).

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10)
ASSERT hint.source != "historical"
```

---

### TS-41-7: Historical Median Computation Odd Count

**Requirement:** 41-REQ-2.3
**Type:** unit
**Description:** Verify median computation for odd number of values.

**Preconditions:**
- `_get_historical_median` returns middle value for odd count.

**Input:**
- 11 outcomes with durations [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110].

**Expected:**
- Median is 60 (the 6th value in sorted order).

**Assertion pseudocode:**
```
# Insert 11 outcomes
median = _get_historical_median(conn, "spec", "coder", min_outcomes=5)
ASSERT median == 60
```

---

### TS-41-8: Historical Median Computation Even Count

**Requirement:** 41-REQ-2.3
**Type:** unit
**Description:** Verify median computation for even number of values.

**Preconditions:**
- `_get_historical_median` returns integer average of two middle values.

**Input:**
- 10 outcomes with durations [10, 20, 30, 40, 50, 60, 70, 80, 90, 100].

**Expected:**
- Median is (50 + 60) // 2 = 55.

**Assertion pseudocode:**
```
median = _get_historical_median(conn, "spec", "coder", min_outcomes=5)
ASSERT median == 55
```

---

### TS-41-9: Preset Lookup By Archetype And Tier

**Requirement:** 41-REQ-3.1, 41-REQ-3.2
**Type:** unit
**Description:** Verify preset durations exist for all archetypes and tiers.

**Preconditions:**
- `DURATION_PRESETS` dict is populated.

**Input:**
- All 6 archetypes x 3 tiers.

**Expected:**
- Every combination returns a positive integer.

**Assertion pseudocode:**
```
for archetype in ["coder", "skeptic", "oracle", "verifier", "librarian", "cartographer"]:
    for tier in ["STANDARD", "ADVANCED", "MAX"]:
        ASSERT archetype in DURATION_PRESETS
        ASSERT tier in DURATION_PRESETS[archetype]
        ASSERT DURATION_PRESETS[archetype][tier] > 0
```

---

### TS-41-10: Default Fallback

**Requirement:** 41-REQ-3.3
**Type:** unit (with in-memory DuckDB)
**Description:** Verify default fallback when no preset matches.

**Preconditions:**
- In-memory DuckDB with empty tables (no history).
- Archetype+tier combination not in presets (e.g. "unknown_arch", "UNKNOWN_TIER").

**Input:**
- `get_duration_hint(conn, "node1", "spec", "unknown_arch", "UNKNOWN_TIER")`

**Expected:**
- `source == "default"` and `predicted_ms == DEFAULT_DURATION_MS` (300,000).

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "spec", "unknown_arch", "UNKNOWN_TIER")
ASSERT hint.source == "default"
ASSERT hint.predicted_ms == 300_000
```

---

### TS-41-11: Regression Model Training Success

**Requirement:** 41-REQ-4.1
**Type:** unit (with in-memory DuckDB)
**Description:** Verify model training succeeds with sufficient outcomes.

**Preconditions:**
- 35 outcomes with valid feature vectors and durations in DuckDB.

**Input:**
- `train_duration_model(conn, min_outcomes=30)`

**Expected:**
- Returns a `LinearRegression` instance (not None).

**Assertion pseudocode:**
```
model = train_duration_model(conn, min_outcomes=30)
ASSERT model is not None
ASSERT isinstance(model, LinearRegression)
```

---

### TS-41-12: Regression Model Training Insufficient Data

**Requirement:** 41-REQ-4.2
**Type:** unit (with in-memory DuckDB)
**Description:** Verify model returns None with insufficient outcomes.

**Preconditions:**
- 10 outcomes in DuckDB.

**Input:**
- `train_duration_model(conn, min_outcomes=30)`

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
model = train_duration_model(conn, min_outcomes=30)
ASSERT model is None
```

---

### TS-41-13: Regression Model Feature Vector

**Requirement:** 41-REQ-4.3
**Type:** unit
**Description:** Verify feature vector extraction for regression input.

**Preconditions:**
- A JSON feature vector string with all expected fields.

**Input:**
- `'{"subtask_count": 4, "spec_word_count": 200, "has_property_tests": true, "edge_case_count": 3, "dependency_count": 2}'`

**Expected:**
- `_feature_vector_to_array()` returns `[4.0, 200.0, 1.0, 3.0, 2.0]`.

**Assertion pseudocode:**
```
result = _feature_vector_to_array('{"subtask_count": 4, "spec_word_count": 200, "has_property_tests": true, "edge_case_count": 3, "dependency_count": 2}')
ASSERT result == [4.0, 200.0, 1.0, 3.0, 2.0]
```

---

### TS-41-14: Regression Takes Precedence Over Historical

**Requirement:** 41-REQ-4.4
**Type:** unit (with in-memory DuckDB)
**Description:** Verify regression source is used when model is available.

**Preconditions:**
- In-memory DuckDB with 15+ outcomes (enough for historical median).
- A trained regression model.

**Input:**
- `get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10, model=trained_model)`

**Expected:**
- `source == "regression"`.

**Assertion pseudocode:**
```
model = train_duration_model(conn, min_outcomes=10)
hint = get_duration_hint(conn, "node1", "myspec", "coder", "STANDARD", min_outcomes=10, model=model)
ASSERT hint.source == "regression"
```

---

### TS-41-15: Regression Prediction Clamped To Minimum

**Requirement:** 41-REQ-4.5
**Type:** unit
**Description:** Verify regression predictions are clamped to minimum 1 ms.

**Preconditions:**
- A mock model that returns a negative prediction.

**Input:**
- `get_duration_hint()` with a model that predicts -50.

**Expected:**
- `predicted_ms == 1` (clamped).

**Assertion pseudocode:**
```
# Mock model that returns -50
hint = get_duration_hint(conn, "node1", "spec", "coder", "STANDARD", model=mock_model)
ASSERT hint.predicted_ms >= 1
```

---

### TS-41-16: PlanningConfig Defaults

**Requirement:** 41-REQ-5.1
**Type:** unit
**Description:** Verify PlanningConfig default values.

**Preconditions:**
- Default PlanningConfig construction.

**Input:**
- `PlanningConfig()`

**Expected:**
- `duration_ordering == True`
- `min_outcomes_for_historical == 10`
- `min_outcomes_for_regression == 30`

**Assertion pseudocode:**
```
config = PlanningConfig()
ASSERT config.duration_ordering == True
ASSERT config.min_outcomes_for_historical == 10
ASSERT config.min_outcomes_for_regression == 30
```

---

### TS-41-17: Duration Ordering Disabled

**Requirement:** 41-REQ-5.2
**Type:** unit
**Description:** Verify no duration hints are computed when ordering is disabled.

**Preconditions:**
- Orchestrator with `planning_config.duration_ordering = False`.

**Input:**
- `_compute_duration_hints()`

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
# Setup orchestrator with duration_ordering=False
result = orchestrator._compute_duration_hints()
ASSERT result is None
```

---

### TS-41-18: Duration Hints Passed To ready_tasks

**Requirement:** 41-REQ-5.3
**Type:** unit
**Description:** Verify ready_tasks receives and uses duration hints from orchestrator.

**Preconditions:**
- GraphSync with pending nodes.
- Duration hints dict with varying durations.

**Input:**
- `ready_tasks(duration_hints={"a": 500, "b": 100, "c": 300})`

**Expected:**
- Output order matches duration-descending: `["a", "c", "b"]`.

**Assertion pseudocode:**
```
gs = GraphSync({"a": "pending", "b": "pending", "c": "pending"}, {})
result = gs.ready_tasks(duration_hints={"a": 500, "b": 100, "c": 300})
ASSERT result == ["a", "c", "b"]
```

---

## Edge Case Tests

### TS-41-E1: Duration Hints Exception Fallback

**Requirement:** 41-REQ-1.E1
**Type:** unit
**Description:** Verify fallback to alphabetical on duration computation error.

**Preconditions:**
- Orchestrator with duration ordering enabled.
- Assessment pipeline that raises an exception on DB access.

**Expected:**
- `_compute_duration_hints()` returns None (triggers alphabetical fallback).
- Warning is logged.

**Assertion pseudocode:**
```
# Mock pipeline.db to raise
result = orchestrator._compute_duration_hints()
ASSERT result is None
```

---

### TS-41-E2: Empty Duration Hints Dict

**Requirement:** 41-REQ-1.E2
**Type:** unit
**Description:** Verify empty hints dict treated as None.

**Preconditions:**
- GraphSync with pending nodes.

**Input:**
- `ready_tasks(duration_hints={})`

**Expected:**
- Output is alphabetically sorted (empty dict is falsy).

**Assertion pseudocode:**
```
gs = GraphSync({"c": "pending", "a": "pending", "b": "pending"}, {})
result = gs.ready_tasks(duration_hints={})
ASSERT result == ["a", "b", "c"]
```

---

### TS-41-E3: DuckDB Query Failure In Historical Median

**Requirement:** 41-REQ-2.E1
**Type:** unit
**Description:** Verify None returned on DuckDB query error.

**Preconditions:**
- DuckDB connection that raises on execute.

**Expected:**
- `_get_historical_median()` returns None.

**Assertion pseudocode:**
```
# Mock conn.execute to raise duckdb.Error
result = _get_historical_median(mock_conn, "spec", "coder", 10)
ASSERT result is None
```

---

### TS-41-E4: Regression Predict Failure Fallthrough

**Requirement:** 41-REQ-4.E1
**Type:** unit (with in-memory DuckDB)
**Description:** Verify fallthrough to historical when model.predict() fails.

**Preconditions:**
- In-memory DuckDB with sufficient outcomes for historical median.
- Mock model whose predict() raises an exception.

**Expected:**
- `get_duration_hint()` returns a hint with `source != "regression"`.
- Warning is logged.

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "spec", "coder", "STANDARD", model=broken_model, min_outcomes=5)
ASSERT hint.source != "regression"
```

---

### TS-41-E5: Unparseable Feature Vector

**Requirement:** 41-REQ-4.E3
**Type:** unit
**Description:** Verify None returned for malformed feature vector JSON.

**Input:**
- `_feature_vector_to_array("not valid json")`

**Expected:**
- Returns None.

**Assertion pseudocode:**
```
result = _feature_vector_to_array("not valid json")
ASSERT result is None
```

---

### TS-41-E6: Config Clamping Historical Min

**Requirement:** 41-REQ-5.E1
**Type:** unit
**Description:** Verify out-of-range min_outcomes_for_historical is clamped.

**Input:**
- `PlanningConfig(min_outcomes_for_historical=0)` and
  `PlanningConfig(min_outcomes_for_historical=5000)`

**Expected:**
- First clamped to 1, second clamped to 1000.

**Assertion pseudocode:**
```
c1 = PlanningConfig(min_outcomes_for_historical=0)
ASSERT c1.min_outcomes_for_historical == 1
c2 = PlanningConfig(min_outcomes_for_historical=5000)
ASSERT c2.min_outcomes_for_historical == 1000
```

---

### TS-41-E7: Config Clamping Regression Min

**Requirement:** 41-REQ-5.E1
**Type:** unit
**Description:** Verify out-of-range min_outcomes_for_regression is clamped.

**Input:**
- `PlanningConfig(min_outcomes_for_regression=2)` and
  `PlanningConfig(min_outcomes_for_regression=50000)`

**Expected:**
- First clamped to 5, second clamped to 10000.

**Assertion pseudocode:**
```
c1 = PlanningConfig(min_outcomes_for_regression=2)
ASSERT c1.min_outcomes_for_regression == 5
c2 = PlanningConfig(min_outcomes_for_regression=50000)
ASSERT c2.min_outcomes_for_regression == 10000
```

---

### TS-41-E8: Pipeline Unavailable Fallback

**Requirement:** 41-REQ-5.E2
**Type:** unit
**Description:** Verify None returned when assessment pipeline is None.

**Preconditions:**
- Orchestrator with `_routing.pipeline = None`.

**Expected:**
- `_compute_duration_hints()` returns None.

**Assertion pseudocode:**
```
orchestrator._routing.pipeline = None
result = orchestrator._compute_duration_hints()
ASSERT result is None
```

---

## Property Tests

### TS-41-P1: Ordering Preserves Set Membership

**Correctness Property:** CP-3
**Type:** property (Hypothesis)
**Description:** `order_by_duration()` output contains exactly the same
elements as the input.

**Strategy:**
- Generate lists of unique strings (1-20 elements).
- Generate partial duration hints dicts.

**Property:**
```
set(order_by_duration(node_ids, hints)) == set(node_ids)
len(order_by_duration(node_ids, hints)) == len(node_ids)
```

---

### TS-41-P2: Ordering Is Deterministic

**Correctness Property:** CP-2
**Type:** property (Hypothesis)
**Description:** Same inputs always produce same output.

**Strategy:**
- Generate lists of unique strings and duration hints.

**Property:**
```
order_by_duration(ids, hints) == order_by_duration(ids, hints)
```

---

### TS-41-P3: Ordering Is Descending

**Correctness Property:** CP-1
**Type:** property (Hypothesis)
**Description:** For all consecutive pairs in the output that both have hints,
the first has duration >= the second.

**Strategy:**
- Generate lists of unique strings all with duration hints.

**Property:**
```
result = order_by_duration(ids, hints)
for i in range(len(result) - 1):
    if result[i] in hints and result[i+1] in hints:
        ASSERT hints[result[i]] >= hints[result[i+1]]
```

---

### TS-41-P4: Duration Predictions Are Positive

**Correctness Property:** CP-4
**Type:** property (Hypothesis)
**Description:** `DurationHint.predicted_ms` is always >= 1, regardless of
source.

**Strategy:**
- Generate various archetype, tier, spec_name combinations.
- Use an in-memory DuckDB with varying amounts of data.

**Property:**
```
hint = get_duration_hint(conn, node_id, spec, arch, tier, ...)
ASSERT hint.predicted_ms >= 1
```

---

### TS-41-P5: Preset Coverage

**Correctness Property:** CP-6
**Type:** property (unit-like)
**Description:** Every archetype has entries for all three tiers.

**Property:**
```
for arch in ["coder", "skeptic", "oracle", "verifier", "librarian", "cartographer"]:
    for tier in ["STANDARD", "ADVANCED", "MAX"]:
        ASSERT DURATION_PRESETS[arch][tier] > 0
```

---

### TS-41-P6: Feature Vector Array Length

**Type:** property (Hypothesis)
**Description:** `_feature_vector_to_array()` always returns a list of
exactly 5 floats or None.

**Strategy:**
- Generate dicts with subset of expected keys plus random extras.

**Property:**
```
result = _feature_vector_to_array(json.dumps(fv_dict))
ASSERT result is None or (isinstance(result, list) and len(result) == 5)
```
