# Requirements Document

## Introduction

This specification defines a new night-shift hunt category that detects
failing quality gates (tests, linters, type checkers, build tools) by
auto-discovering and executing project quality checks, then using AI
analysis to produce structured findings for each failure.

## Glossary

- **Quality gate**: A command-line tool (pytest, ruff, mypy, npm test, cargo
  test, make test, etc.) whose exit code indicates whether the codebase
  meets a quality standard.
- **Hunt category**: A pluggable detection module in the night-shift daemon
  that implements the `HuntCategory` protocol and produces `Finding`
  objects during a hunt scan.
- **Check descriptor**: A `CheckDescriptor` data structure representing a
  detected quality check, containing the check name, shell command, and
  category (test, lint, type, build).
- **Failure record**: A `FailureRecord` data structure capturing the output
  and exit code of a failed quality check.
- **Finding**: The standardised output dataclass from a hunt category,
  containing category, title, description, severity, affected files,
  suggested fix, evidence, and group key.
- **Static phase**: The first phase of the two-phase detection pattern
  where concrete tools are executed and their output is captured.
- **AI phase**: The second phase where captured output is sent to an LLM
  for root-cause analysis and structured finding generation.

## Requirements

### Requirement 1: Check Detection

**User Story:** As a night-shift operator, I want quality checks to be
auto-discovered from project configuration files so that I don't have to
manually configure which checks to run.

#### Acceptance Criteria

[67-REQ-1.1] WHEN the quality_gate category executes its static phase,
THE system SHALL call `detect_checks()` from `agent_fox.fix.checks` to
discover available quality checks from project configuration files.

[67-REQ-1.2] WHEN `detect_checks()` returns an empty list, THE system
SHALL skip check execution and return zero findings.

#### Edge Cases

[67-REQ-1.E1] IF `detect_checks()` raises an exception, THEN THE system
SHALL log a warning and return zero findings without crashing.

### Requirement 2: Check Execution

**User Story:** As a night-shift operator, I want detected quality checks
to be executed as subprocesses so that real failures are captured.

#### Acceptance Criteria

[67-REQ-2.1] WHEN quality checks are detected, THE system SHALL execute
each check as a subprocess in the project root directory.

[67-REQ-2.2] THE system SHALL use a configurable timeout for each check
subprocess, defaulting to 600 seconds.

[67-REQ-2.3] WHEN a check exits with code 0, THE system SHALL treat it
as passing and exclude it from AI analysis.

[67-REQ-2.4] WHEN a check exits with a non-zero code, THE system SHALL
capture combined stdout and stderr as a `FailureRecord`.

#### Edge Cases

[67-REQ-2.E1] IF a check subprocess exceeds the timeout, THEN THE system
SHALL terminate it and record a `FailureRecord` with exit code -1 and a
timeout message.

[67-REQ-2.E2] IF all checks pass, THEN THE system SHALL return zero
findings (silent success).

### Requirement 3: AI Root-Cause Analysis

**User Story:** As a night-shift operator, I want failure output to be
analysed by AI so that the resulting findings have meaningful root-cause
descriptions and actionable fix suggestions.

#### Acceptance Criteria

[67-REQ-3.1] WHEN one or more checks fail, THE system SHALL send the
failure output to the AI backend for root-cause analysis.

[67-REQ-3.2] THE system SHALL produce exactly one Finding per failing
check, regardless of how many individual errors the check reported.

[67-REQ-3.3] WHEN generating a Finding, THE system SHALL populate the
`evidence` field with the check's raw output (truncated to a reasonable
limit to avoid token exhaustion).

[67-REQ-3.4] WHEN generating a Finding, THE system SHALL set the
`group_key` to the check name (e.g., "quality_gate:pytest") to enable
finding consolidation.

#### Edge Cases

[67-REQ-3.E1] IF the AI backend fails or returns unparseable output,
THEN THE system SHALL fall back to a mechanically generated Finding
with the check name as title and the raw output as description.

### Requirement 4: Finding Severity Mapping

**User Story:** As a night-shift operator, I want findings to have
appropriate severity levels so that critical failures are prioritised.

#### Acceptance Criteria

[67-REQ-4.1] WHEN a check in the `test` category fails, THE system
SHALL assign severity `critical`.

[67-REQ-4.2] WHEN a check in the `type` category fails, THE system
SHALL assign severity `major`.

[67-REQ-4.3] WHEN a check in the `lint` category fails, THE system
SHALL assign severity `minor`.

[67-REQ-4.4] WHEN a check in the `build` category fails, THE system
SHALL assign severity `critical`.

### Requirement 5: Configuration

**User Story:** As a night-shift operator, I want to enable/disable the
quality gate category and configure its timeout via the config file.

#### Acceptance Criteria

[67-REQ-5.1] THE system SHALL add a `quality_gate` boolean toggle
(default: `True`) to `NightShiftCategoryConfig` to enable or disable
the category.

[67-REQ-5.2] THE system SHALL add a `quality_gate_timeout` integer field
(default: 600) to `NightShiftConfig` to configure the per-check timeout
in seconds.

[67-REQ-5.3] WHEN `quality_gate_timeout` is set below 60, THE system
SHALL clamp it to 60 and log a warning.

### Requirement 6: Integration

**User Story:** As a night-shift operator, I want the quality gate
category to integrate seamlessly with the existing hunt scanner.

#### Acceptance Criteria

[67-REQ-6.1] THE system SHALL register `QualityGateCategory` in the
`HuntCategoryRegistry` alongside the seven existing built-in categories.

[67-REQ-6.2] THE system SHALL export `QualityGateCategory` from
`agent_fox.nightshift.categories`.

[67-REQ-6.3] WHEN the hunt scanner runs enabled categories in parallel,
THE quality_gate category SHALL execute independently without blocking
or being blocked by other categories.
