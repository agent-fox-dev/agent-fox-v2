# Requirements Document

## Introduction

This specification addresses a race condition in the harvest pipeline where
concurrent sessions can interleave their `git push` operations to
`origin/develop`, causing non-fast-forward rejections. The fix makes
merge+push atomic under the existing merge lock and adds retry-with-rebase
logic for push failures.

## Glossary

- **Harvest:** The process of integrating a feature branch's changes into
  the `develop` branch via `git merge --squash`.
- **Merge lock:** A file-based lock (`MergeLock`) that serializes merge
  operations across asyncio tasks and OS processes.
- **Post-harvest push:** The `git push origin develop` call that pushes the
  merged commit to the remote after harvest completes.
- **Non-fast-forward rejection:** A `git push` failure where the remote
  branch has commits not present in the local branch, preventing a
  fast-forward update.
- **Rebase reconciliation:** Running `git fetch` followed by
  `git rebase origin/develop` to incorporate remote changes before retrying
  a push.
- **Push attempt:** A single invocation of `git push origin develop`. The
  initial push is attempt 1; each retry increments the attempt number.

## Requirements

### Requirement 1: Atomic Merge and Push

**User Story:** As a system operator, I want the merge and push to happen as
a single atomic operation, so that concurrent sessions cannot interleave
their pushes and cause non-fast-forward rejections.

#### Acceptance Criteria

[121-REQ-1.1] WHEN `harvest()` successfully squash-merges a feature branch
into develop, THE system SHALL push develop to origin before releasing the
merge lock.

[121-REQ-1.2] WHILE the merge lock is held for a harvest operation, THE
system SHALL NOT allow another task to merge or push to develop.

[121-REQ-1.3] WHEN the push to origin succeeds inside the merge lock, THE
system SHALL release the merge lock and return the list of touched files to
the caller.

[121-REQ-1.4] WHEN the push to origin fails inside the merge lock, THE
system SHALL attempt retry-with-rebase (per Requirement 2) before releasing
the merge lock.

#### Edge Cases

[121-REQ-1.E1] IF the merge succeeds but no remote is configured (e.g.,
local-only repo), THEN THE system SHALL skip the push, release the lock,
and return normally.

[121-REQ-1.E2] IF the merge lock cannot be acquired within the configured
timeout, THEN THE system SHALL raise `IntegrationError` without attempting
the merge or push.

### Requirement 2: Retry-with-Rebase on Push Failure

**User Story:** As a system operator, I want failed pushes to automatically
retry after rebasing onto the remote HEAD, so that transient conflicts from
concurrent pushes (internal or external) are resolved without manual
intervention.

#### Acceptance Criteria

[121-REQ-2.1] WHEN `git push origin develop` fails with a non-fast-forward
rejection, THE system SHALL fetch `origin/develop`, rebase local develop
onto it, and retry the push.

[121-REQ-2.2] THE system SHALL retry a failed push up to 3 times (4 total
attempts including the initial push).

[121-REQ-2.3] WHEN a retry push succeeds, THE system SHALL log the
successful retry at INFO level, including the attempt number.

[121-REQ-2.4] WHEN all retry attempts are exhausted without a successful
push, THE system SHALL log a WARNING and return without raising an
exception, preserving the current best-effort push semantics.

[121-REQ-2.5] THE system SHALL perform each fetch-rebase-push retry cycle
while still holding the merge lock, so that no other merge can interleave
between rebase and push.

#### Edge Cases

[121-REQ-2.E1] IF `git fetch` fails during a retry cycle, THEN THE system
SHALL skip the rebase and attempt the push as-is for the remaining retries.

[121-REQ-2.E2] IF `git rebase` fails during a retry cycle (e.g., conflict),
THEN THE system SHALL abort the rebase (`git rebase --abort`), log a
WARNING, and stop retrying.

[121-REQ-2.E3] IF the push failure is not a non-fast-forward rejection (e.g.,
authentication error, network timeout), THEN THE system SHALL NOT retry and
SHALL log the failure immediately.

### Requirement 3: Push Failure Audit Events

**User Story:** As a system operator, I want push failures to be recorded as
audit events, so that I can monitor push reliability and set up alerts.

#### Acceptance Criteria

[121-REQ-3.1] WHEN a push to origin fails (regardless of whether a retry
will follow), THE system SHALL emit a `git.push_failed` audit event.

[121-REQ-3.2] THE `git.push_failed` audit event payload SHALL include:
the push attempt number, the git error message, the branch name, and
whether a retry will be attempted.

[121-REQ-3.3] WHEN all push retries are exhausted, THE system SHALL emit a
final `git.push_failed` audit event with `retries_exhausted: true` in the
payload.

[121-REQ-3.4] WHEN a push succeeds after one or more retries, THE system
SHALL emit a `git.push_retry_success` audit event with the total attempt
count in the payload.

#### Edge Cases

[121-REQ-3.E1] IF the audit event sink is unavailable when a push failure
occurs, THEN THE system SHALL log the push failure at WARNING level and
continue without raising an exception.

### Requirement 4: Lock Reentrancy for Reconciliation

**User Story:** As a developer, I want the merge lock to support the
atomic merge+push flow without deadlocking when reconciliation logic
also needs the lock.

#### Acceptance Criteria

[121-REQ-4.1] WHEN `_push_develop_if_pushable()` calls
`_sync_develop_with_remote()` while the merge lock is already held by the
same task, THE system SHALL execute the sync logic without re-acquiring the
lock and without deadlocking.

[121-REQ-4.2] THE system SHALL extract the sync-under-lock logic into a
separate internal function that can be called with or without an
already-held lock, and the existing `_sync_develop_with_remote()` public
function SHALL continue to acquire the lock when called independently.

#### Edge Cases

[121-REQ-4.E1] IF `_sync_develop_with_remote()` is called without the
merge lock being held (e.g., from `ensure_develop_branch`), THEN THE system
SHALL acquire the lock as it does today (no behavioral change for
non-harvest callers).

### Requirement 5: Backward-Compatible API

**User Story:** As a developer, I want the `harvest()` function's public
API to remain backward-compatible so that existing callers do not need
changes.

#### Acceptance Criteria

[121-REQ-5.1] THE `harvest()` function SHALL accept an optional boolean
parameter `push` (default `True`) that controls whether the push to origin
happens inside the lock after a successful merge.

[121-REQ-5.2] WHEN `push=False` is passed to `harvest()`, THE system SHALL
skip the push to origin, preserving the pre-fix behavior for callers that
manage pushing themselves.

[121-REQ-5.3] THE `post_harvest_integrate()` function SHALL remain callable
but SHALL skip the push when the harvest has already pushed (to prevent
double-push).

#### Edge Cases

[121-REQ-5.E1] IF both `harvest(push=True)` and `post_harvest_integrate()`
are called for the same harvest operation, THEN THE system SHALL push
exactly once (the push inside harvest) and `post_harvest_integrate()` SHALL
be a no-op for the push step.
