# PRD: Platform Issue Abstraction

## Problem

Issue management code (create, update, close, search issues) currently lives in
two session-layer files:

- `agent_fox/session/github_issues.py` — `file_or_update_issue()` and
  `format_issue_body_from_findings()`
- `agent_fox/session/auditor_output.py` — `handle_auditor_github_issue()` and
  `create_circuit_breaker_issue_title()`

This code is GitHub-specific and tightly coupled to the session module. It
should live in the platform module behind an abstract interface so that
agent-fox can create or update issues on any configured platform (e.g. GitHub
or GitLab), not just GitHub.

The `GitHubPlatform` class in `agent_fox/platform/github.py` already has the
low-level REST API methods for issue operations. The session-layer code
provides higher-level orchestration (search-before-create idempotency) and
formatting that is platform-agnostic in nature but currently imports
`GitHubPlatform` directly.

## Goals

1. **Abstract issue operations** behind a `Platform` protocol in
   `agent_fox/platform/`. Issue operations (create, search, update, close,
   comment) are defined on the protocol. PR operations stay GitHub-specific
   for now.

2. **Move `file_or_update_issue()`** from `agent_fox/session/github_issues.py`
   to the platform module as a platform-agnostic utility that calls the
   abstract protocol.

3. **Refactor `handle_auditor_github_issue()`** in
   `agent_fox/session/auditor_output.py` to use the abstract platform
   interface instead of calling `GitHubPlatform` methods directly.

4. **Implement a `GitLabPlatform`** class that satisfies the protocol, to
   validate the abstraction.

5. **Add a platform factory** that creates the correct platform instance based
   on `PlatformConfig.type`.

## Non-Goals

- Abstracting PR operations (create_pr) — stays GitHub-specific.
- Supporting platforms beyond GitHub and GitLab.
- Changing `PlatformConfig` schema beyond adding `"gitlab"` as a valid type.
- Moving `format_issue_body_from_findings()` — this is session-domain
  formatting logic that produces a markdown string; it stays in the session
  module.

## Current Callers

All three target functions (`file_or_update_issue`,
`handle_auditor_github_issue`, `format_issue_body_from_findings`) are only
imported by tests — no production code calls them at present. This means the
refactoring has no blast radius on runtime behavior; only import paths in
tests need updating.

## Scope

### In Scope

- Define a `Platform` protocol (or ABC) with issue operations.
- `GitHubPlatform` already implements these methods — ensure it satisfies the
  protocol.
- Create `GitLabPlatform` with issue operations using GitLab REST API.
- Move `file_or_update_issue()` to `agent_fox/platform/issues.py` (or
  similar) as a platform-agnostic function.
- Refactor `handle_auditor_github_issue()` to accept `Platform` instead of
  `GitHubPlatform`.
- Add `"gitlab"` to `PlatformConfig.type` valid values.
- Create a factory function: `create_platform(config) -> Platform | None`.
- Update test imports.
- Delete `agent_fox/session/github_issues.py` after moving its code.

### Out of Scope

- Changing how `harvest.py` creates PRs.
- Adding full GitLab PR support.
- CI/CD integration or deployment changes.

## Clarifications

- **Scope of abstraction**: Only issue operations (create, update, close,
  search, comment) are abstracted. PR creation stays on `GitHubPlatform`
  directly.
- **Orchestration location**: `file_or_update_issue()` moves to the platform
  module as a utility function calling the abstract protocol.
- **Auditor refactoring**: `handle_auditor_github_issue()` is renamed to
  `handle_auditor_issue()` and refactored to use the `Platform` protocol.
- **Target platforms**: GitHub and GitLab. Two implementations validate the
  abstraction.

## Dependencies

This spec has no upstream dependencies on other spec task groups.
