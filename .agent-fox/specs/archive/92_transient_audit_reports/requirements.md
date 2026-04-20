# Requirements Document

## Introduction

This spec changes where auditor reports are written and adds automatic cleanup,
making them truly transient artifacts that never pollute the git working tree.

## Glossary

- **Audit report:** A human-readable Markdown file summarising the auditor's
  per-entry verdicts for a spec's test cases. Produced by
  `persist_auditor_results`.
- **Spec name:** The folder name of a spec (e.g., `91_nightshift_cost_tracking`).
- **Verdict:** The overall auditor result — `PASS`, `FAIL`, or `WEAK`.
- **Spec completion:** The state where all task-graph nodes belonging to a spec
  have status `completed`.

## Requirements

### Requirement 1: Audit Report Output Location

**User Story:** As a developer, I want audit reports written outside of spec
directories, so that they do not appear as untracked files in git.

#### Acceptance Criteria

1. [92-REQ-1.1] WHEN the auditor produces a non-PASS verdict, THE system SHALL
   write the audit report to `.agent-fox/audit/audit_{spec_name}.md` AND return
   `None`.
2. [92-REQ-1.2] WHEN the auditor writes an audit report, THE system SHALL
   ensure the directory `.agent-fox/audit/` exists, creating it if necessary.
3. [92-REQ-1.3] THE system SHALL NOT write `audit.md` files into `.specs/`
   directories.

#### Edge Cases

1. [92-REQ-1.E1] IF the `.agent-fox/audit/` directory cannot be created, THEN
   THE system SHALL log an error and not raise an exception.

### Requirement 2: Overwrite Behaviour

**User Story:** As a developer, I want only the latest audit report per spec,
so that I always see current results without accumulating stale files.

#### Acceptance Criteria

1. [92-REQ-2.1] WHEN the auditor runs for a spec that already has an audit
   report in `.agent-fox/audit/`, THE system SHALL overwrite the existing file.

### Requirement 3: Deletion on PASS Verdict

**User Story:** As a developer, I want audit reports deleted when tests pass,
so that only actionable reports remain on disk.

#### Acceptance Criteria

1. [92-REQ-3.1] WHEN the auditor verdict is PASS, THE system SHALL delete the
   existing audit report file for that spec (if one exists) AND NOT write a new
   report.

#### Edge Cases

1. [92-REQ-3.E1] IF no audit report file exists when a PASS deletion is
   attempted, THEN THE system SHALL proceed without error.
2. [92-REQ-3.E2] IF deletion of the audit report fails due to a filesystem
   error, THEN THE system SHALL log the error and not raise an exception.

### Requirement 4: Deletion on Spec Completion

**User Story:** As a developer, I want leftover audit reports cleaned up when a
spec is fully implemented, so that stale reports do not accumulate.

#### Acceptance Criteria

1. [92-REQ-4.1] WHEN a run completes AND one or more specs have all their
   task-graph nodes in `completed` status, THE system SHALL delete the audit
   report files for those specs.
2. [92-REQ-4.2] THE `cleanup_completed_spec_audits` function SHALL accept a
   project root path and a set of completed spec names, AND delete the
   corresponding audit report files, AND return `None`.

#### Edge Cases

1. [92-REQ-4.E1] IF no audit report files exist for the completed specs, THEN
   THE system SHALL proceed without error.
2. [92-REQ-4.E2] IF deletion fails for one spec, THEN THE system SHALL log a
   warning and continue processing the remaining specs.
