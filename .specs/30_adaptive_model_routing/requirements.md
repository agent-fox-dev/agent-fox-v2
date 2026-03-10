# Requirements Document

## Introduction

Adaptive Model Routing replaces agent-fox's static model tier assignment with a
two-layer system: complexity-based pre-selection picks a starting tier for each
task group, and speculative execution escalates to higher tiers on failure. The
system collects pre- and post-execution data, calibrates predictions over time,
and becomes more cost-efficient as it accumulates execution history.

## Glossary

- **Model Tier**: One of SIMPLE, STANDARD, or ADVANCED — provider-independent
  labels that map to concrete models via `MODEL_REGISTRY` (e.g., Haiku, Sonnet,
  Opus for Anthropic).
- **Complexity Assessment**: A pre-execution prediction of which model tier a
  task group requires, produced by the assessment pipeline.
- **Feature Vector**: A set of numeric and categorical attributes extracted from
  a task group's spec content, used as input to the statistical model.
- **Assessment Method**: The strategy used to produce a complexity assessment:
  `heuristic` (rule-based), `statistical` (trained model), `llm` (AI
  evaluation), or `hybrid` (statistical + LLM cross-check).
- **Escalation Ladder**: The ordered sequence of model tiers a task group
  traverses on repeated failure: selected tier → retry at same tier → next
  higher tier → retry → next higher tier → exhaust.
- **Retries-Before-Escalation**: The number of retry attempts at the same model
  tier before escalating to the next tier (default: 1).
- **Tier Ceiling**: The maximum tier a task group may use, derived from the
  archetype's config override or the archetype registry default. The adaptive
  system never escalates above this ceiling.
- **Calibration**: The process of comparing predicted complexity against actual
  execution outcomes to improve future predictions.
- **Confidence Score**: A float in [0.0, 1.0] representing the assessment
  pipeline's certainty in its tier prediction.
- **Statistical Model**: A logistic regression classifier trained on historical
  feature vectors and execution outcomes, used to predict complexity tiers.

## Requirements

### Requirement 1: Complexity Assessment

**User Story:** As an operator, I want agent-fox to automatically assess task
group complexity before execution, so that simple tasks run on cheaper models
without manual configuration.

#### Acceptance Criteria

1. [30-REQ-1.1] WHEN a task group is ready for execution, THE system SHALL
   produce a complexity assessment containing: predicted tier
   (SIMPLE/STANDARD/ADVANCED), confidence score (0.0-1.0), assessment method,
   and feature vector.

2. [30-REQ-1.2] THE system SHALL extract the following features from the task
   group's spec content for the feature vector: subtask count, spec word count,
   presence of property tests (boolean), edge case count, dependency count, and
   archetype type.

3. [30-REQ-1.3] WHEN no historical execution data exists (fewer than the
   configured training threshold data points), THE system SHALL use heuristic
   assessment only and set the assessment method to `heuristic`.

4. [30-REQ-1.4] WHEN the statistical model's cross-validated accuracy exceeds
   the configured accuracy threshold, THE system SHALL prefer the statistical
   model over LLM assessment and set the assessment method to `statistical`.

5. [30-REQ-1.5] WHEN the statistical model's accuracy is below the configured
   accuracy threshold but historical data exists above the training threshold,
   THE system SHALL use both statistical and LLM assessment, compare their
   predictions, and set the assessment method to `hybrid`.

6. [30-REQ-1.6] THE system SHALL persist every complexity assessment to the
   `complexity_assessments` table in DuckDB before execution begins.

#### Edge Cases

1. [30-REQ-1.E1] IF the LLM assessment call fails (timeout, API error), THEN
   THE system SHALL fall back to heuristic assessment and log a warning.

2. [30-REQ-1.E2] IF the DuckDB knowledge store is unavailable, THEN THE system
   SHALL use heuristic assessment only, skip persistence, and log a warning.

3. [30-REQ-1.E3] IF the feature vector extraction fails (e.g., spec files
   missing or unparseable), THEN THE system SHALL use default feature values
   (zeros for numeric, "unknown" for categorical) and set confidence to 0.0.

---

### Requirement 2: Speculative Execution and Escalation

**User Story:** As an operator, I want failed task groups to automatically
escalate to more capable models, so that tasks succeed without manual
intervention while starting at the cheapest viable tier.

#### Acceptance Criteria

1. [30-REQ-2.1] WHEN a task group session fails, THE system SHALL retry at the
   same model tier up to the configured retries-before-escalation count
   (default: 1), passing the previous error context to the retry.

2. [30-REQ-2.2] WHEN all retries at a tier are exhausted, THE system SHALL
   escalate to the next higher tier in the order SIMPLE → STANDARD → ADVANCED.

3. [30-REQ-2.3] WHEN the highest available tier is exhausted (all retries at
   ADVANCED failed, or all retries at the tier ceiling failed), THE system SHALL
   mark the task as failed and cascade-block dependent tasks.

4. [30-REQ-2.4] THE system SHALL respect the tier ceiling: the adaptive system
   SHALL NOT escalate above the tier derived from the archetype's config
   override or registry default.

5. [30-REQ-2.5] THE system SHALL include all speculative execution attempts
   (including failed lower-tier attempts) in the circuit breaker's cumulative
   cost tracking.

#### Edge Cases

1. [30-REQ-2.E1] IF the complexity assessment predicts ADVANCED (the highest
   tier), THEN THE system SHALL skip escalation and use only same-tier retries.

2. [30-REQ-2.E2] IF the tier ceiling equals SIMPLE, THEN THE system SHALL use
   only same-tier retries at SIMPLE with no escalation path.

---

### Requirement 3: Execution Outcome Recording

**User Story:** As an operator, I want every task group execution to record its
actual resource consumption and outcome, so that the system can calibrate its
predictions over time.

#### Acceptance Criteria

1. [30-REQ-3.1] WHEN a task group execution completes (success or final
   failure), THE system SHALL persist an execution outcome record to the
   `execution_outcomes` table in DuckDB containing: assessment ID (foreign key),
   actual tier used, total tokens, total cost, duration, attempt count,
   escalation count, session outcome, and files touched count.

2. [30-REQ-3.2] THE system SHALL link each execution outcome to its
   corresponding complexity assessment via the assessment ID.

3. [30-REQ-3.3] WHEN a task group requires escalation, THE system SHALL record
   the final tier used (the tier that succeeded, or the highest tier attempted
   if all failed) as the actual tier.

#### Edge Cases

1. [30-REQ-3.E1] IF the DuckDB knowledge store is unavailable when recording an
   outcome, THEN THE system SHALL log a warning and continue without persisting.
   The execution itself is not affected.

---

### Requirement 4: Statistical Model Training and Calibration

**User Story:** As an operator, I want the system to learn from past executions
and improve its model tier predictions over time, so that cost savings increase
with usage.

#### Acceptance Criteria

1. [30-REQ-4.1] WHEN the number of execution outcome records in DuckDB reaches
   the configured training threshold (default: 20), THE system SHALL train a
   logistic regression model on the stored feature vectors and actual tier
   outcomes.

2. [30-REQ-4.2] THE system SHALL evaluate the statistical model using
   cross-validation and compute an accuracy score.

3. [30-REQ-4.3] WHEN the statistical model's cross-validated accuracy exceeds
   the configured accuracy threshold (default: 0.75), THE system SHALL use the
   statistical model as the primary assessment method.

4. [30-REQ-4.4] WHEN the assessment method is `hybrid`, THE system SHALL
   compare the statistical and LLM predictions. IF they disagree, THE system
   SHALL use the prediction from the method with higher historical accuracy and
   log the divergence.

5. [30-REQ-4.5] THE system SHALL retrain the statistical model after every N
   new execution outcomes (configurable, default: 10) to incorporate recent
   data.

#### Edge Cases

1. [30-REQ-4.E1] IF the statistical model training fails (e.g., insufficient
   variance in training data, numerical errors), THEN THE system SHALL fall back
   to heuristic assessment and log a warning.

2. [30-REQ-4.E2] IF the statistical model's accuracy degrades below the
   configured accuracy threshold after retraining, THEN THE system SHALL revert
   to hybrid assessment (statistical + LLM) and log a warning.

---

### Requirement 5: Configuration

**User Story:** As an operator, I want to configure the adaptive routing
behavior through `config.toml`, so that I can tune thresholds for my project's
needs.

#### Acceptance Criteria

1. [30-REQ-5.1] THE system SHALL support the following configuration keys under
   `[routing]` in `config.toml`: `retries_before_escalation` (int, default: 1),
   `training_threshold` (int, default: 20), `accuracy_threshold` (float,
   default: 0.75), `retrain_interval` (int, default: 10).

2. [30-REQ-5.2] THE system SHALL clamp `retries_before_escalation` to [0, 3],
   `training_threshold` to [5, 1000], `accuracy_threshold` to [0.5, 1.0], and
   `retrain_interval` to [5, 100], logging a warning on clamping.

3. [30-REQ-5.3] WHEN a config override sets an archetype's model tier (e.g.,
   `archetypes.models.coder = "STANDARD"`), THE system SHALL treat that tier as
   the ceiling for adaptive routing — never escalating above it but still
   starting at a lower tier if the assessment suggests it.

#### Edge Cases

1. [30-REQ-5.E1] IF the `[routing]` section is absent from `config.toml`, THEN
   THE system SHALL use all default values.

2. [30-REQ-5.E2] IF a `[routing]` field has an invalid type (e.g., string where
   int expected), THEN THE system SHALL raise a ConfigError with a clear message
   identifying the field and expected type.

---

### Requirement 6: DuckDB Schema

**User Story:** As a developer, I want the assessment and outcome data stored in
well-defined DuckDB tables, so that the calibration system and future analytics
have a reliable data source.

#### Acceptance Criteria

1. [30-REQ-6.1] THE system SHALL create a `complexity_assessments` table with
   columns: id (UUID primary key), node_id (VARCHAR), spec_name (VARCHAR),
   task_group (INTEGER), predicted_tier (VARCHAR), confidence (FLOAT),
   assessment_method (VARCHAR), feature_vector (JSON), tier_ceiling (VARCHAR),
   created_at (TIMESTAMP).

2. [30-REQ-6.2] THE system SHALL create an `execution_outcomes` table with
   columns: id (UUID primary key), assessment_id (UUID foreign key),
   actual_tier (VARCHAR), total_tokens (INTEGER), total_cost (FLOAT),
   duration_ms (INTEGER), attempt_count (INTEGER), escalation_count (INTEGER),
   outcome (VARCHAR), files_touched_count (INTEGER), created_at (TIMESTAMP).

3. [30-REQ-6.3] THE system SHALL add the new tables via the existing DuckDB
   migration system (`knowledge/migrations.py`).

#### Edge Cases

1. [30-REQ-6.E1] IF the migration is applied to a database that already contains
   the tables (idempotency), THEN THE system SHALL skip table creation without
   error.

---

### Requirement 7: Integration with Orchestrator

**User Story:** As an operator, I want the adaptive routing to work seamlessly
within the existing orchestration loop, so that I don't need to change my
workflow.

#### Acceptance Criteria

1. [30-REQ-7.1] WHEN the orchestrator dispatches a task group, THE system SHALL
   run the complexity assessment before creating the session runner.

2. [30-REQ-7.2] THE system SHALL replace the current static model resolution in
   `NodeSessionRunner._resolve_model_tier()` with the adaptive assessment
   result.

3. [30-REQ-7.3] THE system SHALL replace the current retry logic in the
   orchestrator engine loop with the escalation ladder (retry at same tier, then
   escalate).

4. [30-REQ-7.4] WHEN a task group completes (success or final failure), THE
   system SHALL record the execution outcome before proceeding to the next task.

#### Edge Cases

1. [30-REQ-7.E1] IF the complexity assessment pipeline raises an unhandled
   exception, THEN THE system SHALL fall back to the archetype's default tier
   and log the error. Execution SHALL NOT be blocked by assessment failures.
