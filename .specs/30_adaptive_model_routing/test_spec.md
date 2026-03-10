# Test Specification: Adaptive Model Routing

## Overview

Tests are organized into three categories: acceptance criterion tests (one per
requirement criterion), property tests (one per design correctness property),
and edge case tests. All tests use pytest with Hypothesis for property-based
tests. Integration tests use a real DuckDB in-memory instance.

## Test Cases

### TS-30-1: Feature Vector Extraction

**Requirement:** 30-REQ-1.2
**Type:** unit
**Description:** Verify feature extraction produces correct values from spec content.

**Preconditions:**
- A temp directory with a `tasks.md` containing 4 subtasks and a `requirements.md`
  with 2 edge cases, 1 property test reference, and 150 words.
- A `design.md` referencing 2 dependencies.

**Input:**
- `spec_dir = <temp_dir>`, `task_group = 2`, `archetype = "coder"`

**Expected:**
- `FeatureVector(subtask_count=4, spec_word_count=150, has_property_tests=True, edge_case_count=2, dependency_count=2, archetype="coder")`

**Assertion pseudocode:**
```
result = extract_features(spec_dir, task_group=2, archetype="coder")
ASSERT result.subtask_count == 4
ASSERT result.spec_word_count == 150
ASSERT result.has_property_tests == True
ASSERT result.edge_case_count == 2
ASSERT result.dependency_count == 2
ASSERT result.archetype == "coder"
```

---

### TS-30-2: Complexity Assessment Production

**Requirement:** 30-REQ-1.1
**Type:** unit
**Description:** Verify assessment pipeline produces a complete assessment with all required fields.

**Preconditions:**
- Assessment pipeline initialized with default config and no DB (heuristic mode).
- Spec directory with valid content.

**Input:**
- `node_id = "test_spec:2"`, `spec_name = "test_spec"`, `task_group = 2`,
  `archetype = "coder"`, `tier_ceiling = ADVANCED`

**Expected:**
- A ComplexityAssessment with all fields populated: non-empty id, correct node_id,
  predicted_tier in {SIMPLE, STANDARD, ADVANCED}, confidence in [0.0, 1.0],
  assessment_method = "heuristic", non-null feature_vector, tier_ceiling = ADVANCED.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=default_config, db=None)
result = await pipeline.assess(node_id, spec_name, 2, spec_dir, "coder", ADVANCED)
ASSERT result.id is not None
ASSERT result.node_id == "test_spec:2"
ASSERT result.predicted_tier in [SIMPLE, STANDARD, ADVANCED]
ASSERT 0.0 <= result.confidence <= 1.0
ASSERT result.assessment_method == "heuristic"
ASSERT result.feature_vector is not None
ASSERT result.tier_ceiling == ADVANCED
```

---

### TS-30-3: Heuristic-Only Assessment on Zero History

**Requirement:** 30-REQ-1.3
**Type:** unit
**Description:** Verify heuristic-only assessment when no historical data exists.

**Preconditions:**
- Empty DuckDB database (no execution outcomes).
- Training threshold = 20.

**Input:**
- Valid spec directory and task group.

**Expected:**
- Assessment method is "heuristic".

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=RoutingConfig(training_threshold=20), db=empty_db)
result = await pipeline.assess(node_id, spec_name, 1, spec_dir, "coder", ADVANCED)
ASSERT result.assessment_method == "heuristic"
```

---

### TS-30-4: Statistical Model Preferred When Accurate

**Requirement:** 30-REQ-1.4
**Type:** integration
**Description:** Verify statistical model is preferred when its accuracy exceeds threshold.

**Preconditions:**
- DuckDB with 30 execution outcomes with consistent tier mappings.
- Trained statistical model with accuracy > 0.75.

**Input:**
- Valid spec directory and task group.

**Expected:**
- Assessment method is "statistical".

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=RoutingConfig(training_threshold=20, accuracy_threshold=0.75), db=populated_db)
result = await pipeline.assess(node_id, spec_name, 1, spec_dir, "coder", ADVANCED)
ASSERT result.assessment_method == "statistical"
```

---

### TS-30-5: Hybrid Assessment When Statistical Below Threshold

**Requirement:** 30-REQ-1.5
**Type:** integration
**Description:** Verify hybrid mode when statistical accuracy is below threshold but data exists.

**Preconditions:**
- DuckDB with 25 execution outcomes with inconsistent tier mappings
  (noisy data producing accuracy < 0.75).
- Training threshold = 20.

**Input:**
- Valid spec directory and task group.

**Expected:**
- Assessment method is "hybrid".

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=RoutingConfig(training_threshold=20, accuracy_threshold=0.75), db=noisy_db)
result = await pipeline.assess(node_id, spec_name, 1, spec_dir, "coder", ADVANCED)
ASSERT result.assessment_method == "hybrid"
```

---

### TS-30-6: Assessment Persisted to DuckDB

**Requirement:** 30-REQ-1.6
**Type:** integration
**Description:** Verify complexity assessment is written to DuckDB before execution.

**Preconditions:**
- DuckDB with `complexity_assessments` table.

**Input:**
- Run assessment pipeline with valid inputs.

**Expected:**
- One row in `complexity_assessments` with matching node_id and predicted_tier.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=default_config, db=test_db)
assessment = await pipeline.assess(node_id, spec_name, 1, spec_dir, "coder", ADVANCED)
rows = test_db.execute("SELECT * FROM complexity_assessments WHERE id = ?", [assessment.id]).fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].node_id == node_id
```

---

### TS-30-7: Same-Tier Retry on First Failure

**Requirement:** 30-REQ-2.1
**Type:** unit
**Description:** Verify escalation ladder retries at same tier before escalating.

**Preconditions:**
- EscalationLadder initialized with starting_tier=SIMPLE, ceiling=ADVANCED,
  retries_before_escalation=1.

**Input:**
- Record one failure.

**Expected:**
- `should_retry()` returns True.
- `current_tier` is still SIMPLE.
- `attempt_count` is 2.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, ADVANCED, retries_before_escalation=1)
ASSERT ladder.current_tier == SIMPLE
ladder.record_failure()
ASSERT ladder.should_retry() == True
ASSERT ladder.current_tier == SIMPLE
ASSERT ladder.attempt_count == 2
```

---

### TS-30-8: Escalation to Next Tier After Retries Exhausted

**Requirement:** 30-REQ-2.2
**Type:** unit
**Description:** Verify escalation to next tier after all same-tier retries exhausted.

**Preconditions:**
- EscalationLadder with starting_tier=SIMPLE, ceiling=ADVANCED,
  retries_before_escalation=1.

**Input:**
- Record two failures (initial attempt + 1 retry).

**Expected:**
- After second failure, `current_tier` escalates to STANDARD.
- `escalation_count` is 1.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, ADVANCED, retries_before_escalation=1)
ladder.record_failure()  # retry at SIMPLE
ladder.record_failure()  # exhausted SIMPLE, escalate
ASSERT ladder.current_tier == STANDARD
ASSERT ladder.escalation_count == 1
ASSERT ladder.should_retry() == True
```

---

### TS-30-9: Exhaustion at Highest Tier

**Requirement:** 30-REQ-2.3
**Type:** unit
**Description:** Verify ladder is exhausted when highest tier retries are used up.

**Preconditions:**
- EscalationLadder with starting_tier=SIMPLE, ceiling=ADVANCED,
  retries_before_escalation=1.

**Input:**
- Record 6 failures (2 per tier: SIMPLE, STANDARD, ADVANCED).

**Expected:**
- `is_exhausted` is True.
- `should_retry()` is False.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, ADVANCED, retries_before_escalation=1)
for i in range(6):
    ladder.record_failure()
ASSERT ladder.is_exhausted == True
ASSERT ladder.should_retry() == False
ASSERT ladder.attempt_count == 7  # 6 failures + 1 initial
```

---

### TS-30-10: Tier Ceiling Enforcement

**Requirement:** 30-REQ-2.4
**Type:** unit
**Description:** Verify escalation never exceeds the tier ceiling.

**Preconditions:**
- EscalationLadder with starting_tier=SIMPLE, ceiling=STANDARD,
  retries_before_escalation=1.

**Input:**
- Record 4 failures (2 at SIMPLE, 2 at STANDARD).

**Expected:**
- `is_exhausted` is True.
- `current_tier` never exceeds STANDARD.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, STANDARD, retries_before_escalation=1)
tiers_seen = [ladder.current_tier]
for i in range(4):
    ladder.record_failure()
    if ladder.should_retry():
        tiers_seen.append(ladder.current_tier)
ASSERT all(t in [SIMPLE, STANDARD] for t in tiers_seen)
ASSERT ladder.is_exhausted == True
```

---

### TS-30-11: Cost Included in Circuit Breaker

**Requirement:** 30-REQ-2.5
**Type:** integration
**Description:** Verify circuit breaker budget includes speculative overhead.

**Preconditions:**
- Orchestrator with max_cost = 0.10.
- Mock session backend that fails at SIMPLE (cost $0.04) and succeeds at
  STANDARD (cost $0.08).

**Input:**
- Execute one task group.

**Expected:**
- Cumulative cost includes both SIMPLE attempt ($0.04) and STANDARD attempt
  ($0.08) = $0.12.
- Circuit breaker triggers on next task if budget exceeded.

**Assertion pseudocode:**
```
engine = create_engine(max_cost=0.10, mock_backend)
result = await engine.run()
ASSERT result.total_cost >= 0.12
ASSERT result.circuit_breaker_triggered == True
```

---

### TS-30-12: Execution Outcome Recorded

**Requirement:** 30-REQ-3.1
**Type:** integration
**Description:** Verify execution outcome is persisted to DuckDB after completion.

**Preconditions:**
- DuckDB with both tables. Assessment already persisted.

**Input:**
- Call `record_outcome()` with known values.

**Expected:**
- One row in `execution_outcomes` with matching assessment_id, actual_tier,
  and outcome.

**Assertion pseudocode:**
```
pipeline.record_outcome(assessment, STANDARD, 5000, 0.05, 3000, 3, 1, "completed", 5)
rows = test_db.execute("SELECT * FROM execution_outcomes WHERE assessment_id = ?", [assessment.id]).fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].actual_tier == "STANDARD"
ASSERT rows[0].escalation_count == 1
ASSERT rows[0].outcome == "completed"
```

---

### TS-30-13: Outcome Linked to Assessment

**Requirement:** 30-REQ-3.2
**Type:** integration
**Description:** Verify execution outcome references its assessment via foreign key.

**Preconditions:**
- Both tables populated via the pipeline.

**Input:**
- Assess, then record outcome.

**Expected:**
- JOIN on assessment_id returns exactly one matching pair.

**Assertion pseudocode:**
```
rows = test_db.execute("""
    SELECT o.*, a.predicted_tier
    FROM execution_outcomes o
    JOIN complexity_assessments a ON o.assessment_id = a.id
    WHERE o.assessment_id = ?
""", [assessment.id]).fetchall()
ASSERT len(rows) == 1
```

---

### TS-30-14: Actual Tier Reflects Escalation

**Requirement:** 30-REQ-3.3
**Type:** unit
**Description:** Verify the recorded actual tier is the tier that succeeded (or the highest attempted).

**Preconditions:**
- EscalationLadder that escalated from SIMPLE to STANDARD.

**Input:**
- Record outcome after STANDARD succeeds.

**Expected:**
- `actual_tier` in outcome is STANDARD.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, ADVANCED, 1)
ladder.record_failure()
ladder.record_failure()  # escalate to STANDARD
ASSERT ladder.current_tier == STANDARD
# Session succeeds at STANDARD
outcome = record_outcome(assessment, actual_tier=ladder.current_tier, ...)
ASSERT outcome.actual_tier == STANDARD
```

---

### TS-30-15: Statistical Model Training Trigger

**Requirement:** 30-REQ-4.1
**Type:** integration
**Description:** Verify statistical model is trained when threshold is reached.

**Preconditions:**
- DuckDB with 19 execution outcomes. Training threshold = 20.

**Input:**
- Insert one more outcome (reaching 20).

**Expected:**
- Statistical model training is triggered.
- Model produces predictions.

**Assertion pseudocode:**
```
assessor = StatisticalAssessor(db=db_with_19_outcomes)
ASSERT assessor.is_ready(training_threshold=20) == False
insert_outcome(db, outcome_20)
ASSERT assessor.is_ready(training_threshold=20) == True
accuracy = assessor.train()
ASSERT accuracy > 0.0
tier, conf = assessor.predict(sample_features)
ASSERT tier in [SIMPLE, STANDARD, ADVANCED]
```

---

### TS-30-16: Cross-Validation Accuracy

**Requirement:** 30-REQ-4.2
**Type:** integration
**Description:** Verify cross-validation produces a valid accuracy score.

**Preconditions:**
- DuckDB with 30 execution outcomes.

**Input:**
- Train statistical model.

**Expected:**
- Accuracy is a float in [0.0, 1.0].

**Assertion pseudocode:**
```
assessor = StatisticalAssessor(db=populated_db)
accuracy = assessor.train()
ASSERT 0.0 <= accuracy <= 1.0
```

---

### TS-30-17: Statistical Model as Primary When Accurate

**Requirement:** 30-REQ-4.3
**Type:** integration
**Description:** Verify statistical model is used as primary when accuracy exceeds threshold.

**Preconditions:**
- Trained model with accuracy = 0.85. Threshold = 0.75.

**Input:**
- Run assessment.

**Expected:**
- Method is "statistical".

**Assertion pseudocode:**
```
# Covered by TS-30-4 (same scenario from pipeline perspective)
pipeline = AssessmentPipeline(config=RoutingConfig(accuracy_threshold=0.75), db=high_accuracy_db)
result = await pipeline.assess(...)
ASSERT result.assessment_method == "statistical"
```

---

### TS-30-18: Hybrid Divergence Handling

**Requirement:** 30-REQ-4.4
**Type:** integration
**Description:** Verify hybrid mode uses higher-accuracy method on divergence.

**Preconditions:**
- Statistical model predicts SIMPLE (accuracy 0.65).
- LLM predicts STANDARD.
- Historical statistical accuracy < LLM accuracy.

**Input:**
- Run assessment in hybrid mode.

**Expected:**
- Predicted tier matches the method with higher historical accuracy (LLM in
  this case: STANDARD).
- Divergence is logged.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=hybrid_config, db=divergent_db)
with capture_logs() as logs:
    result = await pipeline.assess(...)
ASSERT result.predicted_tier == STANDARD  # LLM wins
ASSERT any("divergence" in log.lower() for log in logs)
```

---

### TS-30-19: Retraining Trigger

**Requirement:** 30-REQ-4.5
**Type:** integration
**Description:** Verify retraining is triggered after N new outcomes.

**Preconditions:**
- Statistical model trained at outcome count = 30.
- Retrain interval = 10.

**Input:**
- Insert 10 new outcomes (total = 40).
- Run assessment.

**Expected:**
- Statistical model is retrained (accuracy updated).

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=RoutingConfig(retrain_interval=10), db=db)
# insert 10 outcomes after last training
for i in range(10):
    pipeline.record_outcome(...)
result = await pipeline.assess(...)
ASSERT pipeline._statistical.last_training_count == 40
```

---

### TS-30-20: Routing Config Defaults

**Requirement:** 30-REQ-5.1
**Type:** unit
**Description:** Verify default config values when [routing] is absent.

**Preconditions:**
- config.toml with no `[routing]` section.

**Input:**
- Load config.

**Expected:**
- `routing.retries_before_escalation == 1`
- `routing.training_threshold == 20`
- `routing.accuracy_threshold == 0.75`
- `routing.retrain_interval == 10`

**Assertion pseudocode:**
```
config = load_config(path_to_minimal_toml)
ASSERT config.routing.retries_before_escalation == 1
ASSERT config.routing.training_threshold == 20
ASSERT config.routing.accuracy_threshold == 0.75
ASSERT config.routing.retrain_interval == 10
```

---

### TS-30-21: Routing Config Clamping

**Requirement:** 30-REQ-5.2
**Type:** unit
**Description:** Verify out-of-range config values are clamped.

**Preconditions:**
- config.toml with `retries_before_escalation = 10`, `training_threshold = 2`.

**Input:**
- Load config.

**Expected:**
- `retries_before_escalation` clamped to 3, `training_threshold` clamped to 5.

**Assertion pseudocode:**
```
config = load_config(path_to_extreme_toml)
ASSERT config.routing.retries_before_escalation == 3
ASSERT config.routing.training_threshold == 5
```

---

### TS-30-22: Archetype Model as Ceiling

**Requirement:** 30-REQ-5.3
**Type:** unit
**Description:** Verify archetype model override acts as tier ceiling.

**Preconditions:**
- Config with `archetypes.models.coder = "STANDARD"`.

**Input:**
- Resolve tier ceiling for coder archetype.

**Expected:**
- Tier ceiling is STANDARD. Escalation ladder never exceeds STANDARD.

**Assertion pseudocode:**
```
config = load_config(path_with_coder_standard)
ceiling = resolve_tier_ceiling(config, "coder")
ASSERT ceiling == STANDARD
ladder = EscalationLadder(SIMPLE, ceiling, 1)
ladder.record_failure()
ladder.record_failure()  # escalate
ASSERT ladder.current_tier == STANDARD
ladder.record_failure()
ladder.record_failure()  # exhausted
ASSERT ladder.is_exhausted == True
```

---

### TS-30-23: DuckDB Assessment Table Schema

**Requirement:** 30-REQ-6.1
**Type:** integration
**Description:** Verify complexity_assessments table has correct schema.

**Preconditions:**
- Fresh DuckDB with migrations applied.

**Input:**
- Query table schema.

**Expected:**
- Table exists with all 10 columns, correct types.

**Assertion pseudocode:**
```
apply_migrations(db)
cols = db.execute("DESCRIBE complexity_assessments").fetchall()
col_names = [c.column_name for c in cols]
ASSERT "id" in col_names
ASSERT "node_id" in col_names
ASSERT "predicted_tier" in col_names
ASSERT "confidence" in col_names
ASSERT "feature_vector" in col_names
ASSERT len(col_names) == 10
```

---

### TS-30-24: DuckDB Outcome Table Schema

**Requirement:** 30-REQ-6.2
**Type:** integration
**Description:** Verify execution_outcomes table has correct schema.

**Preconditions:**
- Fresh DuckDB with migrations applied.

**Input:**
- Query table schema.

**Expected:**
- Table exists with all 11 columns, correct types.

**Assertion pseudocode:**
```
apply_migrations(db)
cols = db.execute("DESCRIBE execution_outcomes").fetchall()
col_names = [c.column_name for c in cols]
ASSERT "id" in col_names
ASSERT "assessment_id" in col_names
ASSERT "actual_tier" in col_names
ASSERT "escalation_count" in col_names
ASSERT len(col_names) == 11
```

---

### TS-30-25: Migration via Existing System

**Requirement:** 30-REQ-6.3
**Type:** integration
**Description:** Verify tables are created through the migration system.

**Preconditions:**
- DuckDB with existing tables from prior migrations.

**Input:**
- Apply pending migrations.

**Expected:**
- New tables exist. Existing tables unaffected.

**Assertion pseudocode:**
```
db = open_db_with_existing_schema()
apply_pending_migrations(db)
tables = db.execute("SHOW TABLES").fetchall()
table_names = [t[0] for t in tables]
ASSERT "complexity_assessments" in table_names
ASSERT "execution_outcomes" in table_names
ASSERT "facts" in table_names  # existing table still present
```

---

### TS-30-26: Assessment Before Session Runner

**Requirement:** 30-REQ-7.1
**Type:** integration
**Description:** Verify assessment runs before session runner creation.

**Preconditions:**
- Orchestrator with mock session backend and assessment pipeline.

**Input:**
- Dispatch one task group.

**Expected:**
- Assessment is produced before session execution begins.
- Session runner receives the assessed tier.

**Assertion pseudocode:**
```
events = []
engine = create_engine(mock_backend, on_assess=lambda a: events.append(("assess", a)),
                        on_execute=lambda e: events.append(("execute", e)))
await engine.run()
ASSERT events[0][0] == "assess"
ASSERT events[1][0] == "execute"
ASSERT events[1][1].tier == events[0][1].predicted_tier
```

---

### TS-30-27: Static Model Resolution Replaced

**Requirement:** 30-REQ-7.2
**Type:** unit
**Description:** Verify NodeSessionRunner uses assessment result instead of static resolution.

**Preconditions:**
- NodeSessionRunner initialized with assessment predicting SIMPLE.
- Archetype default would be ADVANCED.

**Input:**
- Check resolved model.

**Expected:**
- Resolved model is SIMPLE (from assessment), not ADVANCED (from archetype).

**Assertion pseudocode:**
```
runner = NodeSessionRunner(node_id, config, archetype="coder", assessed_tier=SIMPLE)
ASSERT runner._resolved_model_id == "SIMPLE"
```

---

### TS-30-28: Orchestrator Uses Escalation Ladder

**Requirement:** 30-REQ-7.3
**Type:** integration
**Description:** Verify orchestrator replaces simple retry with escalation ladder.

**Preconditions:**
- Orchestrator with mock backend: fails at SIMPLE, fails at SIMPLE retry,
  succeeds at STANDARD.
- retries_before_escalation = 1.

**Input:**
- Run one task group.

**Expected:**
- Three attempts total. Tiers: SIMPLE, SIMPLE, STANDARD.
- Final status: completed.

**Assertion pseudocode:**
```
attempts = []
mock_backend = MockBackend(fail_tiers=[SIMPLE], succeed_tiers=[STANDARD])
engine = create_engine(mock_backend, on_attempt=lambda a: attempts.append(a))
await engine.run()
ASSERT len(attempts) == 3
ASSERT attempts[0].tier == SIMPLE
ASSERT attempts[1].tier == SIMPLE
ASSERT attempts[2].tier == STANDARD
ASSERT engine.state.nodes["test:1"].status == "completed"
```

---

### TS-30-29: Outcome Recorded After Completion

**Requirement:** 30-REQ-7.4
**Type:** integration
**Description:** Verify execution outcome is recorded after task completion.

**Preconditions:**
- Orchestrator with DuckDB and mock backend that succeeds immediately.

**Input:**
- Run one task group to completion.

**Expected:**
- One row in `execution_outcomes` after execution.

**Assertion pseudocode:**
```
engine = create_engine(mock_backend, db=test_db)
await engine.run()
rows = test_db.execute("SELECT * FROM execution_outcomes").fetchall()
ASSERT len(rows) == 1
ASSERT rows[0].outcome == "completed"
```

---

## Property Test Cases

### TS-30-P1: Escalation Order Preservation

**Property:** Property 1 from design.md
**Validates:** 30-REQ-2.1, 30-REQ-2.2
**Type:** property
**Description:** Tiers in the escalation ladder are always non-decreasing.

**For any:** starting_tier in {SIMPLE, STANDARD, ADVANCED}, ceiling in {SIMPLE,
STANDARD, ADVANCED} where ceiling >= starting_tier, retries in [0, 3]

**Invariant:** The sequence of `current_tier` values after each `record_failure()`
call is non-decreasing when compared by tier order (SIMPLE < STANDARD < ADVANCED).

**Assertion pseudocode:**
```
FOR ANY starting_tier, ceiling, retries WHERE ceiling >= starting_tier AND retries in [0,3]:
    ladder = EscalationLadder(starting_tier, ceiling, retries)
    tiers = [ladder.current_tier]
    while ladder.should_retry():
        ladder.record_failure()
        tiers.append(ladder.current_tier)
    ASSERT tiers == sorted(tiers, key=tier_order)
```

---

### TS-30-P2: Tier Ceiling Enforcement

**Property:** Property 2 from design.md
**Validates:** 30-REQ-2.4, 30-REQ-5.3
**Type:** property
**Description:** No tier in the escalation sequence ever exceeds the ceiling.

**For any:** starting_tier, ceiling, retries as above

**Invariant:** Every `current_tier` value is <= ceiling in tier order.

**Assertion pseudocode:**
```
FOR ANY starting_tier, ceiling, retries WHERE ceiling >= starting_tier AND retries in [0,3]:
    ladder = EscalationLadder(starting_tier, ceiling, retries)
    while ladder.should_retry():
        ASSERT tier_order(ladder.current_tier) <= tier_order(ceiling)
        ladder.record_failure()
    ASSERT tier_order(ladder.current_tier) <= tier_order(ceiling)
```

---

### TS-30-P3: Retry Budget Correctness

**Property:** Property 3 from design.md
**Validates:** 30-REQ-2.1, 30-REQ-2.2, 30-REQ-2.3
**Type:** property
**Description:** Total attempts equals (retries + 1) * tiers_traversed.

**For any:** starting_tier, ceiling, retries as above

**Invariant:** After exhaustion, attempt_count == (retries + 1) * number_of_tiers
from starting_tier to min(ceiling, ADVANCED) inclusive, plus 1 for the initial.

**Assertion pseudocode:**
```
FOR ANY starting_tier, ceiling, retries WHERE ceiling >= starting_tier AND retries in [0,3]:
    ladder = EscalationLadder(starting_tier, ceiling, retries)
    while ladder.should_retry():
        ladder.record_failure()
    num_tiers = tier_order(ceiling) - tier_order(starting_tier) + 1
    expected_attempts = (retries + 1) * num_tiers
    ASSERT ladder.attempt_count == expected_attempts + 1  # +1 for initial
```

---

### TS-30-P4: Assessment Persistence Completeness

**Property:** Property 4 from design.md
**Validates:** 30-REQ-1.6, 30-REQ-3.1, 30-REQ-3.2
**Type:** integration
**Description:** Every assessed task has exactly one assessment and one outcome record.

**For any:** N task groups executed through the pipeline (N in [1, 5])

**Invariant:** count(complexity_assessments) == N AND count(execution_outcomes) == N
AND every outcome has a valid assessment_id FK.

**Assertion pseudocode:**
```
FOR ANY n in [1, 5]:
    pipeline, db = create_test_pipeline()
    for i in range(n):
        assessment = await pipeline.assess(f"spec:{i}", ...)
        pipeline.record_outcome(assessment, ...)
    assessments = db.execute("SELECT COUNT(*) FROM complexity_assessments").fetchone()[0]
    outcomes = db.execute("SELECT COUNT(*) FROM execution_outcomes").fetchone()[0]
    ASSERT assessments == n
    ASSERT outcomes == n
    orphans = db.execute("""
        SELECT COUNT(*) FROM execution_outcomes o
        LEFT JOIN complexity_assessments a ON o.assessment_id = a.id
        WHERE a.id IS NULL
    """).fetchone()[0]
    ASSERT orphans == 0
```

---

### TS-30-P5: Feature Vector Determinism

**Property:** Property 5 from design.md
**Validates:** 30-REQ-1.2
**Type:** property
**Description:** Feature extraction is deterministic for the same inputs.

**For any:** valid spec directory content (subtask count in [0, 20], word count
in [0, 5000])

**Invariant:** Two calls with identical inputs produce identical FeatureVectors.

**Assertion pseudocode:**
```
FOR ANY spec_content, task_group, archetype:
    spec_dir = create_temp_spec(spec_content)
    v1 = extract_features(spec_dir, task_group, archetype)
    v2 = extract_features(spec_dir, task_group, archetype)
    ASSERT v1 == v2
```

---

### TS-30-P6: Method Selection Consistency

**Property:** Property 6 from design.md
**Validates:** 30-REQ-1.3, 30-REQ-1.4, 30-REQ-1.5
**Type:** property
**Description:** Assessment method follows deterministic selection rules.

**For any:** outcome_count in [0, 100], accuracy in [0.0, 1.0],
training_threshold in [5, 100], accuracy_threshold in [0.5, 1.0]

**Invariant:**
- outcome_count < training_threshold → method = "heuristic"
- outcome_count >= training_threshold AND accuracy >= accuracy_threshold → method = "statistical"
- outcome_count >= training_threshold AND accuracy < accuracy_threshold → method = "hybrid"

**Assertion pseudocode:**
```
FOR ANY outcome_count, accuracy, training_threshold, accuracy_threshold:
    method = select_method(outcome_count, accuracy, training_threshold, accuracy_threshold)
    if outcome_count < training_threshold:
        ASSERT method == "heuristic"
    elif accuracy >= accuracy_threshold:
        ASSERT method == "statistical"
    else:
        ASSERT method == "hybrid"
```

---

### TS-30-P7: Graceful Degradation

**Property:** Property 7 from design.md
**Validates:** 30-REQ-1.E1, 30-REQ-1.E2, 30-REQ-1.E3, 30-REQ-7.E1
**Type:** unit
**Description:** Assessment pipeline always returns a valid result, never raises.

**For any:** combination of failures (LLM down, DB down, bad spec dir)

**Invariant:** `assess()` returns a ComplexityAssessment (never raises).
The predicted_tier is a valid ModelTier.

**Assertion pseudocode:**
```
FOR ANY failure_mode in [llm_timeout, db_unavailable, bad_spec_dir, all_failing]:
    pipeline = AssessmentPipeline(config, db=mock_db(failure_mode))
    result = await pipeline.assess(node_id, spec_name, 1, bad_dir, "coder", ADVANCED)
    ASSERT result is not None
    ASSERT result.predicted_tier in [SIMPLE, STANDARD, ADVANCED]
```

---

### TS-30-P8: Cost Accounting Completeness

**Property:** Property 8 from design.md
**Validates:** 30-REQ-2.5
**Type:** property
**Description:** Cumulative cost includes all attempts across escalation.

**For any:** escalation sequence with known per-attempt costs

**Invariant:** total_cost == sum(cost_per_attempt for each attempt in escalation)

**Assertion pseudocode:**
```
FOR ANY attempt_costs (list of floats, len 1-6):
    total = sum(attempt_costs)
    ladder_cost = simulate_escalation(attempt_costs)
    ASSERT ladder_cost == total
```

---

### TS-30-P9: Configuration Clamping

**Property:** Property 9 from design.md
**Validates:** 30-REQ-5.1, 30-REQ-5.2, 30-REQ-5.E1, 30-REQ-5.E2
**Type:** property
**Description:** All routing config values are clamped to valid ranges.

**For any:** retries in [-10, 100], threshold in [-10, 5000],
accuracy in [-1.0, 2.0], interval in [-10, 500]

**Invariant:**
- 0 <= retries_before_escalation <= 3
- 5 <= training_threshold <= 1000
- 0.5 <= accuracy_threshold <= 1.0
- 5 <= retrain_interval <= 100

**Assertion pseudocode:**
```
FOR ANY retries, threshold, accuracy, interval:
    config = RoutingConfig(
        retries_before_escalation=retries,
        training_threshold=threshold,
        accuracy_threshold=accuracy,
        retrain_interval=interval,
    )
    ASSERT 0 <= config.retries_before_escalation <= 3
    ASSERT 5 <= config.training_threshold <= 1000
    ASSERT 0.5 <= config.accuracy_threshold <= 1.0
    ASSERT 5 <= config.retrain_interval <= 100
```

---

## Edge Case Tests

### TS-30-E1: LLM Assessment Failure Fallback

**Requirement:** 30-REQ-1.E1
**Type:** unit
**Description:** LLM call failure falls back to heuristic.

**Preconditions:**
- LLM client mocked to raise TimeoutError.

**Input:**
- Run assessment in hybrid mode.

**Expected:**
- Assessment succeeds with method = "heuristic". Warning logged.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config, db=db, llm_client=failing_client)
with capture_logs() as logs:
    result = await pipeline.assess(...)
ASSERT result.assessment_method == "heuristic"
ASSERT any("warning" in log.lower() and "llm" in log.lower() for log in logs)
```

---

### TS-30-E2: DuckDB Unavailable During Assessment

**Requirement:** 30-REQ-1.E2
**Type:** unit
**Description:** Assessment works without DuckDB.

**Preconditions:**
- DuckDB = None.

**Input:**
- Run assessment.

**Expected:**
- Returns heuristic assessment. No persistence. Warning logged.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config, db=None)
result = await pipeline.assess(...)
ASSERT result.assessment_method == "heuristic"
ASSERT result.confidence == 0.6  # heuristic default confidence
```

---

### TS-30-E3: Feature Extraction Failure

**Requirement:** 30-REQ-1.E3
**Type:** unit
**Description:** Bad spec directory produces default features.

**Preconditions:**
- Non-existent spec directory.

**Input:**
- Extract features from missing path.

**Expected:**
- FeatureVector with zeros and "unknown", confidence = 0.0.

**Assertion pseudocode:**
```
result = extract_features(Path("/nonexistent"), 1, "coder")
ASSERT result.subtask_count == 0
ASSERT result.spec_word_count == 0
ASSERT result.archetype == "coder"  # archetype is passed in, not extracted
```

---

### TS-30-E4: Assessment Predicts ADVANCED

**Requirement:** 30-REQ-2.E1
**Type:** unit
**Description:** No escalation when starting at ADVANCED.

**Preconditions:**
- EscalationLadder with starting_tier=ADVANCED, ceiling=ADVANCED, retries=1.

**Input:**
- Record 2 failures.

**Expected:**
- `is_exhausted` is True. No escalation occurred.

**Assertion pseudocode:**
```
ladder = EscalationLadder(ADVANCED, ADVANCED, retries_before_escalation=1)
ladder.record_failure()
ASSERT ladder.current_tier == ADVANCED
ladder.record_failure()
ASSERT ladder.is_exhausted == True
ASSERT ladder.escalation_count == 0
```

---

### TS-30-E5: Tier Ceiling Equals SIMPLE

**Requirement:** 30-REQ-2.E2
**Type:** unit
**Description:** No escalation when ceiling is SIMPLE.

**Preconditions:**
- EscalationLadder with starting_tier=SIMPLE, ceiling=SIMPLE, retries=1.

**Input:**
- Record 2 failures.

**Expected:**
- `is_exhausted` is True. No escalation.

**Assertion pseudocode:**
```
ladder = EscalationLadder(SIMPLE, SIMPLE, retries_before_escalation=1)
ladder.record_failure()
ladder.record_failure()
ASSERT ladder.is_exhausted == True
ASSERT ladder.escalation_count == 0
```

---

### TS-30-E6: DuckDB Unavailable During Outcome Recording

**Requirement:** 30-REQ-3.E1
**Type:** unit
**Description:** Outcome recording failure doesn't block execution.

**Preconditions:**
- DuckDB mocked to raise on INSERT.

**Input:**
- Record outcome.

**Expected:**
- No exception raised. Warning logged.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config, db=failing_db)
with capture_logs() as logs:
    pipeline.record_outcome(assessment, ...)  # should not raise
ASSERT any("warning" in log.lower() for log in logs)
```

---

### TS-30-E7: Statistical Training Failure

**Requirement:** 30-REQ-4.E1
**Type:** unit
**Description:** Training failure falls back to heuristic.

**Preconditions:**
- DuckDB with 20 identical outcomes (zero variance in features).

**Input:**
- Train statistical model.

**Expected:**
- Training fails gracefully. Falls back to heuristic. Warning logged.

**Assertion pseudocode:**
```
assessor = StatisticalAssessor(db=zero_variance_db)
with capture_logs() as logs:
    accuracy = assessor.train()
ASSERT accuracy == 0.0 OR assessment method reverts to heuristic
ASSERT any("warning" in log.lower() for log in logs)
```

---

### TS-30-E8: Statistical Accuracy Degradation

**Requirement:** 30-REQ-4.E2
**Type:** integration
**Description:** Accuracy drop triggers revert to hybrid.

**Preconditions:**
- Statistical model previously at 0.85 accuracy.
- After retraining with noisy data, accuracy drops to 0.60.
- Threshold = 0.75.

**Input:**
- Retrain and check assessment method.

**Expected:**
- Assessment method reverts to "hybrid". Warning logged.

**Assertion pseudocode:**
```
pipeline = AssessmentPipeline(config=RoutingConfig(accuracy_threshold=0.75), db=degraded_db)
with capture_logs() as logs:
    result = await pipeline.assess(...)
ASSERT result.assessment_method == "hybrid"
ASSERT any("degraded" in log.lower() or "warning" in log.lower() for log in logs)
```

---

### TS-30-E9: Invalid Routing Config Type

**Requirement:** 30-REQ-5.E2
**Type:** unit
**Description:** Invalid config type raises ConfigError.

**Preconditions:**
- config.toml with `[routing]` containing `retries_before_escalation = "high"`.

**Input:**
- Load config.

**Expected:**
- ConfigError raised with message mentioning "retries_before_escalation".

**Assertion pseudocode:**
```
ASSERT_RAISES ConfigError:
    load_config(path_to_bad_type_toml)
```

---

### TS-30-E10: Migration Idempotency

**Requirement:** 30-REQ-6.E1
**Type:** integration
**Description:** Re-applying migration doesn't error.

**Preconditions:**
- DuckDB with tables already created.

**Input:**
- Apply migrations again.

**Expected:**
- No error. Tables unchanged.

**Assertion pseudocode:**
```
apply_pending_migrations(db)  # first time
apply_pending_migrations(db)  # second time — should be no-op
tables = db.execute("SHOW TABLES").fetchall()
ASSERT "complexity_assessments" in [t[0] for t in tables]
```

---

### TS-30-E11: Assessment Pipeline Unhandled Exception

**Requirement:** 30-REQ-7.E1
**Type:** unit
**Description:** Unhandled assessment error falls back to archetype default.

**Preconditions:**
- Assessment pipeline mocked to raise RuntimeError.

**Input:**
- Orchestrator dispatches task.

**Expected:**
- Task executes at archetype default tier. Error logged.

**Assertion pseudocode:**
```
engine = create_engine(mock_backend, pipeline=exploding_pipeline)
with capture_logs() as logs:
    await engine.run()
ASSERT engine.last_attempt_tier == ADVANCED  # coder default
ASSERT any("error" in log.lower() and "assessment" in log.lower() for log in logs)
```

---

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 30-REQ-1.1 | TS-30-2 | unit |
| 30-REQ-1.2 | TS-30-1 | unit |
| 30-REQ-1.3 | TS-30-3 | integration |
| 30-REQ-1.4 | TS-30-4 | integration |
| 30-REQ-1.5 | TS-30-5 | integration |
| 30-REQ-1.6 | TS-30-6 | integration |
| 30-REQ-1.E1 | TS-30-E1 | unit |
| 30-REQ-1.E2 | TS-30-E2 | unit |
| 30-REQ-1.E3 | TS-30-E3 | unit |
| 30-REQ-2.1 | TS-30-7 | unit |
| 30-REQ-2.2 | TS-30-8 | unit |
| 30-REQ-2.3 | TS-30-9 | unit |
| 30-REQ-2.4 | TS-30-10 | unit |
| 30-REQ-2.5 | TS-30-11 | integration |
| 30-REQ-2.E1 | TS-30-E4 | unit |
| 30-REQ-2.E2 | TS-30-E5 | unit |
| 30-REQ-3.1 | TS-30-12 | integration |
| 30-REQ-3.2 | TS-30-13 | integration |
| 30-REQ-3.3 | TS-30-14 | unit |
| 30-REQ-3.E1 | TS-30-E6 | unit |
| 30-REQ-4.1 | TS-30-15 | integration |
| 30-REQ-4.2 | TS-30-16 | integration |
| 30-REQ-4.3 | TS-30-17 | integration |
| 30-REQ-4.4 | TS-30-18 | integration |
| 30-REQ-4.5 | TS-30-19 | integration |
| 30-REQ-4.E1 | TS-30-E7 | unit |
| 30-REQ-4.E2 | TS-30-E8 | integration |
| 30-REQ-5.1 | TS-30-20 | unit |
| 30-REQ-5.2 | TS-30-21 | unit |
| 30-REQ-5.3 | TS-30-22 | unit |
| 30-REQ-5.E1 | TS-30-20 | unit |
| 30-REQ-5.E2 | TS-30-E9 | unit |
| 30-REQ-6.1 | TS-30-23 | integration |
| 30-REQ-6.2 | TS-30-24 | integration |
| 30-REQ-6.3 | TS-30-25 | integration |
| 30-REQ-6.E1 | TS-30-E10 | integration |
| 30-REQ-7.1 | TS-30-26 | integration |
| 30-REQ-7.2 | TS-30-27 | unit |
| 30-REQ-7.3 | TS-30-28 | integration |
| 30-REQ-7.4 | TS-30-29 | integration |
| 30-REQ-7.E1 | TS-30-E11 | unit |
| Property 1 | TS-30-P1 | property |
| Property 2 | TS-30-P2 | property |
| Property 3 | TS-30-P3 | property |
| Property 4 | TS-30-P4 | property |
| Property 5 | TS-30-P5 | property |
| Property 6 | TS-30-P6 | property |
| Property 7 | TS-30-P7 | property |
| Property 8 | TS-30-P8 | property |
| Property 9 | TS-30-P9 | property |
