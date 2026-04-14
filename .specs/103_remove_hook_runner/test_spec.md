# Test Specification: Remove Hook Runner

## Overview

Tests verify three concerns: (1) the hook runner is fully gone, (2) the
security module works identically from its new package, and (3) the
ConfigReloader returns a typed dataclass. Most existing security tests are
relocated unchanged -- this spec focuses on new assertions specific to the
removal and relocation.

## Test Cases

### TS-103-1: HookConfig Absent from AgentFoxConfig

**Requirement:** 103-REQ-1.2
**Type:** unit
**Description:** Verify `AgentFoxConfig` no longer has a `hooks` field.

**Preconditions:**
- `agent_fox.core.config` is importable.

**Input:**
- Inspect `AgentFoxConfig.model_fields`.

**Expected:**
- `"hooks"` is not in `AgentFoxConfig.model_fields`.

**Assertion pseudocode:**
```
from agent_fox.core.config import AgentFoxConfig
ASSERT "hooks" NOT IN AgentFoxConfig.model_fields
```

### TS-103-2: HookError Absent from Errors Module

**Requirement:** 103-REQ-1.3
**Type:** unit
**Description:** Verify `HookError` is no longer defined in `errors.py`.

**Preconditions:**
- `agent_fox.core.errors` is importable.

**Input:**
- Attempt to access `HookError` attribute.

**Expected:**
- `AttributeError` is raised.

**Assertion pseudocode:**
```
import agent_fox.core.errors as errors
ASSERT NOT hasattr(errors, "HookError")
```

### TS-103-3: TOML With hooks Section Parses Successfully

**Requirement:** 103-REQ-1.E1
**Type:** unit
**Description:** Verify a TOML config containing `[hooks]` is parsed without
error.

**Preconditions:**
- A temporary TOML file with a `[hooks]` section.

**Input:**
```toml
[hooks]
pre_code = ["echo hello"]
timeout = 60
```

**Expected:**
- `load_config()` returns an `AgentFoxConfig` instance without raising.

**Assertion pseudocode:**
```
config = load_config(toml_path)
ASSERT isinstance(config, AgentFoxConfig)
```

### TS-103-4: Security Module Importable at New Path

**Requirement:** 103-REQ-2.1
**Type:** unit
**Description:** Verify all public names are importable from
`agent_fox.security.security`.

**Preconditions:**
- Package `agent_fox.security` exists.

**Input:**
- Import each public name.

**Expected:**
- All imports succeed; each name is callable or a frozenset.

**Assertion pseudocode:**
```
from agent_fox.security.security import (
    make_pre_tool_use_hook,
    DEFAULT_ALLOWLIST,
    build_effective_allowlist,
    check_command_allowed,
    extract_command_name,
    check_shell_operators,
)
ASSERT callable(make_pre_tool_use_hook)
ASSERT isinstance(DEFAULT_ALLOWLIST, frozenset)
```

### TS-103-5: ReloadResult Dataclass Fields

**Requirement:** 103-REQ-3.1
**Type:** unit
**Description:** Verify `ReloadResult` has exactly the four expected fields.

**Preconditions:**
- `ReloadResult` is importable from the engine module.

**Input:**
- Inspect `ReloadResult` fields.

**Expected:**
- Fields are `config`, `circuit`, `archetypes`, `planning`.

**Assertion pseudocode:**
```
import dataclasses
from agent_fox.engine.engine import ReloadResult
field_names = {f.name for f in dataclasses.fields(ReloadResult)}
ASSERT field_names == {"config", "circuit", "archetypes", "planning"}
```

### TS-103-6: ConfigReloader Returns ReloadResult

**Requirement:** 103-REQ-3.1, 103-REQ-3.2
**Type:** unit
**Description:** Verify `ConfigReloader.reload()` returns a `ReloadResult`
on successful reload.

**Preconditions:**
- A temporary TOML config file that differs from the current config hash.

**Input:**
- Call `reloader.reload(...)` with a changed config file.

**Expected:**
- Return value is a `ReloadResult` instance (not a tuple).

**Assertion pseudocode:**
```
result = reloader.reload(current_config=cfg, circuit=cb, sink=None, run_id="")
ASSERT isinstance(result, ReloadResult)
ASSERT hasattr(result, "config")
ASSERT hasattr(result, "circuit")
ASSERT hasattr(result, "archetypes")
ASSERT hasattr(result, "planning")
```

### TS-103-7: config_gen Has No HookConfig References

**Requirement:** 103-REQ-4.3
**Type:** unit
**Description:** Verify `config_gen.py` contains no `HookConfig` entries.

**Preconditions:**
- Source file `agent_fox/core/config_gen.py` is readable.

**Input:**
- Read file content.

**Expected:**
- String `"HookConfig"` does not appear in the file.

**Assertion pseudocode:**
```
content = Path("agent_fox/core/config_gen.py").read_text()
ASSERT "HookConfig" NOT IN content
```

## Property Test Cases

### TS-103-P1: Security Module Functional Equivalence

**Property:** Property 1 from design.md
**Validates:** 103-REQ-2.1, 103-REQ-2.2
**Type:** property
**Description:** The relocated security module produces identical allowlist
decisions for any command string and SecurityConfig.

**For any:** command string (text strategy, 1-200 chars), SecurityConfig
with optional bash_allowlist (list of text or None) and
bash_allowlist_extend (list of text).

**Invariant:** `check_command_allowed(cmd, build_effective_allowlist(cfg))`
returns the same `(bool, str)` tuple regardless of import path.

**Assertion pseudocode:**
```
FOR ANY cmd IN text(1..200), cfg IN security_configs():
    allowlist = build_effective_allowlist(cfg)
    allowed, msg = check_command_allowed(cmd, allowlist)
    # This is a tautology post-move (same code), but verifies the import works
    ASSERT isinstance(allowed, bool)
    ASSERT isinstance(msg, str)
```

### TS-103-P2: Hook Runner Absence in Production Code

**Property:** Property 2 from design.md
**Validates:** 103-REQ-1.1, 103-REQ-1.2, 103-REQ-1.3, 103-REQ-1.6
**Type:** property
**Description:** No production module imports or references hook runner
symbols.

**For any:** Python file in `agent_fox/` (excluding `__pycache__`).

**Invariant:** File content does not contain any of: `HookConfig`,
`HookContext`, `HookResult`, `HookError`, `run_pre_session_hooks`,
`run_post_session_hooks`, `run_sync_barrier_hooks`, `from agent_fox.hooks.hooks`.

**Assertion pseudocode:**
```
FOR ANY py_file IN glob("agent_fox/**/*.py"):
    content = py_file.read_text()
    FOR symbol IN BANNED_SYMBOLS:
        ASSERT symbol NOT IN content
```

### TS-103-P3: ReloadResult Field Access by Name

**Property:** Property 3 from design.md
**Validates:** 103-REQ-3.1, 103-REQ-3.2
**Type:** property
**Description:** ReloadResult fields are accessible by name and the
dataclass is frozen.

**For any:** mock values for each field.

**Invariant:** Constructing a `ReloadResult` and accessing `.config`,
`.circuit`, `.archetypes`, `.planning` returns the same objects passed in.

**Assertion pseudocode:**
```
FOR ANY cfg, cb, arch, plan IN mock_configs():
    result = ReloadResult(config=cfg, circuit=cb, archetypes=arch, planning=plan)
    ASSERT result.config is cfg
    ASSERT result.circuit is cb
    ASSERT result.archetypes is arch
    ASSERT result.planning is plan
```

### TS-103-P4: TOML Backward Compatibility

**Property:** Property 4 from design.md
**Validates:** 103-REQ-1.4, 103-REQ-1.E1
**Type:** property
**Description:** Any TOML with a `[hooks]` section parses without error.

**For any:** TOML string containing `[hooks]` with arbitrary key-value pairs
from a reasonable set (strings, ints, lists).

**Invariant:** `load_config(path)` returns an `AgentFoxConfig` without
raising.

**Assertion pseudocode:**
```
FOR ANY hooks_content IN toml_hooks_sections():
    toml_path = write_temp_toml(hooks_content)
    config = load_config(toml_path)
    ASSERT isinstance(config, AgentFoxConfig)
```

## Edge Case Tests

### TS-103-E1: Old hooks Package Import Fails

**Requirement:** 103-REQ-2.E1
**Type:** unit
**Description:** Importing from the old `agent_fox.hooks.security` path
raises ImportError.

**Preconditions:**
- `agent_fox/hooks/` directory no longer exists (or has no `security.py`).

**Input:**
- Attempt `from agent_fox.hooks.security import make_pre_tool_use_hook`.

**Expected:**
- `ImportError` or `ModuleNotFoundError` is raised.

**Assertion pseudocode:**
```
WITH RAISES ImportError:
    from agent_fox.hooks.security import make_pre_tool_use_hook
```

### TS-103-E2: Hot-Load Tests Still Pass After Conftest Cleanup

**Requirement:** 103-REQ-4.E1
**Type:** unit
**Description:** The `tmp_specs_dir` fixture is still available to hot-load
tests after hook-runner fixtures are removed from conftest.

**Preconditions:**
- `tests/unit/hooks/conftest.py` exists with `tmp_specs_dir` fixture.

**Input:**
- Run hot-load test suite.

**Expected:**
- All tests in `tests/unit/hooks/test_hot_load.py` pass.

**Assertion pseudocode:**
```
result = pytest.main(["tests/unit/hooks/test_hot_load.py", "-q"])
ASSERT result == 0
```

## Integration Smoke Tests

### TS-103-SMOKE-1: Security Allowlist Enforcement End-to-End

**Execution Path:** Path 1 from design.md
**Description:** Verify the security allowlist blocks a disallowed command
after the module is relocated.

**Setup:** Create a `SecurityConfig` with default allowlist. No mocks on
security module internals.

**Trigger:** Call `make_pre_tool_use_hook(config)` and invoke the returned
hook with a disallowed command.

**Expected side effects:**
- Hook returns `{"decision": "block", "message": "..."}` for a command not
  on the allowlist.
- Hook returns `{"decision": "allow"}` for a command on the allowlist.

**Must NOT satisfy with:** Mocking `check_command_allowed` or
`build_effective_allowlist` -- these are the components under test.

**Assertion pseudocode:**
```
from agent_fox.security.security import make_pre_tool_use_hook
from agent_fox.core.config import SecurityConfig

hook = make_pre_tool_use_hook(SecurityConfig())
blocked = hook(tool_name="Bash", tool_input={"command": "rm -rf /"})
ASSERT blocked["decision"] == "block"

allowed = hook(tool_name="Bash", tool_input={"command": "git status"})
ASSERT allowed["decision"] == "allow"

# Non-Bash tools pass through
passthrough = hook(tool_name="Read", tool_input={"path": "/tmp/foo"})
ASSERT passthrough["decision"] == "allow"
```

## Coverage Matrix

| Requirement | Test Spec Entry | Type |
|-------------|-----------------|------|
| 103-REQ-1.1 | TS-103-P2 | property |
| 103-REQ-1.2 | TS-103-1, TS-103-P2 | unit, property |
| 103-REQ-1.3 | TS-103-2, TS-103-P2 | unit, property |
| 103-REQ-1.4 | TS-103-3, TS-103-P4 | unit, property |
| 103-REQ-1.5 | (verified by TS-103-P2 -- CLI code is in agent_fox/) | property |
| 103-REQ-1.6 | TS-103-P2 | property |
| 103-REQ-1.E1 | TS-103-3, TS-103-P4 | unit, property |
| 103-REQ-2.1 | TS-103-4, TS-103-P1 | unit, property |
| 103-REQ-2.2 | TS-103-P1, TS-103-SMOKE-1 | property, integration |
| 103-REQ-2.3 | TS-103-E2 | unit |
| 103-REQ-2.E1 | TS-103-E1 | unit |
| 103-REQ-3.1 | TS-103-5, TS-103-6, TS-103-P3 | unit, property |
| 103-REQ-3.2 | TS-103-6, TS-103-P3 | unit, property |
| 103-REQ-3.3 | TS-103-6 | unit |
| 103-REQ-4.1 | TS-103-P2 | property |
| 103-REQ-4.2 | TS-103-E2 | unit |
| 103-REQ-4.3 | TS-103-7 | unit |
| 103-REQ-4.4 | (manual doc review) | -- |
| 103-REQ-4.E1 | TS-103-E2 | unit |
