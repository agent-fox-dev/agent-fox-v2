# Erratum: Spec 65 — No Feature Branch Push

**Spec:** 65 (Simplified Post-Harvest Integration)
**Superseded by:** Spec 78 (Local-Only Feature Branches)
**Affected Requirements:** 65-REQ-3.1, 65-REQ-3.E1

## Summary

Spec 78 removes the feature branch push from `post_harvest_integrate()`.
The requirements below from spec 65 are no longer applicable.

## Divergences

### 65-REQ-3.1 (superseded)

> WHEN `post_harvest_integrate` is called, THE system SHALL call
> `push_to_remote` with the feature branch name to push it to origin.

**Status:** Superseded by 78-REQ-1.1.

The feature branch is now kept local-only. `push_to_remote` is no longer
called with the feature branch name. Only `develop` is pushed to the remote
(via `_push_develop_if_pushable`).

**Rationale:** Pushing short-lived feature branches pollutes the remote forge
with branches that are never used after harvest. Feature branches are local
implementation details and need not be visible to the remote.

### 65-REQ-3.E1 (no longer applicable)

> IF the feature branch no longer exists locally, THEN THE system SHALL skip
> its push and log a warning; develop SHALL still be pushed.

**Status:** No longer applicable as of spec 78.

Since the feature branch is never pushed (78-REQ-1.1, 78-REQ-1.3), the
conditional check for local branch existence has been removed entirely.
The edge case of a deleted feature branch is now irrelevant: the function
always pushes only `develop` regardless of the feature branch's state
(78-REQ-1.E1).

## Impact

- `post_harvest_integrate()` in `agent_fox/workspace/harvest.py` no longer
  imports or calls `local_branch_exists`.
- `push_to_remote` is no longer called with a feature branch argument.
- The associated warning log for a missing feature branch has been removed.
- Tests from spec 65 that asserted feature branch pushing (TS-65-7, TS-65-E3)
  have been updated to assert the new behavior.
