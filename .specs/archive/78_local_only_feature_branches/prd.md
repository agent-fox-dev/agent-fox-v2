# PRD: Local-Only Feature Branches

## Problem

Agent-fox currently pushes feature branches to the remote git forge during
post-harvest integration. This pollutes the remote with many short-lived
branches that serve no purpose once merged into `develop`. The desired workflow
is: feature branches exist only locally; only the merged `develop` branch (and
`main` for releases) is pushed to the remote.

## Goal

Stop pushing feature branches to the remote. Only push `develop` to origin
during post-harvest integration. Update all agent instructions, skill
templates, and tests to reflect this change.

## Scope

### In Scope

1. **`post_harvest_integrate()`** — Remove the feature branch push. Keep the
   develop push.
2. **Agent instructions template** (`_templates/agents_md.md`) — Update the
   "Landing" instruction and session completion checklist to no longer mention
   pushing the feature branch to origin.
3. **`af-spec` skill template** (`_templates/skills/af-spec`) — Update the
   Definition of Done and git-flow instruction to not reference pushing feature
   branches.
4. **Tests** — Update post-harvest tests to assert that feature branches are
   NOT pushed to origin. Remove or update tests that assert feature branch
   pushing behavior.
5. **Spec errata** — Document the divergence from spec 65 requirements
   (65-REQ-3.1, 65-REQ-3.E1) which mandate feature branch pushing.

### Out of Scope

- **`af-fix` skill** — No changes. It has its own push/PR workflow.
- **`af-release` skill** — No changes. It only pushes `develop` and `main`.
- **Feature branch cleanup** — Feature branches remain locally after merge.
  The existing `make clean-branches` target handles manual cleanup.
- **Remote cleanup** — No deletion of existing remote feature branches.
- **`push_to_remote()` utility** — The function itself is unchanged; it is
  still used to push `develop`.

## Clarifications

- Q: Should af-fix be updated to stop pushing feature branches and creating
  PRs? A: No, af-fix is out of scope.
- Q: Should feature branches be deleted locally after merge? A: No, keep them
  locally.
- Q: Any changes to the release workflow? A: No.
- Q: CLAUDE.md and AGENTS.md both need updating — which is the source?
  A: `_templates/agents_md.md` is the source for both.
- Q: Should existing remote feature branches be cleaned up? A: No, only
  future behavior changes.

## Dependencies

This spec supersedes parts of spec 65 (Platform Config Overhaul), specifically
the requirements related to feature branch pushing (65-REQ-3.1, 65-REQ-3.E1).

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 65_platform_config_overhaul | 3 | 2 | Modifies `post_harvest_integrate()` introduced in group 3 |
