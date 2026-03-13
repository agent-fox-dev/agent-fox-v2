# Requirements Document

## Introduction

This specification defines the abstraction of issue management operations
behind a platform-agnostic protocol, enabling agent-fox to create, update,
and close issues on GitHub or GitLab depending on the configured platform.

Currently, issue operations are scattered across `session/github_issues.py`
and `session/auditor_output.py`, tightly coupled to GitHub. This spec
centralizes them in the `platform` module behind an abstract `Platform`
protocol.

## Glossary

- **Platform**: An abstract interface defining issue operations (create,
  search, update, close, comment). Concrete implementations exist for
  GitHub and GitLab.
- **Platform protocol**: A Python `typing.Protocol` class that declares the
  issue operation method signatures. Concrete platform classes satisfy it
  structurally.
- **Issue operations**: The five operations on a platform issue tracker:
  search, create, update, add comment, and close.
- **Search-before-create**: An idempotency pattern where the system searches
  for an existing issue by title prefix before creating a new one, preventing
  duplicates on re-runs.
- **Platform factory**: A function that reads `PlatformConfig` and returns the
  appropriate concrete `Platform` instance (or `None` for type `"none"`).
- **IssueResult**: A dataclass representing a created or found issue, with
  fields: `number`, `title`, `html_url`.
- **PlatformConfig**: Configuration model with `type` field (`"none"`,
  `"github"`, or `"gitlab"`) and `auto_merge` flag.
- **IntegrationError**: The project's error type for external service failures.

## Requirements

### Requirement 1: Platform Protocol

**User Story:** As a developer, I want issue operations defined on an abstract
protocol, so that new platforms can be added without modifying orchestration
code.

#### Acceptance Criteria

1. [48-REQ-1.1] THE `agent_fox.platform` module SHALL export a `Platform`
   protocol class defining five async methods: `search_issues`,
   `create_issue`, `update_issue`, `add_issue_comment`, and `close_issue`.

2. [48-REQ-1.2] WHEN a class implements all five methods with matching
   signatures, THE class SHALL satisfy the `Platform` protocol without
   explicit inheritance.

3. [48-REQ-1.3] THE `Platform` protocol methods SHALL use the same parameter
   names and types as the existing `GitHubPlatform` issue methods.

4. [48-REQ-1.4] THE `Platform` protocol SHALL define a `name` property that
   returns a string identifying the platform (e.g. `"github"`, `"gitlab"`).

#### Edge Cases

1. [48-REQ-1.E1] IF a class implements only a subset of the five methods,
   THEN THE class SHALL NOT satisfy the `Platform` protocol at static type
   check time.

### Requirement 2: GitHubPlatform Conformance

**User Story:** As a developer, I want `GitHubPlatform` to satisfy the
`Platform` protocol, so that existing GitHub integration works unchanged.

#### Acceptance Criteria

1. [48-REQ-2.1] THE `GitHubPlatform` class SHALL satisfy the `Platform`
   protocol without any signature changes to its existing issue methods.

2. [48-REQ-2.2] THE `GitHubPlatform` class SHALL expose a `name` property
   returning `"github"`.

### Requirement 3: GitLabPlatform Implementation

**User Story:** As a developer, I want a `GitLabPlatform` class that
implements issue operations via the GitLab REST API, so that agent-fox can
manage issues on GitLab projects.

#### Acceptance Criteria

1. [48-REQ-3.1] THE `GitLabPlatform` class SHALL implement all five
   `Platform` protocol methods using the GitLab REST API v4.

2. [48-REQ-3.2] THE `GitLabPlatform` class SHALL authenticate using a
   `GITLAB_PAT` environment variable.

3. [48-REQ-3.3] WHEN the `GitLabPlatform` creates an issue, THE method SHALL
   return an `IssueResult` with the issue's `iid` as `number`, `title`, and
   `web_url` as `html_url`.

4. [48-REQ-3.4] THE `GitLabPlatform` class SHALL accept `project_id` (int or
   str) and `token` as constructor arguments.

5. [48-REQ-3.5] THE `GitLabPlatform` class SHALL expose a `name` property
   returning `"gitlab"`.

#### Edge Cases

1. [48-REQ-3.E1] IF the GitLab API returns a non-success status code, THEN
   THE `GitLabPlatform` SHALL raise `IntegrationError` with the status code
   and response text.

2. [48-REQ-3.E2] IF the GitLab issue search returns no matching issues, THEN
   THE `search_issues` method SHALL return an empty list.

### Requirement 4: Platform Factory

**User Story:** As a developer, I want a factory function that creates the
correct platform instance from configuration, so that callers don't need to
know which platform class to instantiate.

#### Acceptance Criteria

1. [48-REQ-4.1] WHEN `PlatformConfig.type` is `"github"`, THE factory
   function SHALL return a `GitHubPlatform` instance.

2. [48-REQ-4.2] WHEN `PlatformConfig.type` is `"gitlab"`, THE factory
   function SHALL return a `GitLabPlatform` instance.

3. [48-REQ-4.3] WHEN `PlatformConfig.type` is `"none"`, THE factory function
   SHALL return `None`.

4. [48-REQ-4.4] THE factory function SHALL accept `PlatformConfig` and a
   repository root path, and SHALL derive platform-specific constructor
   arguments (owner/repo for GitHub, project_id for GitLab) from the
   environment and git remote URL.

#### Edge Cases

1. [48-REQ-4.E1] IF the required environment variable (e.g. `GITHUB_PAT`,
   `GITLAB_PAT`) is not set, THEN THE factory SHALL log a warning and return
   `None`.

2. [48-REQ-4.E2] IF the git remote URL cannot be parsed for the configured
   platform, THEN THE factory SHALL log a warning and return `None`.

3. [48-REQ-4.E3] IF `PlatformConfig.type` is an unrecognized value, THEN THE
   factory SHALL log a warning and return `None`.

### Requirement 5: Move file_or_update_issue to Platform Module

**User Story:** As a developer, I want `file_or_update_issue()` in the
platform module so that it uses the abstract `Platform` protocol and is
decoupled from the session layer.

#### Acceptance Criteria

1. [48-REQ-5.1] THE `file_or_update_issue()` function SHALL be located in
   `agent_fox/platform/issues.py`.

2. [48-REQ-5.2] THE `file_or_update_issue()` function SHALL accept a
   `platform: Platform | None` parameter (using the abstract protocol, not a
   concrete class).

3. [48-REQ-5.3] THE `file_or_update_issue()` function SHALL preserve the
   existing search-before-create behavior: search by title prefix, update if
   found, create if not found, close if empty and `close_if_empty=True`.

4. [48-REQ-5.4] THE `agent_fox/session/github_issues.py` file SHALL be
   deleted after `file_or_update_issue()` is moved to the platform module.

#### Edge Cases

1. [48-REQ-5.E1] IF `platform` is `None`, THEN `file_or_update_issue()` SHALL
   log a warning and return `None` without raising.

2. [48-REQ-5.E2] IF any platform operation raises an exception, THEN
   `file_or_update_issue()` SHALL catch it, log a warning, and return `None`.

### Requirement 6: Refactor Auditor Issue Handling

**User Story:** As a developer, I want auditor issue handling to use the
abstract `Platform` protocol, so it works on any configured platform.

#### Acceptance Criteria

1. [48-REQ-6.1] THE `handle_auditor_github_issue()` function SHALL be renamed
   to `handle_auditor_issue()`.

2. [48-REQ-6.2] THE `handle_auditor_issue()` function SHALL accept a
   `platform: Platform | None` parameter (using the abstract protocol).

3. [48-REQ-6.3] THE `handle_auditor_issue()` function SHALL preserve existing
   behavior: file issue on FAIL verdict, close issue on PASS verdict, using
   the search-before-create pattern.

#### Edge Cases

1. [48-REQ-6.E1] IF `platform` is `None`, THEN `handle_auditor_issue()` SHALL
   log a warning and return without raising.

### Requirement 7: PlatformConfig Extension

**User Story:** As a user, I want to set `platform.type` to `"gitlab"` in my
configuration, so that agent-fox manages issues on my GitLab project.

#### Acceptance Criteria

1. [48-REQ-7.1] THE `PlatformConfig.type` field SHALL accept `"github"`,
   `"gitlab"`, or `"none"` as valid values.

2. [48-REQ-7.2] WHEN `PlatformConfig.type` is `"gitlab"`, THE config
   description/help text SHALL indicate GitLab platform support.

### Requirement 8: Test Import Updates

**User Story:** As a developer, I want all existing tests to pass with the
new import paths after the refactoring.

#### Acceptance Criteria

1. [48-REQ-8.1] WHEN `file_or_update_issue` is imported from
   `agent_fox.platform.issues`, THE existing test assertions SHALL continue
   to pass.

2. [48-REQ-8.2] WHEN `handle_auditor_issue` is imported from
   `agent_fox.session.auditor_output`, THE existing test assertions SHALL
   continue to pass (with the renamed function).
