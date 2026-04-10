# Requirements Document

## Introduction

Simplify the model routing subsystem by removing the prediction pipeline
(feature extraction, statistical model, LLM assessment, DuckDB persistence)
while preserving the escalation ladder and archetype default tiers. After this
change, every task starts at its archetype's default model tier and escalates
on repeated failure -- no prediction, no training, no outcome recording.

## Glossary

- **Escalation ladder**: State machine tracking retry count and current model
  tier for a single task execution. Retries at the same tier, then escalates
  to the next tier up after `retries_before_escalation` failures.
- **Archetype default tier**: The `default_model_tier` field on an
  `ArchetypeEntry` (e.g. coder=STANDARD, oracle=ADVANCED).
- **Prediction pipeline**: The removed subsystem comprising feature extraction
  (`features.py`), assessment orchestration (`assessor.py`), statistical model
  (`calibration.py`), and DuckDB persistence (`core.py` persistence functions).
- **Tier ceiling**: The maximum tier an escalation ladder can reach (always
  ADVANCED).
- **Model tier**: One of SIMPLE, STANDARD, ADVANCED -- maps to a concrete
  Claude model.

## Requirements

### Requirement 1: Escalation ladder always created from archetype defaults

**User Story:** As the orchestrator, I want every node to get an escalation
ladder before its first dispatch, so that retry/escalation logic works
consistently without depending on a prediction pipeline.

#### Acceptance Criteria

[89-REQ-1.1] WHEN a node is dispatched for the first time, THE system SHALL
create an `EscalationLadder` with `starting_tier` set to the node's archetype
`default_model_tier`.

[89-REQ-1.2] WHEN a node is dispatched for the first time, THE system SHALL
set the escalation ladder's `tier_ceiling` to `ModelTier.ADVANCED`.

[89-REQ-1.3] THE `AssessmentManager.assess_node()` method SHALL create an
escalation ladder for every node regardless of whether an assessment pipeline
is configured.

#### Edge Cases

[89-REQ-1.E1] IF the archetype name is unknown, THEN THE system SHALL fall
back to the `coder` archetype's default tier (STANDARD).

### Requirement 2: Prediction pipeline modules removed

**User Story:** As a maintainer, I want the prediction pipeline code removed,
so that the codebase is simpler and there is no dead code.

#### Acceptance Criteria

[89-REQ-2.1] THE codebase SHALL NOT contain the files `agent_fox/routing/assessor.py`,
`agent_fox/routing/features.py`, `agent_fox/routing/calibration.py`, or
`agent_fox/routing/duration.py`.

[89-REQ-2.2] THE `agent_fox/routing/core.py` module SHALL NOT contain any
DuckDB persistence functions (`persist_assessment`, `persist_outcome`,
`count_outcomes`, `query_outcomes`, `_feature_vector_to_json`).

[89-REQ-2.3] THE `agent_fox/engine/run.py` module SHALL NOT import or
construct an `AssessmentPipeline`.

[89-REQ-2.4] THE `agent_fox/routing/core.py` module SHALL retain the
`FeatureVector`, `ComplexityAssessment`, and `ExecutionOutcome` dataclass
definitions.

### Requirement 3: Outcome recording removed

**User Story:** As a maintainer, I want the dead outcome-recording code path
removed from the result handler, so there is no vestigial prediction pipeline
coupling.

#### Acceptance Criteria

[89-REQ-3.1] THE `SessionResultHandler` class SHALL NOT contain a
`record_node_outcome` method or any code that calls
`self._routing_pipeline.record_outcome()`.

[89-REQ-3.2] THE `SessionResultHandler.__init__` SHALL NOT accept a
`routing_pipeline` parameter.

### Requirement 4: Prediction-only config fields removed

**User Story:** As a maintainer, I want prediction-only configuration fields
removed from `RoutingConfig`, so the config surface matches the simplified
system.

#### Acceptance Criteria

[89-REQ-4.1] THE `RoutingConfig` class SHALL NOT contain the fields
`training_threshold`, `accuracy_threshold`, or `retrain_interval`.

[89-REQ-4.2] THE `RoutingConfig` class SHALL retain the field
`retries_before_escalation`.

### Requirement 5: Prediction pipeline tests removed

**User Story:** As a maintainer, I want tests for removed modules deleted, so
the test suite does not reference non-existent code.

#### Acceptance Criteria

[89-REQ-5.1] THE test suite SHALL NOT contain the files
`tests/test_routing/test_assessor.py`, `tests/test_routing/test_features.py`,
`tests/test_routing/test_calibration.py`, `tests/test_routing/test_storage.py`,
or `tests/test_routing/test_integration.py`.

[89-REQ-5.2] THE test files `tests/test_routing/test_escalation.py` and
`tests/test_routing/test_config.py` SHALL be retained and pass.

[89-REQ-5.3] WHEN `make check` is run after all changes, THE system SHALL
report zero test failures and zero lint errors.

### Requirement 6: Duration hint references removed

**User Story:** As a maintainer, I want all references to duration-based task
ordering removed alongside the duration module.

#### Acceptance Criteria

[89-REQ-6.1] THE files `agent_fox/engine/engine.py` and
`agent_fox/cli/status.py` SHALL NOT import from
`agent_fox.routing.duration`.

### Requirement 7: Superseded specs archived

**User Story:** As a maintainer, I want superseded routing specs clearly
marked, so future agents do not implement against stale specifications.

#### Acceptance Criteria

[89-REQ-7.1] THE specs `30_adaptive_model_routing` and
`57_archetype_model_tiers` in `.specs/archive/` SHALL have a deprecation
banner at the top of each file indicating they are superseded by spec 89.
