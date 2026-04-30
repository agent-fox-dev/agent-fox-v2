# PRD: Atomic Push with Retry

## Problem

The harvest pipeline has a race condition where two concurrent sessions can
both merge their feature branches into `develop` (serialized by the merge
lock), but then both attempt `git push origin develop` simultaneously outside
the lock. The first push succeeds and moves the remote HEAD; the second push
fails with a non-fast-forward rejection because its expected HEAD is stale.

Observed in production:

```
[WARNING] Failed to push 'develop' to 'origin':
  is at 30877b24... but expected 505355c1...
```

The system eventually recovers (later sessions push the accumulated commits),
but there is a window where committed work on local `develop` has not reached
`origin`. In the worst case, a crash during that window could lose work that
was believed to be safely pushed.

## Root Cause

In `harvest.py`, the `harvest()` function acquires the merge lock only for the
squash-merge operation (lines 77-84). After the lock is released, the caller
(`_harvest_and_integrate` in `session_lifecycle.py`) invokes
`post_harvest_integrate()` which calls `_push_develop_if_pushable()` **without
holding the merge lock**. Two concurrent callers can interleave their pushes.

## Proposed Fix

Two complementary changes:

1. **Atomic merge+push under lock:** Move the push into the merge lock scope
   so that the squash-merge and the push to origin happen as a single atomic
   operation. No other session can merge or push between these two steps.

2. **Retry-with-rebase on push failure:** When `git push` fails with a
   non-fast-forward rejection, fetch `origin/develop`, rebase local `develop`
   onto it, and retry the push. This handles both the internal race (as a
   defense-in-depth layer) and external push conflicts (e.g., a human pushing
   to `develop` while the engine is running). Maximum 3 retries.

3. **Audit event for push failures:** Emit a `git.push_failed` audit event
   when a push fails (even if a retry subsequently succeeds), capturing the
   push attempt number, error details, and whether the retry succeeded. This
   enables monitoring and alerting on push reliability.

## Design Decisions

1. **Why both atomic lock and retry?** The atomic lock prevents the internal
   race entirely. The retry handles external conflicts (human pushes, CI
   pushes) that the lock cannot prevent. Together they provide defense in
   depth.

2. **Why 3 retries?** The engine runs up to 5 concurrent sessions. In the
   worst case, all 5 complete simultaneously and serialize through the lock.
   Each push might conflict with the previous one if the lock doesn't fully
   serialize (e.g., external pushes). 3 retries handles the realistic
   concurrent collision count with margin.

3. **Why rebase (not merge) during retry?** The develop branch should have a
   linear history. A merge commit during retry would create an unnecessary
   merge bubble. Rebase keeps history linear and is safe here because the
   local commits are squash-merge commits that haven't been shared yet.

4. **Lock hold time tradeoff:** Moving the push inside the lock increases lock
   hold time by the duration of `git push` (typically 1-5 seconds). This is
   acceptable because the lock timeout is 300 seconds and the push adds
   negligible overhead compared to the merge itself.

5. **Reconciliation nesting:** `_push_develop_if_pushable()` currently calls
   `_sync_develop_with_remote()` which acquires its own merge lock. When the
   push moves inside the harvest lock, this creates nested lock acquisition.
   Since `MergeLock` uses `asyncio.Lock` internally and the same task holds
   the outer lock, this must be handled — either by making the lock reentrant
   or by extracting the sync logic to run under the already-held lock without
   re-acquiring.

6. **Audit event vs. log-only:** Push failures are operationally significant
   and should be visible in the audit trail, not buried in debug logs. The
   new `git.push_failed` event enables dashboards and alerts.

## Dependencies

| Spec | From Group | To Group | Relationship |
|------|-----------|----------|--------------|
| 118_git_hardening | 1 | 1 | Uses error classification from 118; group 1 defines the error taxonomy |

## Source

Source: https://github.com/agent-fox-dev/agent-fox/issues/590
