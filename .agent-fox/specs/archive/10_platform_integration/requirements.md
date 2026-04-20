**SUPERSEDED** by spec `19_git_and_platform_overhaul`.
> This spec is retained for historical reference only.

# Requirements Document: Platform Integration

## Introduction

This document specifies the platform integration layer for agent-fox v2:
the Platform protocol, the NullPlatform (direct merge) implementation, the
GitHubPlatform (`gh` CLI) implementation, the factory function, and the
configuration-driven behavior for PR creation, CI waiting, review waiting,
and auto-merge. It depends on the configuration and error infrastructure
established by spec 01 and integrates into the orchestrator defined by spec 04.

## Glossary

| Term | Definition |
|------|-----------|
| Platform | A Protocol defining the interface for forge integration (PR creation, CI/review gates, merging) |
| NullPlatform | A Platform implementation that merges directly to the development branch without creating PRs |
| GitHubPlatform | A Platform implementation that creates GitHub pull requests using the `gh` CLI |
| PR granularity | The scope of a pull request: "session" means one PR per task group, "spec" means one PR per specification |
| CI waiting | Polling for CI check completion before marking a task as done |
| Review waiting | Polling for PR approval before proceeding with merge |
| Auto-merge | Automatically merging a PR when all configured gates (CI, review) pass |
| `gh` CLI | GitHub's official command-line tool, used for PR operations |
| PR URL | The URL returned by `gh pr create`, used as the handle for subsequent operations |
| Gate | A condition (CI pass, review approval) that must be satisfied before a PR can be merged |

## Requirements

### Requirement 1: Platform Protocol

**User Story:** As a developer of agent-fox, I want a well-defined interface
for platform operations so that different forge implementations can be swapped
without changing the orchestrator.

#### Acceptance Criteria

1. [10-REQ-1.1] THE system SHALL define a `Platform` as a `typing.Protocol`
   with the following async methods: `create_pr`, `wait_for_ci`,
   `wait_for_review`, and `merge_pr`.
2. [10-REQ-1.2] THE `create_pr` method SHALL accept a branch name, title,
   body, and list of labels, and SHALL return the PR URL as a string.
3. [10-REQ-1.3] THE `wait_for_ci` method SHALL accept a PR URL and timeout
   in seconds, and SHALL return a boolean indicating whether CI checks passed.
4. [10-REQ-1.4] THE `wait_for_review` method SHALL accept a PR URL and SHALL
   return a boolean indicating whether the PR was approved.
5. [10-REQ-1.5] THE `merge_pr` method SHALL accept a PR URL and SHALL merge
   the pull request.

---

### Requirement 2: NullPlatform (Direct Merge)

**User Story:** As a developer, I want agent-fox to merge directly to the
development branch by default (no PRs) so that I can use it without any
platform configuration.

#### Acceptance Criteria

1. [10-REQ-2.1] WHEN platform type is "none" (default), THE system SHALL use
   `NullPlatform`, which satisfies the `Platform` protocol.
2. [10-REQ-2.2] THE `NullPlatform.create_pr` method SHALL merge the specified
   branch directly into the development branch using git and SHALL return an
   empty string (no PR URL).
3. [10-REQ-2.3] THE `NullPlatform.wait_for_ci` method SHALL return `True`
   immediately (no CI checks to wait for).
4. [10-REQ-2.4] THE `NullPlatform.wait_for_review` method SHALL return `True`
   immediately (no review to wait for).
5. [10-REQ-2.5] THE `NullPlatform.merge_pr` method SHALL be a no-op (merge
   already happened in `create_pr`).

---

### Requirement 3: GitHubPlatform

**User Story:** As a developer using GitHub, I want agent-fox to create pull
requests for completed work so that my team can review changes through the
standard GitHub workflow.

#### Acceptance Criteria

1. [10-REQ-3.1] WHEN platform type is "github", THE system SHALL use
   `GitHubPlatform`, which satisfies the `Platform` protocol.
2. [10-REQ-3.2] THE `GitHubPlatform.create_pr` method SHALL execute
   `gh pr create` with the specified branch, title, body, and labels, and
   SHALL return the PR URL from the command output.
3. [10-REQ-3.3] THE `GitHubPlatform.wait_for_ci` method SHALL poll
   `gh pr checks` at regular intervals (default: 30 seconds) until all
   checks pass, any check fails, or the timeout expires.
4. [10-REQ-3.4] THE `GitHubPlatform.wait_for_review` method SHALL poll
   `gh pr view` at regular intervals (default: 60 seconds) until the PR
   is approved or changes are requested.
5. [10-REQ-3.5] THE `GitHubPlatform.merge_pr` method SHALL execute
   `gh pr merge` to merge the pull request.

#### Edge Cases

1. [10-REQ-3.E1] IF the `gh` CLI is not installed or not authenticated, THEN
   THE system SHALL raise an `IntegrationError` with a message explaining
   that `gh` must be installed and authenticated.
2. [10-REQ-3.E2] IF `gh pr create` fails (e.g., branch does not exist on
   remote, no permission), THEN THE system SHALL raise an `IntegrationError`
   with the command output.
3. [10-REQ-3.E3] IF CI checks fail (any check reports failure), THEN
   `wait_for_ci` SHALL return `False`.
4. [10-REQ-3.E4] IF the CI timeout expires before all checks complete, THEN
   `wait_for_ci` SHALL return `False`.
5. [10-REQ-3.E5] IF review is rejected (changes requested), THEN
   `wait_for_review` SHALL return `False`.
6. [10-REQ-3.E6] IF `gh pr merge` fails (e.g., merge conflict, branch
   protection), THEN THE system SHALL raise an `IntegrationError` with the
   command output.

---

### Requirement 4: PR Granularity

**User Story:** As a developer, I want to configure whether agent-fox creates
one PR per task group or one PR per specification, so that I can choose the
review granularity that fits my workflow.

#### Acceptance Criteria

1. [10-REQ-4.1] THE platform module SHALL provide building-block primitives
   (`create_pr`, `wait_for_ci`, `wait_for_review`, `merge_pr`) that can be
   called by the orchestrator to implement any PR granularity policy. The
   platform module itself does not implement granularity logic.
2. [10-REQ-4.2] PR granularity policy -- deciding when to create PRs (e.g.,
   one PR per task group "session" vs. one PR per specification "spec") --
   SHALL be an orchestrator-level concern. The orchestrator uses the platform
   primitives to enact the configured `PlatformConfig.pr_granularity` value.

---

### Requirement 5: Platform Factory

**User Story:** As a developer of agent-fox, I want a single factory function
that returns the correct platform implementation based on configuration so
that platform selection logic lives in one place.

#### Acceptance Criteria

1. [10-REQ-5.1] THE system SHALL provide a `create_platform(config)` function
   that accepts a `PlatformConfig` and returns a `Platform` implementation.
2. [10-REQ-5.2] WHEN `config.type` is "none", `create_platform` SHALL return
   a `NullPlatform` instance.
3. [10-REQ-5.3] WHEN `config.type` is "github", `create_platform` SHALL
   return a `GitHubPlatform` instance configured with the provided settings
   (CI timeout, labels, auto-merge, wait flags).

#### Edge Cases

1. [10-REQ-5.E1] IF `config.type` is an unrecognized value (not "none" or
   "github"), THEN `create_platform` SHALL raise a `ConfigError` listing
   valid platform types.
