# PRD: Remove Hook Runner

## Problem

The hook runner system (`agent_fox/hooks/hooks.py`) provides pre-session,
post-session, and sync-barrier shell-script execution. It was built as part of
spec 06 but has **never been used in practice** -- no configuration file has
ever populated `pre_code`, `post_code`, or `sync_barrier` with actual scripts.

The hook runner adds ~300 lines of production code, ~400 lines of tests,
`HookConfig` and `HookError` types, a `--no-hooks` CLI flag, and threading of
`hook_config`/`no_hooks` through five engine modules. This is maintenance drag
for zero value.

Meanwhile, the **security module** (`agent_fox/hooks/security.py`) that lives
in the same package is actively used every session to enforce the bash command
allowlist. It should be preserved and given its own package.

## Goal

Remove the hook runner infrastructure entirely. Relocate the security module
to a dedicated `agent_fox/security/` package. Modernize the `ConfigReloader`
return type (which currently includes `HookConfig`) to use a typed dataclass.

## Scope

### Remove

| Artifact | Location |
|----------|----------|
| Hook runner module | `agent_fox/hooks/hooks.py` |
| `HookConfig` model | `agent_fox/core/config.py` |
| `hooks` field on `AgentFoxConfig` | `agent_fox/core/config.py` |
| `HookError` exception | `agent_fox/core/errors.py` |
| `HookConfig` entries | `agent_fox/core/config_gen.py` |
| `--no-hooks` CLI flag | `agent_fox/cli/code.py` |
| `hook_config` / `no_hooks` params | `session_lifecycle.py`, `barrier.py`, `engine.py`, `run.py` |
| `_build_hook_context` method | `session_lifecycle.py` |
| Pre/post hook calls | `session_lifecycle.py` |
| Sync barrier hook call | `barrier.py` |
| Hook runner tests | `tests/unit/hooks/test_runner.py` |
| Hook runner property tests | `tests/property/hooks/test_runner_props.py` |
| Hook-specific fixtures | `tests/unit/hooks/conftest.py` (hook_context, hook_config, tmp_hook_script, marker_file) |
| `[hooks]` config-reference section | `docs/config-reference.md` |

### Relocate

| From | To |
|------|----|
| `agent_fox/hooks/security.py` | `agent_fox/security/security.py` |
| `agent_fox/hooks/__init__.py` | `agent_fox/security/__init__.py` |
| `tests/unit/hooks/test_security.py` | `tests/unit/security/test_security.py` |
| `tests/property/hooks/test_security_props.py` | `tests/property/security/test_security_props.py` |
| `security_config` fixture | `tests/unit/security/conftest.py` |

### Keep (unchanged except import paths)

| Artifact | Reason |
|----------|--------|
| `agent_fox/security/security.py` | Actively used every session |
| `SecurityConfig` in `config.py` | Drives the allowlist |
| `SecurityError` in `errors.py` | Used by security module |
| `agent_fox/engine/hot_load.py` | Independent spec-discovery infrastructure |
| `tests/unit/hooks/test_hot_load.py` | Tests hot_load (stays in hooks/ test dir) |
| `tests/property/hooks/test_hot_load_props.py` | Tests hot_load |
| `tests/unit/hooks/conftest.py:tmp_specs_dir` | Used by hot_load tests |
| Orphaned `06-REQ-*` comments | Left as historical markers |

### Refactor

| What | Change |
|------|--------|
| `ConfigReloader.reload()` return type | 5-tuple -> `ReloadResult` dataclass |

## Import Sites to Update

These files import from `agent_fox.hooks.security` and must switch to
`agent_fox.security.security`:

- `agent_fox/session/session.py`
- `tests/unit/session/test_security.py`
- `tests/property/session/test_security_props.py`
- `tests/property/test_mode_properties.py`
- `tests/unit/engine/test_sdk_params_modes.py`

These files reference `hook_config` or `no_hooks` in tests and must be updated:

- `tests/unit/engine/test_config_reload.py`
- `tests/unit/engine/test_orchestrator.py`
- `tests/unit/engine/test_barrier.py`
- `tests/unit/engine/test_consolidation_barrier.py`
- `tests/unit/engine/test_end_of_run_discovery.py`
- `tests/property/engine/test_end_of_run_discovery_props.py`
- `tests/integration/knowledge/test_consolidation_smoke.py`
- `tests/unit/session/test_prompt_injection_sanitization.py`

## Non-Goals

- Changing the security module's behavior or API surface.
- Adding new lifecycle hooks or event systems.
- Modifying hot_load.py beyond import-path updates (if any).

## Design Decisions

1. **`--no-hooks` CLI flag: remove entirely.** The flag only gated
   shell-script hooks. With those gone, it has no remaining purpose.
   No backward-compatibility shim needed -- the flag was never documented
   as a public API contract.

2. **Security module: move to `agent_fox/security/` package.** The module
   is a PreToolUse hook for the claude-code-sdk, not a shell-script hook.
   Giving it its own package makes the naming accurate and avoids an
   orphaned `hooks/` package that contains no hooks.

3. **`HookError`: remove.** Only raised by the hook runner. No external
   consumers.

4. **`ConfigReloader.reload()`: return a `ReloadResult` dataclass.**
   Removing `HookConfig` from the 5-tuple is the trigger; switching to a
   dataclass is a maintainability improvement over a positional tuple.

5. **Orphaned `06-REQ-*` comments: leave in place.** These are historical
   markers in `hot_load.py` and `barrier.py`. Cleaning them up adds
   churn without value.

6. **`[hooks]` TOML section: silently ignored.** `AgentFoxConfig` uses
   `extra="ignore"`, so removing the `hooks` field means any `[hooks]`
   section in existing config files is silently dropped. No migration
   needed.
