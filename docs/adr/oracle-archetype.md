# ADR: Oracle Agent Archetype

**Status:** Accepted
**Date:** 2026-03-10

## Context

agent-fox specs are authored at a point in time, but the codebase continues to
evolve between when a spec is written and when a coder session executes it.
File paths get renamed, function signatures change, modules are merged or split.
When a coder starts work on a stale spec, it wastes a session discovering drift
that could have been detected automatically.

The skeptic archetype validates spec *quality* (ambiguity, missing edge cases),
but does not check whether the spec's assumptions about the codebase are still
accurate. A separate concern -- spec *freshness* -- requires reading the actual
codebase and comparing it against spec references.

## Decision

We introduce the **oracle** archetype: an `auto_pre` agent that runs before the
first coder group and validates spec assumptions against the current codebase.

### Key design choices

1. **Same injection pattern as skeptic.** The oracle uses `auto_pre` injection,
   producing a node before the first coder group. This reuses the existing
   graph builder infrastructure and keeps the mental model consistent.

2. **Multi-auto_pre support.** When both oracle and skeptic are enabled, the
   graph builder assigns distinct node IDs using the format
   `{spec}:0:{archetype_name}`. When only one `auto_pre` archetype is enabled,
   the backward-compatible `{spec}:0` format is preserved. Both nodes run in
   parallel with no edges between them.

3. **Structured drift findings.** The oracle outputs a JSON `drift_findings`
   array, parsed into `DriftFinding` dataclass instances and persisted in a
   DuckDB `drift_findings` table. This follows the same pattern as
   `ReviewFinding` for the skeptic.

4. **Supersession on re-run.** When drift findings are re-inserted for the
   same `(spec_name, task_group)`, previous active findings are superseded.
   Only the latest findings are returned by `query_active_drift_findings()`.

5. **Context rendering.** Active drift findings are rendered as an
   `## Oracle Drift Report` markdown section and injected into coder session
   context, grouped by severity.

6. **Optional blocking.** A configurable `block_threshold` in
   `[archetypes.oracle_settings]` controls whether critical findings block
   downstream coder groups. Without a threshold, findings are advisory only.

7. **Disabled by default.** `[archetypes] oracle = false` is the default.
   Enabling adds one session per spec to the task graph. No behavioral change
   for existing users.

## Alternatives Considered

1. **Integrate drift detection into the skeptic.** Rejected because the two
   concerns (spec quality vs. spec freshness) require different tools and
   prompts. Combining them would make the skeptic prompt unwieldy and harder
   to tune independently.

2. **Static analysis without an LLM.** A rule-based scanner could check file
   existence, but cannot verify semantic assumptions (API contracts, module
   responsibilities). The LLM-based approach handles both structural and
   semantic drift.

3. **Run oracle after the coder fails.** Rejected because the goal is to
   prevent wasted sessions, not diagnose them after the fact.

## Consequences

### Positive

- **Reduced waste:** Stale specs are flagged before coder sessions start,
  preventing wasted compute on specs that reference moved or renamed artifacts.
- **Structured output:** Drift findings are queryable in DuckDB and renderable
  in coder context, giving coders actionable information.
- **Parallel execution:** Oracle and skeptic run in parallel, so enabling both
  does not increase the critical path length.
- **Zero-risk rollout:** Disabled by default; existing behavior unchanged.

### Negative

- **Additional cost:** One extra LLM session per spec when enabled.
- **Graph complexity:** Multi-auto_pre node ID format adds a naming convention
  that developers must understand.

### Risks

- **False positives:** The oracle may flag assumptions as drifted when they are
  actually still valid (e.g., complex code that is hard to analyze). Mitigated
  by the "observation" severity for inconclusive checks.
- **Prompt sensitivity:** Oracle effectiveness depends on the prompt template
  quality. Mitigated by keeping the template as a separate markdown file that
  can be iterated independently.
