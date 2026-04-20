# PRD: GitHub Issue REST API Migration

## Overview

The agent-fox codebase mandates that all GitHub operations use the REST API via
`httpx` and authenticate with the `GITHUB_PAT` environment variable (established
by spec 19). However, the GitHub issue filing feature introduced by spec 26
(Agent Archetypes) uses the `gh` CLI instead, creating an inconsistency.

This spec migrates GitHub issue operations from the `gh` CLI to the REST API by
extending the existing `GitHubPlatform` class with issue methods and rewriting
`github_issues.py` to use them.

## Problem Statement

1. **`agent_fox/session/github_issues.py`** shells out to `gh issue list`,
   `gh issue create`, `gh issue edit`, `gh issue comment`, and `gh issue close`.
   This requires the `gh` CLI to be installed and authenticated — an external
   dependency that the platform overhaul (spec 19) deliberately eliminated.

2. **`agent_fox/platform/github.py`** (`GitHubPlatform`) only supports PR
   creation. It has no issue operations, even though the REST API supports
   them with the same authentication mechanism (`GITHUB_PAT`).

3. **Spec 26 requirements** (26-REQ-10.1 through 26-REQ-10.E1) explicitly
   reference `gh issue list --search` and "IF the `gh` CLI is unavailable."
   These need errata to reflect the REST API approach.

## Goals

- Extend `GitHubPlatform` with issue operations: search, create, update,
  comment, and close — all via the GitHub REST API.
- Rewrite `file_or_update_issue()` to accept a `GitHubPlatform` instance
  and use REST API methods instead of `gh` CLI commands.
- Preserve the existing behavioral contract: search-before-create
  idempotency, update-on-rerun, close-if-empty, and never-block-on-failure.
- Maintain backward compatibility: callers that cannot provide a
  `GitHubPlatform` instance (missing token, non-GitHub remote) get a
  graceful no-op with a logged warning.
- Create errata documenting the deviation from spec 26's `gh` CLI references.

## Non-Goals

- Adding new issue-related features beyond what spec 26 requires (labels,
  assignees, milestones).
- Modifying the Skeptic or Verifier archetype behavior — only the underlying
  issue filing mechanism changes.
- Changing the `PlatformConfig` schema — issue filing uses the same
  `GITHUB_PAT` and remote-URL parsing already available.

## Clarifications

1. **`file_or_update_issue()` signature change.** The function gains a
   required `platform: GitHubPlatform | None` parameter. When `None`, the
   function logs a warning and returns `None` (same as the current
   `gh`-not-found fallback). Callers construct the platform instance using
   the same pattern as `integration.py`: parse git remote + `GITHUB_PAT`.

2. **No new config fields.** Issue filing reuses the existing `GITHUB_PAT`
   environment variable and `parse_github_remote()` utility. No changes to
   `PlatformConfig` or `AgentFoxConfig`.

3. **Fallback behavior.** Missing `GITHUB_PAT` or non-GitHub remote = log
   warning, skip issue filing. Same user-visible behavior as the current
   `gh`-not-found fallback.

4. **Test strategy.** Tests mock `httpx.AsyncClient` responses (same pattern
   as `tests/unit/platform/test_github_rest.py`), replacing the current
   `_run_gh_command` mocks.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 19_git_and_platform_overhaul | 3 | 1 | `GitHubPlatform` class, `parse_github_remote()`, REST API pattern — group 3 is where the platform module was implemented |
| 26_agent_archetypes | 8 | 2 | `file_or_update_issue()` function and its callers (Skeptic/Verifier post-session logic) — group 8 is where GitHub issue filing was implemented |
