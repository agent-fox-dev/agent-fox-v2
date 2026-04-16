# Execution, Session Lifecycle, and Agent Archetypes

## Purpose and Placement

This document covers the runtime heart of agent-fox: the engine that dispatches
tasks from the plan graph, the lifecycle of individual coding sessions, the
workspace isolation model, and the agent archetypes that perform the actual work.
It assumes familiarity with how specs become task graphs
([Part 2: Planning](02-planning.md)) and explains what happens when
`agent-fox code` starts executing that graph.

---

## The Orchestrator

The orchestrator is a deterministic dispatch loop. It contains zero LLM
inference — every decision it makes (which task to run next, whether to retry,
when to escalate) is based on rules, thresholds, and the outcomes of prior
sessions. The LLM work happens inside sessions; the orchestrator only manages
them.

### Main Loop

The orchestrator loads the task graph and execution state, then enters a loop:

1. **Check circuit breaker.** If cost, session count, or retry limits are
   exceeded, stop.
2. **Identify ready tasks.** A task is ready when all its predecessors are
   complete and it is not blocked. The graph synchronization layer maintains
   this set incrementally.
3. **Filter file conflicts.** Ready tasks with overlapping predicted file
   impacts are serialized to avoid merge conflicts (see
   [Part 2](02-planning.md) on file impact analysis).
4. **Dispatch.** Fill available parallel slots with ready tasks. Each task
   launches a session in an isolated worktree.
5. **Process results.** When a session completes, assess the outcome, apply
   retry or escalation logic, persist state, and update the graph.
6. **Sync barrier.** At configurable intervals, pause dispatch to synchronize
   with the outside world (pull remote changes, discover new specs, reload
   config, ingest knowledge).
7. **Repeat** until all tasks are complete, the circuit breaker trips, or the
   operator interrupts.

### Ready Task Ordering

When multiple tasks are ready simultaneously, the dispatcher uses a spec-fair
round-robin strategy. Tasks are grouped by spec, specs are sorted by numeric
prefix, and the dispatcher interleaves one task from each spec per round. Within
a spec, tasks are sorted by predicted duration descending — longest tasks
dispatch first, because starting a long task later wastes more wall-clock time
than starting a short one later.

This prevents a spec with many ready tasks from monopolizing all parallel slots
while other specs wait.

### Parallel Execution

The orchestrator maintains a bounded pool of concurrent sessions (configurable,
clamped to a maximum of eight). It uses a streaming pool model rather than a
batch model: when a session completes and frees a slot, the orchestrator
immediately evaluates which tasks are now ready and fills the slot. This is
important because completing one task may unblock several others — the streaming
model starts them without waiting for the rest of the current batch to finish.

Only tasks that are actually executing occupy pool slots and carry the
IN_PROGRESS status. Tasks that are ready but waiting for a slot remain PENDING.
This prevents the state from showing eight tasks "in progress" when only three
are actually running.

### Circuit Breaker

Three limits gate execution:

- **Cost ceiling**: Total accumulated LLM cost across all sessions. Prevents
  runaway spending on a plan that is not converging.
- **Session limit**: Total number of sessions (including retries). Prevents
  infinite retry loops.
- **Per-task retry limit**: Maximum attempts for a single task before it is
  marked blocked.

When a limit is hit, the orchestrator stops dispatching new tasks, waits for
in-flight sessions to complete, and exits with a descriptive status code. The
circuit breaker is checked before every dispatch, not after — a task that is
already running will be allowed to finish.

### Signal Handling

The orchestrator installs a SIGINT handler for graceful shutdown. The first
interrupt sets a flag that prevents new dispatches and waits for in-flight
sessions to complete. A second interrupt cancels in-flight sessions and exits
immediately. This two-stage model protects against both impatient operators
(who want to stop now) and careful operators (who want to let current work
finish cleanly).

---

## Session Lifecycle

Each task in the graph is executed as a session — a single invocation of a
Claude agent in an isolated workspace. The session lifecycle has four phases.

### Prepare

**Workspace creation.** An isolated git worktree is created on a feature branch
named `feature/{spec_name}/{task_group}`. The worktree is a full working copy
of the repository at the current state of `develop`, with its own branch that
can diverge independently. This isolation means multiple sessions can run in
parallel without stepping on each other's working trees.

Worktree creation includes cleanup of stale artifacts: orphaned empty
directories from prior crashes are removed, stale branch references are pruned,
and conflicting branches are deleted if they are no longer used by any worktree.

**Context assembly.** The system builds two prompts — a system prompt and a task
prompt — tailored to the session's archetype and task. Context assembly draws
from several sources:

- Spec documents (requirements, design, test spec, tasks) provide the
  task-specific context.
- Memory facts from the knowledge store provide cross-session learning — what
  worked before, what failed, what conventions the codebase follows.
- Steering directives from `.specs/steering.md` provide project-wide guidance.
- Prior group findings (review findings, drift findings, verification verdicts
  from earlier groups in the same spec) provide accumulated context.
- For retry attempts, critical and major findings from review agents are
  injected so the coder can address them.

Memory fact selection uses keyword matching with causal enrichment: facts are
first filtered by relevance to the current task's keywords, then augmented with
causally linked facts from the knowledge graph. A fact cache avoids redundant
queries when the fact set has not changed.

**Pre-session hooks.** User-configured shell commands run before the session
starts. These can set up dependencies, run migrations, or perform any
preparation the project requires.

### Execute

The session is executed through a backend abstraction. The system sends the
system prompt and task prompt to the Claude agent SDK, which runs the agent
loop — the agent reads files, writes code, runs commands, and produces output
over multiple turns.

Key parameters are resolved per session:

- **Model ID**: Determined by the adaptive routing system based on task
  complexity assessment (see Model Routing below).
- **Max turns**: Archetype-specific limit on the number of agent turns.
- **Thinking mode**: Extended thinking with configurable token budget,
  currently enabled only for the Coder archetype in adaptive mode.
- **Timeout**: Configurable wall-clock limit. Timeout failures trigger
  specialized retry logic with extended limits.
- **Budget cap**: Optional per-session USD limit.
- **Fallback model**: Alternative model if the primary is unavailable.

The backend streams canonical messages (tool use, assistant text, thinking
blocks) which are logged for audit and used for knowledge extraction.

### Harvest

On session completion, if the session produced commits on its feature branch,
those commits are integrated into `develop`. The harvest process:

1. Acquires the merge lock (an intra-process asyncio lock combined with an
   inter-process file lock) to serialize merge operations.
2. Checks for new commits on the feature branch relative to `develop`.
3. Performs a squash merge (`git merge --squash`) to collapse the feature
   branch into a single commit on `develop`, regardless of how many commits
   the feature branch contains. This keeps the `develop` history linear and
   readable.
4. If the squash merge has conflicts, spawns a merge agent — a dedicated
   Claude session with a restricted prompt that only resolves conflicts,
   without making any other changes.
5. After merging, optionally pushes `develop` to the remote.

The merge lock prevents two sessions from merging simultaneously, which would
risk corrupting the `develop` branch. The lock has stale detection: if a lock
file is older than a configurable timeout (default five minutes), it is
considered abandoned and broken atomically using a rename-to-temp pattern that
is safe against TOCTOU races.

### Assess

After harvest, the system extracts knowledge from the session:

- **Review parsing**: For review archetypes (Skeptic, Oracle, Auditor,
  Verifier), the session output is parsed for structured JSON containing
  findings, verdicts, or drift reports. The parser is tolerant of format
  variations — it handles fenced code blocks, bare JSON, wrapper objects with
  various key names, and single-object responses.
- **Knowledge extraction**: Facts, learnings, and causal relationships are
  extracted from the session transcript and stored in the knowledge base for
  future sessions.
- **Review persistence**: Parsed findings are stored in DuckDB tables for
  querying by subsequent sessions and for convergence analysis.

If the initial parse of review output fails and the session is still responsive,
a format retry is attempted — the system asks the agent to re-emit its output
in the correct JSON format. This recovers from common formatting mistakes
(markdown fences around JSON, missing wrapper keys) without failing the session.

---

## Agent Archetypes

An archetype defines the role, capabilities, and constraints of an agent
session. Each archetype has a prompt profile, a model tier, a tool allowlist,
and behavioral rules. The archetype registry contains four built-in entries.
Two of them — the reviewer and the maintainer — support **modes**: named
variants that override specific fields (injection point, tool allowlist,
model tier) while inheriting everything else from the base entry. Modes are
the mechanism by which a single registry entry serves multiple distinct roles.

### The Registry

| Entry | Modes | Purpose |
|---|---|---|
| **coder** | `fix` | Implementation — writes code, tests, commits |
| **reviewer** | `pre-review`, `drift-review`, `audit-review`, `fix-review` | Review — examines specs and code, produces structured findings |
| **verifier** | — | Verification — runs tests, checks requirements, produces verdicts |
| **maintainer** | `hunt`, `fix-triage`, `extraction` | Night-shift internal — not user-facing |

When a mode is specified, the system resolves the effective configuration by
overlaying the mode's overrides onto the base entry. Fields set to `None` in
the mode config inherit from the base. This is a dataclass merge, not
inheritance — the result is a flat `ArchetypeEntry` with no mode reference.

### Coder

The primary implementation agent. Receives the full spec context and implements
one task group per session. For group 1 (by convention), it writes failing tests
from the test spec without implementing production code. For subsequent groups,
it implements code to make existing tests pass. The Coder runs quality checks,
commits with conventional messages, and produces a session summary. It operates
at the STANDARD model tier by default with adaptive extended thinking enabled,
and has unrestricted tool access. A `fix` mode variant is used by the
`agent-fox fix` pipeline.

### Reviewer

A unified review archetype that covers three conceptually distinct review
roles through its mode system. All reviewer modes produce structured JSON
output that the orchestrator uses for blocking decisions, retry triggers, and
knowledge accumulation. Reviewer modes cannot modify code — their tool
allowlists are restricted to read-only operations.

**Pre-review mode** (injection: `auto_pre`) reviews spec quality before
implementation begins. It examines completeness, consistency, feasibility,
testability, edge case coverage, and security. It produces findings with
severity levels (critical, major, minor, observation). This mode has no shell
access at all — it works entirely from the spec documents provided in context.

**Drift-review mode** (injection: `auto_pre`) validates spec assumptions
against the actual codebase. It checks whether referenced files, functions,
and interfaces exist at their stated locations and whether signatures match
spec descriptions. It produces drift findings. This mode has read-only
filesystem access (`ls`, `cat`, `git`, `grep`, `find`, `head`, `tail`, `wc`).
It is automatically skipped for specs that reference no existing code — there
is nothing to detect drift against.

**Audit-review mode** (injection: `auto_mid`) validates test quality against
test spec contracts after tests are written. It examines coverage, assertion
strength, precondition fidelity, edge case rigor, and test independence for
each test spec entry, producing per-entry verdicts (PASS, WEAK, MISSING,
MISALIGNED). This mode has read-only access plus `uv` for test collection.
It triggers predecessor retries when tests are missing or misaligned.

**Fix-review mode** is used by the `agent-fox fix` pipeline and night-shift's
fix pipeline. It operates at the ADVANCED model tier with broader tool access
including `make` and `uv`.

Pre-review and drift-review both run at the `auto_pre` injection point. When
both are enabled, they execute in parallel before the first coder group. If
either produces blocking findings (critical findings exceeding the configured
threshold), downstream coder tasks are blocked.

The reviewer archetype is controlled by a single configuration toggle
(`archetypes.reviewer`). Enabling or disabling it affects all four modes.
Legacy configuration keys (`skeptic`, `oracle`, `auditor`) are accepted and
mapped to the corresponding reviewer modes with deprecation warnings.

### Verifier

Performs post-implementation verification (injection: `auto_post`). It runs the
test suite, checks each requirement against the acceptance criteria, and
produces per-requirement verdicts (PASS, FAIL, PARTIAL). The Verifier has full
tool access (it needs to run tests). It can trigger retries of its predecessor
— if verification fails, the orchestrator may re-run the preceding coder
session with the Verifier's findings injected as context.

### Maintainer

An internal archetype used exclusively by the night-shift daemon (see
[Part 4](04-night-shift.md)). It is not user-facing and not assignable to
task groups. Its modes cover hunt scan analysis (`hunt`), issue triage
(`fix-triage`), and knowledge extraction (`extraction`).

### Design Rationale

All archetypes default to the STANDARD model tier. The adaptive routing system
(described below) may escalate individual tasks to higher tiers based on
complexity assessment and failure history. Operators can also override model
tiers per archetype via configuration. The intent is to start cost-effective
and escalate only when needed, rather than running every session at the most
capable (and expensive) tier.

Read-only tool allowlists for reviewer modes enforce a separation of concerns.
A reviewer that can modify code is no longer a pure reviewer — it might fix
problems it finds, conflating review and implementation. Restricting tools
keeps each mode's role clean and its output predictable.

The consolidation of three conceptual review roles (spec review, drift
detection, test auditing) into a single reviewer archetype with modes reflects
the observation that these roles share most of their configuration: same base
model tier, same output format, same convergence semantics. Modes capture only
the differences — injection point, tool allowlist, and prompt profile — without
duplicating the shared structure.

### Multi-Instance Convergence

The reviewer and verifier archetypes can run multiple instances in parallel on
the same task. When they do, their outputs are merged using mode-specific
convergence strategies. A single dispatcher (`converge_reviewer`) routes to
the correct algorithm by mode.

**Pre-review and drift-review convergence** uses majority-gating for critical
findings. All findings across instances are merged and deduplicated. A critical
finding counts toward blocking only if it appears in at least a majority of
instances (ceiling of N/2). This prevents a single overzealous instance from
blocking progress on a spurious finding. Non-critical findings are
union-merged.

**Audit-review convergence** uses union semantics with worst-verdict-wins. For
each test spec entry, the worst verdict across all instances is taken. This is
conservative — if any instance finds a test MISSING, the entry is considered
MISSING regardless of what other instances report.

**Verifier convergence** uses majority voting per requirement. A requirement
is considered PASS if a majority of instances report PASS. The representative
evidence comes from the first matching verdict.

**Fix-review** does not support multi-instance execution. If multiple results
are provided, convergence raises an error.

For single-instance execution (the default), convergence is a no-op
passthrough.

---

## Result Handling and Retry Logic

When a session completes, the result handler classifies the outcome and decides
what happens next.

### Success

The task node is marked COMPLETED in the graph. If the session was a review
agent with blocking authority (Skeptic or Oracle), the handler evaluates
whether the findings exceed the configured blocking threshold. If they do,
downstream coder tasks are blocked — they will not execute until the findings
are addressed.

### Timeout

Timeout failures receive specialized handling. Instead of immediately
escalating to a higher model tier, the orchestrator extends the session
parameters: max turns and session timeout are multiplied by a configurable
factor, clamped to a ceiling. The task is reset to PENDING for retry at the
same model tier. This is based on the observation that timeouts usually mean
the task needed more time, not a smarter model.

Only after timeout retries are exhausted does the task fall through to the
normal failure escalation path.

### Failure

Non-timeout failures enter the escalation ladder. The escalation system
maintains a per-task state machine that tracks the current model tier, attempt
count, and escalation count. On failure:

1. If retries remain at the current tier, the task is reset to PENDING for
   another attempt.
2. If retries at the current tier are exhausted, the tier is escalated (SIMPLE
   → STANDARD → ADVANCED) and the retry counter resets.
3. If the highest tier's retries are also exhausted, the task is marked BLOCKED
   and all its dependents are cascade-blocked via BFS through the dependency
   graph.

Escalation is strictly non-decreasing — a task never drops back to a lower
tier. The tier ceiling (from the complexity assessment) is enforced at every
step. A task assessed as STANDARD will never escalate beyond STANDARD even if
retries at that tier are exhausted.

### Cascade Blocking

When a task is blocked, all tasks that transitively depend on it are also
blocked. The orchestrator performs a breadth-first traversal of the dependency
graph's reverse edges, marking each reachable node as BLOCKED with a reason
string. This prevents the system from dispatching tasks that cannot possibly
succeed because their prerequisites failed.

---

## Model Routing

The adaptive routing system predicts which model tier to use for each task
before execution. This serves two purposes: controlling cost (SIMPLE tier is
cheaper than ADVANCED) and improving success rates (complex tasks benefit from
stronger models).

### Assessment Pipeline

Before dispatching a task, the assessor extracts a feature vector from the
spec content: subtask count, spec word count, presence of property tests, edge
case count, dependency count, estimated file count, cross-spec integration
flag, language count, and historical median duration.

The assessment method is selected based on the amount of historical data
available:

- **Below the training threshold**: A rules-based heuristic classifies tasks
  using simple thresholds (e.g., cross-spec integration or high file count
  triggers ADVANCED).
- **Above the training threshold with adequate accuracy**: A logistic
  regression classifier trained on historical (feature vector, actual tier)
  pairs provides the prediction.
- **Above the training threshold with poor accuracy**: A hybrid approach
  combines the statistical model with an LLM query and uses the method with
  higher historical accuracy when they disagree.

In all cases, the prediction is clamped to a tier ceiling that prevents
over-escalation.

### Duration Estimation

Task duration estimates feed into the ready-task ordering (longest-first) and
critical path analysis. The duration model uses a precedence chain: regression
model (if trained), historical median for the spec and archetype, preset
duration by archetype and tier, or a five-minute default fallback.

### Outcome Recording

After each session, the actual tier used, token consumption, cost, duration,
and success/failure outcome are recorded. These records train the statistical
models and update historical medians, creating a feedback loop that improves
routing accuracy over time.

---

## Sync Barriers

At configurable intervals during execution, the orchestrator pauses dispatch
and performs synchronization work:

- **Develop sync**: Pull remote changes into `develop`, reconciling divergence
  with the same merge strategy used during harvest.
- **Worktree verification**: Check for orphaned worktrees and clean them up.
- **Hot-load discovery**: Check for new specs in `.specs/` that were not present
  when the plan was built. New specs pass a three-stage gate (git-tracked,
  complete artifacts, passes lint) before being added to the live graph.
- **Knowledge ingestion**: Ingest accumulated facts into the knowledge store.
- **Config reload**: Re-read `config.toml` and apply changes (new cost limits,
  archetype settings, etc.) without restarting.
- **Hook execution**: Run user-configured sync hooks.

Sync barriers are the mechanism by which long-running execution adapts to
changes in the environment. They are deliberately periodic rather than
continuous — checking for new specs or remote changes on every task completion
would add overhead without proportional benefit.

---

## Workspace Integration

### The Develop Branch

`develop` is the integration branch. All session work merges into `develop`,
never into `main`. Feature branches are local-only — they are never pushed to
the remote. Only `develop` (and `main` for releases) is pushed.

Before the first session, the orchestrator ensures `develop` exists and is
synchronized with the remote. If `develop` does not exist locally, it is
created from `origin/develop` (if present) or from the default branch.

### Merge Lock

The merge lock serializes all operations that modify `develop`. It combines
an asyncio lock (for intra-process serialization across concurrent sessions)
with an atomic file lock (for inter-process serialization if multiple agent-fox
instances target the same repository). The file lock uses `O_CREAT | O_EXCL`
for atomic creation and a rename-to-temp pattern for stale lock breaking.

### Reset

When execution produces bad results, the operator can reset tasks:

**Soft reset** resets failed, blocked, and in-progress tasks to PENDING without
rolling back code. Session history and counters are preserved. This is
appropriate after transient failures (network issues, API errors).

**Hard reset** resets tasks and rolls back `develop` to the commit before the
earliest affected task. This undoes the code changes and allows a clean re-
execution. The knowledge base is compacted during hard reset to deduplicate
facts and resolve supersession chains.

Both reset types can target a single spec or the entire plan.

---

## Quality Checks

Quality enforcement happens at two levels. Within each Coder session, the
agent's prompt instructs it to run the relevant test suite and linter before
committing and to fix any failures. This is a prompt-level directive, not
an orchestrator-enforced gate — the agent decides how to satisfy it.

After the last coding group, the Verifier archetype performs structured
post-implementation verification: running the test suite, checking each
requirement against acceptance criteria, and producing per-requirement
verdicts. A failing verification triggers a coder retry with the Verifier's
findings injected as context.

---

*Previous: [Planning — From Specs to Task Graphs](02-planning.md)*
*Next: [Night-Shift Mode](04-night-shift.md)*
