# Requirements Document: Git and Platform Overhaul

## Introduction

This document specifies the changes to agent-fox's git branch management,
agent prompt templates, and platform integration layer. It makes the develop
branch setup robust, removes misleading push instructions from agent prompts,
wires post-harvest remote integration into the session lifecycle, and replaces
the `gh` CLI-based GitHub platform with a REST API implementation.

This spec supersedes `10_platform_integration`.

## Glossary

| Term | Definition |
|------|-----------|
| Develop branch | The long-lived local integration branch (named `develop`) where completed feature work is merged |
| Default branch | The repository's primary branch as configured on the remote (typically `main` or `master`) |
| Harvest | The process of merging a feature branch into the local develop branch after a successful session |
| Post-harvest integration | The process of pushing changes to the remote and optionally creating a PR, after harvest completes |
| Platform | The configured remote integration strategy (`"none"` or `"github"`) |
| GITHUB_PAT | A GitHub personal access token used to authenticate REST API calls |
| Feature branch | A git branch created per task group: `feature/{spec_name}/{group_number}` |
| Auto-merge | When enabled, the engine pushes develop to origin after harvest, making changes immediately available on the remote |

## Requirements

### Requirement 1: Ensure Local Develop Branch

**User Story:** As an operator, I want agent-fox to automatically create or
recover the local develop branch so that sessions do not fail due to a missing
branch.

#### Acceptance Criteria

1. [19-REQ-1.1] WHEN a session is about to start and no local `develop` branch
   exists, THE system SHALL check whether a remote `origin/develop` branch
   exists.
2. [19-REQ-1.2] WHEN a remote `origin/develop` exists, THE system SHALL fetch
   it and create a local `develop` branch tracking `origin/develop`.
3. [19-REQ-1.3] WHEN no remote `origin/develop` exists, THE system SHALL
   detect the repository's default branch and create `develop` from it.
4. [19-REQ-1.4] THE system SHALL detect the default branch by reading
   `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main`, then
   `master`.
5. [19-REQ-1.5] WHEN `af init` runs, THE system SHALL use the same develop
   branch ensure logic described in 19-REQ-1.1 through 19-REQ-1.4.

5. [19-REQ-1.6] WHEN a session is about to start and a local `develop` branch
   exists, THE system SHALL fetch `origin` and fast-forward the local `develop`
   to match `origin/develop` if the remote is ahead.

#### Edge Cases

1. [19-REQ-1.E1] IF the local `develop` branch already exists and is
   up-to-date with (or ahead of) `origin/develop`, THEN THE system SHALL
   use it without modification (no-op).
2. [19-REQ-1.E2] IF none of the fallback branches (`main`, `master`) exist
   locally, THEN THE system SHALL raise a `WorkspaceError` with a descriptive
   message.
3. [19-REQ-1.E3] IF `git fetch origin` fails (e.g., no network, no remote
   configured), THEN THE system SHALL log a warning and attempt to create
   `develop` from the local default branch without fetching.
4. [19-REQ-1.E4] IF the local `develop` has diverged from `origin/develop`
   (local has commits not on remote AND remote has commits not on local), THEN
   THE system SHALL log a warning and use the local `develop` as-is without
   fast-forwarding.

---

### Requirement 2: Remove Push Instructions from Agent Prompts

**User Story:** As a developer, I want the coding agent to only commit locally
so that the engine controls all remote interactions and feature branches do not
pile up on GitHub.

#### Acceptance Criteria

1. [19-REQ-2.1] THE `git-flow.md` template SHALL NOT contain any instructions
   to push branches to a remote.
2. [19-REQ-2.2] THE `git-flow.md` "Session Landing Commands" section SHALL
   instruct the agent to commit and verify a clean working tree, without any
   `git push` commands.
3. [19-REQ-2.3] THE `git-flow.md` "Required End State" section SHALL require
   a clean local working tree and committed changes, without requiring the
   branch to be pushed to origin.
4. [19-REQ-2.4] THE `coding.md` template STEP 9 SHALL NOT contain any
   `git push` commands.
5. [19-REQ-2.5] THE `coding.md` template SHALL NOT contain a "FAILURE POLICY"
   section about push retries.

#### Edge Cases

1. [19-REQ-2.E1] IF other template files reference pushing to origin, THEN
   those references SHALL also be removed.

---

### Requirement 3: Post-Harvest Remote Integration

**User Story:** As an operator, I want agent-fox to push changes to the remote
repository after harvest, with behavior controlled by the platform
configuration.

#### Acceptance Criteria

1. [19-REQ-3.1] WHEN the harvester successfully merges a feature branch into
   local `develop` AND no platform is configured (or `type = "none"`), THE
   system SHALL push `develop` to `origin`.
2. [19-REQ-3.2] WHEN the harvester successfully merges AND platform
   `type = "github"` with `auto_merge = true`, THE system SHALL push the
   feature branch to `origin` for reference, then push `develop` to `origin`.
3. [19-REQ-3.3] WHEN the harvester successfully merges AND platform
   `type = "github"` with `auto_merge = false`, THE system SHALL push the
   feature branch to `origin` and create a pull request against the
   repository's default branch (e.g. `main`). THE system SHALL NOT push
   `develop` to `origin`.
4. [19-REQ-3.4] THE post-harvest integration SHALL run after the harvester
   returns successfully, as part of the session lifecycle.

#### Edge Cases

1. [19-REQ-3.E1] IF pushing to `origin` fails (e.g., no network, permission
   denied), THEN THE system SHALL log a warning and continue. The local merge
   into develop is not rolled back.
2. [19-REQ-3.E2] IF PR creation fails (e.g., API error, authentication
   failure), THEN THE system SHALL log a warning and continue. The local merge
   into develop is not rolled back.
3. [19-REQ-3.E3] IF the feature branch has already been deleted locally (e.g.,
   by worktree cleanup), THEN THE system SHALL skip pushing the feature branch
   and log a warning.

---

### Requirement 4: GitHub REST API Platform

**User Story:** As an operator, I want agent-fox to use the GitHub REST API
directly so that I do not need the `gh` CLI installed.

#### Acceptance Criteria

1. [19-REQ-4.1] THE `GitHubPlatform` class SHALL use the GitHub REST API via
   `httpx` to create pull requests, replacing all `gh` CLI usage.
2. [19-REQ-4.2] THE `GitHubPlatform` SHALL authenticate using the `GITHUB_PAT`
   environment variable, sent as a `Bearer` token in the `Authorization`
   header.
3. [19-REQ-4.3] THE `GitHubPlatform.create_pr` method SHALL call
   `POST /repos/{owner}/{repo}/pulls` with the feature branch as `head`, the
   default branch as `base`, and a title and body.
4. [19-REQ-4.4] THE `GitHubPlatform` SHALL detect `{owner}` and `{repo}` from
   the git remote URL (`origin`).

#### Edge Cases

1. [19-REQ-4.E1] IF the `GITHUB_PAT` environment variable is not set, THEN
   THE system SHALL log a warning and fall back to no-platform behavior (push
   develop only, no PR creation).
2. [19-REQ-4.E2] IF the GitHub API returns an authentication error (HTTP 401
   or 403), THEN THE system SHALL log a warning and fall back to no-platform
   behavior.
3. [19-REQ-4.E3] IF the GitHub API returns any other error (HTTP 4xx/5xx),
   THEN THE system SHALL log a warning including the response status and body,
   and continue without creating the PR.
4. [19-REQ-4.E4] IF the remote URL cannot be parsed to extract owner/repo
   (e.g., non-GitHub remote), THEN THE system SHALL log a warning and fall
   back to no-platform behavior.

---

### Requirement 5: Simplified Platform Configuration

**User Story:** As an operator, I want a simpler platform configuration with
only the fields that matter.

#### Acceptance Criteria

1. [19-REQ-5.1] THE `PlatformConfig` model SHALL contain only two fields:
   `type` (default `"none"`) and `auto_merge` (default `false`).
2. [19-REQ-5.2] THE system SHALL accept `type` values of `"none"` and
   `"github"`. Any other value SHALL raise a `ConfigError`.
3. [19-REQ-5.3] THE `auto_merge` field SHALL only be meaningful when
   `type = "github"`. WHEN `type = "none"`, `auto_merge` SHALL be ignored.

#### Edge Cases

1. [19-REQ-5.E1] IF existing config files contain removed fields (`wait_for_ci`,
   `wait_for_review`, `ci_timeout`, `pr_granularity`, `labels`), THEN THE
   system SHALL ignore them without error (pydantic `extra = "ignore"`
   behavior).

---

### Requirement 6: Remove Dead Code

**User Story:** As a developer, I want unused code removed so that the codebase
is easier to understand and maintain.

#### Acceptance Criteria

1. [19-REQ-6.1] THE system SHALL remove the `NullPlatform` class and its
   module (`agent_fox/platform/null.py`).
2. [19-REQ-6.2] THE system SHALL remove `wait_for_ci`, `wait_for_review`, and
   `merge_pr` methods from the `Platform` protocol and `GitHubPlatform`.
3. [19-REQ-6.3] THE system SHALL remove the `create_platform` factory function
   and its module (`agent_fox/platform/factory.py`).
4. [19-REQ-6.4] THE system SHALL update all tests to reflect the removed code,
   removing tests for deleted functionality and adding tests for new behavior.
