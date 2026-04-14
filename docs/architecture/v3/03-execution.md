# Chapter 03 — Archetypes, Planning & Execution

## The Four Archetypes

v2 had seven archetypes (Coder, Skeptic, Oracle, Auditor, Verifier, Cartographer, Librarian). v3 collapses these to four, each with a clear separation of power.

### Coder

**What it does:** Implements code changes according to a task group description, guided by the PRD and optional design document. Writes code, runs tests, installs dependencies, modifies configuration.

**Permissions:** Read-write filesystem within the worktree. Shell execution. Network access (for package managers). Cannot modify spec files.

**Harness:** Typically `claude-code` (full tool access) or any harness that supports file editing and shell.

**Model tier:** Adaptive routing by default. Simple tier for straightforward tasks; standard for typical work; advanced for complex or cross-cutting changes. The routing system starts with heuristics and graduates to a trained classifier as historical data accumulates.

**Expected output:** Commits on the feature branch, a session summary (what was attempted, what succeeded, what was left incomplete), and a list of files created or modified. If the harness supports `structured_output`, the summary is extracted as JSON; otherwise, it is parsed from the final assistant message.

### Reviewer

**What it does:** Replaces the Skeptic, Oracle, and Auditor from v2 as a single configurable review archetype. A Reviewer session receives a *review mode* that determines its focus:

- **Pre-review** (Skeptic mode): Examines the spec before any coding. Checks for ambiguity, contradictions, missing edge cases, unrealistic scope. Produces findings that the Coder receives as context.
- **Drift-review** (Oracle mode): Compares the spec's design document against the existing codebase. Identifies where the current code diverges from the specified architecture — verifying function signatures, checking import structures, and confirming that specified modules exist. Skipped when the spec references no existing files.
- **Audit-review** (Auditor mode): Validates that tests written by the Coder cover the test spec contracts. Requires `test_spec.md` to be present.

The Reviewer cannot modify files. Its permission model is mode-specific:

- **Pre-review:** Read-only file access, no shell. Pre-review is a reading task — examining spec prose for logical issues. Shell access would not meaningfully improve it.
- **Drift-review and audit-review:** Read-only file access plus read-only shell execution in an ephemeral sandbox. This allows the Reviewer to run analysis commands — grep for function signatures, parse import graphs, run `pytest --collect-only` to enumerate test cases, check coverage reports — that provide empirical grounding for its findings. All shell writes go to an ephemeral overlay and are discarded. The codebase is never modified.

The safety property is preserved across all modes: a compromised or hallucinating Reviewer cannot damage the codebase. The difference from the Verifier is scope of intent, not security boundary — both run in ephemeral sandboxes with discarded writes.

**Harness:** `ClaudeCodeHarness` with a mode-specific permission callback. Pre-review: read-only file tools (no writes, no shell). Drift-review and audit-review: read-only file tools plus shell execution (ephemeral writes discarded). The Reviewer can read source files and spec artifacts directly. The `structured_output` capability ensures findings are parsed as typed JSON.

Audit-review validates test coverage by analyzing test files against test_spec.md contracts — parsing test file structure, checking function names against contract IDs, and running `pytest --collect-only` to enumerate test cases without executing them. It does not execute the test suite — that is the Verifier's responsibility.

**Multi-instance convergence:** Multiple Reviewer instances can run on the same input. Their findings are merged per mode:

| Review Mode | Convergence Strategy | Rationale |
|------------|---------------------|-----------|
| Pre-review | Worst-verdict-wins | Conservative — a single reviewer spotting ambiguity is enough to flag it |
| Drift-review | Worst-verdict-wins | Same rationale — any detected drift is worth investigating |
| Audit-review | Majority-voting | Coverage assessment benefits from consensus — one reviewer may miss a valid test mapping |

**Worst-verdict-wins** works as follows: all findings from all instances are unioned into a single list. If multiple instances report findings about the same aspect (matched by category and affected artifact), the finding with the highest severity is kept (`critical` > `major` > `minor` > `info`). Findings about different aspects are all retained — the union ensures nothing is lost. Each finding is annotated with its **agreement ratio** — the fraction of instances that reported it (e.g., 1/3 if only one of three instances flagged it). The agreement ratio is metadata, not a filter — low-agreement findings are still surfaced, but the Coder's context includes the ratio so it can calibrate its response. A finding reported by 3/3 instances warrants more attention than one reported by 1/3.

**Majority-voting** for audit-review: each instance produces a pass/fail verdict per test-spec contract. A contract is considered "covered" if a majority of instances (>50%) judge it covered. This smooths over individual reviewer hallucinations.

The instance count is configurable per review mode (default: 1 for all modes, via `archetype.reviewer.instance_count`). When instance count is 1, convergence is a no-op — the single instance's findings are used directly.

**Correlated error risk:** Multi-instance convergence provides diminishing returns when all instances use the same model, temperature, and system prompt. Errors from a shared model tend to be correlated — all instances are likely to miss the same subtle issue or hallucinate the same false positive. The agreement ratio mitigates the false-positive problem for worst-verdict-wins (a finding reported by 1/N instances is flagged as low-agreement). For majority-voting, correlated errors are harder to detect. Potential mitigations — temperature variation, prompt variation, or model diversity — are future extensions, not v3 requirements. In practice, the primary value of multi-instance convergence is catching high-variance errors (where the model is uncertain and different samples diverge), not systematic blind spots.

**Verifier multi-instance:** The Verifier does not support multi-instance convergence. Verification is empirical (run tests, observe results), not subjective — running the same test suite twice produces the same verdicts. A single Verifier instance is always sufficient.

**Model tier:** Defaults to standard. v2 used advanced for all review agents; v3 defaults to standard because standard-tier models have improved sufficiently for careful reading tasks since v2. Per-mode overrides are available in archetype configuration.

### Verifier

**What it does:** Runs the test suite after coding and confirms that each requirement (if `requirements.md` exists) or success criterion (from `prd.md`) is met by the implementation. The Verifier evaluates **all requirements** in `requirements.md` for the spec, not just those relevant to the current task group — this catches regressions where fixing one thing breaks another. It produces a pass/fail verdict per requirement and an overall assessment. Verdict mapping: the Verifier parses test results and maps them to requirements by matching test names and descriptions against requirement IDs and keywords. If a requirement cannot be mapped to any test, it receives a verdict of `untested` (distinct from `fail`).

**Permissions:** Read-only filesystem. Shell execution (to run tests). No write access. No network access beyond localhost.

**Why it stays separate from Reviewer:** Verification is fundamentally different from review. Review is analytical (read and critique). Verification is empirical (run tests and observe). They need different tool permissions, different prompts, and different convergence strategies.

**Model tier:** Standard. Verification is structured and well-defined.

### Maintainer

**What it does:** Replaces the Cartographer and Librarian from v2. The Maintainer is the archetype for analysis and knowledge — finding problems and extracting learning. It does not implement fixes; that is the Coder's job.

Two modes:
- **Hunt mode** (night-shift): Scans the codebase using static analysis tools, interprets findings via LLM, consolidates with the critic, deduplicates against known issues. Produces structured work items.
- **Knowledge extraction** (spec pipeline): After a Coder session completes, a Maintainer session extracts facts (causal relationships, architectural decisions, failure patterns) from the session transcript and stores them in the knowledge system.

The night-shift fix pipeline uses the Coder archetype, not the Maintainer (see ch 04, Fix Pipeline). v2 conflated "finding problems" with "fixing problems" under a single role. v3 separates them: the Maintainer finds and analyzes, the Coder implements. This keeps the Maintainer's two modes coherent — both are read-only analysis producing structured output.

**Permissions:** Hunt mode has read-only filesystem access with shell execution (to run linters, static analysis tools, and test collection commands). Knowledge extraction is read-only with respect to the worktree — it reads transcripts via the orchestrator and writes facts to the knowledge store via the orchestrator's API, not via filesystem writes inside the sandbox.

### Archetype Permissions Summary

| Archetype | Filesystem | Shell | Network | Tool Restrictions |
|-----------|-----------|-------|---------|-------------------|
| Coder | Read-write (worktree) | Yes | Gated (proxy-only) | Cannot modify spec files |
| Reviewer (pre-review) | Read-only | No | Gated (API-only) | Read-only file tools only |
| Reviewer (drift/audit) | Read-only (ephemeral writes discarded) | Yes (analysis commands) | Gated (API-only) | Read-only file tools + shell |
| Verifier | Read-only (ephemeral writes discarded) | Yes (test execution) | Localhost only | No file-write tools |
| Maintainer (hunt) | Read-only | Yes (analysis tools) | Blocked | Read-only + shell |
| Maintainer (extraction) | N/A (reads via orchestrator) | No | None | Knowledge store write only |

### Archetype Profiles

The four archetypes define *what* an agent can do (permissions, tools, sandbox). **Archetype profiles** define *how* it behaves — the system prompt template that shapes the agent's approach, focus areas, and output format. Profiles make prompt construction transparent, inspectable, and customizable.

#### Why profiles exist

Without profiles, archetype behavior is invisible. The engine constructs system prompts programmatically. When an agent misbehaves, the first diagnostic question — "what was it told?" — requires reading Python source. There is no place for a team to say "our Reviewers should always check accessibility" or "our Coders must run `make lint` before committing." `CLAUDE.md` is project-wide and role-agnostic; it cannot differentiate between archetypes.

This is the practical takeaway from OpenClaw's SOUL.md concept: an agent's behavior should be defined in a readable, editable file — not buried in code. SOUL.md defines a complete agent identity (personality, rules, working state) in a single document. agent-fox adapts the idea for a multi-archetype system: each archetype gets its own profile, and the engine merges it with project context and task context to build the full prompt.

#### Prompt layering

The system prompt for each session is assembled from three layers:

| Layer | Source | Scope | Who writes it |
|-------|--------|-------|---------------|
| Project context | `CLAUDE.md` | All agents, all sessions | Human (project-wide) |
| Archetype profile | `.agent-fox/profiles/<archetype>.md` | All sessions of this archetype | Human or package default (role-specific) |
| Task context | Spec artifacts + knowledge injection + findings | One session | Engine (assembled per-task) |

The engine prepends the project context, injects the archetype profile, then appends the task-specific context. The three layers are concatenated, not merged — each is a distinct block in the prompt, clearly delineated.

#### Profile structure

Profiles live in `.agent-fox/profiles/`:

```
.agent-fox/profiles/
  coder.md
  reviewer.md
  verifier.md
  maintainer.md
```

Each profile contains four sections:

- **Identity** — What this archetype is and does. One paragraph. Defines the agent's role in the pipeline. Package defaults ship with this section filled in; project overrides rarely need to change it.
- **Rules** — Hard behavioral constraints. "Never modify spec files." "Commit each logical change separately." "Do not refactor code outside the task scope." Package defaults define the invariants. Project overrides append additional rules.
- **Focus areas** — What to pay attention to. This is where customization matters most. A Reviewer at a fintech company focuses on transaction integrity and audit trails. A Reviewer at a game studio focuses on frame budget and memory allocations. Package defaults are intentionally generic; teams add domain-specific focus here.
- **Output format** — Expected structure of the session's output (files changed, test results, findings). Package defaults define the schema. Projects can extend it with additional fields.

#### Override semantics

The engine ships with **default profiles** embedded in the `agent_fox.harness` package. These are the baseline — they work without any project configuration. If a file exists at `.agent-fox/profiles/<archetype>.md`, the engine uses the project file instead of the package default.

The override is **full replacement**, not merge. If a team creates a `coder.md` profile, they are responsible for the complete profile — including the Identity and Rules sections. This avoids the complexity of section-level merging and makes the effective prompt fully visible in one file. To start from the defaults, `af init --profiles` copies the package defaults into the project directory for editing.

**Hard constraints are not overridable via profiles.** A profile cannot grant a Reviewer write access or give a Verifier network access. Permissions are enforced by the permission callback and sandbox profile (ch 02), not by the prompt. A malicious or poorly written profile can make an agent behave suboptimally, but it cannot make an agent violate its security boundary.

#### Archetype extensibility

The four archetypes are the shipped set. But the profile mechanism supports team-defined archetypes beyond the four. A team can:

1. Create a profile at `.agent-fox/profiles/deployer.md`.
2. Define a permission preset in project config (`archetype.deployer.permissions = "coder"` — reuse an existing permission profile).
3. Use it in task group tags: `[archetype: deployer]`.

The engine loads the profile, maps the permission preset to a sandbox profile and permission callback, and runs the session. The custom archetype's prompt comes from the profile; its security boundary comes from the permission preset.

This is an escape hatch, not a primary workflow. The four built-in archetypes cover the spec-driven execution loop. Two common gaps and how the escape hatch addresses them:

- **Deployment.** The pipeline produces merged code, not deployments. Teams that need deploy-and-verify-in-staging can define a `deployer` custom archetype with Coder permissions and a profile focused on deployment scripts and health checks.
- **Research/exploration.** Tasks that require investigating multiple approaches before committing ("evaluate library X vs Y") don't fit the Coder model. A `researcher` custom archetype with Reviewer permissions (read-only + shell) can explore, benchmark, and produce structured recommendations that subsequent Coder groups act on. Alternatively, a task group tagged `[archetype: reviewer]` with a research-focused description achieves the same thing within the built-in set.

## Planning

The planner is unchanged in its core algorithm (reproducible DAG construction, topological sort, Kahn's algorithm with min-heap tie-breaking) but simplified in its interface.

### Graph Construction

Graph construction proceeds in four phases:

**Phase 1 — Base nodes.** Each task group in each spec becomes a node. Intra-spec edges connect groups sequentially: group N depends on group N-1 within the same spec. A spec with 5 task groups produces 5 nodes and 4 intra-spec edges. A spec with 0 task groups is rejected by validation (`TASK-001`) before reaching the planner — this case cannot occur in a valid plan.

**Phase 2 — Archetype injection.** Synthetic nodes are inserted into the graph for non-Coder archetypes:

- **Pre-execution:** Reviewer (pre-review mode). Injected before the first Coder group if enabled.
- **Pre-execution (conditional):** Reviewer (drift-review mode). Injected before the first Coder group *only if* `design.md` references files already present in the repository (i.e., the spec modifies existing code, not greenfield).
- **Mid-execution:** Reviewer (audit-review mode). Injected after the last Coder group whose task description contains test-related keywords (`test`, `spec`, `coverage`, `verify`), or after the last Coder group if no test-specific group is identified. Validates coverage against `test_spec.md`. Skipped if `test_spec.md` is absent or if audit-review is disabled via `archetype.reviewer.audit_review_enabled`.
- **Post-execution:** Verifier. Injected after the last Coder group.
- **Post-Coder:** Maintainer (knowledge extraction mode). Injected after each Coder group to extract knowledge from that session's transcript. Extraction runs asynchronously — it does not block downstream Coder nodes. Multiple extraction nodes may run concurrently.

**Phase 3 — Tag overrides.** `[archetype: X]` and `[model: Y]` tags on task groups override the default archetype and model tier for that node. A tag changes the archetype of an existing base node — it does not create or suppress synthetic nodes. A group tagged `[archetype: verifier]` becomes a Verifier node at that position in the graph. The synthetic post-execution Verifier (injected by Phase 2) still runs after the last Coder group — it is not suppressed by the tag. This means a spec can have both an inline Verifier (author-placed) and a post-execution Verifier (system-injected). This is intentional: the inline Verifier may test a specific intermediate state, while the post-execution Verifier validates the complete spec.

**Phase 4 — Cross-spec edges.** Dependency declarations from each spec's `prd.md` are resolved into graph edges between the specified groups. A dependency from spec A group 3 to spec B group 1 creates an edge: B.1 depends on A.3. If a dependency specifies `From Group = 0` (sentinel), the edge is deferred — the planner rejects the plan until the sentinel is resolved.

### Execution Order

Reproducible topological sort. Same inputs → same plan → same order.

When multiple nodes have satisfied dependencies simultaneously, the min-heap uses a composite sort key: **(spec numeric prefix ascending, group number ascending)**. This produces a deterministic interleaved order — lower-numbered specs are preferred, and within a spec, lower-numbered groups go first. Synthetic nodes (injected by Phase 2) sort immediately before the group they precede.

**Note on reproducibility scope.** The plan is a deterministic function of its *complete* input set: spec content, repository file state at planning time, and (once trained) the routing classifier's model weights. All inputs are captured in the plan's content hash. Three consequences:

- **Repo state matters.** Conditional injection (drift-review) depends on whether `design.md` references existing files. Different repos → different plans from the same specs. This is intentional — the plan adapts to the project, not just the spec.
- **Wording matters.** Archetype injection and model routing use keyword matching on task descriptions. Rewording a task ("add tests" vs "write verification") can shift audit-review placement or model tier. Spec authors who want explicit control should use `[archetype: X]` and `[model: Y]` tags.
- **History matters.** Adaptive routing transitions from heuristic rules to a trained classifier after 50 completed sessions. The same spec run early vs late in a project may get different model tiers. The content hash includes the classifier version to preserve auditability.

The correct mental model is **reproducible given captured inputs**, not **identical across environments**. The plan is always inspectable and the routing decision for every node is logged with its reasoning.

### Plan Persistence

Plans serialize to `.agent-fox/plan.json`. The format is forward-compatible (unknown fields ignored, missing fields get defaults). The plan includes a content hash of the input specs so the engine can detect when specs have changed since the plan was built.

**Content hash scope:** The hash covers the concatenated contents of all five spec artifacts for every spec in the plan. Any byte-level change to any artifact triggers a hash mismatch.

**Plan schema sketch:** Each plan node records: spec name, group number, archetype, model tier, status, dependencies (list of node IDs), and session history (list of session IDs with outcomes). The plan also records: content hash, creation timestamp, and graph-level metadata (critical path length, estimated cost).

**Node statuses and transitions:**

| Status | Meaning | Transitions To |
|--------|---------|---------------|
| `pending` | Not yet started, dependencies may or may not be satisfied | `in_progress` (when dispatched) |
| `in_progress` | Session is running | `completed`, `failed` (after assess/decide) |
| `completed` | Session succeeded and branch merged | Terminal |
| `failed` | Session exhausted all retries at all tiers | `pending` (on re-plan or manual reset only) |
| `blocked` | Upstream failure or manual skip — cannot proceed | `pending` (on re-plan or manual reset only) |
| `cost-blocked` | Per-spec cost ceiling exceeded | `pending` (if ceiling raised and `af resume` run) |
| `merge-blocked` | Merge cascade failed — requires human conflict resolution | `completed` (after manual resolution and `af resume`) |

A node transitions to `in_progress` when the engine dispatches its session. It transitions out of `in_progress` only after the Assess and Decide phases complete. A node cannot regress from `completed` except via explicit `af plan --reset` or re-plan after content hash mismatch.

**Affected groups on re-plan:** When the user re-plans after a content hash mismatch, a group is considered "affected" if its task description in `tasks.md` changed, its archetype or model tag changed, or a new dependency edge targets it. Affected groups reset to `pending`. Unaffected groups retain their completion state. Groups that depend on an affected group are also reset to `pending` (transitive reset) — downstream work built on changed upstream assumptions is not trustworthy.

**Manual plan reset:** `af plan --reset` discards all completion state and rebuilds the plan from scratch. `af plan --reset-spec <name>` resets all groups for a specific spec while preserving completion state for other specs. These are explicit operator commands, not automatic behaviors.

### Implicit Planning

`af run` builds the plan automatically before dispatching. The user never has to run `af plan` as a separate step. The engine's planning behavior:

1. If no `plan.json` exists, build the plan from specs, persist it, and proceed to execution.
2. If `plan.json` exists and its content hash matches the current specs, resume from the persisted plan (skipping completed groups).
3. If `plan.json` exists but the content hash is stale (specs changed), prompt the user: re-plan (which resets completion state for affected groups) or abort.

`af plan` exists as a standalone inspection command — it builds and persists the plan without executing. This is useful for previewing the DAG, debugging graph construction, or feeding `plan.json` into visualization tools.

## Session Lifecycle

Each node in the plan is executed as a session. The session lifecycle has five phases:

### 1. Prepare

Assemble the context for this session:
- **Spec context:** PRD, design doc (if present), relevant portions of requirements and test spec.
- **Knowledge context:** Facts from the knowledge store that are relevant to this task (semantic search by task description, capped at `knowledge.injection_token_budget`, default 2000 tokens). Injected as structured context, not as raw dump.
- **Prior findings:** Findings from Reviewer sessions that precede this node in the graph.
- **Steering:** Archetype-specific instructions (tool permissions, output format expectations, review focus).

Context assembly uses the prompt cache optimization from the harness analysis: the spec context (which is stable across all sessions for the same spec) forms a cacheable prefix. Task-specific context (findings, knowledge, task body) forms the variable suffix.

**Pre-flight check (Scope Guard):** Before launching the session, check whether the task group's expected deliverables — files annotated with this group's number via `[group N]` tags in `design.md` File Layout (see ch 01 §Use explicit file paths) — already exist in the worktree. If `design.md` has no group annotations, the pre-flight check is skipped for that group. If all expected files exist and all quality checks pass (tests, quality gate), the group is assessed as `skip` — no session is launched. This catches cases where an upstream group or a prior attempt already produced the deliverables. The pre-flight check runs after context assembly because it needs the list of expected files from the spec context.

### 2. Execute

The harness starts the agent session. The orchestrator streams events and:
- Records the full transcript for audit and knowledge extraction.
- Monitors turn count against the budget. At 90% of the budget, the orchestrator injects a wind-down message instructing the agent to commit current progress and summarize remaining work. At 100%, the session is stopped.
- Watches for the PreCompact hook (if supported by the harness) to inject critical context before compaction. Critical context, in priority order: (1) the task group description, (2) unresolved findings from upstream Reviewer sessions, (3) the requirements section relevant to the current group.
- Checkpoints the session state periodically (every 20 turns or every 5 minutes, whichever comes first; both intervals configurable via `execution.checkpoint_turn_interval` and `execution.checkpoint_time_interval`). A checkpoint captures: (1) the full transcript up to the current turn, (2) the node's in-progress status and turn count, (3) the last git commit SHA on the worktree branch. Checkpoints are stored in `.agent-fox/checkpoints/<node-id>.json` and cleaned up on session completion. On resume: if the harness supports the `resume` capability, the orchestrator passes the checkpoint transcript to the harness for native continuation; otherwise, it starts a fresh session with the transcript prepended as a "prior attempt" section, resuming work from the last committed state on the worktree branch.

### 3. Harvest

After the session completes, harvest the results:
- For Coder: collect the git diff, test results, and any structured output.
- For Reviewer: collect structured findings (ID, severity, category, description).
- For Verifier: collect pass/fail verdicts per requirement.
- For Maintainer: collect extracted facts, issues discovered, or fix results.

Tool output summarization runs here: known patterns (pytest output, linter output, git diff stats) are parsed into structured summaries that are more token-efficient than raw output. The raw output is still recorded in the transcript for audit.

### 4. Assess

Determine the outcome. Assess is a pure classification — it does not make advancement decisions:

- **Success:** Session completed within budget, and output passes all quality checks. Quality checks: (a) the session produced at least one commit, (b) if the spec has `test_spec.md`, the test suite passes on the feature branch, (c) if an optional quality gate command is configured (`execution.quality_gate_command`), it exits 0.
- **Partial:** Session produced commits but some issues remain. Specifically: (a) it committed code but some test failures remain, (b) it addressed some but not all Reviewer findings, or (c) it completed some subtasks but ran out of turns before finishing all of them. A session that completes within budget but fails quality checks is assessed as partial, not success.
- **Failure:** Session exceeded budget with no useful output, crashed, was killed, or all tests fail (regression from baseline). **Baseline** is the test pass rate on the `develop` branch, captured by the engine before dispatching the first session and stored in `plan.json` as `baseline_test_pass_rate`. The engine runs the quality gate command (`execution.quality_gate_command`) or the project's test suite against the `develop` branch to establish this rate. If no quality gate command is configured and no test suite is detected, the baseline is recorded as `null` and the regression check is skipped. A session is a regression if its test pass rate is strictly lower than baseline.
- **Skip:** All expected deliverables already exist and quality checks pass. Set by the pre-flight check in Prepare — no session was launched. Skip is not an assessment of session output; it is an assessment that no session was needed.

**Stub validation (task group 1):** By convention, task group 1 writes failing tests from `test_spec.md`. After a group-1 Coder session, the Assess phase scans modified files for implementation code beyond test stubs and fixture setup. If real implementations are detected where only stubs were expected, the session is assessed as partial with a finding: `scope-violation: group 1 produced implementation code, not just test stubs`. This prevents a single session from collapsing the test-first workflow. Stub validation applies only to group 1 — spec authors who place test writing in a different group should use appropriate subtask descriptions to communicate intent, but no automated stub check runs for other groups.

### 5. Decide

Based on the assessment:
- **Success → advance.** Mark the node complete. Merge the worktree branch into develop (via the merge cascade). Unblock downstream nodes.
- **Skip → advance.** Mark the node complete. No merge needed (no changes). Unblock downstream nodes. Record the skip in session metrics — a high skip rate across runs indicates specs that are already satisfied and may need review.
- **Partial → conditional advance.** The Decide phase examines the unresolved findings from the Assess output. The threshold is: no critical findings **and** no more than 2 major findings (configurable as `execution.partial_advance_threshold`). Minor and info findings are always carried forward as context for downstream nodes without blocking advancement. If the threshold is exceeded (any critical, or more than `partial_advance_threshold` majors), treat as failure and enter the retry sequence.
- **Failure → retry or escalate.** The retry sequence at each tier: (1) if the harness supports `resume`, resume from checkpoint with the error context injected as a new user message; otherwise, start a fresh session with the error context prepended as a "prior attempt" section. (2) If that fails, one more fresh attempt at the same tier. If both retries at the current tier fail, escalate to the next tier up. Retry counts per tier are configurable (default: 2 attempts per tier, via `execution.retry_attempts_per_tier`). If the advanced tier is exhausted, mark the node as `blocked` and halt downstream work. There is no tier ceiling — any task can escalate to advanced. The `[model: X]` tag override sets both the starting tier and the ceiling for that task.

  **Resume capability:** All archetypes use `ClaudeCodeHarness`, which supports `resume`. On retry, the session resumes from checkpoint with error context injected. Maintainer extraction failure does not trigger the retry sequence at all — extraction is best-effort (see ch 04, Knowledge Extraction).

## Parallel Execution

The engine dispatches sessions in parallel up to a configured concurrency limit. The dispatch strategy:

1. Scan the execution order for nodes whose dependencies are all satisfied.
2. Among eligible nodes, filter out those that conflict on predicted file modifications (from file impact analysis).
3. Dispatch non-conflicting nodes in parallel, up to the pool limit.
4. When a session completes, re-scan for newly eligible nodes.

Each parallel session runs in its own worktree on its own branch. There is no shared mutable state between concurrent sessions.

### File Impact Prediction

To detect potential merge conflicts before they happen, the engine predicts which files each task group will modify. The prediction uses two sources, in priority order:

1. **Explicit file references in `design.md`** — If the spec's design document names specific files or directories (e.g., "Create `src/auth/middleware.py`", "Modify `tests/conftest.py`"), these are extracted as the predicted impact set. This is the primary signal and covers most cases for well-written specs.
2. **Task description heuristics** — If no explicit file references are found, the engine scans the task group description and subtasks for path-like strings (containing `/` or `.py`/`.ts`/etc. extensions) and directory references.

Two task groups **conflict** if their predicted impact sets share any file path. Conflicting groups are never dispatched concurrently — one waits for the other to complete and merge before starting. If neither group has a predictable impact set (no file references found), they are treated as non-conflicting. This is a conservative-enough default: groups with vague descriptions are typically in different specs working on different subsystems. If this assumption is wrong, the merge cascade handles the resulting conflict.

File impact prediction is best-effort. It reduces merge conflicts but does not eliminate them — agents may modify files not mentioned in the spec. The merge cascade (below) is the safety net.

## Merge Cascade

When a session completes successfully, its branch is integrated into `develop` under a **global serializing lock** — only one merge operation runs at a time across the entire plan execution. This lock serializes merge operations but does not block parallel Coder sessions. Sessions that complete while the lock is held wait in a FIFO queue until the lock is released. The cascade tries strategies in order:

1. **Fast-forward** — If develop hasn't moved since the worktree branched, the branch tip becomes develop. Zero-cost, preferred.
2. **Rebase** — If develop has moved but there are no textual conflicts, rebase the branch onto develop and fast-forward.
3. **Merge commit** — If rebase fails (textual conflicts), attempt a three-way merge. This succeeds when git's built-in merge strategies can resolve the conflicts automatically (e.g., changes in different regions of the same file). If the three-way merge itself has unresolved conflicts, proceed to step 4.
4. **AI-assisted resolution (Phase 5)** — Dispatch a Coder session specifically to resolve the remaining conflicts. The Coder receives the conflict markers, the task descriptions of both branches, and the relevant spec context. Until Phase 5, this step is skipped — unresolved conflicts after step 3 go directly to "merge-blocked."

If all applicable strategies fail, the branch is preserved and the node is marked as `merge-blocked` for human intervention. The `af status` command surfaces merge-blocked nodes prominently. The operator can resolve the conflict manually, commit the resolution, and run `af resume` to continue. For merge-blocked nodes, `af resume` re-runs the merge cascade from the beginning. If the operator's resolution committed clean results to the worktree branch, the cascade succeeds at the fast-forward or rebase stage. If conflicts remain, the node stays merge-blocked.

### Merge Throughput

The global lock is a deliberate trade-off: correctness over throughput. Each merge must see the result of all prior merges — concurrent modifications to `develop` would create race conditions. The throughput cost depends on lock hold time per strategy:

| Strategy | Typical lock hold time | When it applies |
|----------|----------------------|-----------------|
| Fast-forward | Milliseconds (ref update) | First merge, or no concurrent completions |
| Rebase + fast-forward | Low seconds (commit rewrite) | Non-conflicting changes, develop moved |
| Three-way merge | Seconds | Textual conflicts, auto-resolvable |
| AI-assisted resolution | Minutes (LLM call) | Unresolved conflicts, Phase 5 only |

At the default concurrency limit (4 parallel sessions), the maximum queue depth is 3. If file impact prediction works well — and it should for specs with explicit file references in `design.md` — conflicting sessions are never dispatched concurrently, so most merges are fast-forward or clean rebase. The queue drains in seconds.

The bottleneck scenario is: file impact prediction misses an overlap, multiple sessions modify the same files concurrently, and merges fall through to three-way or AI-assisted resolution. In that case, the queue stalls. But this is self-limiting — missed predictions that cause merge conflicts also cause the merge cascade to flag the problem, which the operator sees via `af status`. The fix is better spec authoring (explicit file references), not a faster lock.

## Sync Barriers

Periodically (configurable interval, default 30 minutes), the engine pauses dispatch and runs sync checks:

- **Hot-load discovery:** Check for new specs in `.specs/` that weren't in the plan. If a new spec passes validation, inject its nodes into the live graph.
- **Cost check:** If cumulative cost exceeds a warning threshold, emit a warning. If it exceeds the hard ceiling, initiate graceful shutdown.
- **Session health:** Check for stuck sessions (no events for longer than `execution.stuck_session_timeout`, default 10 minutes). A stuck session is killed and treated as a failure — it enters the retry sequence defined in the Decide phase.

## Circuit Breaker

The circuit breaker tracks consecutive failures **globally across the entire plan**, not per-spec or per-node. "Consecutive" is defined by **assessment completion order** — the wall-clock order in which nodes finish their Assess phase. If nodes A, B, and C finish assessment in that order and all three are failures, the circuit breaker triggers regardless of whether they ran in parallel. A successful assessment at any point resets the counter to zero. If 3 consecutive assessments result in failure (default, configurable as `execution.circuit_breaker_threshold`), the engine enters cooldown. During cooldown:

- No new sessions are dispatched.
- Sessions already in progress are allowed to complete (they are not killed).
- The operator is notified via the configured notification channel (stderr by default, webhook if configured).

**Exiting cooldown:** The operator reviews the failures and either (a) runs `af resume` to reset the failure counter and continue dispatch, or (b) runs `af abort` to terminate the plan. There is no automatic cooldown expiry — the engine does not guess whether cascading failures have resolved themselves. The `af resume` command optionally accepts `--skip <node-id>` to mark a specific node as `blocked` and bypass it, unblocking downstream nodes that do not depend on it.

This prevents runaway cost from cascading failures (e.g., a broken dependency that causes every downstream node to fail).

## Signal Handling

The engine handles process signals for graceful and immediate shutdown:

- **SIGTERM / SIGINT:** Graceful shutdown. The engine stops dispatching new sessions. Sessions in progress receive a wind-down injection (same as the 90% budget wind-down) and are given 60 seconds to commit and exit. After the grace period, remaining sessions are terminated. The plan state is persisted — `af run` resumes from the last completed node.
- **SIGQUIT:** Immediate shutdown. All sessions are terminated immediately. Plan state is persisted at the last checkpoint. This may leave uncommitted work in worktrees, which the engine cleans up on next start.
- **SIGHUP:** Reload configuration. The engine re-reads `.agent-fox/config.toml` without restarting. Changes to concurrency limits, cost ceilings, and notification settings take effect immediately. Changes to the plan structure (new specs, different task groups) require a re-plan via sync barrier, not a reload.

## Adaptive Model Routing

The routing system predicts which model tier a task needs. The assessment pipeline:

1. **Feature extraction:** Parse the task description for signals: number of subtasks, file count in scope, presence of keywords indicating complexity (refactor, migration, security, concurrency), historical failure rate for similar tasks.
2. **Tier prediction:** A classifier maps features to a tier (simple → fast model, standard → default model, advanced → strongest model). Initially rule-based; trains on historical outcomes as data accumulates.
3. **Escalation on failure:** If a session fails at its predicted tier, retry at the next tier up. If it fails at advanced, it's a genuine failure.

### Initial Heuristic Rules

Until the trained classifier has sufficient data (minimum 50 completed sessions across at least 3 specs), the routing system uses a deterministic rule chain evaluated in priority order. The first matching rule wins:

1. **Tag override** — If the task group has a `[model: X]` tag, use that tier. Tags are explicit human intent and always take precedence.
2. **Cross-spec dependency** — If the task group is the target of a cross-spec dependency edge (another spec depends on its output), use `standard` or higher. These groups produce artifacts consumed downstream; failures are expensive.
3. **High subtask count** — If the task group has 6 or more subtasks (direct children using `N.M` notation, not counting nested items), use `standard`. Many subtasks indicate breadth that benefits from stronger planning capability.
4. **Complexity keywords** — If the task description contains any of: `refactor`, `migration`, `security`, `concurrency`, `performance`, `backward-compatible`, use `standard`. These signal problem domains where subtle errors are common.
5. **Test-only group** — If all subtasks reference test writing, test setup, or verification (heuristic: subtask descriptions contain `test`, `spec`, `verify`, `assert`), use `simple`. Test-writing tasks are well-structured and rarely need advanced reasoning.
6. **Low subtask count** — If the task group has 3 or fewer subtasks and no complexity keywords, use `simple`.
7. **Default** — `standard`.

The rule chain is intentionally conservative — it prefers `standard` over `simple` when uncertain. The trained classifier can route more aggressively once it has outcome data to justify it.

### Classifier Training

Once the minimum data threshold is met (50 completed sessions), the classifier trains on the feature vector (subtask count, file count, keyword flags, dependency position) mapped to the observed outcome (success at predicted tier, required escalation, or failure). The classifier is retrained after every 25 new completions. The heuristic rules remain as the fallback if the classifier's confidence for a prediction is below 0.6.

The routing system is part of the `engine` package but can be used standalone to analyze a task list without executing anything.

---

*Previous: [02 — Architecture & Library Design](./02-architecture.md)*
*Next: [04 — Memory, Knowledge & Maintenance](./04-knowledge.md)*
