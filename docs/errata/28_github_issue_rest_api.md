# Errata: Spec 26 GitHub Issue Requirements Superseded by REST API

## Summary

Spec 28 (GitHub Issue REST API Migration) supersedes the following spec 26
requirements that originally specified the `gh` CLI for GitHub issue operations.
The implementation now uses the GitHub REST API via `GitHubPlatform` instead.

## Superseded Requirements

| Requirement | Original (Spec 26) | Current (Spec 28) |
|-------------|--------------------|--------------------|
| 26-REQ-10.1 | File GitHub issues via `gh` CLI | File issues via `GitHubPlatform.create_issue()` REST API |
| 26-REQ-10.2 | Search existing issues via `gh issue list` | Search via `GitHubPlatform.search_issues()` REST API |
| 26-REQ-10.3 | Update/close issues via `gh` CLI | Update/close via `GitHubPlatform.update_issue()`, `close_issue()` REST API |
| 26-REQ-10.E1 | Swallow `gh` CLI failures gracefully | Swallow `IntegrationError` from REST API calls gracefully |

## Impact

- `agent_fox/session/github_issues.py` no longer imports
  `asyncio.create_subprocess_exec` or references the `gh` CLI binary.
- `file_or_update_issue()` now accepts a `platform: GitHubPlatform | None`
  parameter instead of `repo: str | None`.
- Authentication uses `GITHUB_PAT` environment variable (same as PR creation).
- The `gh` CLI is no longer required for any agent-fox operation.
