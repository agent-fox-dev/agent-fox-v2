# PRD: Platform Config Overhaul

## Problem Statement

The `[platform]` config section currently conflates two concerns: git code
operations (push, PR creation) and issue tracking (create/list/comment on
issues). The `auto_merge` flag controls post-harvest behavior (push develop vs.
create PR), coupling platform configuration to the git integration workflow.

This creates unnecessary complexity:

- Post-harvest should simply push branches via the local `git` tool.
  Authentication is handled by the shell (SSH keys, credential helpers).
  Agent-fox should not manage credentials or call forge APIs for code
  operations.
- Issue tracking (used by night-shift) is a separate concern. Code may live in
  one forge while issues are tracked in another (e.g., GitHub Enterprise, or
  in a future spec, Jira).

## Goals

1. **Remove `auto_merge`** from `PlatformConfig` and all associated code paths.
2. **Simplify post-harvest** to always push feature branch + develop via local
   `git`, ignoring platform config entirely.
3. **Drop `create_pr`** from `GitHubPlatform` and `PlatformProtocol` — PR
   creation is no longer an agent-fox responsibility.
4. **Add `url` field** to `PlatformConfig` for issue tracker base URL, with
   sensible defaults inferred from `type` (e.g., `type = "github"` defaults
   to `github.com`; `url` overrides for GitHub Enterprise).
5. **Scope `[platform]` config to issue operations only** — night-shift and
   any future issue-driven workflows.
6. **Retain `PlatformProtocol`** for future platform extensibility.
7. **Hardcode token env var per platform type** (e.g., `GITHUB_PAT` for
   GitHub). No credential storage in config files.

## Non-Goals

- Supporting non-GitHub issue trackers (Jira, GitLab, etc.) — future spec.
- Changing night-shift's issue polling or fix pipeline logic beyond removing
  `create_pr`.
- Modifying git branch strategy or harvest merge logic.

## Clarifications

- **Q: What is `url` for?** The API base URL for the issue tracker. When
  `type = "github"`, defaults to `github.com` (resolving to
  `https://api.github.com`). Override with e.g. `url = "github.example.com"`
  for GitHub Enterprise (resolving to `https://github.example.com/api/v3`).
- **Q: Token env var?** Hardcoded per platform type (`GITHUB_PAT` for GitHub).
  Not configurable in the config file.
- **Q: Post-harvest behavior?** Purely "push feature branch + push develop to
  origin via local git." Platform config is completely ignored by post-harvest.
- **Q: `create_pr` removal?** Dropped from `GitHubPlatform`,
  `PlatformProtocol`, and all call sites. Night-shift only needs issue
  operations.
- **Q: Non-GitHub trackers?** Out of scope. Architecture should allow future
  extension but only GitHub is implemented now.

## Config Shape (After)

```toml
[platform]
## Platform type (none or github) (default: "none")
type = "github"
## Issue tracker URL — defaults from type (default: "github.com" when type="github")
# url = "github.example.com"
```

## Dependencies

This spec has no upstream spec dependencies (all prerequisite code exists).

## Supersedes

- `19_git_and_platform_overhaul` (archived) — requirements 19-REQ-3.2,
  19-REQ-3.3, 19-REQ-5.2 (auto_merge field and PR-creation post-harvest
  behavior) are fully replaced by this spec. Requirement 19-REQ-3.1
  (type="none" push develop) is subsumed into simplified post-harvest.
