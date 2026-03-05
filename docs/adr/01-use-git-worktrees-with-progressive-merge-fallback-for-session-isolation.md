---
Title: 01. Use git worktrees with progressive merge fallback for session isolation and harvest
Date: 2026-03-05
Status: Accepted
---

## Context

agent-fox is an autonomous coding-agent orchestrator that reads specifications,
builds a dependency graph of tasks, and drives Claude coding agents through each
task. A central design problem is **workspace isolation**: when multiple coding
sessions run in parallel (up to 8 concurrent agents), each agent must have its
own working tree so that file edits, branch state, and build artefacts from one
session do not interfere with another.

After each session completes, its changes must be **integrated back** into a
shared development branch (`develop`). This integration step -- called
"harvesting" -- must handle the case where `develop` has moved forward since the
session's workspace was created, which happens routinely when parallel sessions
finish in close succession.

The system operates under several constraints:

- **Single-process, single-threaded event loop.** The orchestrator uses Python
  asyncio. All sessions run as async tasks within one process; there is no
  multi-process or distributed component.
- **No human in the loop at merge time.** The system must resolve merge
  conflicts autonomously or report a clear failure -- there is no interactive
  conflict resolution.
- **Parallel sessions may create overlapping files.** When independent task
  groups within the same specification run concurrently, they may independently
  create the same files (e.g. `Makefile`, `go.mod`, test files). This produces
  git "add/add" conflicts that standard `git merge` and `git rebase` cannot
  auto-resolve without a conflict-resolution strategy.
- **The coding agent's work must not be silently lost.** If a session completes
  successfully but the merge fails, that failure must be clearly reported as an
  integration error, distinct from a coding failure.

This ADR documents the architecture of the workspace isolation and harvest
pipeline: how worktrees are created, how sessions execute in isolation, how
changes are merged back, and how merge conflicts are resolved.

## Decision Drivers

- Sessions must be fully isolated: no shared mutable filesystem state between
  concurrent sessions.
- Harvest must be autonomous -- no manual conflict resolution.
- The common case (sequential task completion, non-overlapping files) should
  produce clean, linear git history via fast-forward merge.
- The parallel case (overlapping files, `develop` has diverged) must not fail
  silently or discard completed work.
- The solution must work within a single-threaded asyncio event loop without
  explicit locks on the harvest path (per spec requirement 04-REQ-6.3).

## Options Considered

### Option A: Isolated git worktrees with progressive merge fallback

Each session gets its own git worktree (a lightweight, separate working
directory backed by the same `.git` object store). A feature branch is created
per task group. After the session, the harvester tries increasingly aggressive
merge strategies until one succeeds.

**Pros:**
- Git worktrees are a first-class git feature: cheap to create/destroy, share
  the object store, and provide true filesystem isolation.
- Feature branches provide a clear audit trail per task group.
- Progressive merge fallback (FF -> rebase -> merge commit -> merge with `-X
  theirs`) handles the full spectrum from clean fast-forward to add/add
  conflicts without human intervention.

**Cons:**
- Worktree paths must be managed carefully (stale cleanup, empty directory
  pruning).
- The `-X theirs` final fallback silently prefers the feature branch's version
  of conflicting files, which could discard prior work in `develop` for those
  specific files. (Acceptable because the feature branch represents the latest
  completed work, and the orchestrator can retry if the result is wrong.)
- Git operations on the main repo working tree during harvest are not
  serialised with an explicit lock; concurrent harvests rely on git's own
  internal locking and the fallback chain to recover from races.

### Option B: Copy-on-write directory clones (e.g., `cp --reflink`)

Clone the repository directory for each session using filesystem CoW support.

**Pros:**
- Complete filesystem isolation including `.git` directory.
- No worktree-specific git knowledge required.

**Cons:**
- Platform-dependent: `--reflink` is not available on all filesystems (e.g.,
  ext4, HFS+).
- Each clone has its own `.git` object store, wasting disk space and making
  inter-clone operations (merge back) require fetch/push to a shared remote or
  the original repo.
- Branch management and merge-back are more complex than with worktrees.
- No advantage for the merge conflict problem -- conflicts still occur.

### Option C: Serialise all sessions (no parallelism)

Run sessions one at a time, each building on the previous session's `develop`
state.

**Pros:**
- No merge conflicts possible -- each session sees the latest `develop`.
- Simplest implementation.

**Cons:**
- Loses the primary performance benefit of the orchestrator. Wall-clock time
  scales linearly with the number of tasks.
- Does not meet the product requirement of parallel execution (up to 8
  concurrent agents).

### Option D: Explicit asyncio.Lock around harvest

Add a mutex so that only one harvest operation runs at a time, preventing
concurrent git operations on the main repo.

**Pros:**
- Eliminates the theoretical race between two concurrent harvest calls
  modifying the main repo's working tree.

**Cons:**
- Does not solve the actual problem. Even with serial harvest, the second
  session's feature branch was still created from an older `develop` tip and
  will still have add/add conflicts with the now-updated `develop`. The merge
  fallback chain is still needed.
- Adds latency: sessions that finish nearly simultaneously must wait for each
  other's harvest to complete before starting their own.
- The asyncio event loop already provides sequential processing of completed
  task results via `asyncio.wait()` (spec 04-REQ-6.3), so an explicit lock
  on the production path is redundant.

## Decision

We will **use git worktrees for session isolation with a progressive merge
fallback chain for harvest** (Option A) because it provides true filesystem
isolation using a first-class git mechanism, handles the full range of merge
scenarios autonomously, and works within the single-threaded asyncio model
without explicit locking.

We explicitly chose **not** to add an asyncio.Lock around harvest (Option D)
because it does not solve the root conflict problem and the event loop already
serialises result processing. The spec (04-REQ-6.3) permits an explicit lock
for test and batch APIs as defense-in-depth, but does not require one on the
production streaming-pool path.

## Architecture

### Module Layout

```
agent_fox/workspace/
  worktree.py    -- Create/destroy git worktrees and feature branches
  git.py         -- Low-level async git operations (branch, merge, rebase)
  harvester.py   -- Merge feature branch changes into develop

agent_fox/engine/
  session_lifecycle.py  -- Full session lifecycle: worktree -> execute -> harvest -> cleanup
  orchestrator.py       -- Parallel dispatch and result processing
```

### Workspace Layout on Disk

```
.agent-fox/                          # gitignored
  worktrees/
    01_project_scaffold/
      1/                             # worktree for task group 1
        .git -> /repo/.git/worktrees/...
        src/
        tests/
      2/                             # worktree for task group 2
      3/                             # worktree for task group 3
    02_api_layer/
      1/
```

Each worktree has a corresponding feature branch:
`feature/{spec_name}/{task_group}` (e.g., `feature/01_project_scaffold/3`).

### Session Lifecycle

```
NodeSessionRunner.execute()
  |
  |-- 1. create_worktree(repo_root, spec, group)
  |      Creates .agent-fox/worktrees/{spec}/{group}
  |      Creates branch feature/{spec}/{group} from develop tip
  |
  |-- 2. Run pre-session hooks
  |
  |-- 3. Assemble context + build prompts
  |
  |-- 4. run_session()  [claude-code-sdk query() in the worktree]
  |      Agent commits on feature/{spec}/{group}
  |
  |-- 5. Run post-session hooks
  |
  |-- 6. harvest(repo_root, workspace)  [merge into develop]
  |      (see Harvest Pipeline below)
  |
  |-- 7. Extract knowledge facts from session summary
  |
  |-- 8. destroy_worktree()  [remove worktree + delete branch]
```

### Harvest Pipeline (Progressive Merge Fallback)

When a session completes successfully, the harvester integrates its feature
branch into `develop`. The pipeline tries progressively more aggressive
strategies, stopping at the first one that succeeds:

```
harvest(repo_root, workspace)
  |
  |-- Check: any new commits on feature branch?
  |   No  --> return [] (no-op)
  |   Yes --> continue
  |
  |-- Step 1: git merge --ff-only feature_branch
  |   Success --> return changed_files  (clean linear history)
  |   Fail    --> develop has diverged, continue
  |
  |-- Step 2: git rebase develop feature_branch  (in worktree)
  |   Success --> git merge --ff-only feature_branch  (now fast-forwardable)
  |              return changed_files  (still linear history)
  |   Fail    --> conflicts during rebase, continue
  |
  |-- Step 3: git rebase --abort
  |           git merge --no-edit feature_branch
  |   Success --> return changed_files  (merge commit, non-linear but clean)
  |   Fail    --> content conflicts (e.g. add/add), continue
  |
  |-- Step 4: git merge --abort
  |           git merge -X theirs --no-edit feature_branch
  |   Success --> return changed_files  (conflicts auto-resolved, feature wins)
  |   Fail    --> IntegrationError  (truly unresolvable, e.g. file/dir conflict)
```

**Why `-X theirs` in Step 4:**
When two parallel sessions independently create the same file with different
content, git reports an "add/add" conflict. The `-X theirs` strategy option
instructs git to resolve these conflicts by keeping the incoming (feature)
branch's version. This is the correct default because:
1. The feature branch contains the work just completed by the coding agent.
2. The `develop` version of the conflicting file came from a prior task group
   that was already integrated.
3. If the resolution is incorrect, the orchestrator's retry logic can
   re-attempt the task with the updated `develop` as its base.

**What Step 4 does NOT resolve:**
File-vs-directory conflicts (one side creates a path as a file, the other as a
directory) and submodule conflicts cannot be auto-resolved by `-X theirs`.
These remain as `IntegrationError` and are surfaced to the user. In practice,
these are extremely rare in agent-fox's usage patterns.

### Concurrency Model

The orchestrator dispatches sessions as asyncio tasks in a pool (up to
`max_parallelism`). When a task completes, `asyncio.wait(FIRST_COMPLETED)`
returns it to the main loop, which processes the result:

```
Orchestrator._dispatch_parallel()
  |
  pool = set of asyncio.Task[SessionRecord]
  |
  while pool:
    done, pool = await asyncio.wait(pool, FIRST_COMPLETED)
    for task in done:
      record = task.result()        # includes harvest result
      process_session_result(record) # update state dict in-place
    fill_pool_with_newly_ready_tasks()
    save_state()
```

**Key properties:**

- **In-memory state is never concurrently modified.** All state updates happen
  in the single-threaded event loop after `asyncio.wait()` returns. No lock is
  needed for the in-memory state dict (04-REQ-6.3).
- **Harvest calls CAN overlap.** Each session calls `harvest()` inside its own
  async task. Since `harvest()` awaits git subprocesses, two harvest calls can
  be interleaved at await points. This is why the progressive fallback chain
  exists -- the first merge attempt may fail because another harvest changed
  `develop` between the session's start and its harvest.
- **Git provides command-level atomicity.** Each `git merge` or `git rebase`
  command is atomic from git's perspective (it either completes or fails and
  can be aborted). The harvest pipeline is designed to handle failures at each
  step gracefully.
- **State persistence uses append-only JSONL.** `state.jsonl` is written in
  append mode, which is atomic on POSIX for single-line writes, preventing
  corruption from concurrent appends.

### Error Handling at the Session Lifecycle Level

The `session_lifecycle.py` module distinguishes between coding failures and
integration failures:

```python
if outcome.status == "completed":
    try:
        touched_files = await harvest(repo_root, workspace)
    except IntegrationError as exc:
        status = "failed"
        error_message = (
            f"Session completed but harvest failed: {exc}. "
            f"The coding work was done -- the merge into develop "
            f"encountered a conflict."
        )
```

This ensures the orchestrator's retry logic can distinguish "the code was
wrong" from "the merge failed" and act accordingly.

## Consequences

### Positive

- Parallel sessions achieve true filesystem isolation with zero shared mutable
  state during execution.
- The common case (no conflicts) produces clean fast-forward merges with linear
  git history.
- The add/add conflict case from parallel sessions is handled autonomously
  without human intervention, unblocking `--parallel > 1` execution.
- The worktree lifecycle (create -> execute -> harvest -> destroy) is fully
  managed; disk space is reclaimed after each session.
- Integration failures are clearly distinguished from coding failures in the
  session record.

### Negative / Trade-offs

- The `-X theirs` strategy can silently discard `develop`-side changes to
  conflicting files. This is an acceptable trade-off because: (a) the feature
  branch represents newer work, (b) the orchestrator can retry, and (c) the
  alternative (failing the session) is worse in practice.
- There is no explicit serialisation of harvest calls. Two concurrent harvests
  can race on the main repo's working tree. In practice this is mitigated by
  the asyncio event loop's sequential result processing and the fallback
  chain, but it is a theoretical concern. If this becomes a problem in
  practice, an `asyncio.Lock` can be added around the harvest call in
  `session_lifecycle.py` without changing the architecture.
- Worktree paths under `.agent-fox/worktrees/` must be gitignored and cleaned
  up reliably, including handling stale worktrees from prior interrupted runs.

### Neutral / Follow-up actions

- If harvest races become a practical problem (not just theoretical), consider
  adding an `asyncio.Lock` around the harvest call. The spec (04-REQ-6.3)
  already permits this for defense-in-depth.
- Monitor whether the `-X theirs` fallback is triggered frequently in
  production. If so, consider re-ordering the task graph to reduce overlap
  between parallel task groups within the same spec.
- The harvest pipeline could be extended with a pre-merge rebase-with-
  `-X theirs` step for better history (linear instead of merge commit) in the
  conflict case. This is a minor improvement and not currently implemented.

## References

- Spec 03 (Session and Workspace): `.specs/03_session_and_workspace/requirements.md` -- requirements 03-REQ-7.1 through 03-REQ-7.E2 (harvest), 03-REQ-1.1 through 03-REQ-2.E2 (worktree lifecycle)
- Spec 03 design: `.specs/03_session_and_workspace/design.md` -- architecture diagrams, correctness properties
- Spec 04 (Orchestrator): `.specs/04_orchestrator/requirements.md` -- requirement 04-REQ-6.3 (sequential result processing guarantee)
- Issue #84: [Harvest failed with parallel merge conflicts](https://github.com/agent-fox-dev/agent-fox-v2/issues/84) -- the bug that motivated adding the `-X theirs` fallback (Step 4 in the pipeline)
- PR #85: [fix(harvester): auto-resolve add/add merge conflicts](https://github.com/agent-fox-dev/agent-fox-v2/pull/85) -- implementation of Step 4
- Git worktree documentation: `git help worktree`
