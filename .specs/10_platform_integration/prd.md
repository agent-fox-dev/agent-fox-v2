# PRD: Platform Integration

**Source:** `.specs/prd.md` -- Section 5 "Platform Integration" (REQ-120 through
REQ-125), Section 6 (platform type, PR granularity, CI timeout, review waiting,
auto-merge, PR labels), Section 8 (invalid configuration, PR error handling).

## Overview

Platform integration enables PR-based workflows for agent-fox. When the platform
is configured as GitHub, the system creates pull requests instead of directly
merging to the development branch. This supports teams that require CI checks,
code review, and controlled merging as part of their development process.

When no platform is configured (the default), the system merges directly to the
development branch -- the same behavior as v1.

## Problem Statement

agent-fox v1 merges completed session work directly to the development branch.
This works well for solo developers but does not fit teams that enforce CI
checks, require PR-based code review, or use auto-merge workflows. Platform
integration adds a configurable abstraction layer: the orchestrator calls the
platform to integrate work, and the platform decides whether that means a direct
merge or a pull request with gates.

## Goals

- Define a `Platform` protocol with methods for PR lifecycle operations:
  creation, CI waiting, review waiting, and merging
- Implement `NullPlatform` for direct-merge behavior (no PRs, the default)
- Implement `GitHubPlatform` using the `gh` CLI for PR operations
- Support configurable PR granularity: one PR per task group ("session") or one
  PR per specification ("spec")
- Support configurable gates: CI check waiting (with timeout), review approval
  waiting, and auto-merge
- Provide a factory function `create_platform(config)` that returns the correct
  implementation based on `PlatformConfig.type`
- Integrate with the orchestrator so that platform operations replace the
  direct-merge step after session completion

## Non-Goals

- Supporting platforms other than GitHub (GitLab, Gitea, Bitbucket) -- the
  Protocol design makes this possible in the future, but only GitHub and "none"
  are implemented now
- Interactive PR review within agent-fox -- the system waits for approval but
  does not review code itself
- PR templates or custom PR body formatting beyond title, body, and labels
- Branch protection rule management -- the system works within existing rules
- Webhook-based CI notification -- polling only

## Key Decisions

- **`gh` CLI over GitHub API** -- The `gh` CLI is simpler than raw REST/GraphQL,
  handles authentication automatically (using the user's existing `gh auth`
  session), and is already a standard developer tool. No additional dependencies
  or token management required.
- **Platform as Protocol, not base class** -- Consistent with the SessionSink
  pattern from spec 11. Protocols are structurally typed, composable, and
  testable without inheritance coupling.
- **NullPlatform for direct merge** -- The default behavior (no PRs) is
  implemented as a concrete class, not a special case. The orchestrator always
  calls the platform; NullPlatform simply merges directly.
- **Polling for CI and review** -- The system polls `gh pr checks` and
  `gh pr view` at intervals rather than using webhooks. Simpler architecture,
  no server component, acceptable latency for batch workflows.
- **PR granularity is a configuration choice, not a per-spec decision** -- The
  same granularity applies to all specs in a run. This keeps the orchestrator
  logic simple.

## Dependencies

| Dependency | Spec | What This Spec Uses |
|------------|------|---------------------|
| Config system | 01 | `PlatformConfig` (type, pr_granularity, wait_for_ci, wait_for_review, auto_merge, ci_timeout, labels) |
| Error hierarchy | 01 | `AgentFoxError`, `IntegrationError`, `ConfigError` |
| Orchestrator integration | 04 | Platform replaces the direct-merge step after session completion |
