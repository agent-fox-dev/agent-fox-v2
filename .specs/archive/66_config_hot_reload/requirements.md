# Requirements Document

## Introduction

This specification adds configuration hot-reload to the orchestrator's sync
barrier sequence. When a sync barrier fires, the orchestrator re-reads the
config file, applies changes to its live state, rebuilds derived objects,
and emits an audit event — allowing operators to adjust run parameters
without restarting.

## Glossary

- **Sync barrier**: A periodic checkpoint in the orchestrator's main loop
  (triggered every `sync_interval` completed tasks) that performs worktree
  verification, develop sync, hooks, and spec hot-loading.
- **Config hot-reload**: Re-reading `.agent-fox/config.toml` and applying
  changed values to the running orchestrator without stopping the run.
- **Circuit breaker**: The `CircuitBreaker` object that enforces cost,
  session, and retry limits before each session launch.
- **Immutable field**: A config field that cannot be safely changed mid-run
  (e.g., `parallel`). Changes are logged as warnings but not applied.
- **Config hash**: A hash of the raw config file content, used to detect
  whether the file has changed since the last load.

## Requirements

### Requirement 1: Trigger reload at sync barriers

**User Story:** As an operator, I want config changes to take effect at
the next sync barrier, so that I can adjust run parameters without
restarting.

#### Acceptance Criteria

[66-REQ-1.1] WHEN `run_sync_barrier_sequence` executes, THE orchestrator
SHALL attempt to reload the configuration from `.agent-fox/config.toml`.

[66-REQ-1.2] WHEN the config file content hash matches the last loaded
hash, THE orchestrator SHALL skip reload processing entirely (no-op).

[66-REQ-1.3] WHEN the config file content hash differs from the last
loaded hash, THE orchestrator SHALL parse the file, apply changes, and
update the stored hash.

#### Edge Cases

[66-REQ-1.E1] IF the config file does not exist at reload time, THEN THE
orchestrator SHALL keep the current configuration and log a warning.

### Requirement 2: Update OrchestratorConfig fields

**User Story:** As an operator, I want changes to cost limits, retry
counts, and session timeouts to take effect mid-run, so that I can
respond to budget or time constraints without restarting.

#### Acceptance Criteria

[66-REQ-2.1] WHEN config is reloaded, THE orchestrator SHALL replace its
`OrchestratorConfig` fields (`max_cost`, `max_sessions`, `max_retries`,
`session_timeout`, `inter_session_delay`, `sync_interval`, `hot_load`,
`max_blocked_fraction`, `quality_gate`, `quality_gate_timeout`,
`max_budget_usd`, `causal_context_limit`, `audit_retention_runs`) with
the new values.

[66-REQ-2.2] WHEN config is reloaded, THE orchestrator SHALL reconstruct
the `CircuitBreaker` with the new `OrchestratorConfig`.

#### Edge Cases

[66-REQ-2.E1] IF `sync_interval` is changed to `0` (disabled) mid-run,
THEN THE orchestrator SHALL stop triggering future sync barriers (and
therefore stop reloading config).

### Requirement 3: Guard immutable fields

**User Story:** As an operator, I want to be warned if I change a field
that cannot take effect mid-run, so that I understand why my change was
not applied.

#### Acceptance Criteria

[66-REQ-3.1] WHEN config is reloaded AND the new `parallel` value differs
from the current value, THE orchestrator SHALL log a warning indicating
the change was detected but not applied.

[66-REQ-3.2] WHEN config is reloaded AND the new `parallel` value differs,
THE orchestrator SHALL keep the current `parallel` value and
`_is_parallel` flag unchanged.

### Requirement 4: Update auxiliary configs

**User Story:** As an operator, I want changes to hooks, archetypes, and
planning settings to take effect mid-run.

#### Acceptance Criteria

[66-REQ-4.1] WHEN config is reloaded, THE orchestrator SHALL update its
stored `HookConfig` reference with the new value.

[66-REQ-4.2] WHEN config is reloaded, THE orchestrator SHALL update its
stored `ArchetypesConfig` reference with the new value.

[66-REQ-4.3] WHEN config is reloaded, THE orchestrator SHALL update its
stored `PlanningConfig` reference with the new value.

### Requirement 5: Error resilience

**User Story:** As an operator, I want a typo in my config edit to not
crash a running autonomous session.

#### Acceptance Criteria

[66-REQ-5.1] IF the config file contains invalid TOML or invalid field
values at reload time, THEN THE orchestrator SHALL keep the current
configuration, log a warning with the parse error details, and continue
the run.

#### Edge Cases

[66-REQ-5.E1] IF the config file is unreadable (permissions, I/O error)
at reload time, THEN THE orchestrator SHALL keep the current
configuration and log a warning.

### Requirement 6: Audit event for config changes

**User Story:** As an operator reviewing run logs, I want to see exactly
when and what config values changed, so that I can correlate behavior
shifts to my edits.

#### Acceptance Criteria

[66-REQ-6.1] WHEN config is reloaded AND at least one field value changed,
THE orchestrator SHALL emit an audit event of type `CONFIG_RELOADED`.

[66-REQ-6.2] THE `CONFIG_RELOADED` audit event payload SHALL include a
dictionary of changed fields mapping field name to `{"old": ..., "new": ...}`
pairs.

#### Edge Cases

[66-REQ-6.E1] WHEN config is reloaded AND no field values changed (hash
matched), THE orchestrator SHALL NOT emit an audit event.

### Requirement 7: Config path management

**User Story:** As a developer, I want the orchestrator to know its
config file path so it can reload from the same location.

#### Acceptance Criteria

[66-REQ-7.1] THE orchestrator SHALL accept a `config_path` parameter at
construction time specifying the path to the config file.

[66-REQ-7.2] THE orchestrator SHALL store the config path and use it for
all reload operations.
