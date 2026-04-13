---
Title: 03. Adopt Scope Guard for coder session waste prevention
Date: 2026-04-13
Status: Accepted
---

## Context

Agent-fox orchestrates multi-step coding sessions by decomposing specifications
into task groups. Task group 1 typically writes failing tests and stub
implementations; subsequent groups fill in the real logic. In practice, the
test-writing session sometimes produced full implementations instead of stubs,
leaving downstream sessions with nothing to do.

Audit logs from the `04_cloud_gateway_client` specification documented the
problem concretely: task groups 3, 4, and 5 each launched a coder session,
discovered their assigned functions were already implemented, and exited after
1–4 minutes of verification work — producing zero commits. At roughly $3–4 per
session, this wasted ~$10 and ~7 minutes of wall-clock time on a single spec.
The issue was tracked in GitHub issue #275.

Without intervention, the problem compounds: every specification with overlapping
deliverables or over-eager test-writing sessions risks the same waste pattern,
with no mechanism to detect or prevent it.

## Decision Drivers

- **Eliminate redundant coder sessions** — sessions that discover their work is
  already done cost money and time with zero value.
- **Enforce the stub contract** — test-writing sessions must produce only type
  signatures and stub bodies, not full implementations, so downstream sessions
  have real work to do.
- **Detect scope conflicts early** — overlapping deliverables between task groups
  should be flagged at graph-finalization time, before any sessions launch.
- **Measure waste** — no-op and skipped sessions should be tracked with enough
  fidelity to identify recurring decomposition failures.
- **Per-subsystem control** — each guard behavior must be independently
  toggleable so operators can disable a check that produces false positives
  without losing the others.

## Options Considered

### Option A: Manual review of task decompositions

Require a human to inspect deliverable lists for overlaps and verify test-writing
output before launching downstream sessions.

**Pros:**
- No code to build or maintain.

**Cons:**
- Does not scale — every specification would need manual review.
- Cannot catch over-implementation by a test-writing agent (the violation happens
  mid-session, not at planning time).
- Provides no telemetry for trend analysis.

### Option B: Post-hoc waste detection only

Classify session outcomes after the fact (success, no-op, failure) and report
aggregates, but take no preventive action.

**Pros:**
- Simpler implementation — only needs commit analysis and a telemetry table.
- Provides visibility into how often waste occurs.

**Cons:**
- Every wasted session still runs and incurs full cost.
- Identifies the symptom but does not address the cause.

### Option C: Scope Guard — pre-flight checking, stub enforcement, overlap detection, and outcome tracking

A four-subsystem module that prevents waste at three stages: graph finalization
(overlap detection), session launch (pre-flight scope check), and session
completion (stub enforcement and outcome classification). All results are
persisted to DuckDB for waste reporting.

**Pros:**
- Prevents waste proactively — sessions are skipped or scoped down before they
  incur cost.
- Enforces the stub contract with language-aware validation (Rust, Python,
  TypeScript/JavaScript).
- Overlap detection catches conflicting deliverables at graph time, before any
  sessions launch.
- Telemetry provides per-specification waste aggregates for continuous
  improvement.
- Each subsystem is independently toggleable via configuration flags.

**Cons:**
- Regex-based function extraction is inherently limited — edge cases in complex
  syntax (nested generics, macros, decorators) can cause missed or incorrect
  boundaries.
- Only supports Rust, Python, and TypeScript/JavaScript; files in other languages
  are skipped with a warning.
- Adds ~1,200 lines of production code and a DuckDB dependency for telemetry.

## Decision

We will **adopt Scope Guard (Option C)** because it is the only option that
addresses waste at all three stages of the session lifecycle — planning, launch,
and completion. The pre-flight check alone would have eliminated all three wasted
sessions in the `04_cloud_gateway_client` case by detecting that the target
functions already had non-stub implementations. Stub enforcement prevents the
root cause (over-implementation by test-writing sessions) rather than just
detecting the symptom.

The regex-based parsing limitation is an accepted trade-off: full AST parsing
would add heavy dependencies (tree-sitter or language-specific parsers) for a
marginal improvement in accuracy. The current heuristic approach handles the
common function definition patterns in the three languages this project uses.

## Consequences

### Positive

- Wasted sessions that find their work already done are eliminated (pre-flight
  skip) or reduced in scope (partial implementation detection).
- Test-writing sessions that produce full implementations are flagged with
  specific violation records, enabling fast diagnosis.
- Scope overlaps between independent task groups are caught at graph time and
  block execution, preventing the root cause of duplicate work.
- Waste reporting (`query_waste_report()`) gives per-specification visibility
  into no-op and pre-flight-skip rates, guiding improvements to task
  decomposition.

### Negative / Trade-offs

- Regex-based parsing will miss functions with unusual signatures or produce
  false boundaries in macro-heavy code. Indeterminate results are handled
  gracefully (session launches with full scope) but reduce the guard's
  effectiveness.
- Language coverage is limited to Rust, Python, and TypeScript/JavaScript.
  Adding a new language requires new stub patterns, function-signature regexes,
  and test-block detection rules in `stub_patterns.py` and `source_parser.py`.

### Neutral / Follow-up actions

- The DuckDB telemetry tables (`session_outcomes`, `session_prompts`,
  `scope_check_results`) share the database with the existing knowledge sink.
- If regex-based parsing proves insufficient for a critical language or pattern,
  consider tree-sitter integration as a targeted enhancement.
- Monitor the waste report periodically to verify Scope Guard is reducing
  no-op session rates.

## References

- GitHub issue: https://github.com/agent-fox-dev/agent-fox/issues/275
- Specification: `.specs/archive/87_coder_sessions_over_implement_scope_caus/`
- Implementation: `agent_fox/scope_guard/`
- Design doc: `docs/scope_guard.md`
