# Requirements Document

## Introduction

This document specifies the requirements for migrating GitHub issue operations
from the `gh` CLI to the GitHub REST API, extending the existing
`GitHubPlatform` class and rewriting the issue filing module.

## Glossary

| Term | Definition |
|------|-----------|
| **GitHubPlatform** | The REST API client class in `agent_fox/platform/github.py` that handles GitHub operations using `httpx` and `GITHUB_PAT` authentication. |
| **Search-before-create** | Idempotency pattern: search for an existing open issue with a matching title before creating a new one, to avoid duplicates on re-runs. |
| **GITHUB_PAT** | Personal Access Token environment variable used to authenticate REST API requests to GitHub. |
| **Issue number** | The integer identifier of a GitHub issue within a repository. |
| **Title prefix** | A string prefix used to search for existing issues by title (e.g., `[Skeptic Review] spec_name`). |

## Requirements

### Requirement 1: GitHubPlatform Issue Search

**User Story:** As a developer, I want to search for existing GitHub issues
by title prefix via the REST API, so that issue filing can check for duplicates
without requiring the `gh` CLI.

#### Acceptance Criteria

1. [28-REQ-1.1] THE `GitHubPlatform` class SHALL provide an async
   `search_issues(title_prefix, state)` method that queries the GitHub REST API
   search endpoint and returns a list of matching issue numbers and titles.

2. [28-REQ-1.2] THE `search_issues()` method SHALL use the
   `GET /search/issues` endpoint with query parameter
   `repo:{owner}/{repo} in:title {title_prefix} state:{state} type:issue`.

3. [28-REQ-1.3] THE `search_issues()` method SHALL default the `state`
   parameter to `"open"`.

#### Edge Cases

1. [28-REQ-1.E1] IF the search API returns a non-200 status code, THEN THE
   method SHALL raise an `IntegrationError` with the status code and response
   body.

2. [28-REQ-1.E2] IF the search returns zero results, THEN THE method SHALL
   return an empty list.

---

### Requirement 2: GitHubPlatform Issue Creation

**User Story:** As a developer, I want to create GitHub issues via the REST
API, so that Skeptic and Verifier findings are visible on GitHub without
requiring the `gh` CLI.

#### Acceptance Criteria

1. [28-REQ-2.1] THE `GitHubPlatform` class SHALL provide an async
   `create_issue(title, body)` method that creates a GitHub issue via
   `POST /repos/{owner}/{repo}/issues` and returns the issue number and URL.

2. [28-REQ-2.2] WHEN the API returns status 201, THE method SHALL return a
   tuple of `(issue_number: int, html_url: str)`.

#### Edge Cases

1. [28-REQ-2.E1] IF the create API returns a non-201 status code, THEN THE
   method SHALL raise an `IntegrationError` with the status code and response
   body.

---

### Requirement 3: GitHubPlatform Issue Update

**User Story:** As a developer, I want to update an existing GitHub issue's
body via the REST API, so that re-runs replace stale findings.

#### Acceptance Criteria

1. [28-REQ-3.1] THE `GitHubPlatform` class SHALL provide an async
   `update_issue(issue_number, body)` method that updates the issue body via
   `PATCH /repos/{owner}/{repo}/issues/{issue_number}`.

2. [28-REQ-3.2] THE `GitHubPlatform` class SHALL provide an async
   `add_issue_comment(issue_number, comment)` method that adds a comment via
   `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`.

#### Edge Cases

1. [28-REQ-3.E1] IF the update or comment API returns an error status, THEN
   THE method SHALL raise an `IntegrationError`.

---

### Requirement 4: GitHubPlatform Issue Close

**User Story:** As a developer, I want to close a GitHub issue via the REST
API, so that resolved Skeptic findings can be automatically closed.

#### Acceptance Criteria

1. [28-REQ-4.1] THE `GitHubPlatform` class SHALL provide an async
   `close_issue(issue_number, comment)` method that sets the issue state to
   `"closed"` via `PATCH /repos/{owner}/{repo}/issues/{issue_number}` and
   optionally adds a closing comment.

#### Edge Cases

1. [28-REQ-4.E1] IF the close API returns an error status, THEN THE method
   SHALL raise an `IntegrationError`.

---

### Requirement 5: Rewrite file_or_update_issue to Use REST API

**User Story:** As a developer, I want `file_or_update_issue()` to use the
`GitHubPlatform` REST API methods instead of the `gh` CLI, so that issue filing
is consistent with the rest of the platform layer.

#### Acceptance Criteria

1. [28-REQ-5.1] THE `file_or_update_issue()` function SHALL accept a
   `platform: GitHubPlatform | None` parameter.

2. [28-REQ-5.2] WHEN `platform` is not None, THE function SHALL use the
   platform's `search_issues()`, `create_issue()`, `update_issue()`,
   `add_issue_comment()`, and `close_issue()` methods instead of `gh` CLI
   commands.

3. [28-REQ-5.3] THE function SHALL preserve the existing behavioral contract:
   search-before-create idempotency, update body and add comment on re-run,
   close-if-empty when configured, and return issue URL or None.

4. [28-REQ-5.4] THE `file_or_update_issue()` module SHALL contain no imports
   of `asyncio.create_subprocess_exec` or references to the `gh` CLI after
   migration.

#### Edge Cases

1. [28-REQ-5.E1] IF `platform` is None, THEN THE function SHALL log a warning
   and return None without attempting any GitHub operations.

2. [28-REQ-5.E2] IF any REST API call raises an `IntegrationError`, THEN THE
   function SHALL catch the exception, log a warning, and return None. GitHub
   issue filing SHALL NOT block session completion.

---

### Requirement 6: Errata for Spec 26

**User Story:** As a developer, I want spec 26's `gh` CLI references documented
as superseded, so that future readers know the implementation uses the REST API.

#### Acceptance Criteria

1. [28-REQ-6.1] THE implementation SHALL create an errata document at
   `docs/errata/28_github_issue_rest_api.md` noting that spec 26 requirements
   26-REQ-10.1, 26-REQ-10.2, 26-REQ-10.3, and 26-REQ-10.E1 now use the
   GitHub REST API instead of the `gh` CLI.
