# Requirements Document

## Introduction

This document specifies requirements for intelligent ordering and dependency
detection in the night-shift fix pipeline. The system analyzes `af:fix`-labeled
GitHub issues for inter-issue dependencies and supersession before processing,
and re-evaluates remaining issues after each fix to detect obsolescence.

## Glossary

- **Fix batch**: The set of open `af:fix`-labeled issues fetched in a single
  issue check cycle.
- **Dependency graph**: A directed acyclic graph where an edge from issue A to
  issue B means "A must be fixed before B."
- **Supersession candidate**: A pair of issues where fixing one is likely to
  make the other obsolete.
- **Triage**: The process of analyzing a fix batch to determine processing
  order, dependencies, and supersession candidates.
- **Staleness check**: A post-fix evaluation to determine whether remaining
  issues in the batch are still relevant after a fix was applied.
- **Explicit reference**: A dependency signal expressed in issue text (e.g.,
  "depends on #123") or via GitHub's relationship metadata.
- **Processing order**: The sequence in which issues are processed by the fix
  pipeline, determined by topological sort of the dependency graph.
- **Cycle breaking**: Resolving circular dependencies by selecting the oldest
  issue in the cycle as the starting point.

## Requirements

### Requirement 1: Base Issue Ordering

**User Story:** As a night-shift operator, I want issues processed in a
predictable order so that older issues are addressed first.

#### Acceptance Criteria

1. [71-REQ-1.1] WHEN the engine fetches `af:fix` issues from the platform,
   THE system SHALL request them sorted by creation date ascending (oldest
   first).
2. [71-REQ-1.2] WHEN no dependency information is available, THE system
   SHALL process issues in ascending issue number order.

#### Edge Cases

1. [71-REQ-1.E1] IF the platform API does not support sort parameters, THEN
   THE system SHALL sort the returned issues by issue number ascending
   locally.

### Requirement 2: Explicit Reference Parsing

**User Story:** As a user, I want to express dependencies between issues using
natural text or GitHub relationships so that the fix pipeline respects them.

#### Acceptance Criteria

1. [71-REQ-2.1] WHEN an issue body contains textual dependency hints, THE
   system SHALL extract dependency edges from them.
2. [71-REQ-2.2] WHEN the platform provides relationship metadata (parent,
   blocks, is-blocked-by), THE system SHALL incorporate these as dependency
   edges.
3. [71-REQ-2.3] THE system SHALL support at minimum the following textual
   patterns (case-insensitive): "depends on #N", "blocked by #N",
   "after #N", "requires #N".

#### Edge Cases

1. [71-REQ-2.E1] IF an explicit reference points to an issue not in the
   current fix batch, THEN THE system SHALL ignore that edge.
2. [71-REQ-2.E2] IF explicit references create a dependency cycle, THEN THE
   system SHALL break the cycle by selecting the oldest issue (lowest
   number) as the starting point and log a warning.

### Requirement 3: AI Batch Triage

**User Story:** As a night-shift operator, I want the system to intelligently
analyze issue relationships before processing so that dependent and
overlapping issues are handled in the optimal order.

#### Acceptance Criteria

1. [71-REQ-3.1] WHEN the fix batch contains 3 or more issues, THE system
   SHALL perform an AI batch triage before processing any fixes.
2. [71-REQ-3.2] THE AI triage SHALL use the ADVANCED model tier.
3. [71-REQ-3.3] THE AI triage SHALL return a recommended processing order,
   dependency edges with rationale, and supersession candidates.
4. [71-REQ-3.4] THE system SHALL merge AI-detected edges with explicit
   reference edges, with explicit edges taking precedence on conflict.
5. [71-REQ-3.5] WHEN the fix batch contains fewer than 3 issues, THE system
   SHALL skip AI triage and use explicit-reference parsing with
   issue-number ordering.

#### Edge Cases

1. [71-REQ-3.E1] IF the AI triage call fails (API error, timeout, or
   unparseable response), THEN THE system SHALL fall back to
   explicit-reference parsing and issue-number ordering.
2. [71-REQ-3.E2] IF the AI triage returns a processing order that violates
   explicit dependency edges, THEN THE system SHALL use the explicit edges
   to correct the order.

### Requirement 4: Dependency Graph Resolution

**User Story:** As a night-shift operator, I want the system to compute a
valid processing order from all dependency sources so that fixes are applied
in the correct sequence.

#### Acceptance Criteria

1. [71-REQ-4.1] THE system SHALL compute a topological sort of the
   dependency graph to determine processing order.
2. [71-REQ-4.2] WHEN multiple issues have no dependency relationship, THE
   system SHALL break ties by ascending issue number.
3. [71-REQ-4.3] WHEN the dependency graph contains a cycle, THE system SHALL
   break it by removing the edge pointing to the oldest issue in the cycle
   and log a warning.

#### Edge Cases

1. [71-REQ-4.E1] IF the dependency graph is empty (no edges), THEN THE
   system SHALL process issues in ascending issue number order.

### Requirement 5: Post-Fix Staleness Check

**User Story:** As a night-shift operator, I want the system to detect when
fixing one issue makes other issues obsolete so that no effort is wasted on
redundant fixes.

#### Acceptance Criteria

1. [71-REQ-5.1] WHEN a fix completes successfully, THE system SHALL evaluate
   remaining unprocessed issues for staleness via an AI call.
2. [71-REQ-5.2] THE staleness check SHALL verify results with the GitHub API
   by re-fetching remaining issues to check for closure or label removal.
3. [71-REQ-5.3] WHEN an issue is determined to be obsolete, THE system SHALL
   close it on GitHub with a comment identifying the fix that resolved it.
4. [71-REQ-5.4] WHEN an issue is closed as obsolete, THE system SHALL remove
   it from the processing queue.

#### Edge Cases

1. [71-REQ-5.E1] IF the staleness AI call fails, THEN THE system SHALL
   still verify with the GitHub API and continue processing remaining
   issues.
2. [71-REQ-5.E2] IF the GitHub API re-fetch fails, THEN THE system SHALL
   log a warning and continue processing remaining issues without removing
   any.
3. [71-REQ-5.E3] IF a fix fails (pipeline error), THEN THE system SHALL
   skip the staleness check and proceed to the next issue.

### Requirement 6: Observability

**User Story:** As an operator, I want triage and staleness decisions visible
in logs and audit events so that I can understand and debug the processing
order.

#### Acceptance Criteria

1. [71-REQ-6.1] WHEN AI triage completes, THE system SHALL log the resolved
   processing order at INFO level.
2. [71-REQ-6.2] WHEN an issue is closed as obsolete by a staleness check,
   THE system SHALL emit an audit event with the closed issue number and
   the fix issue number that resolved it.
3. [71-REQ-6.3] WHEN a dependency cycle is detected and broken, THE system
   SHALL log the cycle members and the break point at WARNING level.
