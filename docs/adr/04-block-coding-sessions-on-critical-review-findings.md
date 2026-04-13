---
Title: 04. Block coding sessions on critical review findings
Date: 2026-04-13
Status: Accepted
---
## Context

agent-fox executes spec-driven task graphs where each spec is decomposed into
numbered task groups (0, 1, 2, …) with dependency edges between them. Three
review archetypes — skeptic, verifier, and oracle — run alongside or after
coder sessions to assess code quality, spec compliance, and drift. These
reviewers produce structured findings persisted to DuckDB with severity levels
(critical, major, minor, observation) and optional category tags.

Before this mechanism existed, a coder session could proceed to implement task
group N+1 even when a reviewer had identified fundamental problems with task
group N's preconditions — for example, building on top of a spec whose
dependencies were entirely unimplemented. This resulted in wasted sessions,
compounding errors, and costly rework because each downstream session
inherited and amplified the problems of its predecessors.

The challenge is to define when and how reviewer findings should prevent
downstream work from proceeding, while avoiding false-positive blocks that
halt progress unnecessarily. Security-relevant findings require special
treatment because the cost of building on an insecure foundation is
categorically higher than other quality issues.

## Decision Drivers

- **Prevent compounding errors.** A critical finding in task group 0 (skeptic
  pre-review) should stop task group 1 from executing, since its output would
  be built on a flawed premise.

- **Security findings are non-negotiable.** Findings tagged with
  `category='security'` (detected via keyword matching against a known set of
  vulnerability terms) must always block, regardless of configured thresholds.
  The risk of building atop a security vulnerability outweighs the cost of a
  false-positive block.

- **Configurable thresholds for non-security findings.** Not every critical
  finding warrants blocking — the threshold should be tunable per archetype
  and learnable over time from historical outcomes.

- **Cascade semantics.** Blocking task group N must transitively block all
  groups that depend on it (N+1, N+2, …). The task graph's dependency edges
  already encode this structure.

- **Debuggability.** When a session is blocked, the operator must be able to
  determine exactly which finding(s) caused the block, read their full
  descriptions, and decide how to proceed (fix and re-run, or override).

## Options Considered

### Option A: No blocking — advisory-only findings

Reviewers produce findings that are logged and persisted but never prevent
downstream work. Operators review findings after the run completes.

**Pros:**
- Simplest implementation; no coordination between reviewer and coder
  scheduling.
- No risk of false-positive blocks halting progress.

**Cons:**
- Downstream sessions build on flawed foundations, wasting cost and time.
- Security vulnerabilities propagate through the entire task graph unchecked.
- Operators must manually correlate late-stage failures back to early findings.

### Option B: Block on any critical finding (fixed threshold)

Any reviewer that produces one or more critical findings blocks the downstream
coder task. No configurability, no special-casing by category.

**Pros:**
- Simple, predictable rule.
- Prevents compounding errors in the common case.

**Cons:**
- Too aggressive for archetypes like oracle, where critical drift findings may
  be informational rather than blocking.
- No way to tune sensitivity per project or archetype.
- Treats a cosmetic "critical" mislabel identically to a genuine security
  vulnerability.

### Option C: Category-aware blocking with configurable thresholds (chosen)

Review findings are evaluated after each reviewer session completes. Two
blocking paths exist:

1. **Security bypass:** If any critical finding has `category='security'`
   (auto-detected via keyword matching against terms like "command injection",
   "path traversal", "RCE", etc.), blocking is unconditional — no threshold
   check.

2. **Threshold-based:** For non-security critical findings, blocking occurs
   when `critical_count > effective_threshold`. The threshold is resolved from
   archetype configuration (skeptic vs. oracle), with an optional learning
   path that adjusts thresholds based on historical blocking outcomes.

Blocking cascades through the task graph via BFS over dependency edges,
marking all transitively dependent nodes as blocked.

**Pros:**
- Security findings always block, matching their risk profile.
- Non-security thresholds are configurable per archetype, allowing oracle to
  be advisory-only (`block_threshold: null`).
- Cascade blocking prevents wasted downstream sessions.
- Findings are persisted with UUIDs, enabling the `findings` CLI command for
  post-hoc inspection.

**Cons:**
- Security keyword detection is heuristic — novel vulnerability descriptions
  may not match the keyword set.
- Threshold learning adds complexity and requires historical data to be
  effective.
- False-positive security blocks require manual intervention (re-running the
  skeptic after fixing the underlying issue).

## Decision

We will **block coding sessions based on category-aware review finding
evaluation with configurable thresholds** (Option C) because it is the only
approach that provides unconditional protection against security vulnerabilities
while allowing tunable sensitivity for non-security quality concerns. The
two-path design (security bypass vs. threshold-based) matches the distinct
risk profiles: security findings have unbounded downstream cost, while
non-security findings have bounded cost that operators can weigh against
progress.

### Architecture

```
Skeptic/Oracle session completes
        │
        ▼
evaluate_review_blocking()           [result_handler.py]
        │
        ├─ query findings from DuckDB (review_findings table)
        │
        ├─ count critical findings
        │
        ├─ ANY critical with category='security'?
        │     ├─ YES → BLOCK (unconditional, emit SECURITY_FINDING_BLOCKED audit event)
        │     └─ NO  → resolve threshold from archetype config
        │               ├─ critical_count > threshold → BLOCK
        │               └─ critical_count ≤ threshold → PASS
        │
        ▼
BlockDecision { should_block, coder_node_id, reason }
        │
        ├─ should_block=true → GraphSync.mark_blocked()
        │     └─ BFS cascade: block all transitive dependents
        │
        └─ should_block=false → continue normal execution
```

### Security keyword detection

Category auto-classification in `review_parser.py` checks finding descriptions
against a frozen set of security terms (case-insensitive substring match):

> command injection, SQL injection, XSS, path traversal, RCE, SSRF,
> privilege escalation, arbitrary code/command, code injection, shell
> injection, XXE, LDAP injection, open redirect

Findings matching any keyword receive `category='security'`.

### Finding persistence and inspection

All findings are stored in the `review_findings` DuckDB table with fields
including `id` (UUID), `severity`, `description`, `category`, `spec_name`,
`task_group`, `session_id`, `created_at`, and `superseded_by`.

The `agent-fox findings` CLI command queries active (non-superseded) findings
with filters for `--spec`, `--severity`, `--archetype`, and `--json` output.
This is the primary debugging tool when a session is blocked — it shows the
full, untruncated finding descriptions that are abbreviated in log output.

### Block reason format in logs

Blocking reasons in log output use truncated finding descriptions to avoid
overwhelming the console:

```
[SECURITY] Skeptic found 1 critical security finding(s) for
spec_name:task_group — F-a5e694da: Description truncated to 60 chars…
```

The `F-<8hex>` prefix is derived from the finding's UUID. Use
`agent-fox findings --spec <name> --json` to retrieve the full description.

### Cascade blocking

`GraphSync.mark_blocked()` performs a BFS traversal of the dependency graph
starting from the blocked node, marking all reachable dependent nodes as
blocked. Each cascade-blocked node records `"Blocked by upstream task <id>"`
as its blocking reason. A block budget (configurable fraction of total nodes)
can terminate the entire run if too many nodes are blocked.

## Consequences

### Positive

- **Security vulnerabilities cannot propagate.** The unconditional security
  bypass ensures no coder session builds atop a finding that describes a known
  vulnerability class, regardless of threshold configuration.
- **Wasted sessions are eliminated.** Cascade blocking prevents downstream
  task groups from executing when their preconditions are invalid.
- **Findings are fully inspectable.** The `findings` CLI command provides
  untruncated descriptions, severity, archetype, and timestamps — everything
  needed to understand why a block occurred and what to fix.
- **Oracle can remain advisory.** Setting `block_threshold: null` for the
  oracle archetype means drift findings are recorded but never block, which
  matches the oracle's informational role.

### Negative / Trade-offs

- **Keyword-based security detection is brittle.** A finding describing
  "unsafe deserialization" or a novel attack class not in the keyword set
  would not trigger the security bypass. The keyword set must be maintained
  as new vulnerability classes emerge.
- **False-positive blocks require re-running the skeptic.** If the skeptic
  incorrectly flags a precondition as missing (e.g., a dependency that is
  present but structured differently than expected), the operator must fix the
  underlying issue or adjust the spec, then re-run. There is no manual
  "force-unblock" override.
- **Log output truncation hinders quick diagnosis.** The 60-character
  truncation in blocking log messages means operators must use the `findings`
  CLI command for the full picture — the log alone is insufficient.

### Neutral / Follow-up actions

- The `findings` CLI command (spec 84) is the primary debugging interface.
  Its `--run` filter is not yet implemented; when added, it will allow
  filtering findings to a specific orchestrator run.
- Threshold learning via `resolve_block_threshold()` is available but
  disabled by default (`learn_thresholds=False`). Enabling it requires
  sufficient historical blocking data in `blocking_history`.
- The reset engine (`engine/reset.py`) provides `reset_task()` which can
  clear a blocked task and cascade-unblock its dependents, enabling recovery
  without re-running the full graph.

## References

- Blocking evaluation: `agent_fox/engine/result_handler.py` —
  `evaluate_review_blocking()`, `_format_block_reason()`
- Security keyword detection: `agent_fox/session/review_parser.py` —
  `_SECURITY_KEYWORDS`, `_detect_security_category()`
- Cascade blocking: `agent_fox/engine/graph_sync.py` —
  `GraphSync.mark_blocked()`
- Finding persistence: `agent_fox/knowledge/review_store.py` —
  `ReviewFinding`, `insert_findings()`
- Findings CLI: `agent_fox/cli/findings.py`, `agent_fox/reporting/findings.py`
- Reset engine: `agent_fox/engine/reset.py` — `reset_task()`
- Archetype definitions: `agent_fox/archetypes.py` — skeptic, oracle
  configurations
- Review finding spec: `.specs/27_review_finding_storage/`
- Findings CLI spec: `.specs/84_findings_cli/`
