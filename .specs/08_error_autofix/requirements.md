# Requirements Document: Error Auto-Fix

## Introduction

This document specifies the error auto-fix system for agent-fox v2: automatic
detection of quality checks, failure collection and clustering, fix spec
generation, the iterative fix loop, and the summary report. It depends on core
foundation (spec 01), the session runner (spec 03), and the orchestrator (spec
04).

## Glossary

| Term | Definition |
|------|-----------|
| Quality check | A project-level command that validates code quality: test runner, linter, type checker, or build tool |
| Check descriptor | A structured record describing a detected quality check: name, command, category (test, lint, type, build) |
| Failure record | A structured record capturing a single quality check failure: check name, output text, exit code |
| Failure cluster | A group of related failure records believed to share a common root cause |
| Fix spec | An ephemeral specification generated for a failure cluster, containing requirements, design, tests, and tasks sufficient for a coding session |
| Fix pass | One complete cycle: run all checks, cluster failures, generate specs, run sessions |
| Fix loop | The iterative process of running fix passes until all checks pass or a termination condition is met |
| Fix report | A summary of the fix loop: passes completed, clusters resolved/remaining, sessions consumed, termination reason |
| Detection | The process of discovering available quality checks by inspecting project configuration files |
| AI clustering | Using an AI model (STANDARD tier) to semantically group failures by likely root cause |
| Fallback clustering | Grouping failures by check command when AI clustering is unavailable |

## Requirements

### Requirement 1: Quality Check Detection

**User Story:** As a developer, I want `agent-fox fix` to automatically detect
which quality checks are available in my project so I do not have to configure
them manually.

#### Acceptance Criteria

1. [08-REQ-1.1] WHEN the fix command is run, THE system SHALL inspect project
   configuration files to detect available quality checks.

2. [08-REQ-1.2] THE system SHALL detect the following check types by their
   configuration indicators:
   - pytest: `[tool.pytest]` or `[tool.pytest.ini_options]` in `pyproject.toml`
   - ruff: `[tool.ruff]` in `pyproject.toml`
   - mypy: `[tool.mypy]` in `pyproject.toml`
   - npm test: `"test"` script in `package.json`
   - npm lint: `"lint"` script in `package.json`
   - make test: `test` target in `Makefile`
   - cargo test: `[package]` section in `Cargo.toml`

3. [08-REQ-1.3] FOR EACH detected check, THE system SHALL produce a check
   descriptor containing: a human-readable name, the shell command to execute,
   and the check category (test, lint, type, build).

#### Edge Cases

1. [08-REQ-1.E1] IF no quality checks are detected, THEN THE system SHALL
   report an error explaining that no checks were found and exit with non-zero
   code.

2. [08-REQ-1.E2] IF a configuration file exists but cannot be parsed (invalid
   TOML, invalid JSON), THEN THE system SHALL log a warning, skip that file,
   and continue detecting from other files.

---

### Requirement 2: Failure Collection

**User Story:** As a developer, I want the system to run all detected quality
checks and capture their failures so I can see what is broken.

#### Acceptance Criteria

1. [08-REQ-2.1] THE system SHALL execute each detected quality check command
   as a subprocess, capturing stdout and stderr.

2. [08-REQ-2.2] WHEN a check command exits with a non-zero exit code, THE
   system SHALL create a failure record containing: the check descriptor,
   combined stdout/stderr output, and exit code.

3. [08-REQ-2.3] WHEN all check commands exit with code 0, THE system SHALL
   report that all checks pass and terminate the fix loop.

#### Edge Cases

1. [08-REQ-2.E1] IF a check command times out (exceeding a reasonable
   subprocess timeout of 5 minutes), THEN THE system SHALL record a failure
   with a timeout error message and continue with remaining checks.

---

### Requirement 3: Failure Clustering

**User Story:** As a developer, I want related failures grouped by root cause
so the fix sessions address the underlying problem rather than individual
symptoms.

#### Acceptance Criteria

1. [08-REQ-3.1] WHEN AI clustering is available, THE system SHALL send failure
   records to the STANDARD model tier with a prompt requesting grouping by
   likely root cause, and parse the model's response into failure clusters.

2. [08-REQ-3.2] EACH failure cluster SHALL include: a descriptive label
   summarizing the root cause, the list of failure records in the cluster,
   and the suggested fix approach.

3. [08-REQ-3.3] WHEN AI clustering is unavailable (no API credentials, network
   error, model error), THE system SHALL fall back to one cluster per check
   command, using the check name as the cluster label.

---

### Requirement 4: Fix Specification Generation

**User Story:** As a developer, I want the system to generate fix
specifications for each failure cluster so coding sessions have clear
instructions.

#### Acceptance Criteria

1. [08-REQ-4.1] FOR EACH failure cluster, THE system SHALL generate a fix
   specification containing: a requirements section describing what needs to be
   fixed, a design section with the suggested approach, the relevant failure
   output, and a task list.

2. [08-REQ-4.2] THE system SHALL write generated fix specs to
   `.agent-fox/fix_specs/` in directories named with a pass number prefix:
   `pass_{pass_number}_{sanitized_label}/` (sanitized for filesystem safety).

---

### Requirement 5: Iterative Fix Loop

**User Story:** As a developer, I want the system to keep fixing until
everything passes or a limit is reached so I do not have to re-run manually.

#### Acceptance Criteria

1. [08-REQ-5.1] THE system SHALL iterate: run quality checks, cluster
   failures, generate fix specs, run coding sessions for each cluster, then
   re-run quality checks.

2. [08-REQ-5.2] THE system SHALL terminate the fix loop when ANY of the
   following conditions is met: all quality checks pass, the maximum number of
   passes is reached (default 3, configurable via `--max-passes`), the
   configured cost limit is reached, or the user interrupts (Ctrl+C).

3. [08-REQ-5.3] FOR EACH fix coding session, THE system SHALL use the same
   SessionRunner machinery as regular coding sessions, ensuring consistent
   timeout enforcement, security, and outcome capture.

---

### Requirement 6: Fix Report

**User Story:** As a developer, I want a summary report after the fix loop
completes so I know what was fixed and what remains.

#### Acceptance Criteria

1. [08-REQ-6.1] WHEN the fix loop terminates, THE system SHALL produce a
   summary report containing: total passes completed, failure clusters resolved
   (checks now passing), failure clusters remaining (checks still failing),
   total coding sessions consumed, and the termination reason.

2. [08-REQ-6.2] THE termination reason SHALL be one of: `all_fixed` (all
   checks pass), `max_passes` (pass limit reached), `cost_limit` (cost ceiling
   reached), or `interrupted` (user Ctrl+C).

---

### Requirement 7: CLI Command

**User Story:** As a developer, I want an `agent-fox fix` command with options
to control behavior.

#### Acceptance Criteria

1. [08-REQ-7.1] THE system SHALL expose the fix functionality as `agent-fox
   fix`, registered as a subcommand of the main CLI group.

2. [08-REQ-7.2] THE command SHALL accept a `--max-passes` option (integer,
   default 3) controlling the maximum number of fix passes.

#### Edge Cases

1. [08-REQ-7.E1] IF `--max-passes` is set to 0 or a negative number, THEN THE
   system SHALL clamp it to 1 and log a warning.
