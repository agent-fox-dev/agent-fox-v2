# Requirements Document

## Introduction

This spec removes the unused shell-script hook runner from agent-fox and
relocates the actively-used security module to its own package. It also
modernizes the `ConfigReloader` return type from a positional tuple to a
typed dataclass.

## Glossary

- **Hook runner**: The `hooks.py` module that executes user-configured shell
  scripts at pre-session, post-session, and sync-barrier lifecycle points.
- **Security module**: The `security.py` module that enforces a bash command
  allowlist via a PreToolUse hook for the claude-code-sdk.
- **HookConfig**: Pydantic model holding `pre_code`, `post_code`,
  `sync_barrier`, `timeout`, and `modes` fields.
- **ConfigReloader**: Engine component that hot-reloads configuration from
  disk and returns updated config objects.
- **ReloadResult**: New dataclass that replaces the positional tuple returned
  by `ConfigReloader.reload()`.

## Requirements

### Requirement 1: Hook Runner Removal

**User Story:** As a maintainer, I want the unused hook runner removed, so
that the codebase is smaller and easier to maintain.

#### Acceptance Criteria

[103-REQ-1.1] WHEN the hook runner module is removed, THE system SHALL no
longer contain `agent_fox/hooks/hooks.py` or any module that imports from it.

[103-REQ-1.2] WHEN `HookConfig` is removed from `config.py`, THE system SHALL
no longer define or reference the `HookConfig` class anywhere in production
code.

[103-REQ-1.3] WHEN `HookError` is removed from `errors.py`, THE system SHALL
no longer define or reference the `HookError` class anywhere in production
code.

[103-REQ-1.4] WHEN the `hooks` field is removed from `AgentFoxConfig`, THE
system SHALL silently ignore any `[hooks]` section in existing TOML config
files (via the existing `extra="ignore"` policy).

[103-REQ-1.5] WHEN the `--no-hooks` CLI flag is removed, THE `agent-fox code`
command SHALL no longer accept `--no-hooks` as an argument.

[103-REQ-1.6] WHEN hook runner parameters are removed from engine modules,
THE `NodeSessionRunner`, `run_sync_barrier_sequence`, `Orchestrator`, and
`session_runner_factory` SHALL no longer accept `hook_config` or `no_hooks`
parameters.

#### Edge Cases

[103-REQ-1.E1] IF a TOML config file contains a `[hooks]` section, THEN THE
system SHALL parse successfully without errors or warnings.

### Requirement 2: Security Module Relocation

**User Story:** As a maintainer, I want the security module in its own
package, so that the package name accurately reflects its contents.

#### Acceptance Criteria

[103-REQ-2.1] WHEN the security module is relocated, THE system SHALL provide
`agent_fox.security.security` as the canonical import path for
`make_pre_tool_use_hook`, `DEFAULT_ALLOWLIST`, `build_effective_allowlist`,
`check_command_allowed`, `extract_command_name`, and `check_shell_operators`.

[103-REQ-2.2] WHEN the security module is relocated, THE system SHALL update
all internal import sites to use the new path AND return the same values as
before relocation.

[103-REQ-2.3] WHEN the security tests are relocated, THE system SHALL place
unit tests at `tests/unit/security/test_security.py` and property tests at
`tests/property/security/test_security_props.py`.

#### Edge Cases

[103-REQ-2.E1] IF the old `agent_fox/hooks/` package is removed, THEN THE
system SHALL NOT break any import that previously resolved through
`agent_fox.hooks.security` (all such imports must be updated before removal).

### Requirement 3: ConfigReloader Modernization

**User Story:** As a maintainer, I want the ConfigReloader to return a typed
dataclass, so that the return value is self-documenting and resilient to
future changes.

#### Acceptance Criteria

[103-REQ-3.1] WHEN `ConfigReloader.reload()` returns a successful result, THE
system SHALL return a `ReloadResult` dataclass containing `config`
(`OrchestratorConfig`), `circuit` (`CircuitBreaker`), `archetypes`
(`ArchetypesConfig | None`), and `planning` (`PlanningConfig`) fields.

[103-REQ-3.2] WHEN `_apply_reloaded_config` receives a `ReloadResult`, THE
system SHALL unpack it by field name (not positional index) and apply each
config to the corresponding orchestrator attribute.

[103-REQ-3.3] WHEN `ConfigReloader.reload()` determines no reload is needed
or an error occurs, THE system SHALL return `None` (unchanged from current
behavior).

### Requirement 4: Test and Documentation Cleanup

**User Story:** As a maintainer, I want tests and docs updated to reflect the
removal, so that the test suite passes and documentation is accurate.

#### Acceptance Criteria

[103-REQ-4.1] WHEN hook runner tests are removed, THE system SHALL no longer
contain `tests/unit/hooks/test_runner.py` or
`tests/property/hooks/test_runner_props.py`.

[103-REQ-4.2] WHEN engine tests reference `hook_config` or `no_hooks`, THE
system SHALL update those tests to remove such references while preserving
the tests' original assertions.

[103-REQ-4.3] WHEN config_gen entries for `HookConfig` are removed, THE
`config_gen.py` module SHALL no longer contain any reference to `HookConfig`.

[103-REQ-4.4] WHEN the `[hooks]` section is removed from
`docs/config-reference.md`, THE document SHALL no longer describe hook runner
configuration fields (`pre_code`, `post_code`, `sync_barrier`, `timeout`,
`modes`).

#### Edge Cases

[103-REQ-4.E1] IF `tests/unit/hooks/conftest.py` contains fixtures used by
both hook runner tests and hot_load tests, THEN THE system SHALL retain only
the hot_load fixtures (`tmp_specs_dir`) and remove hook-runner-specific
fixtures (`hook_context`, `hook_config`, `tmp_hook_script`, `marker_file`).
