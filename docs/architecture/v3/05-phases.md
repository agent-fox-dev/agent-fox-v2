# Chapter 05 — Delivery Phases

## Phasing Rationale

agent-fox v3 is a ground-up rebuild. Delivering it as a single monolithic release is high-risk and slow. Instead, each phase produces a usable, self-contained capability that builds toward the full system. A user can adopt at any phase and get value.

The phases are ordered by the dependency graph of the system itself: you can't execute without a plan, you can't plan without specs, and you can't accumulate knowledge without execution.

---

## Phase 0 — Foundation

**Goal:** Importable Python packages with zero orchestration. The building blocks.

**Delivers:**
- `agent_fox.spec` — Spec parser and validator. Reads `.specs/` directories, parses task groups, resolves dependencies, runs static validation and auto-fix. Standalone: `af validate` works.
- `agent_fox.plan` — Graph builder and topological sort. Takes parsed specs, emits `plan.json`. Standalone: `af plan` produces an inspectable plan file for visualization and debugging.
- `agent_fox.knowledge` — DuckDB knowledge store with fact CRUD, work item schema and CRUD, findings, session summaries, metrics, embedding, and semantic search. Standalone: `af knowledge query "auth"` works. No dependency on execution.
- `agent_fox.cli` — Skeleton CLI with `init`, `validate`, `plan`, `knowledge` commands. Agent-first design (JSON output, schema introspection).
- Project config model (`.agent-fox/config.toml` with defaults).
- Pydantic models for specs, plans, facts, findings.

**Not delivered:** Execution, harnesses, sandboxing, night-shift.

**Why this first:** Each package is independently useful. A user can lint specs in CI, inspect the planned execution graph, or query a knowledge store — without ever running an agent. Library-first means value before orchestration.

**Validation:** (a) `af validate` passes on a v3-format test spec corpus (structural and cross-reference checks, zero errors). (b) `af plan` produces a deterministic plan from a multi-spec corpus — running twice on the same input produces identical `plan.json`. (c) Knowledge store round-trips: insert 10 facts, query by semantic similarity, verify top-3 results are relevant. (d) All packages import independently (`from agent_fox.spec import ...`, `from agent_fox.knowledge import ...`) without pulling in unrelated dependencies.

---

## Phase 1 — Single-Spec Execution with Feedback

**Goal:** Run one spec end-to-end with review, knowledge accumulation, and automatic retry. The first phase where agent-fox is genuinely better than raw Claude Code.

**Delivers:**
- `agent_fox.harness` — Harness protocol definition. `ClaudeCodeHarness` implementation (wraps Claude Code running inside a PuzzlePod-managed container).
- `agent_fox.workspace` — Git worktree creation, branch lifecycle, merge cascade (fast-forward, rebase, merge commit). No AI-assisted conflict resolution yet.
- `agent_fox.security` — PuzzlePod integration: sandbox profile management (archetype → profile mapping), container lifecycle, credential configuration via phantom tokens, secret leak detection. `--no-sandbox` escape hatch for development.
- `agent_fox.engine` — Session lifecycle (prepare, execute, harvest, assess, decide). Single-threaded dispatch (one session at a time). No parallelism yet.
- All four archetypes in their essential modes: Coder, Verifier, Reviewer (pre-review only), Maintainer (knowledge extraction only).
- Pre-review Reviewer — flags ambiguities, missing edge cases, and spec issues before the first Coder session. Pre-review mode only (read-only, no shell). No drift-review, audit-review, or multi-instance convergence yet.
- Knowledge extraction — Maintainer extraction mode dispatched after each Coder session. Facts extracted from transcripts, written to knowledge store as proposed.
- Knowledge injection — context assembly queries knowledge store for facts relevant to the task, injects as structured context. Coder sessions get smarter over time.
- Simple retry — on failure, retry once with the same model in a fresh session with error context prepended. No model escalation yet.
- Default archetype profiles shipped with the package. No project overrides yet.
- `af run <spec>` command.
- `af init` checks for Podman + PuzzlePod prerequisites.
- Session transcript recording.
- Basic cost tracking (tokens, turns).

**Not delivered:** Parallel execution, Reviewer drift/audit modes, multi-instance convergence, model escalation, archetype profile customization, prompt caching, session resume, night-shift.

**Why this order:** Phase 1 must justify its setup cost. A user who installs Podman, writes specs, and runs `af run` should get something meaningfully better than raw Claude Code — not just "the same thing but containerized." Pre-review catches spec issues before code is written. Knowledge extraction means the system learns from every session. Knowledge injection means session N+1 benefits from what session N discovered. Retry means transient failures don't require manual intervention. Together, these create a feedback loop that makes the system compound — the differentiating property. Sandboxing and credential isolation are foundational, shipped from day one, not Phase 3 add-ons.

**Validation:** (a) A complete spec with 3 task groups executes inside PuzzlePod containers — pre-review findings are injected into the first Coder session's context. (b) Verifier produces pass/fail verdicts. (c) After Coder completion, Maintainer extraction writes at least 1 fact to the knowledge store. (d) A second `af run` on the same project injects facts from the first run into Coder context. (e) A deliberately failing task retries once before being assessed as failed. (f) Filesystem confinement: agent process cannot read or write files outside the mounted worktree (verified via container inspection). (g) Credential isolation: DLP scanning logs zero exfiltration attempts; agent transcript contains no real API keys. (h) End-to-end test with a real Claude Code session on a test repository.

---

## Phase 2 — Advanced Quality and Customization

**Goal:** Deepen the feedback loops from Phase 1 with empirical review, model intelligence, and project customization.

**Delivers:**
- Reviewer drift-review and audit-review modes (read-only with shell in ephemeral sandbox — empirical verification of spec compliance).
- Multi-instance convergence for Reviewers (majority-voting for audit, worst-verdict-wins for pre-review).
- Model escalation: on failure at predicted tier, retry at next tier up (simple → standard → advanced). Extends Phase 1's simple retry into a full escalation ladder.
- Permission-callback profiles for drift/audit review modes (pre-review profile already delivered in Phase 1).
- Archetype profiles: project overrides via `.agent-fox/profiles/`. Prompt layering (project context + archetype profile + task context). `af init --profiles` for customization.
- Prompt cache optimization: stable prefix / variable suffix split with `cache_control`.
- Tool output summarization for pytest, ruff, git.

**Not delivered:** Parallelism, night-shift, cq export.

**Why this order:** Phase 1 established the feedback loops — review, knowledge, retry. Phase 2 deepens them. Reviewers gain shell access for empirical verification (not just reading code — running commands to confirm drift). The system learns which model tier to use for which tasks. Teams can customize agent behavior per project. This is where agent-fox becomes a tunable multi-agent system, not just a feedback-augmented runner.

**Validation:** (a) Drift-review correctly identifies discrepancies between design.md and codebase using shell commands. (b) Audit-review enumerates test cases via `pytest --collect-only` and maps them to test_spec.md contracts. (c) Retry/escalation: a deliberately failing task group escalates from simple → standard → advanced and is marked `blocked` after exhausting retries. (d) Run three specs sequentially; verify prompt cache hit rate > 50% for sessions on the same spec. (e) Custom archetype profile overrides default Coder behavior.

---

## Phase 3 — Parallel Execution

**Goal:** Speed for multi-spec, long-running execution.

**Delivers:**
- Parallel session dispatch (configurable pool size, default 4).
- File impact analysis and conflict detection to prevent parallel merge conflicts.
- Serializing merge lock.
- Session checkpointing and resume on crash.
- Sync barriers (hot-load discovery, cost checks, session health monitoring).
- Circuit breaker for cascading failures.
- Critical path analysis for plan visualization.
- `af status` with live execution reporting.

**Not delivered:** Night-shift, cq export, AI-assisted merge resolution.

**Why this order:** Parallelism is where the system pays for itself on larger projects. Sandboxing and credential isolation are already in place from Phase 1 (PuzzlePod containers). This phase adds the concurrency layer on top.

**Validation:** (a) A project with 3 specs (cross-dependencies between them) executes with up to 4 concurrent sessions in parallel PuzzlePod containers. (b) File impact prediction correctly serializes two groups that modify the same file. (c) Circuit breaker triggers after 3 consecutive failures and halts dispatch. (d) `af resume` after circuit breaker continues execution. (e) A deliberately killed session (SIGKILL during execution) resumes from checkpoint on next `af run` — the session continues from the last checkpointed turn, not from scratch.

---

## Phase 4 — Night-Shift and Maintenance

**Goal:** Autonomous codebase maintenance.

**Delivers:**
- `agent_fox.nightshift` — Hunt/fix loop with configurable categories.
- Hunt categories: eight built-in (Linter Debt, Dead Code, Test Coverage, Dependency Freshness, Deprecated API, Documentation Drift, TODO/FIXME, Quality Gate) plus custom categories via `.agent-fox/hunters/` TOML files.
- Critic consolidation, fingerprint deduplication.
- Work items in the knowledge store (replacing GitHub Issues as the primary record).
- Optional sync to GitHub Issues / Linear via adapter.
- Triage with dependency detection and supersession.
- Fix pipeline: Coder → Verifier (simplified from v2's three-agent pipeline).
- `af nightshift` daemon command.
- `af nightshift list`, `af nightshift approve`, `af nightshift triage` commands.
- Staleness detection (re-evaluate work items after fixes).
- Cost ceiling enforcement for autonomous operation.

**Not delivered:** cq export, AI-assisted merge resolution, additional harnesses.

**Why this order:** Night-shift depends on the full execution pipeline (Phase 3) for parallel dispatch, checkpointing, and circuit breaker protection. Sandboxing and credential isolation are already in place from Phase 1. Night-shift is the capstone feature — the system maintaining itself while you sleep.

**Validation:** Night-shift discovers linter debt in a test repository, creates work items, auto-approves them, executes fixes, and merges them into develop. Cost ceiling halts execution before budget is exceeded.

---

## Phase 5 — Ecosystem

**Goal:** Integrations and extensibility.

**Delivers:**
- cq-compatible knowledge export/import.
- `PROJECT_MEMORY.md` export (curated markdown projection of the knowledge store).
- AI-assisted merge conflict resolution (Coder session dispatched on merge failure).
- Adaptive model routing with trained classifier (requires Phase 2+ historical data).
- Additional harness adapters (Gemini CLI, OpenCode) as community contributions, with documented capability gaps per ch 02 §Degradation Impact.
- Crawl4ai integration as an optional agent tool (documentation fetching, API research).
- Spec generation assistant (natural language → complete five-artifact spec draft via guided workflow).
- Community registry for sharing archetype profiles and hunt category definitions (builds on the local-first extension points shipped in Phase 2 and Phase 4).

**Why last:** These are ecosystem features that extend a working system, not core functionality. Each can be delivered independently as the community and use cases demand.

---

## Phase Summary

| Phase | Core delivery | Standalone value |
|---|---|---|
| 0 | Spec parsing, planning, knowledge store | CI linting, plan visualization, project knowledge base |
| 1 | Single-spec execution with all four archetypes (essential modes), knowledge feedback loop, simple retry, PuzzlePod sandboxing | Sandboxed coding with pre-review, accumulated knowledge, and automatic retry — genuinely better than raw Claude Code |
| 2 | Reviewer advanced modes (drift/audit), model escalation, archetype profile customization, prompt caching | Tunable multi-agent quality system with empirical verification |
| 3 | Parallelism, checkpoints | Multi-spec concurrent execution |
| 4 | Night-shift autonomous maintenance, pluggable hunt categories | Codebase self-maintenance, domain-specific hunters |
| 5 | Ecosystem integrations, plugins, adapters | Cross-project knowledge, additional harness adapters (with documented capability gaps) |

---

*Previous: [04 — Memory, Knowledge & Maintenance](./04-knowledge.md)*
*Next: [06 — Open Questions & Trade-offs](./06-trade-offs.md)*
