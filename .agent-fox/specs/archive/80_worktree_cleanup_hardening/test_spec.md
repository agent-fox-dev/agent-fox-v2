# Test Specification: Worktree Cleanup Hardening

## Overview

Tests verify the three hardening layers: post-prune verification, delete_branch
self-healing, and orphan cleanup. Unit tests mock git CLI output. Integration
tests use real temporary git repos to simulate stale worktree state.

## Test Cases

### TS-80-1: branch_used_by_worktree returns True when referenced

**Requirement:** 80-REQ-1.3
**Type:** unit
**Description:** Verify the function detects a branch in porcelain output.

**Preconditions:**
- Mock `run_git` returns porcelain output with `branch refs/heads/feature/spec/0`

**Input:**
- branch = "feature/spec/0"

**Expected:** True

**Assertion pseudocode:**
```
mock run_git to return porcelain with "branch refs/heads/feature/spec/0"
result = await branch_used_by_worktree(repo, "feature/spec/0")
ASSERT result == True
```

### TS-80-2: branch_used_by_worktree returns False when not referenced

**Requirement:** 80-REQ-1.3
**Type:** unit
**Description:** Verify the function returns False for an absent branch.

**Preconditions:**
- Mock `run_git` returns porcelain output with only `branch refs/heads/develop`

**Input:**
- branch = "feature/other/1"

**Expected:** False

**Assertion pseudocode:**
```
mock run_git to return porcelain with "branch refs/heads/develop"
result = await branch_used_by_worktree(repo, "feature/other/1")
ASSERT result == False
```

### TS-80-3: destroy_worktree verifies before branch deletion

**Requirement:** 80-REQ-1.1
**Type:** integration
**Description:** After removing a worktree, destroy_worktree verifies the
registry is clean before deleting the branch.

**Preconditions:**
- Real git repo in tmp dir with a worktree created

**Input:**
- Call destroy_worktree on the workspace

**Expected:**
- Branch is deleted successfully
- No WorkspaceError raised

**Assertion pseudocode:**
```
repo, workspace = create_test_repo_with_worktree()
await destroy_worktree(repo, workspace)
ASSERT NOT await local_branch_exists(repo, workspace.branch)
```

### TS-80-4: create_worktree handles stale worktree

**Requirement:** 80-REQ-1.2
**Type:** integration
**Description:** create_worktree succeeds when a stale worktree directory exists.

**Preconditions:**
- Real git repo with a stale worktree (directory exists but worktree was
  partially removed, leaving registry entry)

**Input:**
- Call create_worktree for the same spec/group as the stale one

**Expected:**
- New worktree created successfully
- No WorkspaceError raised

**Assertion pseudocode:**
```
repo = create_test_repo()
workspace = await create_worktree(repo, "spec", 0)
# Simulate stale state: remove directory but leave git registry
shutil.rmtree(workspace.path)
workspace.path.mkdir(parents=True)  # recreate empty dir (stale)
# Should succeed despite stale state
workspace2 = await create_worktree(repo, "spec", 0)
ASSERT workspace2.path.exists()
```

### TS-80-5: delete_branch self-heals on stale worktree error

**Requirement:** 80-REQ-2.1
**Type:** unit
**Description:** delete_branch prunes and retries when "used by worktree"
error occurs for a non-existent worktree path.

**Preconditions:**
- Mock `run_git` to return "used by worktree at '/nonexistent/path'" on first
  call, success on second call after prune

**Input:**
- Call delete_branch for the affected branch

**Expected:**
- No exception raised
- git worktree prune was called between the two attempts

**Assertion pseudocode:**
```
# First git branch -D fails with "used by worktree"
# Then git worktree prune is called
# Then git branch -D succeeds
mock run_git sequence: [fail_used_by_worktree, prune_ok, branch_delete_ok]
await delete_branch(repo, "feature/spec/0", force=True)
# No exception = success
```

### TS-80-6: delete_branch retry failure is non-fatal

**Requirement:** 80-REQ-2.2
**Type:** unit
**Description:** If the retry also fails with "used by worktree", log warning
and return without raising.

**Preconditions:**
- Mock `run_git` to return "used by worktree" on both attempts, with
  non-existent worktree path

**Input:**
- Call delete_branch for the affected branch

**Expected:**
- No exception raised
- Warning logged

**Assertion pseudocode:**
```
mock run_git to always fail with "used by worktree at '/nonexistent'"
with capture_logs("WARNING") as logs:
    await delete_branch(repo, "feature/spec/0", force=True)
ASSERT any("used by worktree" in msg for msg in logs)
# No exception = non-fatal
```

### TS-80-7: orphan ancestor directories are cleaned

**Requirement:** 80-REQ-3.1
**Type:** unit
**Description:** Empty parent directories are removed after worktree cleanup.

**Preconditions:**
- Temp directory structure: root/worktrees/spec_name/0/ (empty)

**Input:**
- Call _cleanup_empty_ancestors(root/worktrees/spec_name/0, root/worktrees)

**Expected:**
- spec_name/ directory removed (was empty after 0/ removed)
- worktrees/ directory still exists (it's the root)

**Assertion pseudocode:**
```
root = tmp / "worktrees"
spec_dir = root / "spec_name"
task_dir = spec_dir / "0"
task_dir.mkdir(parents=True)
_cleanup_empty_ancestors(task_dir, root)
ASSERT NOT spec_dir.exists()
ASSERT root.exists()
```

### TS-80-8: create_worktree cleans orphan directories

**Requirement:** 80-REQ-3.2
**Type:** integration
**Description:** create_worktree removes empty ancestor dirs from stale cleanup.

**Preconditions:**
- Real git repo with an empty stale worktree parent directory

**Input:**
- Call create_worktree for a different task group under the same spec

**Expected:**
- Stale empty directory removed
- New worktree created

**Assertion pseudocode:**
```
repo = create_test_repo()
stale_dir = repo / ".agent-fox" / "worktrees" / "spec" / "99"
stale_dir.mkdir(parents=True)
workspace = await create_worktree(repo, "spec", 0)
ASSERT workspace.path.exists()
# stale_dir parent should be cleaned if empty after worktree ops
```

### TS-80-9: post-prune still referenced triggers second prune

**Requirement:** 80-REQ-1.E1
**Type:** unit
**Description:** If branch is still referenced after first prune,
a second prune is attempted before giving up.

**Preconditions:**
- Mock branch_used_by_worktree to return True on first call, False on second
- Mock run_git for prune calls

**Input:**
- Execute the verify-and-delete flow from destroy_worktree

**Expected:**
- Two prune calls made
- Branch deleted on second attempt

**Assertion pseudocode:**
```
# First verify: True (still referenced)
# Second prune
# Second verify: False (cleaned)
# Branch deleted
mock branch_used_by_worktree sequence: [True, False]
await destroy_worktree(repo, workspace)
ASSERT prune_call_count == 2
ASSERT branch_deleted == True
```

### TS-80-10: porcelain parse failure is optimistic fallback

**Requirement:** 80-REQ-1.E2
**Type:** unit
**Description:** If git worktree list fails, proceed to attempt deletion.

**Preconditions:**
- Mock `run_git` to fail for `git worktree list --porcelain`

**Input:**
- Call branch_used_by_worktree

**Expected:** False (optimistic)

**Assertion pseudocode:**
```
mock run_git("worktree", "list", "--porcelain") to fail
result = await branch_used_by_worktree(repo, "feature/spec/0")
ASSERT result == False
```

## Edge Case Tests

### TS-80-E1: delete_branch with live worktree raises

**Requirement:** 80-REQ-2.E1
**Type:** integration
**Description:** If the worktree directory actually exists, the error is
legitimate and should be raised.

**Preconditions:**
- Real git repo with an active worktree (directory exists)

**Input:**
- Call delete_branch for the branch used by the live worktree

**Expected:**
- WorkspaceError raised

**Assertion pseudocode:**
```
repo = create_test_repo()
workspace = await create_worktree(repo, "spec", 0)
ASSERT workspace.path.exists()
with ASSERT_RAISES(WorkspaceError):
    await delete_branch(repo, workspace.branch, force=True)
```

### TS-80-E2: non-empty ancestor directory preserved

**Requirement:** 80-REQ-3.E1
**Type:** unit
**Description:** Ancestor directories containing other worktrees are not removed.

**Preconditions:**
- Directory structure: root/worktrees/spec_name/0/ (empty), root/worktrees/spec_name/1/ (exists)

**Input:**
- Call _cleanup_empty_ancestors(root/worktrees/spec_name/0, root/worktrees)

**Expected:**
- spec_name/ directory preserved (contains 1/)
- 0/ directory removed

**Assertion pseudocode:**
```
root = tmp / "worktrees"
(root / "spec_name" / "0").mkdir(parents=True)
(root / "spec_name" / "1").mkdir(parents=True)
_cleanup_empty_ancestors(root / "spec_name" / "0", root)
ASSERT (root / "spec_name").exists()  # has sibling
ASSERT NOT (root / "spec_name" / "0").exists()
```

### TS-80-E3: ancestor cleanup failure is non-fatal

**Requirement:** 80-REQ-3.E2
**Type:** unit
**Description:** Permission errors during orphan cleanup are swallowed.

**Preconditions:**
- Mock Path.rmdir to raise PermissionError

**Input:**
- Call _cleanup_empty_ancestors on a path that will fail

**Expected:**
- No exception raised
- Warning logged

**Assertion pseudocode:**
```
with mock.patch("pathlib.Path.rmdir", side_effect=PermissionError):
    _cleanup_empty_ancestors(path, root)  # should not raise
```

### TS-80-E4: branch still referenced after two prunes

**Requirement:** 80-REQ-1.E1
**Type:** unit
**Description:** If branch is still referenced after second prune, skip
deletion with warning.

**Preconditions:**
- Mock branch_used_by_worktree to always return True

**Input:**
- Execute the verify-and-delete flow

**Expected:**
- Branch NOT deleted
- Warning logged
- No exception raised

**Assertion pseudocode:**
```
mock branch_used_by_worktree to always return True
with capture_logs("WARNING") as logs:
    await destroy_worktree(repo, workspace)
ASSERT any("still referenced" in msg for msg in logs)
ASSERT await local_branch_exists(repo, workspace.branch)
```

## Property Test Cases

### TS-80-P1: Porcelain Parsing Accuracy

**Property:** Property 5 from design.md
**Validates:** 80-REQ-1.3
**Type:** property
**Description:** branch_used_by_worktree correctly detects branch presence
in any valid porcelain output.

**For any:** branch_name: text(alphabet=ascii+digits+"/._-"), porcelain entries:
list of (path, head_sha, optional branch_ref)
**Invariant:** branch_used_by_worktree returns True iff any entry's branch_ref
equals "refs/heads/{branch_name}"

**Assertion pseudocode:**
```
FOR ANY branch_name IN valid_branch_names(), entries IN worktree_entries():
    porcelain = build_porcelain(entries)
    mock run_git to return porcelain
    result = await branch_used_by_worktree(repo, branch_name)
    expected = any(e.branch == f"refs/heads/{branch_name}" for e in entries)
    ASSERT result == expected
```

### TS-80-P2: Ancestor Cleanup Safety

**Property:** Property 4 from design.md
**Validates:** 80-REQ-3.1, 80-REQ-3.E1
**Type:** property
**Description:** Ancestor cleanup never removes non-empty directories or
the root itself.

**For any:** directory tree under root with some empty and some non-empty dirs
**Invariant:** After cleanup, root exists AND all non-empty dirs exist AND
all empty-chain dirs from target to root are removed

**Assertion pseudocode:**
```
FOR ANY tree IN directory_trees():
    create_tree(tree)
    _cleanup_empty_ancestors(target, root)
    ASSERT root.exists()
    for dir in non_empty_dirs(tree):
        ASSERT dir.exists()
```

### TS-80-P3: delete_branch Never Raises on Stale Worktree

**Property:** Property 2 from design.md
**Validates:** 80-REQ-2.1, 80-REQ-2.2
**Type:** property
**Description:** delete_branch does not raise WorkspaceError when the "used by
worktree" path does not exist on the filesystem.

**For any:** branch name, non-existent worktree path in error message
**Invariant:** delete_branch returns normally (no exception)

**Assertion pseudocode:**
```
FOR ANY branch IN valid_branch_names(), path IN non_existent_paths():
    mock git to fail with f"used by worktree at '{path}'"
    await delete_branch(repo, branch, force=True)  # must not raise
```

## Integration Smoke Tests

### TS-80-SMOKE-1: Full destroy_worktree with simulated stale state

**Execution Path:** Path 2 from design.md
**Description:** Verifies that destroy_worktree succeeds when a worktree
has stale registry entries.

**Setup:**
- Create a real git repo in a tmp directory
- Create a worktree using `git worktree add`
- Simulate stale state: delete the worktree directory with `shutil.rmtree`
  but do NOT run `git worktree prune` (registry is now stale)

**Trigger:**
- Call `destroy_worktree(repo, workspace)`

**Expected side effects:**
- No exception raised
- Branch is deleted (or skipped with warning)
- No empty directories left under worktrees root

**Must NOT satisfy with:** Mocking `destroy_worktree`, mocking
`branch_used_by_worktree`, mocking `delete_branch`.

**Assertion pseudocode:**
```
repo = create_real_git_repo(tmp)
workspace = await create_worktree(repo, "spec", 0)
shutil.rmtree(workspace.path)  # simulate crash, leave stale registry
await destroy_worktree(repo, workspace)  # must not raise
worktrees_root = repo / ".agent-fox" / "worktrees"
ASSERT NOT any(d.exists() for d in worktrees_root.glob("spec/*"))
```

### TS-80-SMOKE-2: Full create_worktree with stale predecessor

**Execution Path:** Path 4 from design.md
**Description:** Verifies that create_worktree succeeds when a stale worktree
from a previous run exists at the same path.

**Setup:**
- Create a real git repo in a tmp directory
- Create a worktree, then simulate stale state (delete directory, keep registry)
- Recreate the directory (simulating leftover from crash)

**Trigger:**
- Call `create_worktree(repo, "spec", 0)` — same spec/group as stale one

**Expected side effects:**
- New worktree created at the same path
- New branch exists
- WorkspaceInfo returned with correct path and branch

**Must NOT satisfy with:** Mocking `create_worktree`, mocking
`branch_used_by_worktree`.

**Assertion pseudocode:**
```
repo = create_real_git_repo(tmp)
workspace = await create_worktree(repo, "spec", 0)
shutil.rmtree(workspace.path)
workspace.path.mkdir(parents=True)  # stale empty dir
workspace2 = await create_worktree(repo, "spec", 0)
ASSERT workspace2.path.exists()
ASSERT (workspace2.path / ".git").exists()  # valid worktree
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 80-REQ-1.1 | TS-80-3 | integration |
| 80-REQ-1.2 | TS-80-4 | integration |
| 80-REQ-1.3 | TS-80-1, TS-80-2 | unit |
| 80-REQ-1.E1 | TS-80-9, TS-80-E4 | unit |
| 80-REQ-1.E2 | TS-80-10 | unit |
| 80-REQ-2.1 | TS-80-5 | unit |
| 80-REQ-2.2 | TS-80-6 | unit |
| 80-REQ-2.E1 | TS-80-E1 | integration |
| 80-REQ-3.1 | TS-80-7 | unit |
| 80-REQ-3.2 | TS-80-8 | integration |
| 80-REQ-3.E1 | TS-80-E2 | unit |
| 80-REQ-3.E2 | TS-80-E3 | unit |
| Property 1 | TS-80-P1 | property |
| Property 2 | TS-80-P2 | property |
| Property 3 | TS-80-P3 | property |
| Path 2 | TS-80-SMOKE-1 | integration |
| Path 4 | TS-80-SMOKE-2 | integration |
