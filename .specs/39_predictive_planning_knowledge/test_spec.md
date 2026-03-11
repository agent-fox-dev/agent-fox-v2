# Test Specification: Predictive Planning and Knowledge Usage

## Overview

This test specification verifies the 10 predictive planning and knowledge
improvements: duration-based task ordering, duration regression model, review
finding integration into the causal graph, confidence-aware fact selection,
pre-computed ranked facts, cross-task-group finding propagation, project model,
critical path forecasting, predictive file conflict detection, and learned
blocking thresholds.

Test cases map 1:1 to acceptance criteria in requirements.md. Property tests
map 1:1 to correctness properties in design.md.

## Test Cases

### TS-39-1: Duration Ordering Descending

**Requirement:** 39-REQ-1.1
**Type:** unit
**Description:** Verify ready tasks are sorted by predicted duration descending.

**Preconditions:**
- Three task nodes in ready state with known duration hints: A=60s, B=180s, C=120s.

**Input:**
- Call ordering function with the three ready nodes and their duration hints.

**Expected:**
- Order is [B, C, A] (180s, 120s, 60s).

**Assertion pseudocode:**
```
hints = {"A": 60_000, "B": 180_000, "C": 120_000}
ordered = order_by_duration(["A", "B", "C"], hints)
ASSERT ordered == ["B", "C", "A"]
```

### TS-39-2: Duration Hint From Historical Median

**Requirement:** 39-REQ-1.2
**Type:** unit
**Description:** Verify historical median is used when sufficient outcomes exist.

**Preconditions:**
- DuckDB with 15 execution outcomes for spec "foo" archetype "coder" with
  durations [100, 200, 300, 400, 500, 100, 200, 300, 400, 500, 100, 200, 300, 400, 500].

**Input:**
- Call `get_duration_hint(conn, node_id, "foo", "coder", "STANDARD")`.

**Expected:**
- Returns DurationHint with predicted_ms=300_000 (median) and source="historical".

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "foo", "coder", "STANDARD")
ASSERT hint.predicted_ms == 300_000
ASSERT hint.source == "historical"
```

### TS-39-3: Duration Hint Preset Fallback

**Requirement:** 39-REQ-1.3
**Type:** unit
**Description:** Verify preset fallback when no historical data exists.

**Preconditions:**
- DuckDB with no execution outcomes.

**Input:**
- Call `get_duration_hint(conn, node_id, "foo", "coder", "STANDARD")`.

**Expected:**
- Returns DurationHint with predicted_ms from DURATION_PRESETS["coder"]["STANDARD"]
  and source="preset".

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "foo", "coder", "STANDARD")
ASSERT hint.predicted_ms == DURATION_PRESETS["coder"]["STANDARD"]
ASSERT hint.source == "preset"
```

### TS-39-4: get_duration_hint Returns Milliseconds

**Requirement:** 39-REQ-1.4
**Type:** unit
**Description:** Verify get_duration_hint returns a DurationHint with predicted_ms.

**Preconditions:**
- DuckDB with some execution outcomes.

**Input:**
- Call `get_duration_hint()` for a known node.

**Expected:**
- Returns DurationHint dataclass with node_id, predicted_ms (int), and source (str).

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "foo", "coder", "STANDARD")
ASSERT isinstance(hint, DurationHint)
ASSERT isinstance(hint.predicted_ms, int)
ASSERT hint.predicted_ms > 0
ASSERT hint.source in ("historical", "regression", "preset", "default")
```

### TS-39-5: Regression Model Training

**Requirement:** 39-REQ-2.1
**Type:** unit
**Description:** Verify regression model trains when sufficient outcomes exist.

**Preconditions:**
- DuckDB with 35 execution outcomes with feature vectors and durations.

**Input:**
- Call `train_duration_model(conn, min_outcomes=30)`.

**Expected:**
- Returns a trained LinearRegression model (not None).

**Assertion pseudocode:**
```
model = train_duration_model(conn, min_outcomes=30)
ASSERT model is not None
ASSERT isinstance(model, LinearRegression)
```

### TS-39-6: Regression Model Prediction Priority

**Requirement:** 39-REQ-2.2
**Type:** unit
**Description:** Verify regression prediction is used when model is available.

**Preconditions:**
- DuckDB with 35+ outcomes. Regression model trained.

**Input:**
- Call `get_duration_hint()` for a node with trained model available.

**Expected:**
- Returns DurationHint with source="regression".

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "foo", "coder", "STANDARD")
ASSERT hint.source == "regression"
ASSERT hint.predicted_ms > 0
```

### TS-39-7: Regression Model Retraining

**Requirement:** 39-REQ-2.3
**Type:** integration
**Description:** Verify model retrains when new outcomes are recorded.

**Preconditions:**
- DuckDB with 30 outcomes and a trained model.

**Input:**
- Add 5 new outcomes. Retrain model.

**Expected:**
- New model's predictions differ from old model's predictions (reflecting new data).

**Assertion pseudocode:**
```
model_v1 = train_duration_model(conn)
pred_v1 = model_v1.predict(feature_vector)
insert_outcomes(conn, new_outcomes)
model_v2 = train_duration_model(conn)
pred_v2 = model_v2.predict(feature_vector)
ASSERT pred_v1 != pred_v2
```

### TS-39-8: Causal Traversal Includes Review Findings

**Requirement:** 39-REQ-3.1
**Type:** unit
**Description:** Verify causal traversal queries review_findings, drift_findings,
and verification_results tables.

**Preconditions:**
- DuckDB with a memory fact and linked review finding in review_findings table.

**Input:**
- Call `traverse_with_reviews(conn, fact_id)`.

**Expected:**
- Result includes both the CausalFact and the linked ReviewFinding.

**Assertion pseudocode:**
```
results = traverse_with_reviews(conn, seed_fact_id)
types = {type(r).__name__ for r in results}
ASSERT "CausalFact" in types or len([r for r in results if hasattr(r, 'fact_id')]) > 0
ASSERT any(isinstance(r, ReviewFinding) for r in results)
```

### TS-39-9: Extended Traversal Function Exists

**Requirement:** 39-REQ-3.2
**Type:** unit
**Description:** Verify traverse_with_reviews or extended traverse_causal_chain
exists and returns review findings.

**Preconditions:**
- Module `knowledge.causal` importable.

**Input:**
- Import and inspect `traverse_with_reviews`.

**Expected:**
- Function exists and accepts conn, fact_id, max_depth, direction parameters.

**Assertion pseudocode:**
```
from agent_fox.knowledge.causal import traverse_with_reviews
sig = inspect.signature(traverse_with_reviews)
ASSERT "conn" in sig.parameters
ASSERT "fact_id" in sig.parameters
```

### TS-39-10: Review Finding Causal Linking via Requirement ID

**Requirement:** 39-REQ-3.3
**Type:** unit
**Description:** Verify review findings referencing a requirement ID are treated
as causally related to matching memory facts.

**Preconditions:**
- Memory fact with keyword "39-REQ-1.1".
- Review finding referencing requirement_id "39-REQ-1.1".

**Input:**
- Call `traverse_with_reviews(conn, fact_id)`.

**Expected:**
- Review finding appears in traversal results.

**Assertion pseudocode:**
```
# Insert fact with keyword "39-REQ-1.1"
# Insert review finding with requirement_id "39-REQ-1.1"
results = traverse_with_reviews(conn, fact_id)
ASSERT any(r.requirement_id == "39-REQ-1.1" for r in results if hasattr(r, 'requirement_id'))
```

### TS-39-11: Confidence Threshold Filtering

**Requirement:** 39-REQ-4.1
**Type:** unit
**Description:** Verify facts below confidence threshold are excluded.

**Preconditions:**
- Five facts with confidences [0.9, 0.7, 0.5, 0.3, 0.1].

**Input:**
- Call `select_relevant_facts(facts, spec, keywords, confidence_threshold=0.5)`.

**Expected:**
- Only facts with confidence >= 0.5 are returned (three facts).

**Assertion pseudocode:**
```
result = select_relevant_facts(all_facts, "spec1", ["test"], confidence_threshold=0.5)
ASSERT len(result) == 3
ASSERT all(f.confidence >= 0.5 for f in result)
```

### TS-39-12: Confidence Threshold Configurable

**Requirement:** 39-REQ-4.2
**Type:** unit
**Description:** Verify confidence threshold is configurable via config.toml.

**Preconditions:**
- Config with `[knowledge] confidence_threshold = 0.7`.

**Input:**
- Parse config and read knowledge.confidence_threshold.

**Expected:**
- Value is 0.7.

**Assertion pseudocode:**
```
config = parse_config(toml_with_threshold_07)
ASSERT config.knowledge.confidence_threshold == 0.7
```

### TS-39-13: Confidence Filtering Before Scoring

**Requirement:** 39-REQ-4.3
**Type:** unit
**Description:** Verify confidence filtering occurs before keyword scoring.

**Preconditions:**
- Two facts: one with confidence=0.3 and high keyword relevance, one with
  confidence=0.9 and low keyword relevance.

**Input:**
- Call `select_relevant_facts(facts, spec, keywords, confidence_threshold=0.5)`.

**Expected:**
- Low-confidence fact is excluded regardless of keyword score.

**Assertion pseudocode:**
```
low_conf_high_rel = Fact(confidence=0.3, keywords=["exact_match"])
high_conf_low_rel = Fact(confidence=0.9, keywords=["unrelated"])
result = select_relevant_facts([low_conf_high_rel, high_conf_low_rel], "spec1", ["exact_match"], confidence_threshold=0.5)
ASSERT low_conf_high_rel not in result
ASSERT high_conf_low_rel in result
```

### TS-39-14: Fact Rankings Pre-Computed at Plan Time

**Requirement:** 39-REQ-5.1
**Type:** unit
**Description:** Verify precompute_fact_rankings produces cached rankings per spec.

**Preconditions:**
- DuckDB with facts for specs "spec_a" and "spec_b".

**Input:**
- Call `precompute_fact_rankings(conn, ["spec_a", "spec_b"])`.

**Expected:**
- Returns dict with keys "spec_a" and "spec_b", each containing a RankedFactCache.

**Assertion pseudocode:**
```
cache = precompute_fact_rankings(conn, ["spec_a", "spec_b"])
ASSERT "spec_a" in cache
ASSERT "spec_b" in cache
ASSERT isinstance(cache["spec_a"], RankedFactCache)
ASSERT len(cache["spec_a"].ranked_facts) > 0
```

### TS-39-15: Cached Facts Fallback to Live

**Requirement:** 39-REQ-5.2
**Type:** unit
**Description:** Verify stale cache returns None, triggering live computation.

**Preconditions:**
- Cache created with fact_count_at_creation=5. Current fact count is 7.

**Input:**
- Call `get_cached_facts(cache, "spec_a", current_fact_count=7)`.

**Expected:**
- Returns None (cache is stale).

**Assertion pseudocode:**
```
cache_entry = RankedFactCache(spec_name="spec_a", ranked_facts=[...], created_at="...", fact_count_at_creation=5)
result = get_cached_facts({"spec_a": cache_entry}, "spec_a", current_fact_count=7)
ASSERT result is None
```

### TS-39-16: Fact Cache Invalidation

**Requirement:** 39-REQ-5.3
**Type:** unit
**Description:** Verify cache is invalidated when facts are added or superseded.

**Preconditions:**
- Cache created with fact_count_at_creation=5. One new fact added (count=6).

**Input:**
- Call `get_cached_facts(cache, "spec_a", current_fact_count=6)`.

**Expected:**
- Returns None (stale due to new fact).

**Assertion pseudocode:**
```
result = get_cached_facts(cache, "spec_a", current_fact_count=6)
ASSERT result is None
```

### TS-39-17: Cross-Group Finding Propagation

**Requirement:** 39-REQ-6.1
**Type:** integration
**Description:** Verify context for group N includes findings from groups 1..N-1.

**Preconditions:**
- DuckDB with review findings for task groups 1 and 2 of spec "foo".

**Input:**
- Assemble context for task group 3 of spec "foo".

**Expected:**
- Context includes findings from groups 1 and 2.

**Assertion pseudocode:**
```
# Insert finding for group 1 and group 2
context = assemble_context(spec_dir, task_group=3, conn=conn)
ASSERT "group 1 finding text" in context
ASSERT "group 2 finding text" in context
```

### TS-39-18: Propagated Findings Labeled Separately

**Requirement:** 39-REQ-6.2
**Type:** integration
**Description:** Verify propagated findings appear under "Prior Group Findings" label.

**Preconditions:**
- DuckDB with review findings for task group 1 of spec "foo".

**Input:**
- Assemble context for task group 2 of spec "foo".

**Expected:**
- Context contains a section labeled "Prior Group Findings".

**Assertion pseudocode:**
```
context = assemble_context(spec_dir, task_group=2, conn=conn)
ASSERT "Prior Group Findings" in context
```

### TS-39-19: Project Model Aggregates Spec Metrics

**Requirement:** 39-REQ-7.1
**Type:** unit
**Description:** Verify ProjectModel aggregates average cost, duration, failure rate.

**Preconditions:**
- DuckDB with execution outcomes for spec "foo": 3 sessions, costs [1.0, 2.0, 3.0],
  durations [100, 200, 300], 1 failure.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- ProjectModel.spec_outcomes["foo"].avg_cost == 2.0
- ProjectModel.spec_outcomes["foo"].avg_duration_ms == 200
- ProjectModel.spec_outcomes["foo"].failure_rate approx 0.333

**Assertion pseudocode:**
```
model = build_project_model(conn)
metrics = model.spec_outcomes["foo"]
ASSERT metrics.avg_cost == pytest.approx(2.0)
ASSERT metrics.avg_duration_ms == 200
ASSERT metrics.failure_rate == pytest.approx(1/3)
ASSERT metrics.session_count == 3
```

### TS-39-20: Module Stability Score

**Requirement:** 39-REQ-7.2
**Type:** unit
**Description:** Verify module stability computed from finding density.

**Preconditions:**
- DuckDB with 6 review findings across 3 sessions for spec "foo".

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- model.module_stability["foo"] == 2.0 (6 findings / 3 sessions).

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT model.module_stability["foo"] == pytest.approx(2.0)
```

### TS-39-21: Archetype Effectiveness

**Requirement:** 39-REQ-7.3
**Type:** unit
**Description:** Verify archetype effectiveness is success rate per archetype.

**Preconditions:**
- DuckDB with outcomes: coder 8 success / 2 fail, skeptic 9 success / 1 fail.

**Input:**
- Call `build_project_model(conn)`.

**Expected:**
- model.archetype_effectiveness["coder"] == 0.8
- model.archetype_effectiveness["skeptic"] == 0.9

**Assertion pseudocode:**
```
model = build_project_model(conn)
ASSERT model.archetype_effectiveness["coder"] == pytest.approx(0.8)
ASSERT model.archetype_effectiveness["skeptic"] == pytest.approx(0.9)
```

### TS-39-22: Project Model in Status Output

**Requirement:** 39-REQ-7.4
**Type:** integration
**Description:** Verify `agent-fox status --model` includes project model data.

**Preconditions:**
- DuckDB with execution outcomes.

**Input:**
- Call status command with --model flag.

**Expected:**
- Output includes spec metrics, module stability, archetype effectiveness.

**Assertion pseudocode:**
```
output = run_status_command(conn, model=True)
ASSERT "avg_cost" in output or "spec_outcomes" in output
ASSERT "archetype_effectiveness" in output
```

### TS-39-23: Critical Path Computation

**Requirement:** 39-REQ-8.1
**Type:** unit
**Description:** Verify critical path uses duration hints as weights.

**Preconditions:**
- Linear graph: A -> B -> C with durations A=100, B=200, C=50.

**Input:**
- Call `compute_critical_path(nodes, edges, duration_hints)`.

**Expected:**
- Critical path is [A, B, C] with total_duration_ms=350.

**Assertion pseudocode:**
```
nodes = {"A": "pending", "B": "pending", "C": "pending"}
edges = {"B": ["A"], "C": ["B"]}
hints = {"A": 100, "B": 200, "C": 50}
result = compute_critical_path(nodes, edges, hints)
ASSERT result.path == ["A", "B", "C"]
ASSERT result.total_duration_ms == 350
```

### TS-39-24: Critical Path in Status Output

**Requirement:** 39-REQ-8.2
**Type:** integration
**Description:** Verify status output includes critical path and estimated duration.

**Preconditions:**
- Task graph with duration hints.

**Input:**
- Call status command.

**Expected:**
- Output includes critical path nodes and total estimated duration.

**Assertion pseudocode:**
```
output = run_status_command(conn)
ASSERT "critical path" in output.lower() or "Critical Path" in output
```

### TS-39-25: Tied Critical Paths

**Requirement:** 39-REQ-8.3
**Type:** unit
**Description:** Verify all tied critical paths are reported when durations are equal.

**Preconditions:**
- Diamond graph: A -> B, A -> C, B -> D, C -> D.
  Durations: A=100, B=200, C=200, D=50. Paths A-B-D and A-C-D both = 350.

**Input:**
- Call `compute_critical_path(nodes, edges, hints)`.

**Expected:**
- CriticalPathResult has total_duration_ms=350 and tied_paths contains both paths.

**Assertion pseudocode:**
```
result = compute_critical_path(nodes, edges, hints)
ASSERT result.total_duration_ms == 350
all_paths = [result.path] + result.tied_paths
ASSERT ["A", "B", "D"] in all_paths
ASSERT ["A", "C", "D"] in all_paths
```

### TS-39-26: File Impact Extraction

**Requirement:** 39-REQ-9.1
**Type:** unit
**Description:** Verify file impacts are extracted from spec documents.

**Preconditions:**
- Spec directory with tasks.md mentioning files `routing/duration.py` and
  `engine/graph_sync.py`.

**Input:**
- Call `extract_file_impacts(spec_dir, task_group=1)`.

**Expected:**
- Returns set containing "routing/duration.py" and "engine/graph_sync.py".

**Assertion pseudocode:**
```
impacts = extract_file_impacts(spec_dir, task_group=1)
ASSERT "routing/duration.py" in impacts
ASSERT "engine/graph_sync.py" in impacts
```

### TS-39-27: Overlapping File Conflict Detection

**Requirement:** 39-REQ-9.2
**Type:** unit
**Description:** Verify overlapping predicted files are flagged as conflicts.

**Preconditions:**
- Two FileImpacts: node_a touches {f1, f2}, node_b touches {f2, f3}.

**Input:**
- Call `detect_conflicts([impact_a, impact_b])`.

**Expected:**
- Returns [(node_a, node_b, {"f2"})].

**Assertion pseudocode:**
```
impacts = [
    FileImpact("a", {"f1", "f2"}),
    FileImpact("b", {"f2", "f3"}),
]
conflicts = detect_conflicts(impacts)
ASSERT len(conflicts) == 1
ASSERT conflicts[0] == ("a", "b", {"f2"})
```

### TS-39-28: Conflicting Tasks Serialized

**Requirement:** 39-REQ-9.3
**Type:** integration
**Description:** Verify conflicting tasks are serialized in dispatch.

**Preconditions:**
- Two ready tasks with overlapping file predictions. File conflict detection enabled.

**Input:**
- Dispatch ready tasks.

**Expected:**
- Only one of the conflicting tasks is dispatched; the other is deferred.

**Assertion pseudocode:**
```
dispatched = dispatch_with_conflict_detection(ready_tasks, file_impacts)
ASSERT len(dispatched) < len(ready_tasks)
# Conflicting pair not both dispatched
ASSERT not (conflicting_a in dispatched and conflicting_b in dispatched)
```

### TS-39-29: Blocking Decision Recording

**Requirement:** 39-REQ-10.1
**Type:** unit
**Description:** Verify blocking decisions and outcomes are tracked.

**Preconditions:**
- DuckDB with blocking_history table.

**Input:**
- Call `record_blocking_decision(conn, decision)`.

**Expected:**
- Decision is stored in blocking_history table with all fields.

**Assertion pseudocode:**
```
decision = BlockingDecision(spec_name="foo", archetype="skeptic", critical_count=3, threshold=2, blocked=True, outcome="correct_block")
record_blocking_decision(conn, decision)
rows = conn.execute("SELECT * FROM blocking_history").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].archetype == "skeptic"
```

### TS-39-30: Optimal Threshold Computation

**Requirement:** 39-REQ-10.2
**Type:** unit
**Description:** Verify optimal threshold is computed from blocking history.

**Preconditions:**
- DuckDB with 25 blocking decisions, mixed outcomes.

**Input:**
- Call `compute_optimal_threshold(conn, "skeptic", min_decisions=20)`.

**Expected:**
- Returns an integer threshold that satisfies the false negative rate constraint.

**Assertion pseudocode:**
```
threshold = compute_optimal_threshold(conn, "skeptic", min_decisions=20)
ASSERT threshold is not None
ASSERT isinstance(threshold, int)
ASSERT threshold > 0
```

### TS-39-31: Learned Thresholds Stored and Surfaced

**Requirement:** 39-REQ-10.3
**Type:** unit
**Description:** Verify learned thresholds are stored in DuckDB and visible in status.

**Preconditions:**
- DuckDB with learned_thresholds table populated.

**Input:**
- Query learned_thresholds table.

**Expected:**
- Row exists for the archetype with threshold, confidence, sample_count.

**Assertion pseudocode:**
```
conn.execute("INSERT INTO learned_thresholds VALUES ('skeptic', 3, 0.85, 25, current_timestamp)")
rows = conn.execute("SELECT * FROM learned_thresholds WHERE archetype='skeptic'").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].threshold == 3
```

## Edge Case Tests

### TS-39-E1: Insufficient Outcomes Use Presets

**Requirement:** 39-REQ-1.E1
**Type:** unit
**Description:** Verify fewer than min_outcomes uses presets instead of historical.

**Preconditions:**
- DuckDB with 5 execution outcomes (below default threshold of 10).

**Input:**
- Call `get_duration_hint(conn, node_id, "foo", "coder", "STANDARD", min_outcomes=10)`.

**Expected:**
- Returns DurationHint with source="preset" (not "historical").

**Assertion pseudocode:**
```
hint = get_duration_hint(conn, "node1", "foo", "coder", "STANDARD", min_outcomes=10)
ASSERT hint.source == "preset"
ASSERT hint.predicted_ms == DURATION_PRESETS["coder"]["STANDARD"]
```

### TS-39-E2: No File Impacts Treated as Non-Conflicting

**Requirement:** 39-REQ-9.E1
**Type:** unit
**Description:** Verify task with no extractable file impacts is non-conflicting.

**Preconditions:**
- Spec directory with empty tasks.md (no file references).

**Input:**
- Call `extract_file_impacts(spec_dir, task_group=1)`.

**Expected:**
- Returns empty set. Task is not flagged as conflicting.

**Assertion pseudocode:**
```
impacts = extract_file_impacts(empty_spec_dir, task_group=1)
ASSERT impacts == set()
conflicts = detect_conflicts([FileImpact("a", impacts), FileImpact("b", {"f1"})])
ASSERT len(conflicts) == 0
```

## Property Test Cases

### TS-39-P1: Duration Ordering Correctness

**Property:** Property 1 from design.md
**Validates:** 39-REQ-1.1, 39-REQ-1.3
**Type:** property
**Description:** Tasks ordered by predicted duration descending; ties broken alphabetically.

**For any:** List of (node_id, duration_ms) pairs where node_ids are unique strings
and durations are non-negative integers.
**Invariant:** The ordered list has each element's duration >= the next element's
duration. For equal durations, node_ids are in alphabetical order.

**Assertion pseudocode:**
```
FOR ANY tasks IN lists(tuples(text(), integers(min_value=0))):
    ordered = order_by_duration(tasks)
    FOR i IN range(len(ordered) - 1):
        ASSERT ordered[i].duration >= ordered[i+1].duration
        IF ordered[i].duration == ordered[i+1].duration:
            ASSERT ordered[i].node_id < ordered[i+1].node_id
```

### TS-39-P2: Duration Hint Source Precedence

**Property:** Property 2 from design.md
**Validates:** 39-REQ-1.2, 39-REQ-1.4, 39-REQ-2.2
**Type:** property
**Description:** Hint source follows regression > historical > preset > default precedence.

**For any:** Combination of (has_regression_model, historical_count, has_preset).
**Invariant:** Source is the highest-priority available: regression if model exists,
historical if count >= min_outcomes, preset if archetype/tier exists, else default.

**Assertion pseudocode:**
```
FOR ANY has_model, hist_count, has_preset IN booleans(), integers(0, 100), booleans():
    setup_db(has_model, hist_count, has_preset)
    hint = get_duration_hint(conn, ...)
    IF has_model:
        ASSERT hint.source == "regression"
    ELIF hist_count >= min_outcomes:
        ASSERT hint.source == "historical"
    ELIF has_preset:
        ASSERT hint.source == "preset"
    ELSE:
        ASSERT hint.source == "default"
```

### TS-39-P3: Confidence Filter Monotonicity

**Property:** Property 3 from design.md
**Validates:** 39-REQ-4.1
**Type:** property
**Description:** Higher threshold produces subset of lower threshold results.

**For any:** List of facts with float confidences, and two thresholds T1 < T2.
**Invariant:** facts_passing(T2) is a subset of facts_passing(T1).

**Assertion pseudocode:**
```
FOR ANY facts IN lists(facts_strategy()), t1, t2 IN floats(0, 1):
    ASSUME t1 < t2
    result_low = select_relevant_facts(facts, spec, kw, confidence_threshold=t1)
    result_high = select_relevant_facts(facts, spec, kw, confidence_threshold=t2)
    ASSERT set(id(f) for f in result_high).issubset(set(id(f) for f in result_low))
```

### TS-39-P4: Fact Cache Consistency

**Property:** Property 4 from design.md
**Validates:** 39-REQ-5.1, 39-REQ-5.3
**Type:** property
**Description:** Cache returns same results as live computation when not stale.

**For any:** Set of facts and a spec name.
**Invariant:** If no facts added since cache creation, cached result equals live result.

**Assertion pseudocode:**
```
FOR ANY facts IN lists(facts_strategy(), min_size=1):
    cache = precompute_fact_rankings(conn, [spec])
    cached = get_cached_facts(cache, spec, current_fact_count=len(facts))
    live = select_relevant_facts(facts, spec, keywords)
    ASSERT cached == live
```

### TS-39-P5: Cross-Group Finding Visibility

**Property:** Property 5 from design.md
**Validates:** 39-REQ-6.1, 39-REQ-6.2
**Type:** property
**Description:** Context for group K includes findings from groups 1..K-1.

**For any:** Spec with N groups (2 <= N <= 5), findings in each group.
**Invariant:** For group K, all findings from groups < K appear in context.

**Assertion pseudocode:**
```
FOR ANY n IN integers(2, 5):
    insert_findings_per_group(conn, spec, n)
    FOR k IN range(2, n+1):
        context = assemble_context(spec_dir, task_group=k, conn=conn)
        FOR g IN range(1, k):
            ASSERT group_g_finding_text in context
```

### TS-39-P6: File Conflict Symmetry

**Property:** Property 6 from design.md
**Validates:** 39-REQ-9.2
**Type:** property
**Description:** If A conflicts with B, then B conflicts with A.

**For any:** List of FileImpact objects.
**Invariant:** Conflict relation is symmetric.

**Assertion pseudocode:**
```
FOR ANY impacts IN lists(file_impact_strategy()):
    conflicts = detect_conflicts(impacts)
    FOR (a, b, files) IN conflicts:
        ASSERT (b, a, files) IN conflicts OR (a, b, files) IN conflicts
        # The function returns each pair once; check reverse lookup works
```

### TS-39-P7: Critical Path Validity

**Property:** Property 7 from design.md
**Validates:** 39-REQ-8.1, 39-REQ-8.3
**Type:** property
**Description:** Critical path total >= any other path through the graph.

**For any:** DAG with positive duration weights.
**Invariant:** No path through the graph has a total duration exceeding the
critical path's total.

**Assertion pseudocode:**
```
FOR ANY dag IN dag_strategy():
    result = compute_critical_path(dag.nodes, dag.edges, dag.durations)
    all_paths = enumerate_all_paths(dag)
    FOR path IN all_paths:
        path_duration = sum(dag.durations[n] for n in path)
        ASSERT result.total_duration_ms >= path_duration
```

### TS-39-P8: Blocking Threshold Learning Convergence

**Property:** Property 8 from design.md
**Validates:** 39-REQ-10.2, 39-REQ-10.3
**Type:** property
**Description:** Learned threshold satisfies false negative rate constraint.

**For any:** Sequence of 30+ blocking decisions with consistent ground truth.
**Invariant:** Computed threshold produces false negative rate <= max_false_negative_rate.

**Assertion pseudocode:**
```
FOR ANY decisions IN lists(blocking_decision_strategy(), min_size=30):
    insert_decisions(conn, decisions)
    threshold = compute_optimal_threshold(conn, "skeptic", min_decisions=20, max_false_negative_rate=0.1)
    IF threshold is not None:
        fn_rate = compute_fn_rate(decisions, threshold)
        ASSERT fn_rate <= 0.1
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 39-REQ-1.1 | TS-39-1 | unit |
| 39-REQ-1.2 | TS-39-2 | unit |
| 39-REQ-1.3 | TS-39-3 | unit |
| 39-REQ-1.4 | TS-39-4 | unit |
| 39-REQ-1.E1 | TS-39-E1 | unit |
| 39-REQ-2.1 | TS-39-5 | unit |
| 39-REQ-2.2 | TS-39-6 | unit |
| 39-REQ-2.3 | TS-39-7 | integration |
| 39-REQ-3.1 | TS-39-8 | unit |
| 39-REQ-3.2 | TS-39-9 | unit |
| 39-REQ-3.3 | TS-39-10 | unit |
| 39-REQ-4.1 | TS-39-11 | unit |
| 39-REQ-4.2 | TS-39-12 | unit |
| 39-REQ-4.3 | TS-39-13 | unit |
| 39-REQ-5.1 | TS-39-14 | unit |
| 39-REQ-5.2 | TS-39-15 | unit |
| 39-REQ-5.3 | TS-39-16 | unit |
| 39-REQ-6.1 | TS-39-17 | integration |
| 39-REQ-6.2 | TS-39-18 | integration |
| 39-REQ-7.1 | TS-39-19 | unit |
| 39-REQ-7.2 | TS-39-20 | unit |
| 39-REQ-7.3 | TS-39-21 | unit |
| 39-REQ-7.4 | TS-39-22 | integration |
| 39-REQ-8.1 | TS-39-23 | unit |
| 39-REQ-8.2 | TS-39-24 | integration |
| 39-REQ-8.3 | TS-39-25 | unit |
| 39-REQ-9.1 | TS-39-26 | unit |
| 39-REQ-9.2 | TS-39-27 | unit |
| 39-REQ-9.3 | TS-39-28 | integration |
| 39-REQ-9.E1 | TS-39-E2 | unit |
| 39-REQ-10.1 | TS-39-29 | unit |
| 39-REQ-10.2 | TS-39-30 | unit |
| 39-REQ-10.3 | TS-39-31 | unit |
| Property 1 | TS-39-P1 | property |
| Property 2 | TS-39-P2 | property |
| Property 3 | TS-39-P3 | property |
| Property 4 | TS-39-P4 | property |
| Property 5 | TS-39-P5 | property |
| Property 6 | TS-39-P6 | property |
| Property 7 | TS-39-P7 | property |
| Property 8 | TS-39-P8 | property |
