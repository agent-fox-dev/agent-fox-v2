# Requirements Document

## Introduction

This specification overhauls the `[platform]` configuration section to
separate code operations (git push) from issue-tracking operations (GitHub
API). Post-harvest integration is simplified to always push via the local
`git` tool, while the platform config is scoped exclusively to issue
tracking for night-shift and future issue-driven workflows.

## Glossary

- **Post-harvest integration**: The phase after a session's work is merged
  to `develop`, where branches are pushed to the remote.
- **Night-shift**: The autonomous maintenance daemon that scans for issues,
  creates findings, and processes fixes.
- **Platform config**: The `[platform]` section in `.agent-fox/config.toml`.
- **Issue tracker**: An external service (e.g., GitHub) used to create, list,
  and manage issues. Distinct from the git forge used for code hosting.
- **Git forge**: The remote hosting service for git repositories (e.g.,
  GitHub, GitHub Enterprise). Identified from the local `.git/config` remote
  URL.
- **API base URL**: The root URL for REST API calls to the issue tracker.
  For `github.com` this is `https://api.github.com`; for GitHub Enterprise
  at `github.example.com` this is `https://github.example.com/api/v3`.

## Requirements

### Requirement 1: Remove auto_merge from PlatformConfig

**User Story:** As a maintainer, I want the platform config to stop
controlling post-harvest push behavior, so that code operations are
decoupled from issue-tracker configuration.

#### Acceptance Criteria

[65-REQ-1.1] WHEN the `PlatformConfig` model is instantiated, THE system
SHALL NOT accept or expose an `auto_merge` field.

[65-REQ-1.2] IF a config file contains an `auto_merge` key in the
`[platform]` section, THEN THE system SHALL silently ignore it without
error (backward compatibility via `extra = "ignore"`).

#### Edge Cases

[65-REQ-1.E1] IF a config file contains both `auto_merge` and other
unknown keys in `[platform]`, THEN THE system SHALL silently ignore all
unknown keys and load only recognized fields (`type`, `url`).

### Requirement 2: Add url field to PlatformConfig

**User Story:** As a user with GitHub Enterprise, I want to specify a
custom issue-tracker URL, so that agent-fox can reach my organization's
API endpoint.

#### Acceptance Criteria

[65-REQ-2.1] THE `PlatformConfig` model SHALL expose a `url` field of
type string.

[65-REQ-2.2] WHEN `type = "github"` and `url` is not explicitly set, THE
system SHALL default `url` to `"github.com"`.

[65-REQ-2.3] WHEN `type = "none"`, THE system SHALL default `url` to an
empty string `""`.

[65-REQ-2.4] WHEN `url` is `"github.com"`, THE `GitHubPlatform` SHALL
resolve the API base URL to `https://api.github.com`.

[65-REQ-2.5] WHEN `url` is a non-default value (e.g., `"github.example.com"`),
THE `GitHubPlatform` SHALL resolve the API base URL to
`https://{url}/api/v3`.

#### Edge Cases

[65-REQ-2.E1] IF `type = "none"` and `url` is explicitly set to a
non-empty value, THEN THE system SHALL accept the config without error
(the `url` value is unused when `type = "none"`).

### Requirement 3: Simplify post-harvest integration

**User Story:** As a developer, I want post-harvest to simply push
branches via local git without calling any forge APIs, so that
authentication is handled by my shell and the process is simpler.

#### Acceptance Criteria

[65-REQ-3.1] WHEN post-harvest integration runs, THE system SHALL push
the feature branch to `origin` via the local `git` tool.

[65-REQ-3.2] WHEN post-harvest integration runs, THE system SHALL push
`develop` to `origin` via the local `git` tool.

[65-REQ-3.3] THE `post_harvest_integrate` function SHALL NOT read or use
`platform_config` in any way.

[65-REQ-3.4] THE `post_harvest_integrate` function SHALL NOT call any
GitHub REST API endpoints.

[65-REQ-3.5] WHEN a push fails, THE system SHALL log a warning and
continue without raising an exception (best-effort).

#### Edge Cases

[65-REQ-3.E1] IF the feature branch no longer exists locally, THEN THE
system SHALL skip the feature-branch push, log a warning, and still
attempt to push develop.

[65-REQ-3.E2] IF `origin/develop` is ahead of local `develop`, THEN THE
system SHALL attempt reconciliation before pushing (existing behavior
preserved).

### Requirement 4: Remove create_pr from platform layer

**User Story:** As a maintainer, I want PR creation removed from the
platform abstraction, so that the platform layer is scoped to issue
operations only.

#### Acceptance Criteria

[65-REQ-4.1] THE `PlatformProtocol` SHALL NOT define a `create_pr`
method.

[65-REQ-4.2] THE `GitHubPlatform` class SHALL NOT implement a `create_pr`
method.

[65-REQ-4.3] THE `GitHubPlatform` class SHALL NOT implement a
`_get_default_branch` helper method (used only by `create_pr`).

### Requirement 5: GitHubPlatform uses configurable API base URL

**User Story:** As a GitHub Enterprise user, I want the GitHub platform
to call my organization's API endpoint, so that issue operations work
with my private instance.

#### Acceptance Criteria

[65-REQ-5.1] WHEN `GitHubPlatform` is constructed, THE system SHALL
accept a `url` parameter (the issue tracker host, e.g., `"github.com"`).

[65-REQ-5.2] WHEN `url` is `"github.com"`, THE `GitHubPlatform` SHALL
use `https://api.github.com` as the API base URL for all requests.

[65-REQ-5.3] WHEN `url` is not `"github.com"` (e.g.,
`"github.example.com"`), THE `GitHubPlatform` SHALL use
`https://{url}/api/v3` as the API base URL for all requests.

#### Edge Cases

[65-REQ-5.E1] IF the `url` parameter is empty or not provided, THEN THE
`GitHubPlatform` SHALL default to `"github.com"` behavior
(`https://api.github.com`).

### Requirement 6: Platform factory passes url to GitHubPlatform

**User Story:** As a night-shift user, I want the platform factory to
wire the configured `url` into the `GitHubPlatform` instance, so that
issue operations target the correct API endpoint.

#### Acceptance Criteria

[65-REQ-6.1] WHEN `create_platform` instantiates a `GitHubPlatform`, THE
system SHALL pass the `url` value from `PlatformConfig` to the
constructor.

[65-REQ-6.2] WHEN `create_platform` reads the git remote to determine
`owner` and `repo`, THE system SHALL parse the remote URL from the local
`.git/config` (existing behavior preserved).

#### Edge Cases

[65-REQ-6.E1] IF the `GITHUB_PAT` environment variable is not set, THEN
THE system SHALL log an error and exit with code 1.

### Requirement 7: Config template generation reflects new schema

**User Story:** As a user generating a fresh config, I want the template
to show the current `[platform]` fields (`type`, `url`) without the
removed `auto_merge` field.

#### Acceptance Criteria

[65-REQ-7.1] WHEN the config template is generated, THE system SHALL
include `type` and `url` fields under `[platform]`.

[65-REQ-7.2] WHEN the config template is generated, THE system SHALL NOT
include an `auto_merge` field under `[platform]`.

[65-REQ-7.3] THE config template SHALL show `url` as a commented-out
override with a description indicating it defaults from `type`.
