# Coding Session Architecture 2

How agent-fox turns a collection of specifications into committed code through
autonomous, parallel, knowledge-accumulating coding sessions.

This document is a top-down walkthrough — from the persistent state in the
database, through the orchestrator's dispatch loop, through each agent
archetype's role, through workspace isolation and merge integration, and down
to how knowledge is harvested and fed forward to future sessions.

---

## 1. Foundational Concepts

### 1.1 The Contract Model

Everything agent-fox does traces back to a **spec** — a set of five structured
artifacts that together define a coherent unit of work:

| Artifact | Role |
|---|---|
| `prd.md` | Why the feature exists; cross-spec dependency declarations |
| `requirements.md` | Testable acceptance criteria in EARS syntax (`NN-REQ-M.S` identifiers) |
| `design.md` | Interfaces, data models, correctness properties, definition of done |
| `test_spec.md` | Language-agnostic test contracts keyed by `TS-NN-N` identifiers |
| `tasks.md` | Sequenced task groups with checkboxes; the planner's primary input |

A spec is not documentation written after the fact. It is the input artifact
that drives every downstream decision: which agents run, in what order, with
what constraints, and with what success criteria.

### 1.2 The Separation of Concerns

Three concerns are explicitly kept separate:

- **The orchestrator** is entirely deterministic — zero LLM calls. It manages
  the task graph, dispatches sessions, handles retries and escalation, and
  persists state. It never decides what code to write.

- **Sessions** are the LLM-powered work units. Each session runs a Claude
  agent inside an isolated workspace for a single task group. The agent reads
  files, writes code, runs commands, and commits results.

- **The knowledge system** is the institutional memory. It operates
  asynchronously relative to the session lifecycle — extracting facts from
  session transcripts after the fact and injecting relevant facts into the
  context of future sessions.

---

## 2. Persistent State in DuckDB

All system state lives in a single DuckDB database (`.agent-fox/knowledge.db`).
There is no external server; the database is an embedded file opened by the
orchestrator process.

### 2.1 Plan State

The task graph is stored across three tables:

- **`plan_nodes`** — One row per task group node. Fields: node ID
  (`spec_name:group_number`), spec name, group number, title, status, archetype,
  mode, instance count, optional flag, subtask count, body text.
- **`plan_edges`** — Directed dependency edges: `(source_node_id, target_node_id,
  kind)`. Kind is either `intra_spec` (sequential groups within a spec) or
  `cross_spec` (dependency declared in `prd.md`).
- **`plan_meta`** — Content hash of the plan, version, fast-mode flag, and
  optional spec filter.

The plan is rebuilt deterministically from `.agent-fox/specs/` on every
`agent-fox plan` invocation and written atomically to DuckDB. The orchestrator
loads it at startup.

Node status is one of: `pending`, `in_progress`, `completed`, `failed`,
`blocked`, `skipped`, `deferred`. The orchestrator updates status after every
session completes and writes it back to DuckDB.

### 2.2 Execution State

Two tables track runtime history:

- **`session_outcomes`** — One row per session attempt: node ID, spec name, status,
  model used, input/output tokens, cost, duration, touched file paths, commit SHA,
  and a retrieval summary (which knowledge signals fired and how many facts were
  injected).
- **`run_records`** — One row per orchestrator run: run ID, plan hash, start time,
  end time, final status.

### 2.3 Quality Assurance State

Four tables store the outputs of review and verification agents:

- **`review_findings`** — Findings from pre-review and drift-review, classified
  by severity (`critical`, `major`, `minor`, `observation`). Each finding has
  provenance (spec, session, attempt) and a `superseded_by` column so resolved
  findings can be retired without deletion.
- **`drift_findings`** — Spec-to-code discrepancies detected by drift-review.
- **`verification_results`** — Per-requirement verdicts (`PASS`, `FAIL`,
  `PARTIAL`) from the Verifier archetype, with evidence text.
- **`blocking_decisions`** — Records of when quality gates blocked downstream
  tasks, with outcome tracking for future threshold calibration.

### 2.4 Knowledge State

Five tables store the institutional memory:

- **`memory_facts`** — Typed facts extracted from session transcripts. Each fact
  has a UUID, content (1-2 sentences), category, confidence float, keywords,
  spec provenance, session ID, commit SHA, and a `superseded_by` chain.
- **`memory_embeddings`** — Vector embeddings keyed by fact UUID for similarity
  search. Uses DuckDB's native VSS extension.
- **`fact_causes`** — Directed edges between fact UUIDs forming a causal graph.
  An edge `(A → B)` means "fact A led to fact B."
- **`audit_events`** — Structured log of every significant operation: run start,
  session start/complete/fail, git merge, fact extraction, harvest complete,
  config reload. Each event has a type, severity, run ID, node ID, and a JSON
  payload.

---

## 3. From Specs to Task Graph

### 3.1 Discovery and Validation

Before any planning occurs, the system discovers specs by scanning
`.agent-fox/specs/` for directories matching the `NN_name` pattern. Each
discovered spec becomes a `SpecInfo` record.

Static validation runs ~30 rules against the spec artifacts:
- Structural checks (all five artifacts present)
- EARS syntax on requirements
- Traceability chain integrity (every requirement traced through test spec and
  tasks; every test entry traced back to a requirement)
- Cross-spec dependency validity (referenced specs exist, referenced group
  numbers exist, no cycles)
- Section schema checks (expected headings present)

Findings are severity-classified as error (blocks planning), warning (quality
gap), or hint (stylistic). An auto-fixer can mechanically resolve many
warnings. AI validation is an optional second pass that uses an LLM to detect
vague requirements and stale dependency identifiers.

### 3.2 Graph Construction — Four Phases

Given validated specs, the planner builds a directed acyclic graph in four
phases.

**Phase 1: Base Nodes and Intra-Spec Edges.** For each spec with a `tasks.md`,
the planner creates one `Node` per task group. Consecutive groups within a spec
get intra-spec edges: group N → group N+1. Groups already marked `[x]` in
`tasks.md` start as `COMPLETED`. The node ID format is `spec_name:group_number`.

**Phase 2: Archetype Injection.** The planner inserts non-coder agent nodes at
three injection points in each spec's chain:

- **`auto_pre`** (before group 1): Reviewer in `pre-review` mode (spec quality
  review) and `drift-review` mode (spec-vs-codebase drift detection). The
  drift-review node is only injected if the spec references files that already
  exist on disk — there is nothing to drift-check against for brand-new specs.
- **`auto_mid`** (after test-writing groups): Reviewer in `audit-review` mode
  (test coverage validation against `test_spec.md` contracts). Only injected
  if `test_spec.md` has at least a configurable minimum number of entries.
- **`auto_post`** (after the last coder group): Verifier (runs tests, checks
  requirements against implementation).

**Phase 3: Archetype Tag Overrides.** If a task group carries an `[archetype:
<name>]` tag in `tasks.md`, that group's node is reassigned from the default
`coder` archetype to the tagged archetype. This takes highest priority over
both injection rules and defaults.

**Phase 4: Cross-Spec Edges.** Dependencies declared in `prd.md` create edges
between groups in different specs. The planner validates that both endpoints
exist. Spec-level dependencies (coarse format) resolve to the last group of the
referenced spec; group-level dependencies (fine format) create edges between
precise groups.

### 3.3 Execution Order

Kahn's topological sort produces the execution order. Ties among nodes with
zero in-degree are broken deterministically by `(spec_name, group_number)` —
alphabetical by spec, ascending by group. This makes the execution order fully
reproducible across runs from the same specs.

The sorted order, along with nodes and edges, is persisted to DuckDB. The
orchestrator loads this complete structure at startup.

### 3.4 Runtime Graph Patching

The plan is not entirely static. Two mechanisms modify it at runtime:

**Archetype injection patching.** If the loaded plan was built with a different
archetype configuration than the current one (e.g., audit-review was disabled
when the plan was built but is now enabled), the orchestrator injects the
missing nodes into the in-memory graph at startup and persists the updated plan.

**Hot-load discovery.** During sync barriers, the orchestrator checks for new
specs that have appeared since the plan was built. A spec passes four gates
before admission: git-tracked on develop, all five artifacts present and
non-empty, passes static lint validation, and not fully implemented. Admitted
specs are merged into the live graph — new nodes, new edges, archetype injection
— and the `GraphSync` state machine is rebuilt.

---

## 4. The Orchestrator's Dispatch Loop

The orchestrator (`engine/engine.py`) is a pure state machine with zero LLM
calls. It loads the graph, loads or initializes execution state, installs signal
handlers, and enters a loop.

### 4.1 The Main Loop

Each iteration:

1. **Check interruption.** If SIGINT was received, drain in-flight sessions and
   return.

2. **Check circuit breaker.** Three limits gate execution:
   - Cost ceiling: total accumulated LLM cost across all sessions.
   - Session ceiling: total session invocations (including retries).
   - Per-task retry ceiling: maximum attempts before a task is marked blocked.
   If a limit is exceeded, stop dispatching and return with a status code.

3. **Identify ready tasks.** A task is ready when all its predecessor nodes are
   `completed` and its own status is `pending`. The `GraphSync` component
   maintains this set incrementally — when a node completes, it decrements
   in-degree counts for successors and surfaces any that become ready.

4. **Filter file conflicts.** When parallel execution is enabled and multiple
   tasks are ready, the file conflict detector compares predicted file impacts
   (extracted from spec text). Conflicting pairs are serialized — only one of
   them dispatches in this iteration.

5. **Dispatch.** Available parallel slots are filled with ready tasks, each
   launching a session in an isolated worktree.

6. **Process results.** Completed sessions return a `SessionRecord`. The result
   handler classifies the outcome (success, failure, timeout), applies retry or
   escalation logic, persists state, and updates the graph.

7. **Sync barrier.** At configurable intervals (every N completed tasks), the
   orchestrator pauses dispatch, pulls remote changes, checks for new specs,
   runs knowledge consolidation for completed specs, reloads config, and
   executes user-configured hooks.

8. **Repeat** until all tasks complete, a circuit breaker trips, or SIGINT
   arrives.

### 4.2 Ready Task Ordering

When multiple tasks are simultaneously ready, the dispatcher uses **spec-fair
round-robin**: tasks are grouped by spec (sorted by numeric prefix), and the
dispatcher takes one task from each spec per round. Within a spec, tasks are
sorted by predicted duration descending — longest tasks dispatch first to
minimize wall-clock time.

### 4.3 Parallel Execution Model

The parallel runner maintains a bounded pool (max 8 concurrent slots, controlled
by `--parallel N`). It uses a streaming pool rather than a batch model: when a
session completes and frees a slot, the orchestrator immediately evaluates which
tasks are now ready and fills the slot. Completing one task may unblock several
downstream tasks — the streaming model starts them without waiting for the rest
of the current batch.

Only tasks that are actually running carry the `in_progress` status. Tasks that
are ready but waiting for a pool slot remain `pending`.

Review archetype sessions (other than `auto_pre` group-0 nodes) are capped at a
configurable fraction of the pool to prevent review tasks from crowding out
coder sessions when many review nodes become ready simultaneously.

### 4.4 Signal Handling

The orchestrator installs a two-stage SIGINT handler. The first interrupt sets
an `interrupted` flag: no new dispatches, but in-flight sessions finish cleanly.
A second interrupt cancels in-flight sessions and exits immediately.

---

## 5. Session Lifecycle

Each task node is executed as a session — a single invocation of a Claude agent
in an isolated workspace. The session lifecycle has four phases.

```
┌─────────────────────────────────────────────────────────────┐
│  SESSION LIFECYCLE                                          │
│                                                             │
│  1. PREPARE                                                 │
│     ensure_develop → create_worktree → build_prompts        │
│         → run pre-session hooks                             │
│                                                             │
│  2. EXECUTE                                                 │
│     run_session(system_prompt, task_prompt)                 │
│         → Claude SDK streams tool_use / assistant messages  │
│                                                             │
│  3. HARVEST                                                 │
│     acquire merge_lock → git merge --squash feature branch  │
│         → resolve conflicts via merge agent if needed       │
│         → push develop to origin (best-effort)              │
│                                                             │
│  4. ASSESS                                                  │
│     parse review findings → persist to DuckDB               │
│         → extract knowledge facts → generate embeddings     │
│         → dedup / contradiction detection / causal links    │
│         → emit audit events → record session outcome        │
└─────────────────────────────────────────────────────────────┘
```

### 5.1 Prepare

**Workspace creation.** The system first ensures the `develop` branch exists and
is synchronized with the remote. It then creates an isolated git worktree at a
temporary path, on a new feature branch named `feature/{spec_name}/{task_group}`.
A worktree is a fully checked-out working copy of the repository at the current
state of `develop`, with its own branch that can diverge independently. Multiple
sessions can run in parallel in separate worktrees without touching each other.

Worktree creation includes stale artifact cleanup: orphaned empty directories
from prior crashes are removed, stale branch references are pruned, and
conflicting branches are deleted if they are no longer used by any active
worktree.

**Prompt construction.** The system builds two prompts — a system prompt and a
task prompt — tailored to the session's archetype, mode, and task. The full
prompt construction process is described in Section 7.

**Pre-session hooks.** User-configured shell commands run before the session
starts for any per-project preparation.

### 5.2 Execute

The session is submitted to the Claude agent SDK. The SDK drives the agent
loop: the agent reads files, writes code, runs commands (from the archetype's
tool allowlist), and produces output over multiple turns.

Per-session SDK parameters are resolved before dispatch:

- **Model ID** — Determined by the adaptive routing system (see Section 6.2).
- **Max turns** — Archetype-specific cap on the number of agent turns (300 for
  Coder, 120 for Verifier, 80 for Reviewer).
- **Thinking mode** — Extended thinking with configurable token budget. Currently
  enabled only for the Coder archetype (`adaptive` mode, 64K budget).
- **Timeout** — Wall-clock limit. Timeout failures receive specialized retry
  handling (see Section 6.3).
- **Budget cap** — Optional per-session USD ceiling.
- **Fallback model** — Alternative model if the primary is unavailable.

The backend streams canonical events (tool use, tool results, assistant text,
thinking blocks) to the sink dispatcher. These events are logged for audit and
are the source material for knowledge extraction.

On completion, the SDK returns a `SessionOutcome` carrying status, token counts,
cost, duration, full response text, and any error message.

### 5.3 Harvest

On successful session completion, the feature branch is integrated into
`develop`. The harvest process:

1. **Check for new commits.** If the feature branch has no new commits relative
   to `develop`, harvest is skipped — the session produced no code changes.

2. **Acquire the merge lock.** An asyncio lock (intra-process) combined with an
   atomic file lock (`O_CREAT | O_EXCL` with rename-based stale detection)
   serializes all merge operations. No two sessions can merge simultaneously.

3. **Squash merge.** `git merge --squash feature/{spec}/{group}` collapses the
   feature branch into a single staged diff on `develop`, regardless of how many
   commits the feature branch contains. This keeps `develop` history linear.

4. **Conflict resolution.** If the squash merge has conflicts, a dedicated merge
   agent session is spawned — a restricted Claude session whose only job is to
   resolve the conflicting hunks without making other changes. If the merge agent
   also fails, the merge is aborted and the session is marked failed.

5. **Commit.** The squash commit is created on `develop` with a message derived
   from the tip commit of the feature branch. For multi-commit branches, earlier
   commit subjects are appended as a bullet list.

6. **Push.** `develop` is pushed to origin (best-effort). If origin is ahead,
   the system reconciles first. Push failures are logged as warnings and do not
   fail the session.

7. **Worktree cleanup.** The feature branch worktree is always destroyed at the
   end of the session lifecycle, even if the session failed. Cleanup failures are
   logged but do not affect the outcome record.

### 5.4 Assess

After harvest, the system processes the session's outputs.

**Review persistence.** For review archetypes (Reviewer in all modes, Verifier),
the session output is parsed for structured JSON. The parser is tolerant: it
handles fenced code blocks, bare JSON, wrapper objects with various key names,
and single-object responses. Parsed findings are written to the appropriate
DuckDB quality tables (`review_findings`, `drift_findings`,
`verification_results`).

If the initial parse fails and the session is still responsive, a format retry
is attempted — the system asks the agent to re-emit its output in the correct
JSON format. This recovers from common formatting mistakes without failing the
session.

**Knowledge extraction.** For coder sessions, the session transcript is
processed through the knowledge pipeline (Section 8).

**Outcome recording.** The `SessionRecord` (node ID, attempt, status, token
counts, cost, duration, touched files, model, commit SHA, retrieval summary)
is appended to `session_outcomes` in DuckDB.

**Audit events.** `session.complete` or `session.fail` events are emitted to
the audit trail with full metadata.

---

## 6. Result Handling and Retry Logic

### 6.1 Success

The node is marked `completed` in the graph. If the session was a review agent
with blocking authority (Reviewer in `pre-review` or `drift-review` mode), the
result handler evaluates whether the findings exceed the configured blocking
threshold (default: any critical finding). If they do, all downstream coder
tasks for that spec are set to `blocked`, and all their transitive dependents
are cascade-blocked via BFS.

The `audit-review` and `verifier` archetypes both have `retry_predecessor=true`.
When their session completes with failing outputs (MISSING tests, FAIL
requirements), the orchestrator may re-run the preceding coder session with the
review/verification findings injected as context.

### 6.2 Model Routing and the Assessment Pipeline

Before dispatching a task, the **assessor** computes a complexity feature vector:

- Subtask count, spec word count
- Presence of property tests, edge case count
- Dependency count, estimated file count
- Cross-spec integration flag, language count
- Historical median duration for this spec

Based on the amount of historical data available, the assessment method is
selected:

- **Below training threshold**: Rules-based heuristic using simple thresholds
  (cross-spec integration or high file count → ADVANCED).
- **Above threshold, adequate accuracy**: Logistic regression classifier trained
  on `(feature_vector, actual_tier)` pairs from `session_outcomes`.
- **Above threshold, poor accuracy**: Hybrid — the statistical model and an LLM
  query are compared, and the method with higher historical accuracy wins.

The predicted tier (SIMPLE, STANDARD, ADVANCED) is clamped to a configured
ceiling. The escalation ladder never exceeds the ceiling even after repeated
failures.

### 6.3 Timeout Handling

Timeout failures receive specialized handling. Instead of immediately escalating
to a higher model tier (which would be wasteful — the problem is time, not
capability), the orchestrator extends the session parameters: max turns and
timeout are multiplied by a configurable factor and clamped to a ceiling. The
task is reset to `pending` for retry at the same tier.

Only after timeout retries are exhausted does the task fall through to the
normal failure escalation path.

### 6.4 Failure and Escalation

Non-timeout failures enter the **escalation ladder**. The ladder is a per-task
state machine that tracks current tier, attempt count, and escalation count:

1. If retries remain at the current tier, reset to `pending` for another attempt.
2. If retries at the current tier are exhausted, escalate to the next tier
   (SIMPLE → STANDARD → ADVANCED) and reset the retry counter.
3. If the highest tier's retries are also exhausted, mark the task `blocked` and
   cascade-block all transitive dependents.

Escalation is strictly non-decreasing — a task never drops back to a lower tier.
The tier ceiling prevents over-escalation.

On each retry, the previous error message is sanitized and appended to the task
prompt. Active critical and major review findings are also prepended so the coder
can address identified issues.

---

## 7. Prompt Construction

Each session receives a two-part prompt: a **system prompt** (establishes context
and behavioral guidance) and a **task prompt** (specifies what to do). The system
prompt is built from three layers; the task prompt is archetype-specific.

### 7.1 Three-Layer System Prompt

```
Layer 1: Agent base profile  (agent.md)
   ↕ section break
Layer 2: Archetype profile   (e.g., coder.md, reviewer_pre-review.md)
   ↕ section break
Layer 3: Task context        (spec docs + knowledge + findings + steering)
```

**Layer 1 — Agent base profile.** The `agent.md` template provides instructions
shared by every agent regardless of archetype: project orientation steps,
directory structure conventions, and general policies.

**Layer 2 — Archetype profile.** Loaded from a markdown profile file for the
session's archetype and mode. Profile resolution uses a four-step priority chain
where the first matching file wins:

1. Project-level mode-specific: `.agent-fox/profiles/{archetype}_{mode}.md`
2. Package-embedded mode-specific: `_templates/profiles/{archetype}_{mode}.md`
3. Project-level base: `.agent-fox/profiles/{archetype}.md`
4. Package-embedded base: `_templates/profiles/{archetype}.md`

Project-level profiles always override package defaults. Mode-specific profiles
always override base profiles. This allows projects to customize agent behavior
without modifying the package.

**Layer 3 — Task context.** Assembled from six sources in order:

1. **Spec documents.** `requirements.md`, `design.md`, `test_spec.md`,
   `tasks.md` — formatted under markdown section headers. Missing files are
   logged as warnings but do not prevent the session.

2. **DB-backed findings.** Review findings, drift findings, and verification
   verdicts are queried from DuckDB and rendered as structured markdown
   (grouped by severity for reviews, tabular for verifications). This gives the
   agent visibility into prior quality assessments on this spec.

3. **Steering directives.** Project-wide guidance from `.agent-fox/steering.md`
   is included after spec files.

4. **Knowledge facts.** Relevant facts from the knowledge store are retrieved by
   the adaptive retrieval pipeline and injected as a bulleted list. See Section
   7.2 for how retrieval works.

5. **Prior group findings.** For task groups beyond group 1, active findings
   from earlier groups in the same spec (reviews, drift, verifications) are
   appended as accumulated context. This gives later groups visibility into
   issues found during earlier implementation work.

All external content passes through a sanitization layer that labels each source
and filters patterns that could constitute prompt injection attacks.

### 7.2 Adaptive Knowledge Retrieval

Before each session, the orchestrator queries four signals in parallel and fuses
their results to select the most relevant knowledge facts:

| Signal | Mechanism |
|---|---|
| **Keyword** | Matches task keywords against fact keywords and spec names; scored by overlap count plus recency bonus |
| **Vector** | Embeds the task description; queries `memory_embeddings` via cosine similarity |
| **Entity** | Traverses the entity graph from touched file paths via BFS; returns facts linked to related code entities |
| **Causal** | Traverses the `fact_causes` graph from same-spec facts; returns causally linked facts ordered by graph distance |

The four ranked lists are fused via **weighted Reciprocal Rank Fusion (RRF)**:
for each fact, a fused score is `sum(weight_i / (k + rank_i))` across all
signals where it appears. The per-signal weights are drawn from an **intent
profile** keyed by `(archetype, node_status)`:

| Archetype | Status | Keyword | Vector | Entity | Causal |
|---|---|---|---|---|---|
| coder | fresh | 1.0 | 0.8 | 1.5 | 1.0 |
| coder | retry | 0.8 | 0.6 | 1.0 | 2.0 |
| reviewer | * | 1.0 | 1.5 | 0.8 | 1.0 |
| verifier | * | 0.8 | 0.6 | 1.5 | 1.5 |

A coder retry session heavily weights the causal signal to surface facts about
what went wrong and why. A fresh coder session emphasizes entity relationships
to surface facts about the files it will touch. A reviewer emphasizes vector
similarity to find semantically related knowledge. A verifier emphasizes both
entity and causal signals to surface facts about the code being verified.

After fusion, the top facts are selected and formatted with **salience-based
token budgeting**: the top 20% by fused score receive full detail, the next 40%
receive one-line summaries, and the bottom 40% are included at full detail only
if the token budget allows. Facts are topologically sorted by causal precedence
(causes before effects) so the agent sees context in a logical order.

### 7.3 Task Prompt

The task prompt is short and archetype-specific:

- **Coder sessions** receive explicit instructions: implement task group N from
  specification X, update checkbox states in `tasks.md`, commit with conventional
  messages, and run quality gates before finalizing. For retry attempts, the
  previous error and active critical/major findings are prepended.

- **Review/verification sessions** receive a concise prompt that defers to the
  archetype profile for detailed instructions, since the profile fully specifies
  the review process and expected output format.

---

## 8. Agent Archetypes in Detail

The archetype registry defines four built-in entries. Two support **modes** —
named variants that override specific fields (injection point, tool allowlist,
model tier) while inheriting everything else.

### 8.1 Coder

**Role:** Primary implementation agent. Writes code and tests, runs quality
gates, commits with conventional messages.

**Execution model:** One task group per session. By convention, task group 1
writes failing tests from `test_spec.md` without implementing production code.
Subsequent groups implement code to make those tests pass. The Coder runs
quality checks, verifies its work against the requirements, and produces a
session summary artifact (`.agent-fox/session-summary.json`).

**Configuration:**
- Model tier: STANDARD (adaptive routing may escalate)
- Thinking mode: adaptive, 64K budget
- Max turns: 300
- Tool access: unrestricted
- Injection: none (assigned to task groups)

**Modes:** `fix` — used by the `agent-fox fix` pipeline for targeted fixes on
specific issues.

### 8.2 Reviewer

**Role:** Quality gate agent with four modes covering distinct review roles.
All modes produce structured JSON output and have read-only tool allowlists
(they cannot modify code).

**Pre-review mode** (`auto_pre`, before group 1):
- Examines spec quality: completeness, consistency, feasibility, testability,
  edge case coverage, security.
- Produces findings with severity levels.
- Has no shell access — works entirely from spec documents in context.
- If critical findings exceed a configured threshold, downstream coder tasks
  are blocked.

**Drift-review mode** (`auto_pre`, before group 1, parallel with pre-review):
- Validates spec assumptions against the actual codebase: referenced files
  exist, function signatures match, interfaces are consistent.
- Has read-only filesystem access (`ls`, `cat`, `git`, `grep`, `find`, `head`,
  `tail`, `wc`).
- Automatically skipped for specs that reference no existing code — there is
  nothing to detect drift against for brand-new specs.

**Audit-review mode** (`auto_mid`, after test-writing groups):
- Validates test quality against test spec contracts: coverage, assertion
  strength, precondition fidelity, edge case rigor, test independence.
- Produces per-entry verdicts: `PASS`, `WEAK`, `MISSING`, `MISALIGNED`.
- Has read-only access plus `uv` for test collection.
- Triggers a predecessor retry when tests are MISSING or MISALIGNED.

**Fix-review mode** (used by `agent-fox fix` and night-shift's fix pipeline):
- Broader tool access (`make`, `uv`) and ADVANCED model tier.
- Not injected automatically into coding session plans.

When both pre-review and drift-review are enabled, they execute in parallel
before the first coder group. Either can produce blocking findings independently.

**Multi-instance convergence.** The reviewer can run multiple parallel instances
on the same task. For pre-review and drift-review, convergence uses
**majority-gating** for critical findings: a critical finding counts toward
blocking only if it appears in at least a majority (⌈N/2⌉) of instances. For
audit-review, convergence uses **worst-verdict-wins**: if any instance reports
a test MISSING, the entry is MISSING regardless of other reports.

### 8.3 Verifier

**Role:** Post-implementation verification. Runs the test suite, checks each
requirement against acceptance criteria, produces per-requirement verdicts.

**Injection:** `auto_post` — added after the last coder group in every spec.

**Convergence:** Majority voting per requirement — a requirement is `PASS` if a
majority of instances report `PASS`.

**Retry trigger:** If verification fails, the orchestrator may re-run the
preceding coder session with the Verifier's verdicts injected as context.

**Configuration:**
- Model tier: STANDARD
- Max turns: 120
- Tool access: full (needs to run tests)
- `retry_predecessor`: true

### 8.4 Maintainer

**Role:** Internal archetype used exclusively by the night-shift daemon. Not
assignable to task groups in coding session plans.

**Modes:** `hunt` (read-only scan), `fix-triage` (read-only triage of single
issues), `extraction` (no shell access, knowledge extraction).

---

## 9. Worktree and Git Architecture

### 9.1 The Develop Branch

`develop` is the sole integration target. All session work merges into
`develop`; `main` is reserved for releases. Feature branches are local-only —
they are never pushed to the remote.

Before the first session, the orchestrator ensures `develop` exists locally. If
not, it is created from `origin/develop` (if available) or from the default
branch.

### 9.2 Isolation via Worktrees

Each session gets its own `git worktree` at a temporary directory path. Worktrees
share the same object store and ref namespace as the main repository but have
independent working trees and HEAD pointers. This makes it safe to run multiple
sessions concurrently — each session operates on its own branch, in its own
directory, without any shared mutable state.

The feature branch name follows the pattern `feature/{spec_name}/{task_group}`.
The worktree is created from the current state of `develop`, so each session
starts from the latest integrated work.

### 9.3 The Merge Lock

All merge operations are serialized by a two-layer lock:

- **Asyncio lock** — Prevents two concurrent sessions in the same process from
  merging simultaneously.
- **File lock** — Prevents multiple `agent-fox` processes targeting the same
  repository from merging simultaneously. Uses `O_CREAT | O_EXCL` for atomic
  creation; stale lock detection uses a rename-to-temp pattern safe against
  TOCTOU races.

The file lock has a configurable stale timeout (default: 5 minutes). If a lock
file is older than the timeout, it is considered abandoned and broken.

### 9.4 The Merge Agent

When a squash merge produces conflicts, a dedicated Claude session — the
**merge agent** — is spawned. The merge agent's prompt restricts it to resolving
the specific conflicts presented, without making any other changes. If the merge
agent also fails, the merge is aborted (`git reset --merge`) and the session
record carries a failure status so the orchestrator can retry or escalate.

### 9.5 Reset Operations

**Soft reset** resets failed, blocked, and in-progress task nodes to `pending`
without rolling back any code. Session history and attempt counters are
preserved. Appropriate after transient failures (network issues, API errors).

**Hard reset** resets tasks and rolls back `develop` to the commit before the
earliest affected task, undoing all code changes since that point. The knowledge
base is compacted during hard reset to deduplicate facts and resolve supersession
chains.

Both reset types can target a single spec or the entire plan.

---

## 10. Knowledge Harvest Pipeline

After every coder session completes (whether the session produced code or not),
the knowledge harvest pipeline processes the session transcript.

### 10.1 Transcript Construction

The primary transcript source is the agent trace JSONL — structured events
written by the SDK during the session. When debug tracing is active, the
harvester reconstructs the full conversation by replaying the events for the
session's node ID.

If no trace is available, the harvester falls back to a **structured metadata
block**: spec name, task group, node ID, and the commit diff (`git diff HEAD~1`
from the worktree). This fallback provides enough context for basic fact
extraction even without full conversational history.

Transcripts shorter than 2,000 characters are skipped — below this threshold
the extraction overhead far exceeds the expected value.

### 10.2 Fact Extraction

The transcript is submitted to an LLM (the configured `memory_extraction_model`,
typically a SIMPLE-tier model) with a structured extraction prompt. The LLM
identifies learnings and classifies each as one of six categories:

| Category | Description |
|---|---|
| `gotcha` | Surprising non-obvious behavior that tripped the agent |
| `pattern` | A recurring approach that works well |
| `decision` | An architectural or design choice and its rationale |
| `convention` | A coding standard or project norm |
| `anti-pattern` | Something tried that should be avoided |
| `fragile_area` | A part of the codebase that is known to be brittle |

Each extracted fact carries: content (1-2 sentence description), category,
confidence (0.0–1.0), and 2-5 keywords. Facts shorter than 50 characters are
filtered out before storage.

Review archetypes (`reviewer`, `verifier`) skip this LLM extraction step — their
outputs are structured JSON findings that are already persisted by the review
persistence layer. Running LLM extraction on review output would add ~18K tokens
of overhead while reliably returning zero actionable facts.

### 10.3 Lifecycle Management

After extraction, new facts pass through three lifecycle stages:

**Embedding-based deduplication.** Each new fact's content is embedded and
compared against all existing active facts via cosine similarity. If an existing
fact's embedding is within a configurable threshold (default: 0.92 similarity),
the existing fact is superseded by the new one — treating the new fact as an
updated version of semantically equivalent knowledge.

**Contradiction detection.** Surviving new facts are checked against the existing
corpus. Candidate pairs are identified by embedding proximity (facts similar
enough to potentially contradict each other), then sent to an LLM in batches for
classification. When a contradiction is confirmed, the older fact is superseded
by the newer one with the LLM's reasoning recorded.

**Confidence decay.** Every fact's effective confidence decays exponentially over
time: `effective_confidence = stored_confidence × 0.5^(age_days / half_life_days)`.
At a 90-day half-life, a fact with 0.8 confidence becomes effectively 0.4
confident after 90 days. Facts whose effective confidence falls below a floor
(default: 0.1) are auto-superseded. This mirrors how real codebases evolve —
conventions established months ago may no longer apply.

### 10.4 Causal Link Extraction

Once the knowledge store has at least 5 active facts, the harvester performs a
second LLM pass to extract causal relationships. The prompt includes all new
facts plus a context-bounded sample of prior facts (ranked by embedding
similarity to new facts when the full corpus exceeds a configurable limit).

The LLM identifies directed "led to" relationships between facts. Confirmed links
are stored as edges in the `fact_causes` table with referential integrity — both
endpoints must exist in `memory_facts`.

Causal links power the causal retrieval signal and enable temporal queries
("what led to this decision?").

### 10.5 Post-Harvest Rendering

After all lifecycle management completes:

- `docs/memory.md` is regenerated from the current active fact set. This file is
  git-tracked and provides a human-readable snapshot of accumulated knowledge.
- The orchestrator emits a `harvest.complete` audit event with fact count,
  categories, causal link count, dedup count, and contradiction count.

At sync barriers and at end-of-run, **knowledge consolidation** runs for
completed specs — an LLM-assisted process that finds cross-spec causal
connections between facts from different specifications.

---

## 11. Sync Barriers

At configurable intervals (every N completed tasks), the orchestrator pauses
dispatch and runs a synchronization sequence:

1. **Develop sync.** Pull remote changes into `develop`, reconciling divergence
   using the same merge strategy as harvest.

2. **Worktree verification.** Check for orphaned worktrees (left by crashed
   sessions) and clean them up.

3. **Hot-load discovery.** Scan `.agent-fox/specs/` for new specs that weren't
   present when the plan was built. Each candidate passes four gates: git-tracked
   on develop, all five artifacts non-empty, passes static lint, not fully
   implemented. Admitted specs are merged into the live graph.

4. **Knowledge ingestion.** Run consolidation for recently completed specs.

5. **Config reload.** Re-read `config.toml` and apply changes (new cost limits,
   archetype settings). The `parallel` field is immutable and cannot be changed
   at runtime. All other fields take effect immediately.

6. **Hook execution.** Run user-configured sync hooks.

Sync barriers are periodic rather than continuous to limit overhead.

---

## 12. End-of-Run Cleanup

When the orchestrator's main loop terminates (all tasks complete, circuit
breaker trips, or SIGINT received):

1. **Persist final node statuses** to DuckDB so the state accurately reflects
   actual progress.

2. **Clean up transient audit reports** for fully-completed specs. Per-session
   audit JSONL files are deleted once a spec is complete.

3. **Run end-of-run knowledge consolidation** for any specs that completed since
   the last sync barrier.

4. **Render `docs/memory.md`** to reflect all facts extracted during the run.

5. **Post issue summaries** (if a platform is configured) for newly completed
   specs — creating or updating GitHub issues with a summary of what was
   implemented.

6. **Mark the run record complete** in DuckDB with the final status and
   timestamp.

7. **Emit `run.complete`** audit event with total sessions, total cost, duration,
   and final status.

---

## 13. Information Flow Summary

```
Human Intent
    │
    ▼
Spec Artifacts (.agent-fox/specs/NN_name/)
    │  prd.md, requirements.md, design.md, test_spec.md, tasks.md
    ▼
Planner  [deterministic, zero LLM]
    │  Static validation → Graph construction → Topo sort
    ▼
Task Graph (DuckDB: plan_nodes + plan_edges + plan_meta)
    │
    ▼
Orchestrator  [deterministic dispatch loop, zero LLM]
    │
    ├─ Ready tasks → dispatch to sessions
    │
    │   ┌─── Session Lifecycle ──────────────────────────────────────┐
    │   │                                                            │
    │   │  Worktree (feature/{spec}/{group})                         │
    │   │      ↓                                                     │
    │   │  System prompt [agent.md + archetype profile + context]    │
    │   │      ↓                                                     │
    │   │  Knowledge retrieval [keyword + vector + entity + causal]  │
    │   │      ↓                                                     │
    │   │  Claude Agent SDK ──→ LLM inference                        │
    │   │      ↓                                                     │
    │   │  Session output (code, tests, commits, JSON findings)      │
    │   │      ↓                                                     │
    │   │  Harvest: squash merge → develop                           │
    │   │      ↓                                                     │
    │   │  Assess: parse findings / extract facts / embed / dedup    │
    │   │                                                            │
    │   └────────────────────────────────────────────────────────────┘
    │
    │   ┌─── Knowledge Store (DuckDB) ──────────────────────────────┐
    │   │                                                            │
    │   │  memory_facts ──── memory_embeddings ──── fact_causes      │
    │   │  review_findings ── verification_results ─ drift_findings  │
    │   │  session_outcomes ─ audit_events ────────── run_records    │
    │   │                                                            │
    │   └────────────────────────────────────────────────────────────┘
    │
    └─ Sync barriers: pull develop, hot-load specs, consolidate knowledge
```

Each session's outputs feed back into the knowledge store, which feeds forward
into the context of the next session for the same spec (or for any future
session where the facts are relevant). Over many sessions, the system
accumulates institutional memory that lets later sessions benefit from the
discoveries of earlier ones — without any of the context window exhaustion that
would result from keeping all prior sessions in one continuous conversation.

---

## 14. Design Principles in Action

**Deterministic planning, stochastic execution.** The graph is fully determined
by the specs before any LLM is invoked. The LLM work happens inside sessions;
the orchestrator coordinates but never improvises.

**Isolation by default.** Every session runs in its own worktree on its own
branch. Multiple sessions share no mutable workspace state. Integration happens
through a serializing merge lock, not through shared files.

**Separation of concerns through archetypes.** The Coder writes code; the
Reviewer judges quality; the Verifier checks correctness; the Maintainer handles
maintenance. Their tool allowlists enforce the separation — Reviewers cannot
write code; Verifiers can run tests; Coders have full access.

**Knowledge compounds over time.** Facts extracted from session transcripts are
stored, embedded, deduplicated, and linked causally. Each subsequent session
receives a curated, ranked selection of the most relevant accumulated knowledge.
The knowledge store grows richer with every session while lifecycle management
(dedup, contradiction detection, decay) prevents it from becoming stale or noisy.

**Graceful degradation everywhere.** If embedding generation fails, facts are
stored without embeddings (keyword retrieval still works). If contradiction
detection fails, facts are ingested unchecked. If DuckDB is locked, the system
falls back to JSONL. If the merge agent fails, the session is marked failed and
retried. The knowledge system never blocks the coding lifecycle.

**Specs are contracts.** Every generated artifact traces back to a spec
artifact. Agents that deviate from specs are caught by review agents before
their code lands. The human judgment is front-loaded in the spec; the machine
executes without improvisation.
