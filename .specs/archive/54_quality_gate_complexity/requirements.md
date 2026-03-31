# Requirements Document

## Introduction

This specification adds a configurable post-session quality gate and enriches
the complexity feature vector with additional signals. The quality gate runs
a project-defined command (e.g. `make check`) after each coder session and
records the result as an informational signal. The complexity enrichment adds
four new fields to the feature vector to improve tier prediction accuracy.

## Glossary

- **Quality gate**: A configurable shell command executed after each successful
  coder session to validate code correctness (e.g. `make check`, `pytest`).
- **Gate failure**: A quality gate that exits with a non-zero status or exceeds
  its timeout. Recorded as an informational signal, not a hard block.
- **Feature vector**: A set of numeric and boolean signals derived from a
  task group's spec content, used by the complexity assessor to predict the
  appropriate model tier. Defined as `FeatureVector` in `routing/core.py`.
- **Heuristic assessor**: The rule-based complexity assessor that uses
  threshold logic on feature vector fields.
- **Statistical assessor**: The data-driven complexity assessor that learns
  from prior `execution_outcomes`.
- **Model tier**: The complexity classification (STANDARD or ADVANCED) that
  determines which LLM model is used for a session.
- **Execution outcome**: A record of actual session cost, duration, and tier,
  stored in `execution_outcomes` for future assessment training.

## Requirements

### Requirement 1: Quality Gate Configuration

**User Story:** As an operator, I want to configure a shell command that
validates code after each coder session, so that I get early signal on
regressions.

#### Acceptance Criteria

1. [54-REQ-1.1] THE engine SHALL support a `quality_gate` configuration field
   (string) in `[orchestrator]`. WHEN set, THE engine SHALL execute the command
   after every coder session that completes with status `"completed"`, in the
   project root directory.

2. [54-REQ-1.2] THE engine SHALL support a `quality_gate_timeout`
   configuration field (integer, seconds, default 300) in `[orchestrator]`.
   IF the quality gate command does not exit within the timeout, THE engine
   SHALL send SIGTERM, wait 5 seconds, then SIGKILL. The result SHALL be
   recorded as a gate failure with exit code -1.

3. [54-REQ-1.3] WHEN `quality_gate` is not configured (empty string or absent),
   THE engine SHALL skip quality gate execution entirely. Behavior SHALL be
   identical to the current implementation.

#### Edge Cases

1. [54-REQ-1.E1] IF the quality gate command is not found (e.g.
   `FileNotFoundError`), THEN THE engine SHALL record a gate failure with
   exit code -2 and log a warning with the command string.

2. [54-REQ-1.E2] IF the quality gate command produces more than 10000 lines
   of stdout or stderr, THE engine SHALL capture only the last 50 lines of
   each for the audit event.

### Requirement 2: Quality Gate Result Recording

**User Story:** As an operator, I want quality gate results recorded as audit
events, so that I can track pass/fail trends across runs.

#### Acceptance Criteria

1. [54-REQ-2.1] WHEN the quality gate completes (success or failure), THE
   engine SHALL emit a `quality_gate.result` audit event with payload
   containing: `exit_code` (integer), `stdout_tail` (last 50 lines),
   `stderr_tail` (last 50 lines), `duration_ms` (integer), and `passed`
   (boolean).

2. [54-REQ-2.2] IF the quality gate fails (non-zero exit code or timeout),
   THEN THE session status SHALL be set to `completed_with_gate_failure`.
   This status SHALL be visible in `session_outcomes` and the run summary.

3. [54-REQ-2.3] A quality gate failure SHALL NOT block subsequent sessions.
   The next task group or spec SHALL proceed normally.

#### Edge Cases

1. [54-REQ-2.E1] IF the sink dispatcher is None or `run_id` is empty, THEN
   THE quality gate result SHALL still be logged at info level but no audit
   event SHALL be emitted.

### Requirement 3: Feature Vector — File Count Estimate

**User Story:** As an operator, I want the assessor to consider how many files
a task group will touch, so that multi-file tasks get higher complexity.

#### Acceptance Criteria

1. [54-REQ-3.1] THE feature vector SHALL include a `file_count_estimate` field
   (integer): the count of distinct file paths mentioned in the task group's
   section of `tasks.md`. File paths are detected by the pattern
   `[a-zA-Z_/]+\.\w{1,5}` (alphanumeric with a dot extension).

2. [54-REQ-3.2] WHEN no file paths are detected, THE `file_count_estimate`
   SHALL default to 0.

### Requirement 4: Feature Vector — Cross-Spec Integration

**User Story:** As an operator, I want the assessor to detect tasks that
span multiple specs, so that integration tasks get higher complexity.

#### Acceptance Criteria

1. [54-REQ-4.1] THE feature vector SHALL include a `cross_spec_integration`
   field (boolean): True when the task group's description in `tasks.md`
   references spec names other than its own. Spec names are detected by the
   pattern `\d{2}_[a-z_]+` (e.g. `03_api_routes`).

2. [54-REQ-4.2] WHEN the task group description contains only its own spec
   name or no spec names at all, `cross_spec_integration` SHALL be False.

### Requirement 5: Feature Vector — Language Count

**User Story:** As an operator, I want the assessor to consider how many
programming languages a task involves, so that polyglot tasks get higher
complexity.

#### Acceptance Criteria

1. [54-REQ-5.1] THE feature vector SHALL include a `language_count` field
   (integer): the count of distinct programming language file extensions
   mentioned in the task group's section of `tasks.md`. Recognized extensions:
   `.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`, `.rb`, `.proto`, `.sql`,
   `.toml`, `.yaml`, `.yml`, `.json`.

2. [54-REQ-5.2] WHEN no recognized extensions are found, `language_count`
   SHALL default to 1 (assume the project's primary language).

### Requirement 6: Feature Vector — Historical Median Duration

**User Story:** As an operator, I want the assessor to learn from prior
execution durations for the same spec, so that historically slow specs get
higher complexity predictions.

#### Acceptance Criteria

1. [54-REQ-6.1] THE feature vector SHALL include a
   `historical_median_duration_ms` field (integer or None): the median
   `duration_ms` of successful `execution_outcomes` for the same `spec_name`.

2. [54-REQ-6.2] WHEN no prior successful outcomes exist for the spec,
   `historical_median_duration_ms` SHALL be None.

#### Edge Cases

1. [54-REQ-6.E1] IF there is exactly one prior outcome, THE median SHALL
   equal that single value.

### Requirement 7: Heuristic Assessor Threshold Update

**User Story:** As an operator, I want the heuristic assessor to use the new
signals for better tier predictions.

#### Acceptance Criteria

1. [54-REQ-7.1] THE heuristic assessor SHALL assess tasks with
   `cross_spec_integration=True` or `file_count_estimate >= 8` as ADVANCED
   (confidence 0.7) unless overridden by the statistical model.

2. [54-REQ-7.2] ALL feature vector fields (existing and new) SHALL be
   serialized in the `feature_vector` JSON column of `complexity_assessments`.

#### Edge Cases

1. [54-REQ-7.E1] IF both `cross_spec_integration=True` AND
   `file_count_estimate >= 8`, THE assessor SHALL still predict ADVANCED
   with confidence 0.7 (no double-upgrade).
