# Chapter 07 — Spec Breakdown & Implementation Guide

## Purpose

This document maps the product specification (chapters 00-06) to a set of implementable specs that the `af-spec` skill can generate. Each entry defines what a spec covers, what it depends on, which chapters to read for context, and sizing guidance.

This is the bridge between "what we want to build" (the PRD) and "how we break it into work" (the `.specs/` directory).

## How to Use This Document

When generating a spec with the `af-spec` skill:

1. Find the spec entry in this document.
2. Read the listed source chapters — these are the PRD input for that spec.
3. Use the scope description as the basis for the PRD.
4. Respect the dependency declarations — they become the `## Dependencies` table in the generated PRD.
5. Stay within the sizing targets. If a spec exceeds 10 requirements or 6 task groups, split it.

## Conventions

- **Spec names** use the `NN_snake_case` format required by af-spec.
- **Source chapters** reference the root docs (e.g., "ch 02 §Harness Abstraction" means `02-architecture.md`, section "Harness Abstraction").
- **Package** indicates which `agent_fox.*` Python package the spec primarily implements.
- **Dependencies** list upstream specs by number. Group-level granularity is determined during af-spec generation when task groups are defined.

### Phase-straddling specs

Specs `09_reviewer` and `11_retry_escalation` each deliver scope across two phases — early task groups cover Phase 1, later groups cover Phase 2. This is not partial spec execution at runtime. All task groups exist in `tasks.md` from the start. The straddling is an implementation-ordering convention:

- **Phase 1 groups** are self-contained — they depend only on Phase 1 infrastructure and produce a usable subset of the spec's capability (pre-review for `09`, simple retry for `11`).
- **Phase 2 groups** extend the Phase 1 foundation. They depend on Phase 1 groups within the same spec (via sequential intra-spec edges) and introduce new archetype modes or engine features.

Operationally, during Phase 1 development: run the spec, complete the Phase 1 groups, and leave Phase 2 groups in `pending` state. Phase 2 groups will become eligible for dispatch (their intra-spec predecessors completed), but may fail or produce incomplete results because Phase 2 infrastructure is not yet implemented. Mark Phase 2 groups as `blocked` via `af resume --skip` and complete them during Phase 2 development.

When generating these specs with af-spec, structure the task groups so that Phase 1 groups form a self-contained deliverable: group 1 writes failing tests for Phase 1 scope, group 2 implements Phase 1 scope, and subsequent groups handle Phase 2 scope. Phase 1 subtask descriptions should not reference Phase 2 concepts.

---

## Phase 0 — Foundation

These specs have no dependency on the execution engine. Each produces a standalone, independently usable library package. Specs `01`, `03` are fully independent and can be developed in parallel. Spec `02` depends on `01`. Spec `21` depends on `03`. Spec `04` depends on `01`, `02`, and `03`.

### `01_spec_parser`

**Package:** `agent_fox.spec`

**Scope:** Parse `.specs/` directories, verify five-artifact completeness, parse task group structure and inline tags, resolve cross-spec dependencies into graph edges, run static validation (structural checks, cross-reference checks, consistency checks), auto-fix mechanical issues (renumbering, ID prefix normalization, tag syntax). Pydantic models for spec artifacts.

**Source chapters:**
- ch 01 — entire chapter (spec model, task groups, dependencies, validation, immutability)
- ch 00 §5 — success criteria (spec validation context)

**Does NOT include:** AI-assisted validation (ambiguity detection, completeness assessment). That is Phase 2 territory — it requires an LLM harness.

**Sizing target:** ~7-8 requirements, 4-5 task groups.

---

### `02_planner`

**Package:** `agent_fox.plan`

**Scope:** Build a DAG from parsed specs. Topological sort with Kahn's algorithm and min-heap tie-breaking. Archetype injection (pre-execution Reviewer, mid-execution Reviewer, post-execution Verifier/Maintainer). Plan persistence to `.agent-fox/plan.json` with content hashing. Implicit planning logic (no plan → build; fresh plan → resume; stale plan → prompt). Critical path analysis. Graph serialization for visualization.

**Source chapters:**
- ch 03 §Planning — graph construction, execution order, plan persistence, implicit planning
- ch 03 §The Four Archetypes — archetype injection rules (which archetypes go where)
- ch 01 §Cross-Spec Dependencies — dependency syntax and resolution

**Dependencies:** `01_spec_parser` (takes parsed specs as input).

**Sizing target:** ~6-8 requirements, 4-5 task groups.

---

### `03_knowledge_store`

**Package:** `agent_fox.knowledge`

**Scope:** DuckDB schema design and initialization. Fact CRUD (create, read, update, delete) with lifecycle states (proposed → confirmed → superseded → stale). ONNX-based embeddings with auto-detection of execution provider (CoreML on Apple Silicon, CUDA on Linux GPU, CPU fallback). Semantic search with composite scoring (similarity × confidence × recency). Findings storage. Session summary storage. Metrics storage. Token-budgeted knowledge retrieval. Embedding model migration (`af knowledge reindex`).

**Source chapters:**
- ch 04 §The Knowledge System — storage, what gets stored (facts, findings, session summaries, metrics), semantic search
- ch 02 §Python Version and Dependencies — ONNX runtime, embedding model
- ch 06 — resolved Q4 (ONNX + Apple Silicon)

**Does NOT include:** Work item schema and CRUD (see `21_work_items`). Knowledge extraction from transcripts (see `10_knowledge_pipeline`). cq export/import (see `16_cq_export`). `PROJECT_MEMORY.md` export (see `17_project_memory`).

**Sizing target:** ~6-8 requirements, 4-5 task groups.

---

### `21_work_items`

**Package:** `agent_fox.knowledge`

**Scope:** Work item schema, CRUD operations (create, query, update status), status lifecycle (discovered → approved → in_progress → fixed/wontfix), fingerprint algorithm (SHA-256 of category + canonical paths + normalized description), deduplication on write. Work item scoring for semantic search (status_weight × similarity × recency). Cross-type search integration with facts and findings. CLI commands: `af work-item create` (manual entry), `af work-item list` (filterable by status, severity, category).

**Source chapters:**
- ch 04 §Work Items — schema, lifecycle, fingerprint, deduplication, scoring
- ch 04 §The Knowledge System — cross-type search

**Dependencies:** `03_knowledge_store` (extends the knowledge store schema and search).

**Sizing target:** ~5-6 requirements, 3-4 task groups.

---

### `04_cli_foundation`

**Package:** `agent_fox.cli`

**Scope:** CLI skeleton using Click. Agent-first design: JSON output when stdout is not a TTY, `--output json` flag, machine-readable errors (`code`, `message`, `context`), runtime schema introspection (`af schema <command>`), self-describing help (`af help --format json`). Commands: `af init` (create `.agent-fox/` and `.specs/`), `af validate [<spec>]`, `af plan [<spec>]`, `af knowledge query <topic>`, `af spec new <name>` (scaffold five-artifact template). Project config model (`.agent-fox/config.toml`), Pydantic config schema with defaults.

**Source chapters:**
- ch 02 §Agent-First CLI Design — full section
- ch 02 §Configuration — config model, flat structure

**Dependencies:** `01_spec_parser`, `02_planner`, `03_knowledge_store` (CLI wraps their APIs).

**Sizing target:** ~6-8 requirements, 4-5 task groups.

---

## Phase 1 — Single-Spec Execution with Feedback

These specs build the execution loop with feedback: author a spec → pre-review it → run it in a governed container → extract knowledge → retry on failure → get code on develop. Specs `05` and `07` can be developed in parallel. Spec `06` depends on `05`. Spec `08` depends on all three. Specs `09` (pre-review subset), `10`, and `11` (simple retry subset) depend on `08` and extend the engine with feedback capabilities.

### `05_harness_protocol`

**Package:** `agent_fox.harness`

**Scope:** Define the `Harness` protocol (start session, stream events, inject messages, stop, report session ID). Capability negotiation: harness declares supported capabilities (`resume`, `structured_output`, `pre_compact_hook`, `effort_control`, `fork_session`); orchestrator queries and adapts. `ClaudeCodeHarness` implementation (wraps Claude Code subprocess with programmatic API, permission callback for per-archetype tool restriction). Event types: assistant message, tool call, tool result, status update.

**Source chapters:**
- ch 02 §Harness Abstraction — protocol, capability negotiation, ClaudeCodeHarness, permission-callback profiles
- ch 06 — resolved Q1 (capability negotiation)
- ref/coding-harness-analysis.md — SDK capabilities and hooks

**Sizing target:** ~7-9 requirements, 4-5 task groups.

---

### `06_sandbox_security`

**Package:** `agent_fox.security`

**Scope:** PuzzlePod integration: manage sandbox profiles mapped to archetypes (Coder → gated, Reviewer → gated, Verifier → localhost, Maintainer → mode-dependent). Container lifecycle (create, start, stop, cleanup). Agent session Containerfile (UBI 10 Minimal base, per-archetype package installation). Credential configuration via PuzzlePod phantom tokens. `--no-sandbox` mode (bypass container, run on host with sanitized environment). Secret leak detection (scan tool outputs, agent messages, file contents for API key / token / PEM patterns). `af init` prerequisite checks (Podman installed, PuzzlePod daemon running, Podman machine status on macOS). Environment sanitization.

**Source chapters:**
- ch 02 §Process Sandboxing — PuzzlePod model, platform model, archetype profiles, `--no-sandbox`
- ch 02 §Credential Isolation — phantom tokens, DLP, defense-in-depth
- ch 06 — resolved Q2 (built-in proxy → phantom tokens), resolved Q6 (PuzzlePod)

**External reference:** https://github.com/agent-fox-dev/puzzlepod (maintained fork of `LobsterTrap/puzzlepod`) — PuzzlePod architecture, profiles, credential proxy, sandbox modes. agent-fox depends on the fork, not upstream directly. See ch 02 §PuzzlePod as a Dependency for the contribution model.

**Dependencies:** `05_harness_protocol` (harness calls into security for container setup).

**Sizing target:** ~8-10 requirements, 5-6 task groups.

---

### `07_workspace`

**Package:** `agent_fox.workspace`

**Scope:** Git worktree creation on dedicated feature branches. Worktree cleanup after session completion. Merge cascade: fast-forward → rebase → merge commit (AI-assisted resolution deferred to `18_merge_resolution`). Branch lifecycle (create, merge, delete). Serializing merge lock (only one merge at a time). Worktree ↔ container mount integration (worktree path mounted at `/workspace` inside PuzzlePod container).

**Source chapters:**
- ch 03 §Merge Cascade — strategy order, conflict handling
- ch 02 §Process Sandboxing — workspace integration paragraph
- ch 03 §Parallel Execution — merge lock (spec the lock here, parallel dispatch uses it later)

**Sizing target:** ~5-7 requirements, 3-4 task groups.

---

### `08_engine_v1`

**Package:** `agent_fox.engine`

**Scope:** Session lifecycle: prepare (context assembly from spec + task body), execute (stream events, record transcript, monitor turn budget), harvest (collect git diff/test results/structured output), assess (success/partial/failure/skip), decide (advance/retry/escalate). Baseline test pass rate capture (run quality gate or test suite on `develop` before first dispatch, store in `plan.json`). Coder archetype prompt and steering. Verifier archetype prompt and steering. Default archetype profiles (loaded from package defaults, prompt layering with project context). Single-threaded dispatch (one session at a time). Signal handling: graceful shutdown (SIGTERM/SIGINT), immediate shutdown (SIGQUIT), config reload (SIGHUP). CLI commands: `af run <spec>` (implicit validate → plan → dispatch), `af status` (execution state, cost, blocked nodes), `af resume [--skip <node-id>]` (continue after circuit breaker or merge-blocked), `af abort` (terminate plan), `af cost` (per-session cost reporting). Transcript recording. Basic cost tracking (tokens, turns). Integration with harness, workspace, and security packages.

**Source chapters:**
- ch 03 §Session Lifecycle — all five phases
- ch 03 §The Four Archetypes — Coder and Verifier sections only
- ch 03 §Adaptive Model Routing — heuristic tier prediction (initial version)
- ch 02 §Agent-First CLI Design — `af run` command

**Dependencies:** `05_harness_protocol`, `06_sandbox_security`, `07_workspace`, `01_spec_parser`, `02_planner`.

**Does NOT include:** Reviewer drift/audit modes, multi-instance convergence, model escalation, parallel dispatch, session resume/checkpointing. (Pre-review Reviewer, knowledge pipeline, and simple retry are separate Phase 1 specs.)

**Sizing target:** ~8-10 requirements, 5-6 task groups.

---

### `09_reviewer`

**Package:** `agent_fox.engine` (archetype addition)

**Phase 1 scope (pre-review):** Reviewer archetype in pre-review mode only — flags ambiguities, contradictions, and missing edge cases before the first Coder session. Read-only enforcement via permission callback (no writes, no shell). Structured findings output (ID, severity, category, description). Single-instance only. Findings flow into Coder session context. Archetype injection into the planner (pre-execution Reviewer node).

**Phase 2 scope (advanced modes):** Drift-review mode (design.md vs. codebase divergence, read-only with shell). Audit-review mode (test coverage against test_spec.md, read-only with shell). Multi-instance convergence: worst-verdict-wins for pre-review, majority-voting for audit. Configurable instance count per review mode. Mid-execution archetype injection.

**Source chapters:**
- ch 03 §The Four Archetypes — Reviewer section
- ch 03 §Planning — archetype injection rules (pre-execution, mid-execution)

**Dependencies:** `08_engine_v1` (extends the engine with a new archetype).

**Sizing target:** ~6-8 requirements, 4-5 task groups. Task groups 1-2 deliver Phase 1 scope (pre-review); groups 3-5 deliver Phase 2 scope (drift/audit, convergence).

---

### `10_knowledge_pipeline`

**Package:** `agent_fox.engine` + `agent_fox.knowledge`

**Scope:** Maintainer archetype in knowledge extraction mode. After Coder session completion, extract facts from transcript: causal relationships, architectural decisions, failure patterns, environment requirements. Structured output extraction via harness. Facts written to knowledge store as "proposed" (low confidence). Knowledge injection into Coder context assembly: query knowledge store by task description and affected file paths, inject as categorized structured context, respect token budget (configurable, default 2000 tokens). Asynchronous extraction via background thread (does not consume a dispatch slot or block downstream nodes, even in single-threaded dispatch).

**Source chapters:**
- ch 04 §Knowledge Extraction — extraction prompt, what to extract, async behavior
- ch 04 §Context Assembly from Knowledge — query, injection, token budget
- ch 03 §The Four Archetypes — Maintainer section (knowledge extraction mode)

**Dependencies:** `08_engine_v1`, `03_knowledge_store`.

**Sizing target:** ~6-8 requirements, 4-5 task groups.

---

### `11_retry_escalation`

**Package:** `agent_fox.engine`

**Phase 1 scope (simple retry):** On session failure, retry once with the same model in a fresh session with error context prepended as "prior attempt" narrative. Single retry only — no escalation, no session resume. Extends the engine's assess/decide phases with a retry counter.

**Phase 2 scope (escalation and optimization):** Session resume on retry (if harness supports `resume` capability). Model escalation: on failure at predicted tier, retry at next tier up (simple → standard → advanced). Prompt cache optimization: split session context into stable prefix (spec docs, system prompt) and variable suffix (task body, findings, knowledge); annotate with `cache_control` for KV-cache reuse across sessions on the same spec. Tool output summarization: parse known patterns (pytest output, linter output, git diff stats) into structured summaries for token efficiency.

**Source chapters:**
- ch 03 §Session Lifecycle — assess and decide phases (retry/escalation)
- ch 03 §Adaptive Model Routing — tier prediction, escalation on failure
- ref/coding-harness-analysis.md — prompt cache optimization, PreCompact hooks

**Dependencies:** `08_engine_v1`.

**Sizing target:** ~5-7 requirements, 3-4 task groups. Task groups 1-2 deliver Phase 1 scope (simple retry); groups 3-4 deliver Phase 2 scope (escalation, caching, summarization).

---

## Phase 2 — Advanced Quality and Customization

Specs `09` and `11` straddle Phases 1 and 2: their early task groups (pre-review, simple retry) are delivered in Phase 1, and their later groups (drift/audit, convergence, escalation, caching) are delivered in Phase 2. Spec `22` delivers the project-level archetype profile customization mechanism.

### `22_archetype_profiles`

**Package:** `agent_fox.engine`

**Scope:** Project-level archetype profile overrides via `.agent-fox/profiles/`. Full-replacement override semantics (project file replaces package default entirely). `af init --profiles` command (copies package defaults into project for editing). Custom archetype support: team-defined archetypes via profile file + permission preset mapping in project config (`archetype.<name>.permissions`).

**Source chapters:**
- ch 03 §Archetype Profiles — profile structure, override semantics, prompt layering, extensibility

**Dependencies:** `08_engine_v1` (extends the engine's prompt assembly).

**Sizing target:** ~4-5 requirements, 2-3 task groups.

---

## Phase 3 — Parallel Execution

### `12_parallel_dispatch`

**Package:** `agent_fox.engine`

**Scope:** Parallel session dispatch with configurable concurrency limit (default 4). Dispatch strategy: scan for nodes with satisfied dependencies, filter by file impact conflict detection, dispatch non-conflicting nodes in parallel. File impact analysis (predict which files a task group will modify). `af status` live execution reporting (extends `08`'s basic status with in-flight sessions, completed nodes, cost so far).

**Source chapters:**
- ch 03 §Parallel Execution — dispatch strategy, file impact analysis
- ch 02 §Agent-First CLI Design — `af status` command

**Dependencies:** `08_engine_v1`, `07_workspace` (parallel merges use the serializing lock).

**Sizing target:** ~5-7 requirements, 3-4 task groups.

---

### `13_checkpointing`

**Package:** `agent_fox.engine`

**Scope:** Session checkpointing: periodically persist session state (every N turns or M minutes) so crash recovery resumes from last checkpoint instead of restarting. Uses harness `resume` capability when available, else replays context. Sync barriers: hot-load discovery (check for new specs in `.specs/` during execution, inject into live graph if valid), cost ceiling checks (warning threshold + hard ceiling + graceful shutdown), session health monitoring (detect stuck sessions, kill and retry). Circuit breaker: halt dispatch after N consecutive failures, notify operator.

**Source chapters:**
- ch 03 §Session Lifecycle — checkpointing during execute phase
- ch 03 §Sync Barriers — full section
- ch 03 §Circuit Breaker — full section

**Dependencies:** `12_parallel_dispatch`.

**Sizing target:** ~6-8 requirements, 4-5 task groups.

---

## Phase 4 — Night-Shift

### `14_nightshift_hunt`

**Package:** `agent_fox.nightshift`

**Scope:** Eight built-in hunt categories: Linter Debt, Dead Code, Test Coverage, Dependency Freshness, Deprecated API, Documentation Drift, TODO/FIXME, Quality Gate. Custom hunt categories via `.agent-fox/hunters/` TOML files (tool command, prerequisites, critic prompt, override semantics for built-in categories). Categories run in parallel, raw output passed through LLM critic for consolidation. Work item production: create structured work items in the knowledge store via the work item CRUD API. Fingerprint deduplication against existing work items. `af nightshift list`, `af nightshift triage` commands. Staleness detection (re-evaluate work items after fixes).

**Source chapters:**
- ch 04 §Night-Shift Mode — hunt categories, custom hunters, work item production
- ch 04 §The Knowledge System — work item storage

**Dependencies:** `08_engine_v1`, `03_knowledge_store`, `21_work_items`.

**Sizing target:** ~8-10 requirements, 5-6 task groups.

---

### `15_nightshift_fix`

**Package:** `agent_fox.nightshift`

**Scope:** Fix pipeline: auto-generate lightweight spec from work item → Coder → Verifier. Approval modes: `--auto` (all work items auto-approved) vs. manual (`af nightshift approve <id>`). Daemon mode: two independent timers (hunt: default 4h, fix: default 15min), both fire on startup. Graceful shutdown on SIGINT/SIGTERM. Cost ceiling enforcement for autonomous operation (night-shift ceiling defaults to 50% of project ceiling). Optional one-way sync to GitHub Issues (`af nightshift sync-issues`). `af nightshift` daemon command.

**Source chapters:**
- ch 04 §Night-Shift Mode — fix pipeline, lifecycle, cost management
- ch 04 §Cost Management — per-project budgets, night-shift ceiling
- ch 06 — resolved Q3 (knowledge store primary, GitHub sync optional)

**Dependencies:** `14_nightshift_hunt`, `07_workspace`.

**Sizing target:** ~7-9 requirements, 4-5 task groups.

---

## Phase 5 — Ecosystem

These specs extend a working system. Each is independent and can be developed on demand.

### `16_cq_export`

**Package:** `agent_fox.knowledge`

**Scope:** Export facts as cq-compatible knowledge units (domain tags, statement, metadata, provenance). Scrub project-specific paths. Import external knowledge units at low confidence. Confirmation cycle for imported facts.

**Source chapters:** ch 04 §Knowledge Sharing (cq Protocol).

**Dependencies:** `03_knowledge_store`.

**Sizing target:** ~4-5 requirements, 2-3 task groups.

---

### `17_project_memory`

**Package:** `agent_fox.knowledge`

**Scope:** Export `PROJECT_MEMORY.md` — curated, size-capped markdown projection of highest-confidence facts. Update-don't-append pattern. Triggered manually (`af knowledge export-memory`) or automatically after spec execution. Committed to git.

**Source chapters:** ch 04 §Project Memory File.

**Dependencies:** `03_knowledge_store`.

**Note:** The automatic export trigger (after successful spec execution) requires a hook in the engine's post-execution flow. This spec delivers both the export logic and the engine hook registration.

**Sizing target:** ~3-4 requirements, 2-3 task groups.

---

### `18_merge_resolution`

**Package:** `agent_fox.workspace`

**Scope:** AI-assisted merge conflict resolution. When merge cascade fails at the merge-commit stage, dispatch a Coder session specifically to resolve conflicts. Preserve branch for human intervention if AI resolution also fails.

**Source chapters:** ch 03 §Merge Cascade — strategy 4 (AI-assisted resolution).

**Dependencies:** `07_workspace`, `08_engine_v1`.

**Sizing target:** ~3-4 requirements, 2-3 task groups.

---

### `19_adaptive_routing`

**Package:** `agent_fox.engine`

**Scope:** Replace heuristic model tier prediction with a trained classifier. Feature extraction from task descriptions (subtask count, file count, complexity keywords, historical failure rate). Train on accumulated session outcome data from knowledge store metrics. Standalone analysis mode (analyze task list without executing).

**Source chapters:** ch 03 §Adaptive Model Routing.

**Dependencies:** `08_engine_v1`, `03_knowledge_store`.

**Sizing target:** ~4-5 requirements, 2-3 task groups.

---

### `20_spec_cli_wrapper`

**Package:** `agent_fox.cli`

**Scope:** `af spec generate` command that wraps the af-spec skill in a CLI interface. Chat-style refinement loop. Natural language → complete five-artifact spec draft.

**Source chapters:** ch 06 — resolved Q5 (skill-only for now, CLI wrapper is Phase 5).

**Dependencies:** `04_cli_foundation`.

**Sizing target:** ~3-4 requirements, 2-3 task groups.

---

### v3 Skill Definitions (non-code deliverables)

The `af-spec` and `af-spec-audit` skills are prompt-based skill definitions, not Python packages. They live in `.claude/commands/` and are maintained alongside the codebase. v3 versions of both skills incorporate hardening from the spec review process:

**af-spec v3** — Updated from the v2 skill in `assets/af-spec`. Key changes:
- Five mandatory artifacts (v2 skill text was inconsistent between "four" and "five").
- Completion tracking language updated — checkboxes are a visual convenience, `plan.json` is the source of truth.
- Dependency table guidance strengthened: precise interface contracts in the Relationship column, mutual dependency warnings, cross-reference to upstream `design.md` for validation.
- Design doc guidance: explicit file path references for file impact prediction and knowledge staleness.
- Terminology: "reproducible planning" replaces "deterministic planning."

**af-spec-audit v3** — Updated from the v2 skill in `assets/af-spec-audit`. Key changes:
- Completion state check reads `plan.json` node status (not checkbox state in `tasks.md`).
- Drift findings written as work items to the knowledge store (primary record), with GitHub issue sync as optional one-way push.
- Knowledge cross-check: query knowledge store for facts about audited modules before flagging drift.
- Dependency contract validation: check upstream spec output against dependency table Relationship descriptions.
- Reviewer-aligned analysis: skill can use shell commands for empirical verification (grep, import graph analysis) rather than relying solely on LLM reading.

These skills are updated whenever the root spec docs (ch 00-07) change in ways that affect spec authoring or auditing workflows.

---

## Dependency Graph

```
Phase 0 (foundation — no execution dependency):

  01_spec_parser ───────────────┐
                                ├──→ 04_cli_foundation
  03_knowledge_store ──┬────────┤
                       │        │
  02_planner ──────────│────────┘
       ↑               │
       └── depends on 01
                       └──→ 21_work_items


Phase 1 (single-spec execution):

  05_harness_protocol ──→ 06_sandbox_security ──┐
                                                ├──→ 08_engine_v1
  07_workspace ─────────────────────────────────┘
       (05 and 07 can run in parallel)
       (08 also depends on 01, 02)


Phase 2 (quality + customization):

  09_reviewer             (depends on 08)
  10_knowledge_pipeline   (depends on 08, 03)
  11_retry_escalation     (depends on 08)
  22_archetype_profiles   (depends on 08)
       (all four can run in parallel)


Phase 3 (parallelism):

  12_parallel_dispatch ──→ 13_checkpointing
       (12 depends on 08, 07)


Phase 4 (night-shift):

  14_nightshift_hunt ──→ 15_nightshift_fix
       (14 depends on 08, 03, 21)
       (15 depends on 14, 07)


Phase 5 (ecosystem — all independent, on demand):

  16_cq_export           (depends on 03)
  17_project_memory      (depends on 03)
  18_merge_resolution    (depends on 07, 08)
  19_adaptive_routing    (depends on 08, 03)
  20_spec_cli_wrapper    (depends on 04)
```

## Sizing Guidelines

These targets align with the af-spec skill's constraints:

| Guideline | Target | Hard limit |
|-----------|--------|------------|
| Requirements per spec | 5-8 | 10 max |
| Task groups per spec | 3-5 | 6 max (excluding verification) |
| Subtasks per task group | 3-5 | 6 max (excluding N.V) |
| Cross-spec dependencies | minimize | use group-level granularity |

If a spec exceeds these during af-spec generation, split it. Prefer vertical slices (end-to-end for one concern) over horizontal slices (all models, then all views).

## Generating a Spec

To generate spec `NN_name`:

1. Read this entry to understand scope, source chapters, and dependencies.
2. Read the listed source chapters in the root docs.
3. Run the af-spec skill: `/af-spec` with the scope description as the PRD input.
4. The skill will walk through: PRD clarification → requirements (EARS) → design (with correctness properties) → test spec → tasks.
5. Ensure the generated `## Dependencies` table uses group-level granularity per the af-spec conventions.
6. Verify the spec lands within the sizing guidelines above.

---

*Previous: [06 — Open Questions & Trade-offs](./06-trade-offs.md)*
