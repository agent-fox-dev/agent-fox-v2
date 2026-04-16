# PRD: Fix Branch Push to Upstream

## Overview

During night-shift fix processing, the system creates a local feature branch
(`fix/{slug}`) for each `af:fix` issue. Currently, this branch is local-only
and is destroyed after the fix is harvested into `develop`. This feature adds
an optional configuration to push the fix branch to the upstream remote
(`origin`) so it is visible on the platform for review, auditing, or manual PR
creation.

## Problem

When night-shift fixes issues autonomously, fix branches are transient and
local-only. Operators have no way to inspect the fix branch on GitHub before it
is merged into `develop`. This limits visibility and auditability of autonomous
fixes.

## Proposed Solution

Add a boolean config field `push_fix_branch` (default: `false`) to the
`[night_shift]` section of `config.toml`. When enabled:

1. The fix branch is pushed to the upstream remote (`origin`) after the
   coder-reviewer loop passes but before harvesting into `develop`.
2. The branch name includes the issue number for traceability (e.g.,
   `fix/42-unused-imports`).
3. If a remote branch with the same name already exists, force-push overwrites
   it.
4. The remote branch is left on the remote after the fix is complete (no
   automatic cleanup).
5. Push failures are best-effort -- logged as warnings, never blocking the
   harvest.

## Clarifications

1. "Upstream" means the `origin` remote. No configurable remote name is needed.
2. The existing `fix/{slug}` branch is what gets pushed, with the branch name
   modified to include the issue number for traceability.
3. The push happens BEFORE harvest (merge into develop), so the branch exists
   independently on the remote.
4. Remote branches are left on the remote -- no automatic cleanup after merge.
5. This feature is independent of the existing `merge_strategy` setting
   (`"direct"` or `"pr"`).
6. If a branch with the same name already exists on the remote, force-push
   overwrites it.

## Non-Goals

- Configurable remote name (always uses `origin`).
- Automatic remote branch cleanup after merge.
- PR creation from the pushed branch (handled separately by `merge_strategy`).
