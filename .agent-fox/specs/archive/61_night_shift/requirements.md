# Requirements Document

## Introduction

Night Shift is an autonomous maintenance mode for agent-fox. It runs
continuously as a daemon, scanning the codebase on a timed schedule using both
static tooling and AI-powered agents to discover maintenance issues. Each
finding is reported as a platform issue (GitHub). When issues are labelled
`af:fix`, the system automatically processes them through the full archetype
pipeline (skeptic, coder, verifier) and opens a pull request per fix.

## Glossary

- **Night Shift**: The continuously-running maintenance daemon mode of
  agent-fox, invoked via `agent-fox night-shift`.
- **Hunt category**: A pluggable detection module that scans the codebase for a
  specific class of maintenance issue (e.g. linter debt, dead code). Each
  category is implemented as a dedicated agent with a configurable prompt.
- **Hunt scan**: A scheduled run of all enabled hunt categories against the
  codebase.
- **Issue check**: A scheduled poll of the platform for open issues carrying
  the `af:fix` label.
- **Finding**: A structured report of a detected maintenance issue, produced by
  a hunt category agent in a standardised JSON format.
- **Finding format**: The standardised JSON schema used by all hunt categories
  to report findings, enabling consolidation and issue creation regardless of
  category.
- **Platform**: An external forge (GitHub, GitLab, Gitea) used for issue
  tracking and pull request management. Only GitHub is supported in v1.
- **Platform protocol**: A Python protocol (interface) defining the operations
  required from any platform implementation (create issue, create PR, etc.).
- **af:fix label**: A label on a platform issue indicating that agent-fox
  should autonomously fix the issue.
- **Fix pipeline**: The workflow that takes an `af:fix`-labelled issue through
  investigation, coding, and review using the full archetype pipeline.
- **In-memory spec**: A lightweight spec structure (task prompt, context) built
  at runtime from an issue's content, sufficient for the fix engine without
  persisting full EARS spec files.
- **Archetype pipeline**: The full sequence of agent archetypes (skeptic ->
  coder -> verifier) applied to a fix.

## Requirements

### Requirement 1: Night-Shift Command and Lifecycle

**User Story:** As a developer, I want to start an autonomous maintenance
daemon that runs continuously until I interrupt it, so that maintenance work
happens without manual intervention.

#### Acceptance Criteria

[61-REQ-1.1] WHEN the user runs `agent-fox night-shift`, THE system SHALL
start a continuous event loop that runs until interrupted by SIGINT.

[61-REQ-1.2] WHEN the user passes the `--auto` flag, THE system SHALL
automatically assign the `af:fix` label to every platform issue it creates
during hunt scans.

[61-REQ-1.3] WHEN the system receives SIGINT, THE system SHALL complete the
currently active operation (hunt scan, issue check, or fix session) before
exiting with code 0.

[61-REQ-1.4] WHEN the system receives a second SIGINT during graceful
shutdown, THE system SHALL abort immediately and exit with code 130.

#### Edge Cases

[61-REQ-1.E1] IF the platform is not configured or the access token is
missing, THEN THE system SHALL abort with a descriptive error message and
exit code 1 before entering the event loop.

[61-REQ-1.E2] IF `max_cost` is configured and the accumulated cost reaches
the limit, THEN THE system SHALL log the cost limit, stop dispatching new
work, and exit with code 0.

### Requirement 2: Timed Scheduling

**User Story:** As a developer, I want night-shift to poll for issues and run
hunt scans on configurable intervals, so I can control how aggressively it
works.

#### Acceptance Criteria

[61-REQ-2.1] WHILE night-shift is running, THE system SHALL poll the platform
for open issues with the `af:fix` label at the configured
`issue_check_interval` (default 900 seconds).

[61-REQ-2.2] WHILE night-shift is running, THE system SHALL execute a full
hunt scan at the configured `hunt_scan_interval` (default 14400 seconds).

[61-REQ-2.3] WHEN night-shift starts, THE system SHALL run an initial issue
check and hunt scan immediately, then continue on the timed schedule.

#### Edge Cases

[61-REQ-2.E1] IF the platform API is temporarily unavailable during an issue
check, THEN THE system SHALL log a warning and retry at the next scheduled
interval without crashing.

[61-REQ-2.E2] IF a hunt scan is still in progress when the next hunt scan is
due, THEN THE system SHALL skip the overlapping scan and log an informational
message.

### Requirement 3: Hunt Category Plugin System

**User Story:** As a developer, I want hunt categories to be pluggable so I
can enable/disable categories and add new ones in the future.

#### Acceptance Criteria

[61-REQ-3.1] THE system SHALL ship with seven built-in hunt categories:
dependency freshness, TODO/FIXME resolution, test coverage gaps, deprecated
API usage, linter debt, dead code detection, and documentation drift.

[61-REQ-3.2] WHEN a hunt scan runs, THE system SHALL execute only the hunt
categories enabled in the `[night_shift.categories]` configuration section.

[61-REQ-3.3] THE system SHALL define a hunt category interface that accepts a
project root path and returns a list of findings in the standardised finding
format.

[61-REQ-3.4] WHEN multiple hunt categories are enabled, THE system SHALL
execute independent categories in parallel.

#### Edge Cases

[61-REQ-3.E1] IF a hunt category agent fails or times out, THEN THE system
SHALL log the failure, skip that category for the current scan, and continue
with remaining categories.

### Requirement 4: Two-Phase Detection

**User Story:** As a developer, I want each hunt category to use both static
tools and AI analysis so that deep issues are caught beyond what linters find.

#### Acceptance Criteria

[61-REQ-4.1] WHEN a hunt category executes, THE system SHALL first run any
available static tooling (linters, test runners, dependency checkers) relevant
to that category.

[61-REQ-4.2] WHEN static tooling completes, THE system SHALL invoke a
dedicated Claude agent with the static tool output and the codebase context to
perform deeper analysis.

[61-REQ-4.3] THE system SHALL provide each hunt category agent with a
category-specific prompt template that can be customised in configuration.

#### Edge Cases

[61-REQ-4.E1] IF no static tooling is available for a category, THEN THE
system SHALL proceed with AI-only analysis using the codebase context
directly.

### Requirement 5: Finding Consolidation and Issue Creation

**User Story:** As a developer, I want findings grouped by root cause and
reported as platform issues, so I can review them efficiently each morning.

#### Acceptance Criteria

[61-REQ-5.1] WHEN a hunt scan completes, THE system SHALL group findings by
root cause, then by category.

[61-REQ-5.2] WHEN findings are grouped, THE system SHALL create one platform
issue per finding or finding group, with a title, detailed analysis, and
suggested fix in the issue body.

[61-REQ-5.3] WHEN creating an issue, THE system SHALL include the hunt
category, severity assessment, affected files, and a suggested remediation
approach in the issue body.

[61-REQ-5.4] WHEN `--auto` is active and an issue is created, THE system
SHALL assign the `af:fix` label to the issue.

#### Edge Cases

[61-REQ-5.E1] IF issue creation fails due to a platform API error, THEN THE
system SHALL log the failure with the finding details and continue processing
remaining findings.

### Requirement 6: Fix Pipeline

**User Story:** As a developer, I want issues labelled `af:fix` to be
automatically fixed using the full archetype pipeline, so that fixes are
high-quality and reviewed before merging.

#### Acceptance Criteria

[61-REQ-6.1] WHEN an issue with the `af:fix` label is discovered during an
issue check, THE system SHALL build a lightweight in-memory spec from the
issue title and body.

[61-REQ-6.2] WHEN a fix session starts, THE system SHALL create a feature
branch named `fix/{sanitised-issue-title}` from the current `develop` HEAD.

[61-REQ-6.3] WHEN a fix is executed, THE system SHALL use the full archetype
pipeline (skeptic, coder, verifier) as configured.

[61-REQ-6.4] WHEN a fix session produces implementation details, THE system
SHALL post them as comments on the originating platform issue.

#### Edge Cases

[61-REQ-6.E1] IF the fix session fails after exhausting retries, THEN THE
system SHALL post a comment on the issue describing the failure and move on
to the next issue.

[61-REQ-6.E2] IF the issue body is empty or insufficient for building an
in-memory spec, THEN THE system SHALL post a comment requesting more detail
and skip the issue.

### Requirement 7: PR and Branch Management

**User Story:** As a developer, I want one PR per fix linked to the
originating issue, so I can review each change independently.

#### Acceptance Criteria

[61-REQ-7.1] WHEN a fix session completes successfully, THE system SHALL
create one pull request from the fix branch targeting the main branch.

[61-REQ-7.2] WHEN a pull request is created, THE system SHALL include a
reference to the originating issue number in the PR body.

[61-REQ-7.3] WHEN a pull request is created, THE system SHALL post a comment
on the originating issue linking to the PR.

#### Edge Cases

[61-REQ-7.E1] IF PR creation fails due to a platform API error, THEN THE
system SHALL log the failure and post a comment on the issue with the branch
name for manual PR creation.

### Requirement 8: Platform Abstraction

**User Story:** As a maintainer, I want platform operations behind an abstract
protocol so that GitLab and Gitea support can be added later.

#### Acceptance Criteria

[61-REQ-8.1] THE system SHALL define a platform protocol with operations for:
creating issues, listing issues by label, adding issue comments, assigning
labels, creating pull requests, and parsing remote URLs.

[61-REQ-8.2] THE system SHALL ship a GitHub implementation of the platform
protocol that uses only the GitHub REST API.

[61-REQ-8.3] WHEN the night-shift command starts, THE system SHALL
instantiate the platform implementation based on the `[platform]`
configuration section.

#### Edge Cases

[61-REQ-8.E1] IF the configured platform type has no implementation, THEN THE
system SHALL abort with a descriptive error listing supported platform types.

### Requirement 9: Configuration

**User Story:** As a developer, I want to configure night-shift intervals,
enabled categories, and cost limits so I can tune it to my project's needs.

#### Acceptance Criteria

[61-REQ-9.1] THE system SHALL support a `[night_shift]` configuration section
with `issue_check_interval` (default 900) and `hunt_scan_interval`
(default 14400) as integer seconds.

[61-REQ-9.2] THE system SHALL support a `[night_shift.categories]`
configuration subsection where each of the seven built-in categories can be
enabled or disabled (all enabled by default).

[61-REQ-9.3] WHILE night-shift is running, THE system SHALL honour the
existing `orchestrator.max_cost` and `orchestrator.max_sessions`
configuration limits for cost control.

#### Edge Cases

[61-REQ-9.E1] IF `issue_check_interval` or `hunt_scan_interval` is set to a
value less than 60 seconds, THEN THE system SHALL clamp it to 60 seconds and
log a warning.
