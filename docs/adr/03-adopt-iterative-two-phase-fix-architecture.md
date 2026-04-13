---
Title: 03. Adopt iterative two-phase fix architecture
Date: 2026-04-13
Status: Accepted
---

## Context

agent-fox is an autonomous coding-agent orchestrator that runs LLM-powered
sessions against spec-driven task graphs. While the core session system handles
planned development work (implementing features from specs), there was no
mechanism to handle the inverse problem: given a project with failing quality
checks (tests, linters, type checkers), automatically diagnose what is broken,
determine root causes, and iteratively drive coding sessions to resolve
failures without human intervention.

This capability is essential for two workflows:

1. **Repair after drift.** After large refactors or dependency upgrades, many
   quality checks may fail simultaneously. Manually triaging and fixing each
   failure is time-consuming, especially when multiple failures share a single
   root cause.

2. **Progressive improvement.** Once a codebase is green (all checks pass),
   there are often opportunities for simplification, dead code removal, and
   structural cleanup that a coding agent can safely perform — provided there is
   a verification mechanism that catches regressions.

The design must handle projects in multiple ecosystems (Python, Node.js, Rust,
Make-based) without requiring manual check configuration, must bound resource
consumption (both time and cost), and must not leave the working tree in a
worse state than it started.

## Decision Drivers

- **Zero-configuration check discovery.** Users should not have to list their
  quality checks manually; the tool should detect them from standard project
  configuration files (pyproject.toml, package.json, Cargo.toml, Makefile).

- **Semantic root-cause grouping.** Naive one-session-per-check strategies
  waste sessions and cost. Many failures share a common root cause (e.g., a
  renamed module breaking both tests and type checking). The system must group
  failures intelligently so each coding session addresses a root cause, not
  an individual check.

- **Bounded autonomy.** The system runs unsupervised. It must terminate in
  finite time with clear exit codes and diagnostics, respecting both a maximum
  iteration count and a cost ceiling.

- **Safety through verification.** Improvement changes (Phase 2) carry
  subjective risk — the system might remove functionality it mistakenly
  classifies as dead code. A verification step must validate improvements
  before they are retained, with automatic rollback on failure.

- **Consistency with spec-driven workflow.** The fix system should integrate
  with the existing session architecture rather than building a parallel
  execution path. Coding sessions should receive structured context (spec-like
  artifacts) to maximize agent effectiveness.

## Options Considered

### Option A: Single-pass naive fixer

Run all checks once, send all failure output to a single coding session, hope
the agent fixes everything, report the result.

**Pros:**

- Simplest possible implementation: one check run, one session.
- Low latency for small failure sets.

**Cons:**

- Cannot distinguish root causes from symptoms; the agent receives an
  undifferentiated wall of error output.
- No iteration: if the session's fix introduces a new failure, no recovery.
- No cost control: a single long session can consume the entire budget.
- No mechanism for improvement beyond repair.
- Scales poorly: large failure sets overwhelm the session's context window.

### Option B: Per-check iterative fixer

Run each check independently, spawn one session per failing check, repeat
until all pass or a limit is reached.

**Pros:**

- Focused sessions — each session receives output from exactly one check.
- Simple clustering logic (one cluster = one check).

**Cons:**

- Misses cross-check root causes. A missing import breaks both pytest and
  mypy, but this approach launches two separate sessions that may make
  conflicting edits.
- Higher session count and cost for correlated failures.
- Still no improvement phase.

### Option C: Two-phase architecture with AI-assisted clustering (chosen)

**Phase 1 (Repair):** Detect checks, run them, collect failures, use an AI
model to cluster failures by semantic root cause, generate a fix specification
per cluster, run targeted coding sessions, iterate up to N passes.

**Phase 2 (Improve, optional):** After all checks pass, run an
analyzer-coder-verifier pipeline that identifies improvement opportunities
(tiered by impact), implements them, validates via a verifier session, and
rolls back on failure. Iterate up to M passes.

**Pros:**

- AI clustering reduces total sessions by grouping correlated failures across
  different checks (e.g., a renamed module breaking both tests and type
  checking is one cluster, not two).
- Iterative loop handles cascading fixes: pass 1 may fix imports, revealing
  test failures that pass 2 addresses.
- Spec artifacts (requirements.md, design.md, tasks.md) per cluster give the
  coder agent structured context consistent with the project's spec-driven
  workflow.
- Phase 2 improvement is opt-in (`--auto`), decoupling the deterministic
  "fix what's broken" from the subjective "make it better."
- Verifier + rollback in Phase 2 prevents the system from landing bad
  improvements.
- Cost tracking and budget enforcement prevent runaway spending.
- Graceful termination with clear exit codes and structured reports.

**Cons:**

- Highest implementation complexity of the three options.
- AI clustering adds an API call per pass; if the model returns a bad
  grouping, the fallback (one cluster per check) is equivalent to Option B.
- Phase 2's three-session-per-pass cost (analyzer + coder + verifier) is
  significant; budget must be carefully managed.

## Decision

We will **adopt the two-phase iterative architecture with AI-assisted failure
clustering** (Option C) because it is the only evaluated option that handles
cross-check root cause correlation, bounds resource consumption, and provides a
safe path from repair to improvement. The additional complexity is concentrated
in well-separated modules (checks, clusterer, spec_gen, analyzer, improve) that
can be tested and evolved independently.

### Architecture summary

```
Phase 1 — Repair (agent_fox/fix/fix.py)
─────────────────────────────────────────
For pass = 1 to max_passes:
  1. detect_checks()         → CheckDescriptor[]          [checks.py]
  2. run_checks()            → FailureRecord[]             [checks.py]
  3. if no failures           → terminate(ALL_FIXED)
  4. cluster_failures()      → FailureCluster[]            [clusterer.py]
  5. for each cluster:
     a. generate_fix_spec()  → FixSpec (req/design/tasks)  [spec_gen.py]
     b. run_session(spec)    → cost                        [session.py]
     c. check cost budget
  6. cleanup_fix_specs()

Phase 2 — Improve (agent_fox/fix/improve.py, opt-in via --auto)
─────────────────────────────────────────────────────────────────
Precondition: Phase 1 terminated with ALL_FIXED

For pass = 1 to improve_passes:
  1. check budget for full pass (analyzer + coder + verifier)
  2. analyzer session       → Improvement[] tiered by impact  [analyzer.py]
  3. if diminishing returns  → terminate(CONVERGED)
  4. filter improvements (confidence, tier priority)
  5. coder session          → implements improvements
  6. git commit
  7. verifier session       → VerifierVerdict (PASS/FAIL)
  8. if FAIL                → rollback commit, terminate(VERIFIER_FAIL)
```

### Termination reasons

| Phase | Reason | Exit Code | Meaning |
|-------|--------|-----------|---------|
| 1 | ALL_FIXED | 0 | All quality checks pass |
| 1 | MAX_PASSES | 1 | Iteration limit exhausted, failures remain |
| 1 | COST_LIMIT | 1 | Budget exhausted before resolution |
| 1 | INTERRUPTED | 130 | User cancelled (Ctrl-C) |
| 2 | CONVERGED | 0 | No further improvements identified |
| 2 | PASS_LIMIT | 0 | All improvement passes completed |
| 2 | VERIFIER_FAIL | 1 | Improvement regressed quality; rolled back |
| 2 | COST_LIMIT | 0 | Budget exhausted (improvements so far retained) |

### Check detection

The system inspects standard project configuration files rather than requiring
user-provided check lists:

| Config file | Detection rule | Check produced |
|-------------|---------------|----------------|
| pyproject.toml | `[tool.pytest]` or `[tool.pytest.ini_options]` | `uv run pytest` |
| pyproject.toml | `[tool.ruff]` | `uv run ruff check .` |
| pyproject.toml | `[tool.mypy]` | `uv run mypy .` |
| package.json | `scripts.test` | `npm test` |
| package.json | `scripts.lint` | `npm run lint` |
| Makefile | `test:` target | `make test` |
| Cargo.toml | `[package]` | `cargo test` |

### Clustering strategy

The primary path sends truncated failure output (max 2000 chars per failure) to
a STANDARD-tier model with a structured prompt requesting JSON-formatted root
cause groups. Each group includes a label, the indices of failures it covers,
and a suggested fix approach. The response is validated to ensure all failures
are covered with no duplicates.

The fallback path (used when AI clustering fails for any reason) groups failures
by check name — equivalent to Option B above. This ensures the system always
makes progress even when the AI model is unavailable or returns an unparseable
response.

### Spec generation

For each failure cluster, the system generates a temporary spec directory under
`.agent-fox/fix_specs/pass_N_<label>/` containing:

- `requirements.md` — problem statement with full failure output
- `design.md` — suggested fix approach and affected checks
- `tasks.md` — task list for the session

This reuses the project's spec-driven workflow conventions, giving the coder
agent structured context rather than raw error output.

### Phase 2 improvement tiers

The analyzer categorizes improvements into three tiers, processed in priority
order:

| Tier | Risk | Examples |
|------|------|---------|
| `quick_win` | Low | Remove unused imports, delete dead code, simplify conditionals |
| `structural` | Moderate | Consolidate duplicate logic, extract or inline functions |
| `design_level` | High | Reorganize module boundaries, simplify class hierarchies |

Improvements are filtered by confidence threshold before being handed to the
coder. The verifier validates that no functionality was removed, no public APIs
changed, no test coverage was reduced, and the code is measurably simpler.

## Consequences

### Positive

- **Semantic clustering reduces session count and cost.** Correlated failures
  across different checks are fixed in a single session rather than multiple
  redundant sessions.
- **Iterative loop handles cascading failures.** Fixing a root cause in pass 1
  may reveal latent failures that pass 2 addresses; the loop naturally handles
  this progression.
- **Zero-configuration for supported ecosystems.** Users run `agent-fox fix`
  without specifying checks — the system discovers them from project config
  files.
- **Phase 2 is opt-in.** Users who want only repair get a focused tool;
  users who want polish enable `--auto`.
- **Verifier + rollback prevents regressions.** Phase 2 never lands changes
  that fail quality gates or that the verifier rejects.
- **Bounded resource consumption.** Both `--max-passes` and cost limits
  prevent unbounded spending. Exit codes and structured reports provide clear
  diagnostics.

### Negative / Trade-offs

- **AI clustering adds latency and cost per pass.** Each pass requires an
  additional API call for clustering. If the model returns poor groupings,
  the system falls back to per-check grouping, wasting that API call.
- **Phase 2 is expensive.** Each improvement pass consumes three sessions
  (analyzer + coder + verifier). With default settings (3 improvement passes),
  this is up to 9 sessions plus Phase 1 costs.
- **Verifier is conservative.** A single FAIL verdict terminates Phase 2
  entirely and rolls back, even if the rejected improvement was one of several.
  This is by design (safety over throughput) but means Phase 2 may terminate
  early when a more nuanced approach could have salvaged partial improvements.
- **Check detection is ecosystem-specific.** Projects using non-standard build
  systems or check runners outside the detection rules receive no checks and
  get an early-exit error. Extending detection requires code changes.

### Neutral / Follow-up actions

- ADR-01 (Use Claude Exclusively) governs which models power the clustering,
  analyzer, coder, and verifier sessions.
- Extending check detection to new ecosystems (e.g., Go, Elixir) is a natural
  future extension that does not affect the core architecture.
- The `--dry-run` flag (generate fix specs without running sessions) enables
  human review of clustering and spec quality, serving as a diagnostic mode.

## References

- Phase 1 spec: `.specs/08_error_auto_fix/`
- Phase 2 spec: `.specs/31_auto_improve/`
- Progress display spec: `.specs/76_fix_progress_display/`
- JSON I/O spec: `.specs/23_json_io/`
- Implementation: `agent_fox/fix/` package (checks.py, clusterer.py,
  spec_gen.py, fix.py, improve.py, analyzer.py, events.py, report.py,
  improve_report.py)
- CLI entry point: `agent_fox/cli/fix.py`
