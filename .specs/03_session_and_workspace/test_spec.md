# Test Specification: Session and Workspace

## Overview

Tests for the session execution and workspace isolation layer: git worktree
management, coding session execution, context assembly, prompt building,
timeout enforcement, session outcome capture, and change integration
(harvesting). Tests map to requirements in `requirements.md` and correctness
properties in `design.md`.

## Test Cases

### TS-03-1: Worktree creation produces correct structure

**Requirement:** 03-REQ-1.1, 03-REQ-1.2, 03-REQ-1.3
**Type:** integration
**Description:** Verify that creating a worktree produces the expected
directory, feature branch, and WorkspaceInfo.

**Preconditions:**
- A temporary git repository with a `develop` branch and at least one commit.

**Input:**
- `create_worktree(repo_root, spec_name="test_spec", task_group=1)`

**Expected:**
- Directory `.agent-fox/worktrees/test_spec/1` exists.
- Git branch `feature/test_spec/1` exists in the repository.
- Returned `WorkspaceInfo.path` points to the worktree directory.
- Returned `WorkspaceInfo.branch` equals `feature/test_spec/1`.
- Returned `WorkspaceInfo.spec_name` equals `test_spec`.
- Returned `WorkspaceInfo.task_group` equals `1`.
- The worktree has `feature/test_spec/1` checked out.

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
ASSERT ws.path == repo / ".agent-fox" / "worktrees" / "test_spec" / "1"
ASSERT ws.branch == "feature/test_spec/1"
ASSERT ws.spec_name == "test_spec"
ASSERT ws.task_group == 1
ASSERT ws.path.is_dir()
ASSERT "feature/test_spec/1" IN git_branches(repo)
```

---

### TS-03-2: Worktree destruction removes directory and branch

**Requirement:** 03-REQ-2.1, 03-REQ-2.2
**Type:** integration
**Description:** Verify that destroying a worktree removes the worktree
directory, the feature branch, and cleans up the empty spec directory.

**Preconditions:**
- A worktree has been created for spec "test_spec", group 1.

**Input:**
- `destroy_worktree(repo_root, workspace)`

**Expected:**
- The worktree directory no longer exists.
- The feature branch `feature/test_spec/1` no longer exists.
- The spec directory `.agent-fox/worktrees/test_spec/` is removed
  (since it is now empty).

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
await destroy_worktree(repo, ws)
ASSERT NOT ws.path.exists()
ASSERT "feature/test_spec/1" NOT IN git_branches(repo)
ASSERT NOT (repo / ".agent-fox" / "worktrees" / "test_spec").exists()
```

---

### TS-03-3: Stale worktree is removed on re-creation

**Requirement:** 03-REQ-1.E1, 03-REQ-1.E2
**Type:** integration
**Description:** Verify that if a worktree or feature branch already exists,
create_worktree removes them and creates fresh ones.

**Preconditions:**
- A worktree already exists for spec "test_spec", group 1.

**Input:**
- `create_worktree(repo_root, spec_name="test_spec", task_group=1)` (again)

**Expected:**
- No error raised.
- A fresh worktree exists at the same path.
- The feature branch points to the current develop tip (fresh branch point).

**Assertion pseudocode:**
```
ws1 = await create_worktree(repo, "test_spec", 1)
# Create a commit on develop to prove the branch point moves
add_commit_to_develop(repo)
ws2 = await create_worktree(repo, "test_spec", 1)
ASSERT ws2.path.is_dir()
ASSERT branch_tip(repo, ws2.branch) == branch_tip(repo, "develop")
```

---

### TS-03-4: Context assembly includes spec documents

**Requirement:** 03-REQ-4.1, 03-REQ-4.3
**Type:** unit
**Description:** Verify that the context assembler reads spec documents and
returns them with section headers.

**Preconditions:**
- A temporary spec directory with `requirements.md`, `design.md`, and
  `tasks.md` containing known content.

**Input:**
- `assemble_context(spec_dir, task_group=2)`

**Expected:**
- Returned string contains the content of all three files.
- Returned string contains section headers like "## Requirements" or similar
  markers that separate the documents.

**Assertion pseudocode:**
```
spec_dir = create_spec_dir(requirements="REQ content", design="Design content", tasks="Task content")
ctx = assemble_context(spec_dir, task_group=2)
ASSERT "REQ content" IN ctx
ASSERT "Design content" IN ctx
ASSERT "Task content" IN ctx
```

---

### TS-03-5: Context assembly includes memory facts

**Requirement:** 03-REQ-4.2, 03-REQ-4.3
**Type:** unit
**Description:** Verify that memory facts are included in the assembled context.

**Preconditions:**
- A spec directory with at least one spec file.
- A list of memory facts.

**Input:**
- `assemble_context(spec_dir, task_group=1, memory_facts=["Fact 1", "Fact 2"])`

**Expected:**
- Returned string contains both facts.
- Facts are in a clearly labeled section.

**Assertion pseudocode:**
```
ctx = assemble_context(spec_dir, 1, memory_facts=["Fact 1", "Fact 2"])
ASSERT "Fact 1" IN ctx
ASSERT "Fact 2" IN ctx
```

---

### TS-03-6: Prompt builder produces system and task prompts

**Requirement:** 03-REQ-5.1, 03-REQ-5.2
**Type:** unit
**Description:** Verify that the prompt builder constructs non-empty prompts
containing the expected references.

**Preconditions:** None.

**Input:**
- `build_system_prompt(context="...", task_group=2, spec_name="my_spec")`
- `build_task_prompt(task_group=2, spec_name="my_spec")`

**Expected:**
- System prompt is non-empty and mentions the task group and spec.
- Task prompt is non-empty and references the task group.

**Assertion pseudocode:**
```
sys_p = build_system_prompt("context text", 2, "my_spec")
task_p = build_task_prompt(2, "my_spec")
ASSERT len(sys_p) > 0
ASSERT "2" IN sys_p
ASSERT "my_spec" IN sys_p
ASSERT len(task_p) > 0
ASSERT "2" IN task_p
```

---

### TS-03-7: Session runner returns completed outcome on success

**Requirement:** 03-REQ-3.1, 03-REQ-3.2, 03-REQ-3.3
**Type:** unit
**Description:** Verify that a successful session returns a SessionOutcome with
status "completed" and populated token/duration fields.

**Preconditions:**
- claude-code-sdk `query()` is mocked to yield a sequence ending with a
  `ResultMessage(is_error=False, duration_ms=5000, usage={"input_tokens": 100, "output_tokens": 200})`.
- A workspace exists.

**Input:**
- `run_session(workspace, node_id="03:1", system_prompt="...", task_prompt="...", config=default_config)`

**Expected:**
- `outcome.status == "completed"`
- `outcome.input_tokens == 100`
- `outcome.output_tokens == 200`
- `outcome.duration_ms == 5000`
- `outcome.error_message is None`
- `outcome.spec_name == workspace.spec_name`
- `outcome.task_group == workspace.task_group`

**Assertion pseudocode:**
```
outcome = await run_session(workspace, "03:1", sys_prompt, task_prompt, config)
ASSERT outcome.status == "completed"
ASSERT outcome.input_tokens == 100
ASSERT outcome.output_tokens == 200
ASSERT outcome.duration_ms == 5000
ASSERT outcome.error_message IS None
```

---

### TS-03-8: Session runner returns failed outcome on SDK error

**Requirement:** 03-REQ-3.E1
**Type:** unit
**Description:** Verify that an SDK error results in a failed SessionOutcome.

**Preconditions:**
- claude-code-sdk `query()` is mocked to raise `ProcessError("boom")`.

**Input:**
- `run_session(workspace, ...)`

**Expected:**
- `outcome.status == "failed"`
- `outcome.error_message` contains "boom".

**Assertion pseudocode:**
```
# Mock query() to raise ProcessError("boom")
outcome = await run_session(workspace, "03:1", sys_prompt, task_prompt, config)
ASSERT outcome.status == "failed"
ASSERT "boom" IN outcome.error_message
```

---

### TS-03-9: Session runner returns timeout outcome

**Requirement:** 03-REQ-6.1, 03-REQ-6.2, 03-REQ-6.E1
**Type:** unit
**Description:** Verify that a timed-out session returns a timeout outcome
with partial metrics preserved.

**Preconditions:**
- claude-code-sdk `query()` is mocked to yield some messages then hang.
- Config has `session_timeout=1` (1 minute, but test uses a shorter
  override for speed).

**Input:**
- `run_session(workspace, ...)` with a very short timeout.

**Expected:**
- `outcome.status == "timeout"`
- `outcome.duration_ms > 0` (partial metrics preserved).

**Assertion pseudocode:**
```
# Mock query() to hang after yielding one AssistantMessage
outcome = await run_session(workspace, "03:1", sys_prompt, task_prompt, config_with_short_timeout)
ASSERT outcome.status == "timeout"
```

---

### TS-03-10: Harvester merges changes via fast-forward

**Requirement:** 03-REQ-7.1, 03-REQ-7.3
**Type:** integration
**Description:** Verify that the harvester successfully fast-forward merges
a feature branch with commits into develop.

**Preconditions:**
- A temporary repo with develop branch.
- A worktree has been created, and a commit has been added to the feature
  branch within the worktree.

**Input:**
- `harvest(repo_root, workspace)`

**Expected:**
- Merge succeeds.
- Returned file list contains the committed file.
- Develop branch tip matches the feature branch tip.

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
add_file_and_commit(ws.path, "new_file.py")
files = await harvest(repo, ws)
ASSERT "new_file.py" IN files
ASSERT branch_tip(repo, "develop") == branch_tip(repo, ws.branch)
```

---

### TS-03-11: Harvester rebases on conflict and retries

**Requirement:** 03-REQ-7.2
**Type:** integration
**Description:** Verify that when fast-forward fails because develop has
diverged, the harvester rebases and retries successfully.

**Preconditions:**
- A worktree with a commit on the feature branch.
- A separate commit has been added to develop (causing divergence), touching
  a different file so rebase succeeds.

**Input:**
- `harvest(repo_root, workspace)`

**Expected:**
- Merge succeeds after rebase.
- Returned file list contains the committed file.

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
add_file_and_commit(ws.path, "feature_file.py")
add_commit_to_develop(repo, "other_file.py")  # diverge develop
files = await harvest(repo, ws)
ASSERT "feature_file.py" IN files
```

---

### TS-03-12: Allowlist hook blocks disallowed commands

**Requirement:** 03-REQ-8.1, 03-REQ-8.2
**Type:** unit
**Description:** Verify that the PreToolUse hook blocks commands not on the
allowlist and allows commands that are on it.

**Preconditions:**
- An allowlist hook built from a config with a small allowlist (e.g., only
  `["git", "python"]`).

**Input:**
- Simulate a PreToolUse hook call with `tool_name="Bash"` and
  `tool_input={"command": "rm -rf /"}`.
- Simulate a hook call with `tool_input={"command": "git status"}`.

**Expected:**
- `rm` command is blocked (decision == "block").
- `git` command is allowed.

**Assertion pseudocode:**
```
hook = build_allowlist_hook(config_with_small_allowlist)
result_blocked = await invoke_hook(hook, tool_name="Bash", command="rm -rf /")
ASSERT result_blocked["decision"] == "block"
result_allowed = await invoke_hook(hook, tool_name="Bash", command="git status")
ASSERT "decision" NOT IN result_allowed OR result_allowed.get("decision") != "block"
```

## Property Test Cases

### TS-03-P1: Worktree paths are unique per (spec, group)

**Property:** Property 1 from design.md
**Validates:** 03-REQ-1.1, 03-REQ-1.2
**Type:** property
**Description:** Different (spec_name, task_group) pairs always produce
different worktree paths and branch names.

**For any:** two distinct (spec_name, task_group) pairs where spec_name
contains only alphanumeric characters and underscores
**Invariant:** The resulting WorkspaceInfo objects have different `path` and
`branch` values.

**Assertion pseudocode:**
```
FOR ANY (spec_a, group_a), (spec_b, group_b) WHERE (spec_a, group_a) != (spec_b, group_b):
    ws_a = await create_worktree(repo, spec_a, group_a)
    ws_b = await create_worktree(repo, spec_b, group_b)
    ASSERT ws_a.path != ws_b.path
    ASSERT ws_a.branch != ws_b.branch
```

---

### TS-03-P2: SessionOutcome fields are well-formed

**Property:** Property 3 from design.md
**Validates:** 03-REQ-3.3
**Type:** property
**Description:** Every SessionOutcome has valid field values regardless of
how the session completes.

**For any:** SessionOutcome returned by run_session()
**Invariant:**
- `spec_name` is non-empty
- `task_group >= 0`
- `status` is one of "completed", "failed", "timeout"
- `input_tokens >= 0`
- `output_tokens >= 0`
- `duration_ms >= 0`

**Assertion pseudocode:**
```
FOR ANY outcome IN session_outcomes():
    ASSERT len(outcome.spec_name) > 0
    ASSERT outcome.task_group >= 0
    ASSERT outcome.status IN ["completed", "failed", "timeout"]
    ASSERT outcome.input_tokens >= 0
    ASSERT outcome.output_tokens >= 0
    ASSERT outcome.duration_ms >= 0
```

---

### TS-03-P3: Allowlist hook blocks all non-allowlisted commands

**Property:** Property 5 from design.md
**Validates:** 03-REQ-8.1, 03-REQ-8.2
**Type:** property
**Description:** For any command string whose first token is not in the
allowlist, the hook blocks it.

**For any:** command string where the first whitespace-delimited token is
not in a given allowlist
**Invariant:** The hook returns a block decision.

**Assertion pseudocode:**
```
FOR ANY cmd IN strings_not_starting_with_allowlisted_command():
    result = await invoke_hook(hook, tool_name="Bash", command=cmd)
    ASSERT result["decision"] == "block"
```

## Edge Case Tests

### TS-03-E1: Worktree creation fails on git error

**Requirement:** 03-REQ-1.E3
**Type:** unit
**Description:** Verify that a git failure during worktree creation raises
WorkspaceError.

**Preconditions:**
- Git subprocess is mocked to return a non-zero exit code.

**Input:**
- `create_worktree(repo, "test_spec", 1)`

**Expected:**
- `WorkspaceError` raised.
- Error message contains the git error output.

**Assertion pseudocode:**
```
# Mock run_git to fail
ASSERT_RAISES WorkspaceError FROM create_worktree(repo, "test_spec", 1)
```

---

### TS-03-E2: Destroy non-existent worktree is no-op

**Requirement:** 03-REQ-2.E1
**Type:** unit
**Description:** Verify that destroying a worktree that does not exist
succeeds silently.

**Preconditions:**
- A WorkspaceInfo pointing to a non-existent path.

**Input:**
- `destroy_worktree(repo, non_existent_workspace)`

**Expected:**
- No exception raised.

**Assertion pseudocode:**
```
ws = WorkspaceInfo(path=Path("/nonexistent"), branch="feature/x/1", spec_name="x", task_group=1)
await destroy_worktree(repo, ws)  # should not raise
```

---

### TS-03-E3: ResultMessage with is_error produces failed outcome

**Requirement:** 03-REQ-3.E2
**Type:** unit
**Description:** Verify that a ResultMessage with is_error=True produces a
failed outcome.

**Preconditions:**
- claude-code-sdk `query()` is mocked to yield a `ResultMessage(is_error=True,
  result="something went wrong")`.

**Input:**
- `run_session(workspace, ...)`

**Expected:**
- `outcome.status == "failed"`
- `outcome.error_message` is not None.

**Assertion pseudocode:**
```
outcome = await run_session(workspace, "03:1", sys_prompt, task_prompt, config)
ASSERT outcome.status == "failed"
ASSERT outcome.error_message IS NOT None
```

---

### TS-03-E4: Context assembly with missing spec file

**Requirement:** 03-REQ-4.E1
**Type:** unit
**Description:** Verify that a missing spec file is skipped without error.

**Preconditions:**
- A spec directory with only `requirements.md` (no design.md or tasks.md).

**Input:**
- `assemble_context(spec_dir, task_group=1)`

**Expected:**
- Returned string contains the requirements content.
- No exception raised.

**Assertion pseudocode:**
```
spec_dir = create_spec_dir(requirements="REQ content")  # no design or tasks
ctx = assemble_context(spec_dir, task_group=1)
ASSERT "REQ content" IN ctx
```

---

### TS-03-E5: Harvester with no new commits is no-op

**Requirement:** 03-REQ-7.E2
**Type:** integration
**Description:** Verify that harvesting a branch with no new commits returns
an empty file list.

**Preconditions:**
- A worktree exists but no commits have been made on the feature branch.

**Input:**
- `harvest(repo_root, workspace)`

**Expected:**
- Returns an empty list.
- Develop branch is unchanged.

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
files = await harvest(repo, ws)
ASSERT files == []
```

---

### TS-03-E6: Harvester raises IntegrationError on unresolvable conflict

**Requirement:** 03-REQ-7.E1
**Type:** integration
**Description:** Verify that an unresolvable merge conflict raises
IntegrationError.

**Preconditions:**
- A worktree with a commit modifying file X.
- A commit on develop also modifying the same lines in file X (creating
  a true conflict).

**Input:**
- `harvest(repo_root, workspace)`

**Expected:**
- `IntegrationError` raised.
- Develop branch is unchanged (no partial merge).

**Assertion pseudocode:**
```
ws = await create_worktree(repo, "test_spec", 1)
modify_file_and_commit(ws.path, "shared.py", "feature content")
modify_file_and_commit_on_develop(repo, "shared.py", "develop content")
ASSERT_RAISES IntegrationError FROM harvest(repo, ws)
ASSERT develop_tip_unchanged(repo)
```

---

### TS-03-E7: Allowlist hook blocks empty command

**Requirement:** 03-REQ-8.E1
**Type:** unit
**Description:** Verify that an empty or whitespace-only command string is
blocked.

**Preconditions:**
- An allowlist hook built from default config.

**Input:**
- Simulate a PreToolUse hook call with `command=""`.
- Simulate a hook call with `command="   "`.

**Expected:**
- Both are blocked.

**Assertion pseudocode:**
```
result_empty = await invoke_hook(hook, tool_name="Bash", command="")
ASSERT result_empty["decision"] == "block"
result_spaces = await invoke_hook(hook, tool_name="Bash", command="   ")
ASSERT result_spaces["decision"] == "block"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 03-REQ-1.1 | TS-03-1, TS-03-P1 | integration, property |
| 03-REQ-1.2 | TS-03-1, TS-03-P1 | integration, property |
| 03-REQ-1.3 | TS-03-1 | integration |
| 03-REQ-1.E1 | TS-03-3 | integration |
| 03-REQ-1.E2 | TS-03-3 | integration |
| 03-REQ-1.E3 | TS-03-E1 | unit |
| 03-REQ-2.1 | TS-03-2 | integration |
| 03-REQ-2.2 | TS-03-2 | integration |
| 03-REQ-2.E1 | TS-03-E2 | unit |
| 03-REQ-2.E2 | TS-03-E2 | unit |
| 03-REQ-3.1 | TS-03-7 | unit |
| 03-REQ-3.2 | TS-03-7 | unit |
| 03-REQ-3.3 | TS-03-7, TS-03-P2 | unit, property |
| 03-REQ-3.4 | TS-03-12 | unit |
| 03-REQ-3.E1 | TS-03-8 | unit |
| 03-REQ-3.E2 | TS-03-E3 | unit |
| 03-REQ-4.1 | TS-03-4 | unit |
| 03-REQ-4.2 | TS-03-5 | unit |
| 03-REQ-4.3 | TS-03-4, TS-03-5 | unit |
| 03-REQ-4.E1 | TS-03-E4 | unit |
| 03-REQ-5.1 | TS-03-6 | unit |
| 03-REQ-5.2 | TS-03-6 | unit |
| 03-REQ-6.1 | TS-03-9 | unit |
| 03-REQ-6.2 | TS-03-9 | unit |
| 03-REQ-6.E1 | TS-03-9 | unit |
| 03-REQ-7.1 | TS-03-10 | integration |
| 03-REQ-7.2 | TS-03-11 | integration |
| 03-REQ-7.3 | TS-03-10 | integration |
| 03-REQ-7.E1 | TS-03-E6 | integration |
| 03-REQ-7.E2 | TS-03-E5 | integration |
| 03-REQ-8.1 | TS-03-12, TS-03-P3 | unit, property |
| 03-REQ-8.2 | TS-03-12, TS-03-P3 | unit, property |
| 03-REQ-8.E1 | TS-03-E7 | unit |
| 03-REQ-9.1 | TS-03-1, TS-03-2, TS-03-10, TS-03-11 | integration |
| 03-REQ-9.2 | TS-03-E1, TS-03-E6 | unit, integration |
| Property 1 | TS-03-P1 | property |
| Property 3 | TS-03-P2 | property |
| Property 5 | TS-03-P3 | property |
