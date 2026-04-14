# agent-fox v3 — Product Requirements Document

## 1. What This Is

agent-fox v3 is a ground-up reinvention of the autonomous coding-agent orchestrator. It keeps the things that made agent-fox unique — spec-driven workflows, agent archetypes, structured memory, reproducible planning — and strips away everything else. The result is a lean, library-first Python toolkit that a solo developer or small team can adopt incrementally, starting from a single command.

The system orchestrates coding agents (Claude Code, Claude API, or other harnesses) through structured specifications. You describe what you want built. The system plans, executes, reviews, and integrates — in parallel, in isolated sandboxes, with accumulated knowledge that makes every subsequent run smarter.

## 2. Vision

**One sentence:** Specs in, working code out — with memory.

**Three beliefs that shape the design:**

1. **Specs are the interface between human judgment and machine execution.** Not prompts, not tickets, not chat. Structured, validated, traceable specifications. This is non-negotiable.

2. **Agents should accumulate project wisdom, not start from scratch.** Every session produces knowledge. That knowledge feeds future sessions. Over time, the system behaves like a senior engineer who has been on the project for months — because it has.

3. **Small teams need leverage, not overhead.** Every feature must justify itself against the question: "Does a team of 1-3 people actually benefit from this, or is it organizational theater?" If a feature only pays off at scale, it doesn't belong here.

## 3. What Changed and Why

### Kept (non-negotiable)

| Concept | Why it stays |
|---|---|
| Spec-driven workflow | The core differentiator. Specs replace prompts. Front-loads human judgment. |
| Reproducible planning | Same specs + same repo state → same plan. All inputs are captured in a content hash. Inspectable, auditable, explainable. |
| Agent archetypes | Separation of concerns between implementation and review is fundamental. |
| Parallel execution with isolation | Concurrent agents in isolated workspaces. The only way to get throughput. |
| Structured memory / knowledge | Agents that learn. The DuckDB-backed knowledge store stays and expands. |
| Night-shift (autonomous maintenance) | The "janitor mode" is a genuine differentiator for small teams. |
| Multi-agent convergence | Multiple reviewers, merged verdicts. Reduces single-shot LLM variance. |

### Dropped

| Concept | Why it goes |
|---|---|
| Tight Claude SDK coupling | Lock-in to one provider is a strategic risk. The system should work with Claude Code, Claude API, Gemini CLI, or any harness that runs in a container. Claude remains primary; others are adapters. |
| Seven archetypes | Seven roles is too many. Collapse to four composable roles (see Chapter 2). The Cartographer and Librarian were never fully realized and their functions fold into the knowledge system. |
| Complex config hierarchy | Three-level config resolution was clever but confusing. Flatten to project config + archetype overrides. |
| In-memory-only plan state | Plans should be checkpointed. Session crashes shouldn't lose progress. |
| Checkbox completion tracking | Tracking task group completion via markdown checkboxes (`- [ ]`, `- [x]`) in `tasks.md` is fragile. Checkbox state in markdown is a presentation concern, not a reliable state machine. Completion state moves to a dedicated tracking mechanism (see Chapter 01). |

### New

| Concept | Source of inspiration |
|---|---|
| **Harness protocol with Claude Code primary** | Scion (Google). Agents run in containers/sandboxes via harness adapters. Claude Code is the primary harness — the security model, context management, and retry system depend on its capabilities (permission callbacks, pre-compact hooks, session resume). Other harnesses can implement the protocol but operate with degraded guarantees. See ch 02 §Degradation Impact and ch 06 §Harness-agnosticism. |
| **Container sandboxing with governance** | PuzzlePod + Podman. Each agent session runs in a governed OCI container with Fork-Explore-Commit isolation, kernel-enforced sandboxing, and per-archetype profiles. Uniform model across macOS and Linux. |
| **Credential isolation** | PuzzlePod phantom tokens. Agents never see real API keys. Surrogate tokens are resolved to real credentials at the proxy layer. DLP scanning prevents exfiltration. |
| **Shared knowledge protocol** | mozilla-ai/cq. The knowledge system can export/import knowledge units in a standard format, enabling cross-project and cross-team learning. |
| **Agent-first CLI** | Poehnelt (Google Workspace CLI). JSON output by default when stdout is not a TTY. Runtime schema introspection. Machine-readable errors. |
| **Library-first architecture** | Every capability is an importable Python module. CLI and daemon are thin consumers. You can embed the planner, the knowledge store, or a single archetype session into any Python program. |
| **Session checkpointing and resume** | Claude Agent SDK `resume` / `fork_session`. Crashed sessions resume from the last checkpoint rather than restarting. |
| **Prompt cache optimization** | Raschka's harness analysis. Stable prefix / variable suffix split with `cache_control` annotations to exploit KV-cache across sessions on the same spec. |
| **Context-first work management** | Work items are knowledge records, not issues. They live in the same DuckDB store as facts and session summaries, enabling automatic context assembly for fixes — the Coder gets a knowledge briefing about the affected area, not just a bug description. Night-shift, spec audits, and Reviewers produce work items; external trackers are a one-way sync target. Inspired by Linear's thesis that project health should be queryable context, not a ticket queue. |

## 4. Target User

A solo developer or a team of 2-5 engineers who:

- Work on projects large enough that unattended agent execution saves meaningful time (multi-day feature work, large refactors, test coverage campaigns).
- Are comfortable writing a PRD and task list but don't want to hand-hold agents turn by turn.
- Want the system to get smarter over time without active knowledge curation.
- Run on a Mac or Linux workstation, or a Linux server. Not Windows-first.

## 5. Success Criteria

1. **Time to first run under 15 minutes.** Clone, install, ensure Podman + PuzzlePod are available, write a spec (PRD, requirements, design, test spec, tasks), run. The `af-spec` skill assists with spec generation. `af init` validates prerequisites and guides setup.
2. **Zero-secret exposure.** No API key ever appears in agent context, logs, or transcripts.
3. **Session resume on crash.** A network timeout or OOM kill does not restart a 200-turn coding session from scratch.
4. **Knowledge payoff by spec #3.** By the third spec executed on a project, the first-pass success rate of Coder sessions (percentage of task groups assessed as `success` on the initial attempt, before any retries) should improve measurably compared to the first spec. The metric is tracked in the session metrics table. Concretely: at least 3 facts from prior specs should appear in context assembly for the third spec's Coder sessions, and the first-pass success rate should be at least 15% higher than the first spec's rate.
5. **Library adoption without CLI.** A user can `uv pip install agent-fox` and use the planner, knowledge store, or session runner from their own Python code without touching the CLI.

## 6. Document Structure

This PRD is organized into four domain chapters, a phasing plan, a trade-offs register, and an implementation guide:

| Chapter | Scope |
|---|---|
| [01 — Spec System](./01-spec-system.md) | The specification model, the five-artifact package, validation, and completion tracking. How human intent enters the system. |
| [02 — Architecture & Library Design](./02-architecture.md) | Package structure, library-first design, harness abstraction, credential isolation, sandboxing, and the execution model. |
| [03 — Archetypes, Planning & Execution](./03-execution.md) | The four archetypes, reproducible planning, session lifecycle, parallel dispatch, retry/escalation, checkpointing, and merge integration. |
| [04 — Memory, Knowledge & Maintenance](./04-knowledge.md) | The knowledge store, fact extraction, knowledge sharing (cq protocol), night-shift mode, and the context-first work management model. |
| [05 — Delivery Phases](./05-phases.md) | Six incremental phases (0-5), each standalone-useful. What ships when. |
| [06 — Open Questions & Trade-offs](./06-trade-offs.md) | Resolved decisions (Q1-Q6) and trade-offs to monitor. |
| [07 — Spec Breakdown](./07-spec-breakdown.md) | 22 implementation specs across 6 phases with dependency graph. Guides the af-spec skill. |

Chapters 01-04 describe *what* the system does and *why*, at a level suitable for a senior engineer or product manager. Implementation details (APIs, data schemas, algorithms) are deferred to design documents within the generated spec packages.

---

*Next: [01 — Spec System](./01-spec-system.md)*
