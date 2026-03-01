# Requirements Document: Specification Validation

## Introduction

This document specifies the specification validation system for agent-fox v2:
static validation rules, AI-powered semantic analysis, finding reporting, and
the `agent-fox lint-spec` CLI command. It depends on the core foundation
(spec 01) and the planning engine's spec discovery and parsing (spec 02).

## Glossary

| Term | Definition |
|------|-----------|
| Finding | A single validation result: a rule violation detected in a spec file |
| Severity | Classification of a finding's impact: Error, Warning, or Hint |
| Error (severity) | A finding that will break execution or indicates a missing contract |
| Warning (severity) | A finding that is likely to cause problems in practice |
| Hint (severity) | A suggestion for improvement that does not affect execution |
| Static check | A validation rule that examines spec structure without AI assistance |
| AI check | A validation rule that uses an AI model for semantic analysis |
| Spec folder | A directory under `.specs/` named `NN_name/` containing specification files |
| Expected files | The five files every spec folder should contain: `prd.md`, `requirements.md`, `design.md`, `test_spec.md`, `tasks.md` |
| Task group | A top-level numbered entry in `tasks.md` -- the scheduling unit |
| Subtask | A nested checkbox entry within a task group |
| Verification step | A subtask designated to verify the task group's completion (conventionally named `N.V`) |
| Acceptance criterion | A testable condition within a requirement that defines "done" |
| Dependency reference | A cross-spec reference in a `prd.md` dependency table pointing to another spec or task group |

## Requirements

### Requirement 1: Spec Discovery and Orchestration

**User Story:** As a developer, I want `agent-fox lint-spec` to automatically
find and validate all specification folders so I do not have to list them
manually.

#### Acceptance Criteria

1. [09-REQ-1.1] WHEN the lint-spec command is run, THE system SHALL discover
   all spec folders under `.specs/` using the same discovery mechanism as the
   plan command (spec 02).

2. [09-REQ-1.2] THE system SHALL run all enabled validation rules against each
   discovered spec folder and collect all findings into a single report.

3. [09-REQ-1.3] THE system SHALL sort findings in the report by spec name
   (ascending), then by file name, then by severity (Error first, then Warning,
   then Hint).

#### Edge Cases

1. [09-REQ-1.E1] IF the `.specs/` directory does not exist or contains no spec
   folders, THEN THE system SHALL report a single Error-severity finding
   indicating no specifications were found and exit with non-zero code.

---

### Requirement 2: Missing Files Check

**User Story:** As a developer, I want to be warned when a spec folder is
missing expected files so I can complete it before execution.

#### Acceptance Criteria

1. [09-REQ-2.1] FOR EACH discovered spec folder, THE system SHALL check for the
   presence of five expected files: `prd.md`, `requirements.md`, `design.md`,
   `test_spec.md`, and `tasks.md`.

2. [09-REQ-2.2] FOR EACH missing file, THE system SHALL produce an
   Error-severity finding identifying the spec folder and the missing filename.

---

### Requirement 3: Task Group Size Check

**User Story:** As a developer, I want to be warned when a task group has too
many subtasks, because oversized groups are unlikely to complete in a single
coding session.

#### Acceptance Criteria

1. [09-REQ-3.1] FOR EACH task group in a spec's `tasks.md`, THE system SHALL
   count the number of subtasks (nested checkboxes, excluding verification
   steps).

2. [09-REQ-3.2] WHEN a task group contains more than 6 subtasks (excluding
   verification steps), THE system SHALL produce a Warning-severity finding
   identifying the spec, task group number, and subtask count.

---

### Requirement 4: Verification Step Check

**User Story:** As a developer, I want to be warned when a task group is
missing a verification step so I remember to include one.

#### Acceptance Criteria

1. [09-REQ-4.1] FOR EACH task group in a spec's `tasks.md`, THE system SHALL
   check whether the group contains a verification subtask (a subtask whose
   label matches the pattern `N.V` where N is the task group number).

2. [09-REQ-4.2] WHEN a task group lacks a verification step, THE system SHALL
   produce a Warning-severity finding identifying the spec and task group.

---

### Requirement 5: Acceptance Criteria Check

**User Story:** As a developer, I want to be warned when requirements lack
acceptance criteria so I can add them before execution.

#### Acceptance Criteria

1. [09-REQ-5.1] FOR EACH requirement section in a spec's `requirements.md`,
   THE system SHALL check whether the requirement has at least one acceptance
   criterion (a line containing a requirement ID in the format
   `[NN-REQ-N.N]`).

2. [09-REQ-5.2] WHEN a requirement section has no acceptance criteria, THE
   system SHALL produce an Error-severity finding identifying the spec,
   requirement section heading, and file.

---

### Requirement 6: Dependency Reference Check

**User Story:** As a developer, I want broken cross-spec dependency references
caught before execution so they do not cause planning failures.

#### Acceptance Criteria

1. [09-REQ-6.1] THE system SHALL parse cross-spec dependency declarations from
   each spec's `prd.md` dependency table.

2. [09-REQ-6.2] WHEN a dependency references a spec folder that does not exist
   in the discovered set, THE system SHALL produce an Error-severity finding
   identifying the referencing spec and the missing target.

3. [09-REQ-6.3] WHEN a dependency references a task group number that does not
   exist in the target spec's `tasks.md`, THE system SHALL produce an
   Error-severity finding identifying the referencing spec, the target spec,
   and the missing group number.

---

### Requirement 7: Requirement Traceability Check

**User Story:** As a developer, I want to know when a requirement is not
covered by any test so I can add test coverage.

#### Acceptance Criteria

1. [09-REQ-7.1] THE system SHALL collect all requirement IDs from a spec's
   `requirements.md` and all requirement references from the spec's
   `test_spec.md`.

2. [09-REQ-7.2] WHEN a requirement ID appears in `requirements.md` but is
   not referenced by any test case in `test_spec.md`, THE system SHALL produce
   a Warning-severity finding identifying the untraced requirement.

---

### Requirement 8: AI-Powered Semantic Analysis

**User Story:** As a developer, I want optional AI analysis of my acceptance
criteria so I can improve their quality before execution.

#### Acceptance Criteria

1. [09-REQ-8.1] WHERE the `--ai` flag is provided, THE system SHALL send
   acceptance criteria text to an AI model (STANDARD tier) for semantic
   analysis.

2. [09-REQ-8.2] THE AI analysis SHALL identify acceptance criteria that are
   vague or unmeasurable (e.g., "the system should be fast", "the UI should
   look good") and produce Hint-severity findings.

3. [09-REQ-8.3] THE AI analysis SHALL identify acceptance criteria that
   describe how the system should be built rather than what it should do
   (implementation-leaking) and produce Hint-severity findings.

#### Edge Cases

1. [09-REQ-8.E1] IF the AI model is unavailable (no API credentials, network
   error, rate limit), THEN THE system SHALL log a warning, skip AI analysis,
   and continue with static checks only.

---

### Requirement 9: Output and Exit Code

**User Story:** As a developer, I want lint results in multiple formats and a
clear exit code so I can integrate spec validation into scripts and CI.

#### Acceptance Criteria

1. [09-REQ-9.1] THE system SHALL support three output formats: `table`
   (default, Rich-formatted table), `json`, and `yaml`.

2. [09-REQ-9.2] THE `table` format SHALL display findings grouped by spec,
   showing severity, file, rule name, message, and line number (when
   available), followed by a summary line with counts per severity.

3. [09-REQ-9.3] THE `json` and `yaml` formats SHALL serialize the full list of
   findings plus summary counts, suitable for programmatic consumption.

4. [09-REQ-9.4] THE system SHALL exit with a non-zero exit code (1) when any
   Error-severity findings are present.

5. [09-REQ-9.5] THE system SHALL exit with code 0 when no Error-severity
   findings are present, even if Warning or Hint findings exist.
