# PRD: Git and Platform Overhaul

## Summary

Overhaul how agent-fox manages git branches and interacts with remote
repositories. Make the develop branch setup robust, remove misleading push
instructions from agent prompts, wire the platform layer into the post-harvest
flow, and simplify the platform to use the GitHub REST API instead of the `gh`
CLI.

## Supersedes

- `10_platform_integration` — fully replaced by this spec.

## Motivation

1. **Fragile develop branch.** If the local `develop` branch is missing when a
   session starts, `create_worktree` fails with a git error and the session
   never runs. No recovery is attempted.
2. **Misleading agent prompts.** The `git-flow.md` and `coding.md` prompt
   templates instruct the coding agent to push feature branches to origin. The
   engine never does this itself — the pushed branches are orphaned artifacts
   that pile up on GitHub.
3. **Platform layer not wired in.** The platform module (`NullPlatform`,
   `GitHubPlatform`, factory) is fully implemented but never called by the
   orchestrator or session lifecycle. The harvester handles all merging directly.
4. **`gh` CLI dependency.** The GitHub platform requires the `gh` CLI to be
   installed and authenticated. Using the GitHub REST API with a `GITHUB_PAT`
   environment variable is simpler and more portable.
5. **Dead code.** `wait_for_ci` and `wait_for_review` are implemented but never
   called. They add complexity without value.

## Requirements

### 1. Robust develop branch

Before a session starts, ensure a local `develop` branch exists:

- If a remote `develop` exists (`origin/develop`), fetch and create a local
  tracking branch from it.
- If no remote `develop` exists, create `develop` from the repository's default
  branch (detected via `git symbolic-ref refs/remotes/origin/HEAD`, falling back
  to `main`, then `master`).

The same logic should apply during `af init`.

### 2. Remove push instructions from agent prompts

Remove all instructions that tell the coding agent to push feature branches to
origin:

- `git-flow.md`: Remove the "Session Landing Commands" push instruction and the
  "Required End State" push requirement.
- `coding.md`: Remove the `git push origin HEAD` from STEP 9, remove the
  FAILURE POLICY section about push retries.

The agent should commit locally. The engine handles all remote interactions.

### 3. Post-harvest remote integration

After the harvester merges a feature branch into local `develop`:

- **No platform or `type = "none"`:** Push `develop` to `origin`.
- **Platform `type = "github"`, `auto_merge = true`:** Push the feature branch
  to `origin` for reference, then push `develop` to `origin`.
- **Platform `type = "github"`, `auto_merge = false`:** Push the feature branch
  to `origin` and create a pull request against `main`. The user merges
  manually. Do not push `develop` to `origin`.

### 4. Simplify platform layer

- **Remove `NullPlatform`:** When there is no platform configuration (or
  `type = "none"`), the engine pushes `develop` directly. No Platform object
  needed.
- **Remove `wait_for_ci`, `wait_for_review`, `merge_pr`:** These are dead code.
  Keep only `create_pr` (and the push logic).
- **Replace `gh` CLI with GitHub REST API:** Use `httpx` (already a project
  dependency via the Anthropic SDK) to call the GitHub REST API. Authenticate
  with the `GITHUB_PAT` environment variable.
- **Remove config fields:** `wait_for_ci`, `wait_for_review`, `ci_timeout`,
  `pr_granularity`, `labels` are removed from `PlatformConfig`.
- **GITHUB_PAT missing:** If the environment variable is not set or the API
  returns 401, log a warning and fall back to no-platform behavior (push
  develop only, no PR).

### 5. Config changes

The simplified `PlatformConfig`:

```toml
[platform]
type = "none"          # "none" or "github"
auto_merge = false     # only relevant when type = "github"
```

All other fields are removed.

## Clarifications

1. `auto_merge = true` means agent-fox merges the local feature branch into
   local develop and pushes the merged develop to remote. It is equivalent to
   pushing the feature branch and auto-merging a PR against remote develop.
2. `auto_merge = false` creates a PR against `main` (not develop). The user
   merges manually.
3. `merge_pr` is dead code in the new design and is removed.
4. If `GITHUB_PAT` is missing or invalid, warn and fall back to no-platform
   behavior.
5. `ci_timeout`, `pr_granularity`, `labels`, `wait_for_ci`, `wait_for_review`
   are all removed from config.
6. `NullPlatform` is removed entirely. No-platform behavior is handled inline.
7. All push references are removed from both `git-flow.md` and `coding.md`.
8. Default branch detection uses `git symbolic-ref refs/remotes/origin/HEAD`,
   falling back to `main`, then `master`.
9. The harvester keeps its existing merge logic (FF -> rebase -> merge commit ->
   -X theirs). The platform layer only handles the remote side (push, PR).
10. This spec fully supersedes spec `10_platform_integration`.
