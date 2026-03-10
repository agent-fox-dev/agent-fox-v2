# ADR: Adaptive Model Routing

**Status:** Accepted
**Date:** 2026-03-10

## Context

agent-fox assigns model tiers (SIMPLE, STANDARD, ADVANCED) statically based on
archetype defaults or explicit config overrides. This means every task group
runs at the same tier regardless of complexity. Simple tasks waste money on
expensive models, and hard tasks sometimes fail on cheap models and require
manual re-runs at a higher tier.

## Decision

We introduce a two-layer adaptive routing system:

### Layer 1: Complexity Assessment

Before executing a task group, an assessment pipeline predicts the appropriate
model tier. The pipeline uses one of three methods, selected automatically:

- **Heuristic** (default, no history): Rule-based classification using features
  extracted from spec content (subtask count, word count, property tests, edge
  cases, dependencies, archetype type). Fixed confidence of 0.6.
- **Statistical** (sufficient accurate history): A logistic regression model
  (scikit-learn) trained on historical feature vectors and execution outcomes.
  Preferred when cross-validated accuracy exceeds the configured threshold
  (default: 0.75).
- **Hybrid** (sufficient history but low accuracy): Both statistical and LLM
  assessments are run; the method with higher historical accuracy wins.

### Layer 2: Speculative Execution (Escalation Ladder)

When a task group fails, the system retries at the same tier (configurable,
default: 1 retry) before escalating to the next higher tier (SIMPLE -> STANDARD
-> ADVANCED). The escalation ladder respects a tier ceiling derived from the
archetype's config override.

### Data Collection and Calibration

Every assessment and execution outcome is persisted to DuckDB tables
(`complexity_assessments`, `execution_outcomes`). The statistical model is
retrained after every N new outcomes (configurable, default: 10). This creates a
feedback loop: predictions improve with usage, reducing cost over time.

### Configuration

All tuning knobs live under `[routing]` in `config.toml`:

```toml
[routing]
retries_before_escalation = 1   # 0-3
training_threshold = 20         # 5-1000
accuracy_threshold = 0.75       # 0.5-1.0
retrain_interval = 10           # 5-100
```

Archetype model overrides (e.g., `archetypes.models.coder = "STANDARD"`) act as
tier ceilings: the adaptive system may start lower but never escalates above.

## Alternatives Considered

1. **LLM-only assessment.** Use an LLM call to evaluate every task group's
   complexity. Rejected because it adds latency and cost to every task dispatch,
   and the LLM has no memory of past accuracy. The hybrid approach uses the LLM
   only when statistical confidence is low.

2. **Fixed escalation without assessment.** Always start at SIMPLE and escalate
   on failure. Rejected because it wastes attempts on tasks that are obviously
   complex (e.g., those with many subtasks and property tests).

3. **Neural network classifier.** Use a more complex model for predictions.
   Rejected because the data volumes are small (tens to hundreds of outcomes)
   and logistic regression is sufficient, interpretable, and fast.

4. **Per-subtask routing.** Assess complexity at the subtask level rather than
   task group. Rejected because execution happens at the task-group level and
   subtask-level signals are too noisy.

## Consequences

### Positive

- **Cost reduction:** Simple tasks run on cheaper models automatically.
- **Resilience:** Failed tasks escalate without manual intervention.
- **Self-improving:** Predictions improve with accumulated history.
- **Zero-config:** Works out of the box with heuristic assessment; no
  configuration required for basic operation.
- **Backward compatible:** Existing `max_retries` config is read as a fallback.
  Explicit archetype model tiers become ceilings rather than being ignored.

### Negative

- **New dependency:** scikit-learn is added as a runtime dependency (~30MB).
- **Complexity:** The assessment pipeline and escalation ladder add new concepts
  to the orchestration loop.
- **Cold start:** Heuristic assessment has limited accuracy until enough history
  is accumulated for statistical training.

### Risks

- **Heuristic misprediction:** Simple heuristic rules may not generalize across
  all project types. Mitigated by the escalation ladder (wrong tier is corrected
  by escalation) and by transitioning to statistical assessment with history.
- **Statistical model staleness:** If project characteristics change, the model
  may degrade. Mitigated by periodic retraining and automatic fallback to hybrid
  mode when accuracy drops.
