# PRD: Auto-Improve (`fix --auto`)

## Problem

The `agent-fox fix` command resolves quality check failures (tests, lint,
type-check, build) but stops as soon as all checks pass. Passing checks is a
necessary baseline, but code that passes checks is not necessarily *good* code.
Redundancy, unnecessary complexity, stale patterns, and missed simplifications
accumulate over time and are invisible to quality gates.

Separately, the `af-code-simplifier` skill can audit a codebase and propose
structural improvements, but it requires manual invocation and has no
verification loop: the developer must inspect changes, re-run checks, and
decide when to stop. Running it multiple times yields diminishing returns, but
there is no automated way to detect that convergence point.

Today, combining these two activities requires manual orchestration: run `fix`,
then invoke the simplifier, then verify, then decide whether another pass is
worthwhile. This is exactly the kind of repetitive multi-step workflow that an
agent should handle autonomously.

## Solution

Extend `agent-fox fix` with a `--auto` flag that adds a second phase after the
existing repair loop. When `--auto` is set, the command operates in two phases:

**Phase 1 — Repair** (existing behavior, unchanged): Run quality checks, fix
failures, iterate until all checks pass or a termination condition is met. If
Phase 1 does not achieve all-green, Phase 2 does not run.

**Phase 2 — Improve**: Once all checks pass, iteratively analyze the entire
codebase for improvement opportunities, implement them, and verify the changes
preserve correctness. Each improvement pass uses three agents in sequence:

1. **Analyzer** — audits the codebase and produces a prioritized improvement
   plan (quick wins, structural, design-level), informed by project knowledge
   from the oracle.
2. **Coder** — implements the top improvements from the analyzer's plan.
3. **Verifier** — runs all quality checks and validates that changes are genuine
   improvements (no regressions, code measurably simpler, public APIs
   preserved). On FAIL, the entire pass is rolled back.

Phase 2 iterates until a termination condition is met: the analyzer reports no
meaningful improvements remaining, the configured pass limit is reached, or the
shared cost budget is exhausted.

```
Phase 1: Repair                    Phase 2: Improve
========================          ====================================

 checks -> cluster -> fix -.       analyze -> code -> verify -.
   ^                      |          ^                        |
   '--- failures? --------'          '--- PASS + more? -------'
         |                                    |
     all green -----> enter Phase 2      FAIL -> rollback pass
                                         no improvements -> DONE
                                         pass limit -> DONE
                                         cost limit -> DONE
```

## Behaviour

### CLI Interface

```
agent-fox fix [OPTIONS]

Existing options (unchanged):
  --max-passes N     Maximum repair passes (default: 3)
  --dry-run          Generate fix specs only, do not run sessions

New option:
  --auto             After repair, run iterative improvement passes
  --improve-passes N Maximum improvement passes (default: 3, requires --auto)
```

`--auto` without `--improve-passes` defaults to 3 improvement passes.
`--improve-passes` without `--auto` is an error.

### Phase 1: Repair (unchanged)

Identical to the existing `fix` behaviour. Runs quality checks, clusters
failures, generates fix specs, runs coding sessions, and iterates. Terminates
when all checks pass, max passes reached, cost limit hit, or interrupted.

If Phase 1 terminates with anything other than `ALL_FIXED`, Phase 2 is skipped
and the command exits with the existing exit code and report.

### Phase 2: Improve

Each improvement pass proceeds through three stages:

#### Stage 1: Analyze

An analyzer agent (STANDARD model tier) receives:

- The full project structure (file tree, module boundaries)
- The project's coding conventions (from CLAUDE.md / AGENTS.md / README)
- Oracle context: project knowledge retrieved via the knowledge store's vector
  search, seeded with the query "What are the established patterns, conventions,
  and architectural decisions in this project?"
- Skeptic/Verifier findings from DuckDB (if any exist from prior sessions)
- The diff of changes made during Phase 1 (if any)
- Results from the previous improvement pass (if not the first pass)

The analyzer produces a structured JSON report:

```json
{
  "improvements": [
    {
      "id": "IMP-1",
      "tier": "quick_win",
      "title": "Remove dead import in engine.py",
      "description": "...",
      "files": ["agent_fox/engine/engine.py"],
      "impact": "low",
      "confidence": "high"
    },
    {
      "id": "IMP-2",
      "tier": "structural",
      "title": "Consolidate duplicate validation logic",
      "description": "...",
      "files": ["agent_fox/cli/fix.py", "agent_fox/cli/code.py"],
      "impact": "medium",
      "confidence": "high"
    }
  ],
  "summary": "Found 5 improvements across 3 tiers.",
  "diminishing_returns": false
}
```

**Tier priority order:** quick_win > structural > design_level.

**Impact levels:** low, medium, high — used for reporting, not filtering.

**Confidence levels:** high, medium, low — improvements with "low" confidence
are excluded from implementation.

**Diminishing returns flag:** The analyzer sets `diminishing_returns: true` when
it judges that remaining improvements are too minor or risky to justify a coding
session. This is a termination signal.

**Convergence rule:** If the analyzer returns zero improvements with high or
medium confidence, OR sets `diminishing_returns: true`, Phase 2 terminates.

#### Stage 2: Code

A coder agent (ADVANCED model tier, same as regular fix sessions) receives:

- The analyzer's improvement plan (filtered to high/medium confidence items)
- The af-code-simplifier guardrails (never refactor tests for DRYness, preserve
  public APIs, preserve "why" comments, maintain error handling)
- Instructions to implement improvements in tier-priority order

The coder makes changes and commits them as a single atomic commit on the
current branch. The commit message follows conventional commit format:
`refactor: auto-improve pass {N} — {summary}`.

#### Stage 3: Verify

A verifier agent (STANDARD model tier) performs two checks:

1. **Quality gate check:** Runs all detected quality checks (same detection
   logic as Phase 1). ALL checks must pass.
2. **Improvement validation:** Confirms that the changes are genuine
   improvements — no functionality removed, no public API changes, no test
   coverage reduction, code is measurably simpler or clearer.

The verifier produces a structured verdict:

```json
{
  "quality_gates": "PASS",
  "improvement_valid": true,
  "verdict": "PASS",
  "evidence": "All 47 tests pass. 3 files simplified, net -28 lines."
}
```

**On PASS:** The improvement commit stands. Loop continues to next pass (if
budget and pass limit allow).

**On FAIL:** The improvement commit is rolled back via `git reset --hard` to the
pre-pass state. Phase 2 terminates — we do not retry a failed improvement pass
because the analyzer would likely suggest the same changes.

### Oracle Integration

The analyzer agent's context is enriched with project knowledge from the
knowledge store (spec 12). Before the analyzer runs, the system:

1. Queries the oracle with: "What are the established patterns, conventions, and
   architectural decisions in this project?"
2. Retrieves the top-k facts (k=10) with their provenance (spec, ADR, session)
3. Includes these facts in the analyzer's system prompt under a
   `## Project Knowledge` section

This ensures the analyzer respects project-specific conventions rather than
applying generic refactoring heuristics. For example, if an ADR documents a
deliberate choice to use a particular pattern, the analyzer will not suggest
replacing it.

If the knowledge store is unavailable (no DuckDB, no embeddings), the analyzer
runs without oracle context. This is a graceful degradation, not an error.

### Termination Conditions

Phase 2 terminates when ANY of the following is true:

| Condition | Reason | Behaviour |
|-----------|--------|-----------|
| Analyzer reports `diminishing_returns: true` | No more meaningful improvements | Clean exit |
| Analyzer returns 0 high/medium-confidence improvements | Nothing actionable | Clean exit |
| `--improve-passes` limit reached | Pass budget exhausted | Clean exit |
| Shared cost limit reached (`config.orchestrator.max_cost`) | Cost budget exhausted | Clean exit |
| Verifier returns FAIL | Improvement broke something | Rollback pass, exit |
| User interrupts (Ctrl+C) | Manual stop | Save state, exit |

### Cost Budget

Phase 1 and Phase 2 share the same cost budget (`config.orchestrator.max_cost`).
There is no separate cost allocation. The cost consumed during Phase 1 reduces
the budget available for Phase 2. Each analyzer, coder, and verifier session
contributes to the running cost total.

### Report

The completion report extends the existing fix report with Phase 2 data:

```
Phase 1: Repair
  Passes completed: 2
  Clusters resolved: 3
  Sessions consumed: 3
  Status: all_fixed

Phase 2: Improve
  Passes completed: 2 of 3
  Improvements applied: 7
  Improvements by tier: 4 quick_win, 2 structural, 1 design_level
  Verifier verdicts: 2 PASS, 0 FAIL
  Sessions consumed: 6 (2 analyzer + 2 coder + 2 verifier)
  Status: diminishing_returns

Total cost: $4.82
```

In JSON mode (`--json`), the report is emitted as JSONL with an `"event":
"complete"` line containing both phase summaries.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0    | Phase 1 all fixed AND Phase 2 completed (or skipped if no `--auto`) |
| 1    | Phase 1 did not achieve all-green, or Phase 2 verifier failed |
| 130  | Interrupted by SIGINT |

Exit code 0 when `--auto` is used means: all quality checks pass AND all
improvement passes that ran were verified successfully.

## Clarifications

1. **Scope of analysis:** The analyzer examines the entire repository, not just
   files changed during Phase 1. The goal is holistic codebase improvement.

2. **Rollback mechanism:** Each improvement pass creates a git commit. On
   verifier FAIL, the system runs `git reset --hard HEAD~1` to remove that
   commit. This is safe because the commit was created by the auto-improve
   system on the current branch, and no push has occurred.

3. **Interaction with `--dry-run`:** When `--dry-run` is combined with `--auto`,
   Phase 1 runs in dry-run mode (specs generated, no sessions). Phase 2 does
   not run (it requires Phase 1 to achieve all-green, which dry-run cannot
   confirm).

4. **Parallel execution:** Phase 2 stages (analyze, code, verify) run
   sequentially within each pass. There is no parallelism within an improvement
   pass — the pipeline is strictly serial because each stage depends on the
   previous stage's output.

5. **Existing verifier archetype:** Phase 2 uses the verifier archetype template
   (spec 26) with an extended prompt that adds improvement validation on top of
   the standard quality gate check. It does not replace or modify the existing
   verifier archetype.

6. **Oracle fallback:** If the knowledge store is not initialized (no DuckDB
   database, no embedded facts), the analyzer runs without the
   `## Project Knowledge` section. A log-level info message notes the omission.
   This is not an error.

7. **Branch hygiene:** Phase 2 commits are made on whatever branch the user is
   currently on (typically a feature branch created by Phase 1 or the user).
   The system does not create a new branch for improvements.

8. **Idempotency:** Running `fix --auto` twice in succession is safe. If all
   checks pass on the first Phase 1 run, Phase 1 terminates immediately with
   ALL_FIXED and Phase 2 begins. If Phase 2 already achieved convergence,
   the analyzer will report `diminishing_returns: true` and Phase 2 terminates
   after one pass.

## Out of Scope

- A standalone `agent-fox improve` command (may be added later; this PRD scopes
  it as a mode of `fix`).
- Analyzer archetype as a reusable archetype in the archetype registry (spec
  26). The analyzer in this spec is internal to the fix-improve loop.
- Automatic PR creation or branch management for improvements.
- File-scoped or glob-scoped analysis (always whole-repo in v1).
- Per-phase cost budgets (shared budget in v1).

## Dependencies

| Spec | Relationship |
|------|--------------|
| 08_error_autofix | Extends the fix command with `--auto` flag and Phase 2 loop |
| 03_session_and_workspace | Uses `run_session` for analyzer, coder, and verifier sessions |
| 26_agent_archetypes | Uses verifier archetype template for Phase 2 verification |
| 12_fox_ball | Uses oracle RAG pipeline to enrich analyzer context |
| 11_duckdb_knowledge_store | Reads skeptic/verifier findings for analyzer context |
| 01_core_foundation | CLI registration, config, error handling |
| 27_structured_review_records | Reads existing review findings for analyzer context |
