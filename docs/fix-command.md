# The `fix` Command — Architecture Overview

The `fix` command is agent-fox's autonomous code repair pipeline. It detects
quality failures, groups them intelligently, and dispatches AI coding sessions
to fix them — iterating until the codebase is clean or a budget is exhausted.

## Two-Phase Design

The command operates in two sequential phases:

1. **Repair** (always runs) — make failing quality checks pass.
2. **Improve** (optional, `--auto` flag) — iteratively improve code quality
   once all checks are green.

---

## Phase 1: Repair

The repair phase is a multi-pass loop. Each pass follows this pipeline:

```
Detect checks ──► Run checks ──► Cluster failures ──► Generate fix specs ──► Run fix sessions
      │                                                                            │
      │                              ◄──── next pass ◄────────────────────────────-┘
```

### Step 1 — Detect Checks

On the first pass, agent-fox inspects project configuration files
(`pyproject.toml`, `Makefile`, `package.json`, `Cargo.toml`) to discover
available quality checks. Each check has a **name**, a **command**, and a
**category** (test, lint, type-check, or build).

### Step 2 — Run Checks

All detected checks are executed as subprocesses. Each produces a pass/fail
result. If everything passes, the loop terminates immediately with
`ALL_FIXED`. Otherwise the failures move to clustering.

### Step 3 — Cluster Failures

Rather than fixing each failing check in isolation, agent-fox groups failures
by **root cause**. This is where the "cluster" concept comes from.

- **AI clustering (primary):** Failure outputs are sent to an LLM which groups
  them semantically — e.g., two different test failures caused by the same
  missing import become one cluster.
- **Fallback clustering:** If AI clustering is unavailable (model error,
  connectivity), failures are grouped by check name instead (one cluster per
  check tool). This is the `"falling back to per-check grouping"` warning.

Each cluster gets a **label** (e.g., `"ruff"`, `"mypy"`) and a **suggested
approach** — a brief AI-generated strategy for the fix.

### Step 4 — Generate Fix Specs

For each cluster, agent-fox generates a temporary specification directory
(under `.agent-fox/fix_specs/`) containing:

- **requirements.md** — the problem statement and raw failure output.
- **design.md** — the suggested approach from clustering.
- **tasks.md** — a task list for the coding session.

These specs are assembled into a **task prompt** — the complete instructions
given to the coding agent.

### Step 5 — Run Fix Sessions

Each cluster's task prompt is handed to a coding session (an AI agent backed
by Claude). The session reads the failures, examines the code, and makes
edits to resolve them. After all clusters in a pass are processed, the loop
returns to Step 2 to re-run checks.

### Why Multiple Passes?

Fixing one failure can unmask others. A lint fix might introduce a type error;
a type fix might break a test. The multi-pass loop (default 3 passes) handles
these cascading effects. Each pass re-evaluates the full check suite against
the current state of the code.

### Termination

The repair loop stops when any of these conditions is met:

| Reason | Meaning |
|--------|---------|
| `ALL_FIXED` | Every check passes — success. |
| `MAX_PASSES` | Pass limit reached, some failures remain. |
| `COST_LIMIT` | Budget exhausted before completion. |
| `INTERRUPTED` | User cancelled (Ctrl+C). |

---

## Phase 2: Improve

Only runs when Phase 1 succeeds (`ALL_FIXED`) and `--auto` is set. It uses a
three-role feedback loop per pass:

```
Analyzer ──► Coder ──► Verifier
    │                      │
    │    ◄── next pass ◄───┘ (if PASS)
    │                      │
    │    ◄── rollback  ◄───┘ (if FAIL, retry with escalation)
```

- **Analyzer** — scans the codebase for improvement opportunities (ranked by
  impact and confidence). Signals `diminishing_returns` when further passes
  would add little value.
- **Coder** — implements the selected improvements.
- **Verifier** — re-runs quality checks and judges whether the improvements
  are valid. On failure, changes are rolled back and the coder retries with a
  more capable model.

The improve loop terminates on convergence, pass limit, cost limit, or
persistent verifier failure.

---

## Reading the Output

Here is what each line of the output means:

```
 Pass 1/3: running checks                        # Starting check execution (pass 1 of 3)
  check pytest: ✔                                 # pytest passed
  check ruff: ✘ (exit 1)                          # ruff failed (lint errors)
  check mypy: ✘ (exit 1)                          # mypy failed (type errors)
  check make test: ✔                              # make test passed
[WARNING] ...falling back to per-check grouping   # AI clustering unavailable; using one cluster per check
 Pass 1/3: 2 cluster(s) found                     # Two failure groups identified (ruff + mypy)
 Pass 1/3: fixing cluster 'ruff'                  # Launching a coding session for the ruff cluster
 Pass 1/3: fix session complete                   # That session finished
 Pass 1/3: fixing cluster 'mypy'                  # Launching a coding session for the mypy cluster
```

After all clusters are fixed, the loop advances to Pass 2/3 and re-runs all
checks. If everything passes, you see `ALL_FIXED`. If not, clustering and
fixing repeat.

---

## Cost Control

Every coding session reports its token cost. The orchestrator tracks cumulative
spend and terminates with `COST_LIMIT` if the configured budget
(`max_cost`) is exceeded. This prevents runaway spending on
hard-to-fix failures.

---

## Key Architectural Decisions

- **Spec-as-prompt:** Fix instructions are materialized as spec files before
  being sent to the coding agent. This enables `--dry-run` mode (generate
  specs without running sessions) and makes the pipeline inspectable.
- **Callback-driven UI:** The loop emits structured progress events; the CLI
  renders them. The core logic has no direct dependency on the display layer.
- **Graceful degradation:** AI clustering falls back to per-check grouping.
  Verifier failures trigger model escalation. The pipeline adapts rather than
  crashing.
