# PRD: Configuration Hot-Reload at Sync Barriers

## Problem Statement

The orchestrator loads configuration once at startup and never re-reads it.
During long autonomous runs (hours, days), the operator cannot adjust
parameters like cost limits, retry counts, or session timeouts without
stopping and restarting the entire run — losing progress on in-flight
sessions and requiring manual state recovery.

## Goals

1. **Reload configuration at every sync barrier.** When `run_sync_barrier_sequence`
   executes, re-read `.agent-fox/config.toml` and apply changes to the
   orchestrator's live state.
2. **Full reload.** Update all config sections the orchestrator holds:
   `OrchestratorConfig`, `HookConfig`, `ArchetypesConfig`, `PlanningConfig`.
3. **Rebuild derived state.** Reconstruct `CircuitBreaker` from the new
   `OrchestratorConfig` so cost/session/retry limits take effect immediately.
4. **Guard immutable fields.** The `parallel` setting cannot be safely changed
   mid-run (semaphore, dispatch mode). Log a warning if the new value differs
   but keep the current value.
5. **Resilient to errors.** If the config file is missing, malformed, or
   contains invalid fields, keep the previous config and log a warning.
   Never abort a run due to a config reload failure.
6. **Audit trail.** Emit an audit event listing which fields changed, so
   operators can trace behavior shifts to config edits.
7. **No-op optimization.** Skip reload processing if the file hasn't changed
   since the last load (compare file content hash).

## Non-Goals

- Reloading `RoutingConfig` (requires rebuilding the routing pipeline — too
  complex for this spec).
- Reloading the session runner factory's captured config (sessions created
  after reload will use new auxiliary configs held by the orchestrator, but
  the factory closure itself is not replaced).
- CLI override re-application. CLI flags (`--max-cost`, `--parallel`, etc.)
  are applied once at startup. After reload, the config file value wins.
  CLI parameter support will be removed in a future spec.

## Clarifications

- **Q: Scope of reload?** Full `AgentFoxConfig` reload. OrchestratorConfig,
  HookConfig, ArchetypesConfig, and PlanningConfig are all updated on the
  orchestrator.
- **Q: CLI override precedence?** Config file wins on reload. CLI overrides
  are not re-applied.
- **Q: Config parse error?** Keep old config, log warning, continue run.
- **Q: Audit?** Emit a `config.reloaded` audit event with changed fields.
- **Q: Parallel changes?** Warn if value differs, keep the current value.
- **Q: Config path?** Fixed at `.agent-fox/config.toml`, same as startup.
- **Q: Concurrent file access?** Acceptable edge case — no special handling
  for partial reads.
