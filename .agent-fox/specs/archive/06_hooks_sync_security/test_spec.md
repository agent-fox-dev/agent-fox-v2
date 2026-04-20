# Test Specification: Hooks, Sync Barriers, and Security

## Overview

Tests for the hook runner, command allowlist security system, sync barriers,
and hot-loading. Tests map to requirements in `requirements.md` and
correctness properties in `design.md`.

## Test Cases

### TS-06-1: Pre-session hooks execute in order

**Requirement:** 06-REQ-1.1
**Type:** unit
**Description:** Verify that configured pre-session hooks execute sequentially
in the order they are listed.

**Preconditions:**
- Two temporary executable scripts: `hook_a.sh` (writes "a" to a marker file),
  `hook_b.sh` (appends "b" to the same marker file).
- HookConfig with `pre_code = ["hook_a.sh", "hook_b.sh"]`.

**Input:**
- `run_pre_session_hooks(context, config)`

**Expected:**
- Both hooks execute successfully (exit code 0).
- Marker file contains "ab" (confirming order).
- Two HookResults returned.

**Assertion pseudocode:**
```
results = run_pre_session_hooks(context, config)
ASSERT len(results) == 2
ASSERT results[0].exit_code == 0
ASSERT results[1].exit_code == 0
ASSERT marker_file.read_text() == "ab"
```

---

### TS-06-2: Post-session hooks execute after session

**Requirement:** 06-REQ-1.2
**Type:** unit
**Description:** Verify that configured post-session hooks execute and receive
the correct context environment variables.

**Preconditions:**
- A temporary script that writes `$AF_SPEC_NAME` and `$AF_TASK_GROUP` to a
  marker file.
- HookConfig with `post_code = ["write_context.sh"]`.

**Input:**
- `run_post_session_hooks(context, config)` where context has
  `spec_name="03_session"` and `task_group="2"`.

**Expected:**
- Hook executes successfully.
- Marker file contains "03_session 2".

**Assertion pseudocode:**
```
results = run_post_session_hooks(context, config)
ASSERT len(results) == 1
ASSERT results[0].exit_code == 0
ASSERT "03_session" IN marker_file.read_text()
ASSERT "2" IN marker_file.read_text()
```

---

### TS-06-3: Hook abort mode raises HookError

**Requirement:** 06-REQ-2.1, 06-REQ-2.3
**Type:** unit
**Description:** Verify that a hook failing in abort mode raises HookError.

**Preconditions:**
- A temporary script that exits with code 1.
- HookConfig with default mode (abort).

**Input:**
- `run_hook(script, context, mode="abort")`

**Expected:**
- `HookError` is raised.
- Error message contains the script name and exit code.

**Assertion pseudocode:**
```
ASSERT_RAISES HookError FROM run_hook(failing_script, context, mode="abort")
ASSERT "exit code" IN str(error) OR "1" IN str(error)
```

---

### TS-06-4: Hook warn mode logs and continues

**Requirement:** 06-REQ-2.2
**Type:** unit
**Description:** Verify that a hook failing in warn mode logs a warning and
returns a result without raising.

**Preconditions:**
- A temporary script that exits with code 1.
- HookConfig with mode set to "warn" for this script.

**Input:**
- `run_hook(script, context, mode="warn")`

**Expected:**
- No exception raised.
- HookResult has exit_code=1.
- Warning was logged (verify via caplog or mock).

**Assertion pseudocode:**
```
result = run_hook(failing_script, context, mode="warn")
ASSERT result.exit_code == 1
ASSERT NOT result.timed_out
# Check that a warning was logged
ASSERT "warn" IN caplog.text.lower()
```

---

### TS-06-5: Hook timeout terminates subprocess

**Requirement:** 06-REQ-3.1, 06-REQ-3.2
**Type:** unit
**Description:** Verify that a hook script exceeding the timeout is terminated
and treated as a failure.

**Preconditions:**
- A temporary script that sleeps for 10 seconds.
- Timeout set to 2 seconds.

**Input:**
- `run_hook(script, context, timeout=2, mode="abort")`

**Expected:**
- `HookError` is raised (abort mode).
- HookResult has `timed_out=True`.

**Assertion pseudocode:**
```
ASSERT_RAISES HookError FROM run_hook(slow_script, context, timeout=2, mode="abort")
```

---

### TS-06-6: Hook context environment variables

**Requirement:** 06-REQ-4.1
**Type:** unit
**Description:** Verify that build_hook_env produces the correct AF_*
environment variables.

**Preconditions:** None.

**Input:**
- `build_hook_env(HookContext(spec_name="05_platform", task_group="3",
  workspace="/tmp/ws", branch="feature/05/3"))`

**Expected:**
- Returned dict contains `AF_SPEC_NAME="05_platform"`,
  `AF_TASK_GROUP="3"`, `AF_WORKSPACE="/tmp/ws"`,
  `AF_BRANCH="feature/05/3"`.

**Assertion pseudocode:**
```
env = build_hook_env(context)
ASSERT env["AF_SPEC_NAME"] == "05_platform"
ASSERT env["AF_TASK_GROUP"] == "3"
ASSERT env["AF_WORKSPACE"] == "/tmp/ws"
ASSERT env["AF_BRANCH"] == "feature/05/3"
```

---

### TS-06-7: Sync barrier hook context

**Requirement:** 06-REQ-4.2
**Type:** unit
**Description:** Verify that sync-barrier hooks receive the special context
with `AF_SPEC_NAME="__sync_barrier__"`.

**Preconditions:**
- A temporary script that writes `$AF_SPEC_NAME` to a marker file.
- HookConfig with `sync_barrier = ["write_spec.sh"]`.

**Input:**
- `run_sync_barrier_hooks(barrier_number=3, config=config)`

**Expected:**
- Hook executes successfully.
- Marker file contains "__sync_barrier__".

**Assertion pseudocode:**
```
results = run_sync_barrier_hooks(barrier_number=3, config=config)
ASSERT len(results) == 1
ASSERT results[0].exit_code == 0
ASSERT "__sync_barrier__" IN marker_file.read_text()
```

---

### TS-06-8: No-hooks flag skips all hooks

**Requirement:** 06-REQ-5.1
**Type:** unit
**Description:** Verify that passing no_hooks=True causes all hook functions
to return empty lists without executing any scripts.

**Preconditions:**
- HookConfig with hooks configured for all phases.

**Input:**
- `run_pre_session_hooks(context, config, no_hooks=True)`
- `run_post_session_hooks(context, config, no_hooks=True)`
- `run_sync_barrier_hooks(1, config, no_hooks=True)`

**Expected:**
- All return empty lists.
- No subprocesses spawned (verify via mock or marker file absence).

**Assertion pseudocode:**
```
ASSERT run_pre_session_hooks(context, config, no_hooks=True) == []
ASSERT run_post_session_hooks(context, config, no_hooks=True) == []
ASSERT run_sync_barrier_hooks(1, config, no_hooks=True) == []
```

---

### TS-06-9: Default allowlist contains expected commands

**Requirement:** 06-REQ-8.3
**Type:** unit
**Description:** Verify the DEFAULT_ALLOWLIST contains all documented
commands.

**Preconditions:** None.

**Input:**
- `DEFAULT_ALLOWLIST`

**Expected:**
- Contains "git", "python", "python3", "uv", "npm", "node", "pytest",
  "ruff", "mypy", "make", "cargo", "go", "ls", "cat", "mkdir", "cp", "mv",
  "rm", "find", "grep", "sed", "awk", "echo", "curl", "wget", "tar",
  "gzip", "which", "env", "printenv", "date", "head", "tail", "wc", "sort",
  "diff", "touch", "chmod".

**Assertion pseudocode:**
```
expected = {"git", "python", "python3", "uv", "npm", "node", "pytest",
            "ruff", "mypy", "make", "cargo", "go", "ls", "cat", "mkdir",
            "cp", "mv", "rm", "find", "grep", "sed", "awk", "echo",
            "curl", "wget", "tar", "gzip", "which", "env", "printenv",
            "date", "head", "tail", "wc", "sort", "diff", "touch", "chmod"}
ASSERT expected.issubset(DEFAULT_ALLOWLIST)
```

---

### TS-06-10: Allowed command passes allowlist check

**Requirement:** 06-REQ-8.1, 06-REQ-8.2
**Type:** unit
**Description:** Verify that a command on the allowlist is permitted.

**Preconditions:** None.

**Input:**
- `check_command_allowed("git status --short", DEFAULT_ALLOWLIST)`

**Expected:**
- Returns `(True, ...)`.

**Assertion pseudocode:**
```
allowed, msg = check_command_allowed("git status --short", DEFAULT_ALLOWLIST)
ASSERT allowed is True
```

---

### TS-06-11: Blocked command fails allowlist check

**Requirement:** 06-REQ-8.2
**Type:** unit
**Description:** Verify that a command not on the allowlist is blocked.

**Preconditions:** None.

**Input:**
- `check_command_allowed("docker run evil", DEFAULT_ALLOWLIST)`

**Expected:**
- Returns `(False, ...)`.
- Message mentions "docker".

**Assertion pseudocode:**
```
allowed, msg = check_command_allowed("docker run evil", DEFAULT_ALLOWLIST)
ASSERT allowed is False
ASSERT "docker" IN msg
```

---

### TS-06-12: Command extraction strips path prefix

**Requirement:** 06-REQ-8.1
**Type:** unit
**Description:** Verify that extract_command_name handles path-prefixed
commands correctly.

**Preconditions:** None.

**Input:**
- `extract_command_name("/usr/bin/python3 -m pytest")`
- `extract_command_name("/home/user/.local/bin/ruff check .")`

**Expected:**
- Returns `"python3"` and `"ruff"` respectively.

**Assertion pseudocode:**
```
ASSERT extract_command_name("/usr/bin/python3 -m pytest") == "python3"
ASSERT extract_command_name("/home/user/.local/bin/ruff check .") == "ruff"
```

---

### TS-06-13: Custom allowlist replaces default

**Requirement:** 06-REQ-9.1
**Type:** unit
**Description:** Verify that setting bash_allowlist replaces the default list.

**Preconditions:** None.

**Input:**
- `build_effective_allowlist(SecurityConfig(bash_allowlist=["git", "make"]))`

**Expected:**
- Returns `frozenset({"git", "make"})`.
- Does not contain "python" or other defaults.

**Assertion pseudocode:**
```
result = build_effective_allowlist(SecurityConfig(bash_allowlist=["git", "make"]))
ASSERT result == frozenset({"git", "make"})
ASSERT "python" NOT IN result
```

---

### TS-06-14: Allowlist extend adds to default

**Requirement:** 06-REQ-9.2
**Type:** unit
**Description:** Verify that bash_allowlist_extend adds commands to the
default list.

**Preconditions:** None.

**Input:**
- `build_effective_allowlist(SecurityConfig(bash_allowlist_extend=["docker", "kubectl"]))`

**Expected:**
- Returns DEFAULT_ALLOWLIST union {"docker", "kubectl"}.
- Contains both "git" (from default) and "docker" (from extension).

**Assertion pseudocode:**
```
result = build_effective_allowlist(SecurityConfig(bash_allowlist_extend=["docker", "kubectl"]))
ASSERT "git" IN result
ASSERT "docker" IN result
ASSERT "kubectl" IN result
```

---

### TS-06-15: Hot-load discovers new specs

**Requirement:** 06-REQ-7.1, 06-REQ-7.2, 06-REQ-7.3
**Type:** unit
**Description:** Verify that hot_load_specs finds new spec folders and adds
them to the task graph.

**Preconditions:**
- A temporary `.specs/` directory containing `01_existing/` (already in graph)
  and `07_new_feature/` (with valid tasks.md and prd.md).
- A TaskGraph containing only nodes from `01_existing`.

**Input:**
- `hot_load_specs(graph, specs_dir)`

**Expected:**
- Updated graph contains nodes from both `01_existing` and `07_new_feature`.
- Returned list of new spec names includes `"07_new_feature"`.
- Graph ordering includes the new nodes.

**Assertion pseudocode:**
```
updated_graph, new_specs = hot_load_specs(graph, specs_dir)
ASSERT "07_new_feature" IN new_specs
ASSERT any(n.spec_name == "07_new_feature" for n in updated_graph.nodes.values())
ASSERT len(updated_graph.order) > len(graph.order)
```

---

### TS-06-16: Hot-load with no new specs is a no-op

**Requirement:** 06-REQ-7.E2
**Type:** unit
**Description:** Verify that hot_load_specs returns the original graph when
no new specs are found.

**Preconditions:**
- A `.specs/` directory whose contents match the current graph exactly.

**Input:**
- `hot_load_specs(graph, specs_dir)`

**Expected:**
- Returns the same graph object (or an equivalent one).
- Empty list of new spec names.

**Assertion pseudocode:**
```
updated_graph, new_specs = hot_load_specs(graph, specs_dir)
ASSERT new_specs == []
ASSERT updated_graph.nodes == graph.nodes
```

## Property Test Cases

### TS-06-P1: Allowlist enforcement completeness

**Property:** Property 1 from design.md
**Validates:** 06-REQ-8.1, 06-REQ-8.2
**Type:** property
**Description:** Every non-empty command string is deterministically allowed
or blocked based on the allowlist.

**For any:** non-empty command string and any frozenset allowlist
**Invariant:** `check_command_allowed(cmd, allowlist)` returns `(True, _)` if
and only if the extracted command name is in the allowlist.

**Assertion pseudocode:**
```
FOR ANY cmd IN non_empty_strings(), allowlist IN frozensets_of_strings():
    name = extract_command_name(cmd)
    allowed, _ = check_command_allowed(cmd, allowlist)
    ASSERT allowed == (name in allowlist)
```

---

### TS-06-P2: Default allowlist stability

**Property:** Property 3 from design.md
**Validates:** 06-REQ-8.3, 06-REQ-9.1, 06-REQ-9.2
**Type:** property
**Description:** Default configuration always yields the default allowlist.

**For any:** SecurityConfig with default values
**Invariant:** `build_effective_allowlist(config)` equals `DEFAULT_ALLOWLIST`.

**Assertion pseudocode:**
```
config = SecurityConfig()
ASSERT build_effective_allowlist(config) == DEFAULT_ALLOWLIST
```

---

### TS-06-P3: Hook mode determinism

**Property:** Property 4 from design.md
**Validates:** 06-REQ-2.1, 06-REQ-2.2, 06-REQ-2.3
**Type:** property
**Description:** Abort mode always raises on failure; warn mode never raises.

**For any:** hook script with non-zero exit code, mode in {"abort", "warn"}
**Invariant:** run_hook raises HookError iff mode == "abort".

**Assertion pseudocode:**
```
FOR ANY mode IN ["abort", "warn"]:
    IF mode == "abort":
        ASSERT_RAISES HookError FROM run_hook(failing_script, context, mode=mode)
    ELSE:
        result = run_hook(failing_script, context, mode=mode)
        ASSERT result.exit_code != 0
        # No exception raised
```

---

### TS-06-P4: Hot-load monotonicity

**Property:** Property 5 from design.md
**Validates:** 06-REQ-7.1, 06-REQ-7.3
**Type:** property
**Description:** Hot-loading never removes existing nodes.

**For any:** task graph and .specs/ directory
**Invariant:** After hot_load_specs, all original node IDs are still present.

**Assertion pseudocode:**
```
FOR ANY graph, specs_dir:
    original_ids = set(graph.nodes.keys())
    updated_graph, _ = hot_load_specs(graph, specs_dir)
    ASSERT original_ids.issubset(set(updated_graph.nodes.keys()))
```

## Edge Case Tests

### TS-06-E1: No hooks configured

**Requirement:** 06-REQ-1.E1
**Type:** unit
**Description:** Verify that empty hook lists result in no subprocess calls.

**Preconditions:**
- HookConfig with `pre_code=[]`, `post_code=[]`, `sync_barrier=[]`.

**Input:**
- `run_pre_session_hooks(context, config)`
- `run_post_session_hooks(context, config)`

**Expected:**
- Both return empty lists.
- No subprocesses spawned.

**Assertion pseudocode:**
```
ASSERT run_pre_session_hooks(context, config) == []
ASSERT run_post_session_hooks(context, config) == []
```

---

### TS-06-E2: Hook script not found

**Requirement:** 06-REQ-2.E1
**Type:** unit
**Description:** Verify that a non-existent hook script is treated as a
failure with the configured mode applied.

**Preconditions:**
- HookConfig with `pre_code=["/nonexistent/hook.sh"]`, mode="abort".

**Input:**
- `run_pre_session_hooks(context, config)`

**Expected:**
- `HookError` raised (abort mode).

**Assertion pseudocode:**
```
ASSERT_RAISES HookError FROM run_pre_session_hooks(context, config)
```

---

### TS-06-E3: Empty command string blocked

**Requirement:** 06-REQ-8.E1
**Type:** unit
**Description:** Verify that an empty command string is blocked.

**Preconditions:** None.

**Input:**
- `extract_command_name("")`
- `extract_command_name("   ")`

**Expected:**
- `SecurityError` raised for both.

**Assertion pseudocode:**
```
ASSERT_RAISES SecurityError FROM extract_command_name("")
ASSERT_RAISES SecurityError FROM extract_command_name("   ")
```

---

### TS-06-E4: Non-Bash tool passes through

**Requirement:** 06-REQ-8.E2
**Type:** unit
**Description:** Verify that the PreToolUse hook allows non-Bash tools.

**Preconditions:**
- A PreToolUse hook created via `make_pre_tool_use_hook(config)`.

**Input:**
- Call the hook with `tool_name="Read"` and any `tool_input`.

**Expected:**
- Returns `{"decision": "allow"}` or equivalent pass-through.

**Assertion pseudocode:**
```
hook = make_pre_tool_use_hook(SecurityConfig())
result = hook(tool_name="Read", tool_input={"file_path": "/tmp/test"})
ASSERT result["decision"] == "allow"
```

---

### TS-06-E5: New spec with invalid dependency

**Requirement:** 06-REQ-7.E1
**Type:** unit
**Description:** Verify that a new spec referencing a nonexistent dependency
is skipped with a warning.

**Preconditions:**
- A new spec folder `99_broken/` with prd.md declaring dependency on
  `50_nonexistent`.
- A task graph with no `50_nonexistent` spec.

**Input:**
- `hot_load_specs(graph, specs_dir)`

**Expected:**
- Warning logged about invalid dependency.
- `99_broken` not added to graph.
- Graph unchanged.

**Assertion pseudocode:**
```
updated_graph, new_specs = hot_load_specs(graph, specs_dir)
ASSERT "99_broken" NOT IN new_specs
ASSERT updated_graph.nodes == graph.nodes
```

---

### TS-06-E6: Both bash_allowlist and bash_allowlist_extend set

**Requirement:** 06-REQ-9.E1
**Type:** unit
**Description:** Verify that bash_allowlist takes precedence when both are set.

**Preconditions:** None.

**Input:**
- `build_effective_allowlist(SecurityConfig(bash_allowlist=["git"],
  bash_allowlist_extend=["docker"]))`

**Expected:**
- Returns `frozenset({"git"})`.
- "docker" is not included.
- Warning logged about precedence.

**Assertion pseudocode:**
```
result = build_effective_allowlist(SecurityConfig(
    bash_allowlist=["git"],
    bash_allowlist_extend=["docker"],
))
ASSERT result == frozenset({"git"})
ASSERT "docker" NOT IN result
```

---

### TS-06-E7: Sync interval zero disables barriers

**Requirement:** 06-REQ-6.E1
**Type:** unit
**Description:** Verify that sync_interval=0 means sync barriers never
trigger.

**Preconditions:**
- OrchestratorConfig with sync_interval=0.

**Input:**
- Simulate 100 completed sessions.

**Expected:**
- No sync barrier is triggered.

**Assertion pseudocode:**
```
FOR completed IN range(1, 101):
    triggered = (sync_interval > 0 and completed % sync_interval == 0)
    ASSERT triggered is False
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 06-REQ-1.1 | TS-06-1 | unit |
| 06-REQ-1.2 | TS-06-2 | unit |
| 06-REQ-1.E1 | TS-06-E1 | unit |
| 06-REQ-2.1 | TS-06-3 | unit |
| 06-REQ-2.2 | TS-06-4 | unit |
| 06-REQ-2.3 | TS-06-3 | unit |
| 06-REQ-2.E1 | TS-06-E2 | unit |
| 06-REQ-3.1 | TS-06-5 | unit |
| 06-REQ-3.2 | TS-06-5 | unit |
| 06-REQ-4.1 | TS-06-6 | unit |
| 06-REQ-4.2 | TS-06-7 | unit |
| 06-REQ-5.1 | TS-06-8 | unit |
| 06-REQ-6.1 | TS-06-7 | unit |
| 06-REQ-6.2 | (verified by orchestrator integration) | integration |
| 06-REQ-6.3 | TS-06-15 | unit |
| 06-REQ-6.E1 | TS-06-E7 | unit |
| 06-REQ-7.1 | TS-06-15 | unit |
| 06-REQ-7.2 | TS-06-15 | unit |
| 06-REQ-7.3 | TS-06-15 | unit |
| 06-REQ-7.E1 | TS-06-E5 | unit |
| 06-REQ-7.E2 | TS-06-16 | unit |
| 06-REQ-8.1 | TS-06-10, TS-06-12 | unit |
| 06-REQ-8.2 | TS-06-10, TS-06-11 | unit |
| 06-REQ-8.3 | TS-06-9 | unit |
| 06-REQ-8.E1 | TS-06-E3 | unit |
| 06-REQ-8.E2 | TS-06-E4 | unit |
| 06-REQ-9.1 | TS-06-13 | unit |
| 06-REQ-9.2 | TS-06-14 | unit |
| 06-REQ-9.E1 | TS-06-E6 | unit |
| Property 1 | TS-06-P1 | property |
| Property 3 | TS-06-P2 | property |
| Property 4 | TS-06-P3 | property |
| Property 5 | TS-06-P4 | property |
